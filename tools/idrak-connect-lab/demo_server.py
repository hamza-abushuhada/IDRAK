#!/usr/bin/env python3
"""IDRAK Connect Lab: local-only sample POS + storefront + simulated IDRAK receiver.

No third-party dependencies, no real payments, no production integrations.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('IDRAK_LAB_DATA_DIR', str(ROOT / 'data')))
SOURCE_DB = DATA / 'sources.sqlite3'
RECEIVER_DB = DATA / 'simulated_idrak.sqlite3'
HOST = '127.0.0.1'
SOURCE_PORT = int(os.environ.get('IDRAK_LAB_SOURCE_PORT', '8765'))
RECEIVER_PORT = int(os.environ.get('IDRAK_LAB_RECEIVER_PORT', '8766'))
# The public default exists only so the localhost demo starts with no setup.
# It is never acceptable for hosted/serverless runs or for pairing (see
# signing_secret_is_safe), because anything signed with it is forgeable.
DEFAULT_SIGNING_SECRET = 'idrak-local-demo-only-secret'
SIGNING_SECRET = os.environ.get('IDRAK_LAB_WEBHOOK_SECRET', DEFAULT_SIGNING_SECRET)


def signing_secret_is_safe(value=None):
    """True only for a deployment-specific secret: at least 32 chars, never the public default."""
    value = SIGNING_SECRET if value is None else value
    return isinstance(value, str) and len(value) >= 32 and value != DEFAULT_SIGNING_SECRET
SEED_PRODUCTS = [
    ('BRG-001','برغر كلاسيك','Classic Burger','🍔',4250,60),
    ('BRG-002','تشيز برغر','Cheese Burger','🧀',5250,60),
    ('FRY-001','بطاطا مقلية','French Fries','🍟',1750,90),
    ('DRK-001','مشروب غازي','Soft Drink','🥤',1000,120),
    ('PZA-001','بيتزا مارجريتا','Margherita Pizza','🍕',6750,45),
    ('SLD-001','سلطة خضراء','Green Salad','🥗',3000,40),
]

def iso_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def money(mils):
    return str((Decimal(int(mils)) / Decimal(1000)).quantize(Decimal('0.001')))

@contextmanager
def connect(path):
    db = sqlite3.connect(path, timeout=15, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout=15000')
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()

LEGACY_SHOP = 'idrak-test-shop-001'  # shop that owns all pre-multi-shop data
SHOP_ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')
SOURCE_SCHEMA = 'idrak_lab_source'


class LabAuthError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class RouteNotFound(LookupError):
    pass


@dataclass(frozen=True)
class Principal:
    kind: str                 # operator | shop | local | anonymous | integration
    shop_id: str | None = None
    role: str | None = None   # shop sessions: 'owner' | 'cashier' (None = shop credential)
    user_id: str | None = None  # set for email/password user sessions


LOCAL_PRINCIPAL = Principal('local')  # unauthenticated localhost runner only

SHOPS_DDL = """
CREATE TABLE IF NOT EXISTS shops (
  shop_id TEXT PRIMARY KEY CHECK(length(shop_id) BETWEEN 1 AND 64), name TEXT NOT NULL,
  token_hash TEXT UNIQUE, disabled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);"""
SOURCE_DDL = SHOPS_DDL + """
CREATE TABLE IF NOT EXISTS products (
  shop_id TEXT NOT NULL REFERENCES shops(shop_id), sku TEXT NOT NULL, name_ar TEXT NOT NULL,
  name_en TEXT NOT NULL, emoji TEXT NOT NULL, price_mils INTEGER NOT NULL,
  stock INTEGER NOT NULL CHECK(stock>=0), PRIMARY KEY(shop_id, sku)
);
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id TEXT NOT NULL REFERENCES shops(shop_id),
  order_no INTEGER NOT NULL, external_id TEXT NOT NULL,
  channel TEXT NOT NULL, status TEXT NOT NULL, payment_method TEXT NOT NULL,
  customer TEXT NOT NULL DEFAULT '', total_mils INTEGER NOT NULL,
  inventory_applied INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(shop_id, external_id), UNIQUE(shop_id, order_no), UNIQUE(id, shop_id)
);
CREATE TABLE IF NOT EXISTS order_items (
  order_id INTEGER NOT NULL, shop_id TEXT NOT NULL, sku TEXT NOT NULL,
  name_ar TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price_mils INTEGER NOT NULL,
  FOREIGN KEY(order_id, shop_id) REFERENCES orders(id, shop_id)
);
CREATE TABLE IF NOT EXISTS source_events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, shop_id TEXT NOT NULL REFERENCES shops(shop_id),
  channel TEXT NOT NULL, event_id TEXT NOT NULL,
  event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0, delivered INTEGER NOT NULL DEFAULT 0,
  last_error TEXT, UNIQUE(shop_id, event_id)
);
CREATE INDEX IF NOT EXISTS orders_shop_channel_idx ON orders(shop_id, channel, id);
CREATE INDEX IF NOT EXISTS order_items_order_idx ON order_items(order_id);
CREATE INDEX IF NOT EXISTS source_events_cursor_idx ON source_events(shop_id, channel, seq);
"""
RECEIVER_DDL = """
CREATE TABLE IF NOT EXISTS received_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id TEXT NOT NULL,
  event_id TEXT NOT NULL, source_id TEXT NOT NULL,
  event_type TEXT NOT NULL, payload TEXT NOT NULL, received_at TEXT NOT NULL,
  UNIQUE(shop_id, event_id)
);
CREATE TABLE IF NOT EXISTS synced_orders (
  shop_id TEXT NOT NULL, source_id TEXT NOT NULL, external_id TEXT NOT NULL,
  channel TEXT NOT NULL, status TEXT NOT NULL, total_mils INTEGER NOT NULL,
  revision INTEGER NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(shop_id, source_id, external_id)
);
CREATE TABLE IF NOT EXISTS synced_inventory (
  shop_id TEXT NOT NULL, source_id TEXT NOT NULL, sku TEXT NOT NULL, stock INTEGER NOT NULL,
  revision INTEGER NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(shop_id, source_id, sku)
);
"""
# Pre-multi-shop layout rebuilt in one transaction. Every existing row is assigned
# to LEGACY_SHOP so ids, event cursors, invoice numbers and event ids are unchanged.
_SOURCE_REBUILD = [
    SHOPS_DDL,
    "INSERT OR IGNORE INTO shops(shop_id,name,created_at) VALUES('%s','متجر التجربة',datetime('now'))" % LEGACY_SHOP,
    "ALTER TABLE products RENAME TO products_old",
    "ALTER TABLE orders RENAME TO orders_old",
    "ALTER TABLE order_items RENAME TO order_items_old",
    "ALTER TABLE source_events RENAME TO source_events_old",
]
_SOURCE_COPY = [
    "INSERT INTO products SELECT '%s',sku,name_ar,name_en,emoji,price_mils,stock FROM products_old" % LEGACY_SHOP,
    """INSERT INTO orders(id,shop_id,order_no,external_id,channel,status,payment_method,customer,total_mils,
         inventory_applied,revision,created_at,updated_at)
       SELECT id,'%s',id,COALESCE(external_id,CASE channel WHEN 'pos' THEN 'POS-' ELSE 'WEB-' END||printf('%%06d',id)),
         channel,status,payment_method,customer,total_mils,inventory_applied,revision,created_at,updated_at
       FROM orders_old""" % LEGACY_SHOP,
    "INSERT INTO order_items SELECT order_id,'%s',sku,name_ar,quantity,unit_price_mils FROM order_items_old" % LEGACY_SHOP,
    """INSERT INTO source_events(seq,shop_id,channel,event_id,event_type,payload,created_at,attempts,delivered,last_error)
       SELECT seq,'%s',channel,event_id,event_type,payload,created_at,attempts,delivered,last_error FROM source_events_old""" % LEGACY_SHOP,
    "DROP TABLE order_items_old", "DROP TABLE orders_old", "DROP TABLE products_old", "DROP TABLE source_events_old",
]
_RECEIVER_COPY = [
    "ALTER TABLE received_events RENAME TO received_events_old",
    "ALTER TABLE synced_orders RENAME TO synced_orders_old",
    "ALTER TABLE synced_inventory RENAME TO synced_inventory_old",
]


def _columns(db, table):
    return [r[1] for r in db.execute(f'PRAGMA table_info({table})')]


def _legacy_layout(path, table):
    if not path.exists():
        return False
    db = sqlite3.connect(path)
    try:
        cols = _columns(db, table)
        return bool(cols) and 'shop_id' not in cols
    finally:
        db.close()


def _rebuild(path, steps_before, ddl, steps_after):
    """Run the rebuild atomically; FK enforcement is off only for the swap."""
    db = sqlite3.connect(path, timeout=15, isolation_level=None)
    try:
        db.execute('PRAGMA foreign_keys=OFF')
        db.execute('BEGIN IMMEDIATE')
        try:
            for sql in steps_before:
                db.execute(sql)
            for stmt in [s for s in ddl.split(';') if s.strip()]:
                db.execute(stmt)
            for sql in steps_after:
                db.execute(sql)
            bad = db.execute('PRAGMA foreign_key_check').fetchall()
            if bad:
                raise sqlite3.IntegrityError(f'foreign key check failed after migration: {len(bad)} rows')
            db.execute('COMMIT')
        except BaseException:
            db.execute('ROLLBACK')
            raise
    finally:
        db.close()


def migrate_legacy_sqlite():
    """Upgrade pre-multi-shop SQLite files in place. Idempotent; no-op on new files."""
    if _legacy_layout(SOURCE_DB, 'products'):
        _rebuild(SOURCE_DB, _SOURCE_REBUILD, SOURCE_DDL, _SOURCE_COPY)
    if _legacy_layout(RECEIVER_DB, 'received_events'):
        copy = [
            "INSERT INTO received_events(id,shop_id,event_id,source_id,event_type,payload,received_at) "
            "SELECT id,'%s',event_id,source_id,event_type,payload,received_at FROM received_events_old" % LEGACY_SHOP,
            "INSERT INTO synced_orders SELECT '%s',source_id,external_id,channel,status,total_mils,revision,updated_at FROM synced_orders_old" % LEGACY_SHOP,
            "INSERT INTO synced_inventory SELECT '%s',source_id,sku,stock,revision,updated_at FROM synced_inventory_old" % LEGACY_SHOP,
            "DROP TABLE received_events_old", "DROP TABLE synced_orders_old", "DROP TABLE synced_inventory_old",
        ]
        _rebuild(RECEIVER_DB, _RECEIVER_COPY, RECEIVER_DDL, copy)


def init_db():
    DATA.mkdir(parents=True, exist_ok=True)
    migrate_legacy_sqlite()
    with connect(SOURCE_DB) as db:
        db.executescript('PRAGMA journal_mode=WAL;' + SOURCE_DDL)
        db.execute("INSERT OR IGNORE INTO shops(shop_id,name,created_at) VALUES(?,?,?)",
                   (LEGACY_SHOP, 'متجر التجربة', iso_now()))
        db.executemany('INSERT OR IGNORE INTO products(shop_id,sku,name_ar,name_en,emoji,price_mils,stock) VALUES(?,?,?,?,?,?,?)',
                       [(LEGACY_SHOP, *p) for p in SEED_PRODUCTS])
        import pairing
        db.executescript(pairing.DDL)
        import lab_users
        db.executescript(lab_users.DDL)
    with connect(RECEIVER_DB) as db:
        db.executescript('PRAGMA journal_mode=WAL;' + RECEIVER_DDL)


# ---- shops, per-shop credentials and authorization -------------------------
def _hash_secret(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def shop_secret(shop_id):
    """Per-shop webhook signing key derived from the deployment secret (not stored)."""
    return hmac.new(SIGNING_SECRET.encode(), b'idrak-lab-shop:' + shop_id.encode(), hashlib.sha256).hexdigest()


def create_shop(name):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
        raise ValueError('Invalid shop name')
    shop_id = 'shop-' + secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    with connect(SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO shops(shop_id,name,token_hash,created_at) VALUES(?,?,?,?)',
                   (shop_id, name.strip(), _hash_secret(secret), iso_now()))
        for p in SEED_PRODUCTS:
            db.execute('INSERT INTO products(shop_id,sku,name_ar,name_en,emoji,price_mils,stock) VALUES(?,?,?,?,?,?,?)',
                       (shop_id, *p))
    return {'shop_id': shop_id, 'name': name.strip(), 'token': f'{shop_id}.{secret}',
            'webhook_secret': shop_secret(shop_id)}


def rotate_token(shop_id):
    if not isinstance(shop_id, str) or not SHOP_ID_RE.match(shop_id):
        raise ValueError('Invalid shop id')
    secret = secrets.token_urlsafe(32)
    with connect(SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM shops WHERE shop_id=?', (shop_id,)).fetchone():
            raise ValueError('Unknown shop')
        db.execute('UPDATE shops SET token_hash=? WHERE shop_id=?', (_hash_secret(secret), shop_id))
    return {'shop_id': shop_id, 'token': f'{shop_id}.{secret}'}


def list_shops():
    with connect(SOURCE_DB) as db:
        rows = db.execute('SELECT shop_id,name,disabled,created_at,(token_hash IS NOT NULL) AS has_token FROM shops ORDER BY created_at,shop_id')
        return {'shops': [{'shop_id': r['shop_id'], 'name': r['name'], 'disabled': bool(r['disabled']),
                           'has_token': bool(r['has_token']), 'created_at': r['created_at']} for r in rows]}


def shop_exists(shop_id):
    with connect(SOURCE_DB) as db:
        return bool(db.execute('SELECT 1 FROM shops WHERE shop_id=? AND disabled=0', (shop_id,)).fetchone())


def authenticate_bearer(authorization):
    """Shop principal for 'Bearer <shop_id>.<secret>'; None if absent; raises if invalid."""
    if not authorization or not authorization.lower().startswith('bearer '):
        return None
    shop_id, _, secret = authorization[7:].strip().partition('.')
    row = None
    if SHOP_ID_RE.match(shop_id) and secret:
        with connect(SOURCE_DB) as db:
            row = db.execute('SELECT token_hash,disabled FROM shops WHERE shop_id=?', (shop_id,)).fetchone()
    expected = (row['token_hash'] if row and row['token_hash'] else '0' * 64)
    matches = hmac.compare_digest(_hash_secret(secret), expected)
    if not (matches and row and row['token_hash'] and not row['disabled']):
        raise LabAuthError(401, 'Invalid shop token')
    return Principal('shop', shop_id)


def authenticate(authorization, path, method, operator_header):
    """Hosted-mode gate. Operator = the site Basic credential. A shop token is
    accepted only for data APIs, never for shop administration or static pages."""
    if method == 'GET' and path == '/health':
        return Principal('anonymous')
    if authorization.startswith('Bearer lc.'):
        from pairing import integration_principal
        return integration_principal(authorization, path, method)
    if authorization and hmac.compare_digest(authorization.encode(), operator_header.encode()):
        return Principal('operator')
    if (path.startswith('/api/') or path.startswith('/simulator/api/')) and not path.startswith('/api/shops'):
        try:
            return authenticate_bearer(authorization)
        except LabAuthError:
            return None
    return None


def effective_shop(principal, requested=None):
    """The only place a request's shop is decided: a shop token is pinned to its
    own shop; operators (or the local runner) may select any shop via X-Lab-Shop."""
    if principal.kind in ('shop', 'integration'):
        if requested and requested != principal.shop_id:
            raise LabAuthError(403, 'This token cannot access another shop')
        return principal.shop_id
    if principal.kind not in ('operator', 'local'):
        raise LabAuthError(401, 'Authentication required')
    shop = requested or LEGACY_SHOP
    if not SHOP_ID_RE.match(shop) or not shop_exists(shop):
        raise LabAuthError(404, 'Unknown shop')
    return shop


def require_operator(principal):
    if principal.kind not in ('operator', 'local'):
        raise LabAuthError(403, 'Shop administration requires the operator credential')


def require_owner(principal):
    """Cashier sessions may only sell and read products/orders; everything else
    for a shop needs its owner (or the shop credential / operator)."""
    if principal.kind == 'shop' and principal.role == 'cashier':
        raise LabAuthError(403, 'This action requires the shop owner')


CASHIER_GET = ('/api/products', '/api/orders')
CASHIER_POST = ('/api/pos/sales',)
OWNER_PAGES = ('/', '/operator', '/shop', '/admin', '/simulator', '/simulator/')


def page_allowed(principal, path):
    return not (principal and principal.kind == 'shop' and principal.role == 'cashier' and path in OWNER_PAGES)


_OWNER_ELEMENT = re.compile(r'<a\b[^>]*\bdata-owner\b[^>]*>.*?</a>', re.S)


def page_role(principal):
    if principal is None or principal.kind in ('anonymous', 'integration'):
        return 'none'
    if principal.kind == 'shop' and principal.role == 'cashier':
        return 'cashier'
    return 'owner'  # shop owner, shop credential, operator or the localhost runner


def render_html(text, principal):
    """Decide role-dependent UI on the server, before any script runs: stamp
    the confirmed role on <html> and drop owner-only elements for everyone else,
    so no unauthorized option is ever painted (no authorization UI flash)."""
    role = page_role(principal)
    text = text.replace('<html lang="ar" dir="rtl">', f'<html lang="ar" dir="rtl" data-role="{role}">', 1)
    return text if role == 'owner' else _OWNER_ELEMENT.sub('', text)


def source_id(channel):
    return 'idrak-lab-pos' if channel == 'pos' else 'idrak-lab-store'

def product_rows(db, shop):
    return [dict(r) for r in db.execute('SELECT * FROM products WHERE shop_id=? ORDER BY sku', (shop,))]

def order_payload(db, row):
    items = [
        {'sku': r['sku'], 'name': r['name_ar'], 'quantity': r['quantity'],
         'unit_price': money(r['unit_price_mils'])}
        for r in db.execute('SELECT * FROM order_items WHERE order_id=? AND shop_id=?', (row['id'], row['shop_id']))
    ]
    return {
        'external_id':row['external_id'], 'status':row['status'],
        'payment_method':row['payment_method'], 'customer':row['customer'],
        'currency':'JOD', 'total':money(row['total_mils']),
        'items':items, 'created_at':row['created_at'], 'updated_at':row['updated_at'],
        'revision':row['revision']
    }

def append_event(db, shop, channel, event_type, external_id, revision, body):
    payload = {
      'schema_version':'1.0', 'event_id':f'{source_id(channel)}:{external_id}:r{revision}:{event_type}',
      'event_type':event_type, 'occurred_at':iso_now(),
      'source': {'system':source_id(channel), 'account_id':shop,
                 'channel':channel},
      **body
    }
    cur=db.execute('INSERT INTO source_events(shop_id,channel,event_id,event_type,payload,created_at) VALUES (?,?,?,?,?,?)',
               (shop,channel,payload['event_id'],event_type,json.dumps(payload,ensure_ascii=False),iso_now()))
    payload['source_sequence']=cur.lastrowid
    db.execute('UPDATE source_events SET payload=? WHERE seq=?', (json.dumps(payload,ensure_ascii=False),cur.lastrowid))
    return payload

def append_inventory_events(db, shop, channel, order_external_id, revision, skus):
    for sku in set(skus):
        p = db.execute('SELECT stock FROM products WHERE shop_id=? AND sku=?', (shop,sku)).fetchone()
        append_event(db, shop, channel, 'inventory.updated', f'{order_external_id}:{sku}', revision,
                     {'inventory':{'sku':sku, 'on_hand':p['stock'], 'location_id':'main'}})

def create_order(shop, channel, req):
    if channel not in ('pos','web'):
        raise ValueError('Invalid sales channel')
    selections = req.get('items', [])
    if not isinstance(selections, list) or not selections or len(selections)>30:
        raise ValueError('اختر منتجًا واحدًا على الأقل')
    counts = {}
    for choice in selections:
        if not isinstance(choice,dict): raise ValueError('Invalid cart item')
        sku = choice.get('sku')
        qty = choice.get('quantity')
        if not isinstance(sku,str) or type(qty) is not int or not 1<=qty<=30:
            raise ValueError('Invalid SKU or quantity')
        counts[sku] = counts.get(sku, 0) + qty
    payment = req.get('payment_method','cash' if channel=='pos' else 'demo_card')
    allowed = ('cash','card') if channel=='pos' else ('demo_card','cash_on_delivery')
    if payment not in allowed: raise ValueError('Unsupported payment method')
    completed = channel=='pos' or payment=='demo_card'
    status = 'completed' if completed else 'pending'
    customer = (req.get('customer') or 'عميل تجريبي')
    if not isinstance(customer,str) or len(customer)>80: raise ValueError('Invalid customer')
    with connect(SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        products = {}
        total = 0
        for sku,qty in counts.items():
            p=db.execute('SELECT * FROM products WHERE shop_id=? AND sku=?',(shop,sku)).fetchone()
            if not p: raise ValueError('المنتج غير موجود')
            if completed and p['stock']<qty: raise ValueError('المخزون غير كافٍ')
            products[sku] = p
            total += p['price_mils']*qty
        now=iso_now()
        # Per-shop invoice sequence (serialized by the surrounding write lock).
        order_no=db.execute('SELECT COALESCE(MAX(order_no),0)+1 FROM orders WHERE shop_id=?',(shop,)).fetchone()[0]
        external_id=f'{"POS" if channel=="pos" else "WEB"}-{order_no:06d}'
        cur=db.execute('INSERT INTO orders(shop_id,order_no,external_id,channel,status,payment_method,customer,total_mils,inventory_applied,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (shop,order_no,external_id,channel,status,payment,customer,total,1 if completed else 0,now,now))
        oid=cur.lastrowid
        for sku,qty in counts.items():
            p=products[sku]
            db.execute('INSERT INTO order_items(order_id,shop_id,sku,name_ar,quantity,unit_price_mils) VALUES(?,?,?,?,?,?)', (oid,shop,sku,p['name_ar'],qty,p['price_mils']))
            if completed:
                db.execute('UPDATE products SET stock=stock-? WHERE shop_id=? AND sku=?',(qty,shop,sku))
        row=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
        append_event(db,shop,channel,'sale.created',external_id,1,{'order':order_payload(db,row)})
        if completed: append_inventory_events(db,shop,channel,external_id,1,counts)
    flush_events(channel, shop)
    notify_idrak(shop, channel)
    return {'order_id':external_id, 'total':money(total),'status':status}

def notify_idrak(shop, channel):
    """After the sale is committed and no DB connection is held: signal IDRAK if this shop is linked."""
    import idrak_notify
    idrak_notify.notify(shop, channel)

def change_order(shop, external_id, status):
    if status not in ('completed','cancelled','refunded'):
        raise ValueError('Invalid status')
    with connect(SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        order=db.execute('SELECT * FROM orders WHERE shop_id=? AND external_id=?',(shop,external_id)).fetchone()
        if not order: raise ValueError('Order does not exist')
        old=order['status']
        if (old,status) not in {('pending','completed'),('pending','cancelled'),('completed','refunded')}:
            raise ValueError(f'Cannot change {old} to {status}')
        items=list(db.execute('SELECT sku,quantity FROM order_items WHERE order_id=? AND shop_id=?',(order['id'],shop)))
        if status=='completed':
            for it in items:
                p=db.execute('SELECT stock FROM products WHERE shop_id=? AND sku=?',(shop,it['sku'])).fetchone()
                if p['stock']<it['quantity']:raise ValueError('المخزون غير كافٍ')
                db.execute('UPDATE products SET stock=stock-? WHERE shop_id=? AND sku=?',(it['quantity'],shop,it['sku']))
        elif status=='refunded':
            for it in items:
                db.execute('UPDATE products SET stock=stock+? WHERE shop_id=? AND sku=?',(it['quantity'],shop,it['sku']))
        new_rev=order['revision']+1
        db.execute('UPDATE orders SET status=?, inventory_applied=?, revision=?, updated_at=? WHERE id=? AND shop_id=?',
                   (status,1 if status=='completed' else 0,new_rev,iso_now(),order['id'],shop))
        row=db.execute('SELECT * FROM orders WHERE id=?',(order['id'],)).fetchone()
        append_event(db,shop,order['channel'],'sale.updated',external_id,new_rev,{'order':order_payload(db,row)})
        if status in ('completed','refunded'):
            append_inventory_events(db,shop,order['channel'],external_id,new_rev,[i['sku'] for i in items])
        channel=order['channel']
    flush_events(channel, shop)
    notify_idrak(shop, channel)
    return {'order_id':external_id, 'status':status}

def sign(raw, shop):
    return 'sha256='+hmac.new(shop_secret(shop).encode(),raw,hashlib.sha256).hexdigest()

def post_signed(url, payload):
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    shop=payload['source']['account_id']
    req=Request(url, data=raw,headers={'Content-Type':'application/json',
                'X-Idrak-Signature':sign(raw,shop), 'X-Idrak-Event-Id':payload['event_id']},method='POST')
    with urlopen(req,timeout=2) as response:
        return response.status

def flush_events(channel=None, shop=None):
    base=f'http://127.0.0.1:{RECEIVER_PORT}/ingest'
    where=['delivered=0']; args=[]
    if channel: where.append('channel=?'); args.append(channel)
    if shop: where.append('shop_id=?'); args.append(shop)
    with connect(SOURCE_DB) as db:
        pending=list(db.execute('SELECT * FROM source_events WHERE '+' AND '.join(where)+' ORDER BY seq LIMIT 200',tuple(args)))
    for evt in pending:
        payload=json.loads(evt['payload'])
        try:
            status=post_signed(base,payload)
            if status not in (200,201):raise RuntimeError(f'Receiver returned HTTP {status}')
            delivered=1
            error=None
        except (HTTPError,URLError,TimeoutError,OSError,RuntimeError) as ex:
            delivered=0
            error=str(ex)[:250]
        with connect(SOURCE_DB) as db:
            db.execute('UPDATE source_events SET attempts=attempts+1, delivered=?,last_error=? WHERE seq=?',
                      (delivered,error,evt['seq']))
        # A separate real IDRAK adapter would be needed for any external URL.
        # Never forward events to an unverified destination automatically.

def ingest_event(raw,signature):
    # The shop is read from the body only to pick its signing key; nothing is
    # trusted or stored unless the signature for THAT shop verifies.
    try:
        data=json.loads(raw)
        shop=data['source']['account_id']
        if not isinstance(shop,str) or not SHOP_ID_RE.match(shop): raise ValueError('invalid shop')
    except (KeyError,TypeError,ValueError,json.JSONDecodeError) as exc:
        return (400,{'error':str(exc)})
    if not hmac.compare_digest(sign(raw,shop),signature or ''):
        return (401,{'error':'invalid webhook signature'})
    try:
        evt_id=data['event_id'];source=data['source']['system']; typ=data['event_type']
        if source not in ('idrak-lab-pos','idrak-lab-store'):
            raise ValueError('unknown source')
        if typ not in ('sale.created','sale.updated','inventory.updated'):
            raise ValueError('unknown event type')
    except (KeyError,TypeError,ValueError) as exc:
        return (400,{'error':str(exc)})
    with connect(RECEIVER_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT 1 FROM received_events WHERE shop_id=? AND event_id=?',(shop,evt_id)).fetchone()
        if existing:
            return (200,{'status':'duplicate_skipped','event_id':evt_id})
        if typ.startswith('sale.'):
            order=data['order']; oid=order['external_id']; rev=int(order['revision'])
            if order['status'] not in ('completed','pending','cancelled','refunded'):
                return (400,{'error':'unknown sale status'})
            total_mils=int((Decimal(order['total'])*1000).to_integral_exact())
            prev=db.execute('SELECT revision FROM synced_orders WHERE shop_id=? AND source_id=? AND external_id=?',(shop,source,oid)).fetchone()
            if not prev or rev > prev['revision']:
                db.execute('INSERT INTO synced_orders(shop_id,source_id,external_id,channel,status,total_mils,revision,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(shop_id,source_id,external_id) DO UPDATE SET status=excluded.status,total_mils=excluded.total_mils,revision=excluded.revision,updated_at=excluded.updated_at',
                           (shop,source,oid,data['source']['channel'],order['status'],total_mils,rev,order['updated_at']))
        elif typ=='inventory.updated':
            inventory=data['inventory']; rev=int(data['source_sequence']); sku=inventory['sku']
            prev=db.execute('SELECT revision FROM synced_inventory WHERE shop_id=? AND source_id=? AND sku=?',(shop,source,sku)).fetchone()
            if not prev or rev >= prev['revision']:
                db.execute('INSERT INTO synced_inventory(shop_id,source_id,sku,stock,revision,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(shop_id,source_id,sku) DO UPDATE SET stock=excluded.stock,revision=excluded.revision,updated_at=excluded.updated_at',
                           (shop,source,sku,int(inventory['on_hand']),rev,iso_now()))
        db.execute('INSERT INTO received_events(shop_id,event_id,source_id,event_type,payload,received_at) VALUES(?,?,?,?,?,?)',
                   (shop,evt_id,source,typ,raw.decode('utf-8'),iso_now()))
    return (201,{'status':'accepted','event_id':evt_id})

def source_get(shop,path,q):
    with connect(SOURCE_DB) as db:
        if path=='/api/products':
            return {'products':[{'sku':p['sku'],'name_ar':p['name_ar'],'name_en':p['name_en'],
                               'emoji':p['emoji'],'price':money(p['price_mils']),'stock':p['stock']}
                               for p in product_rows(db,shop)]}
        if path=='/api/orders':
            channel=(q.get('channel')or[''])[0]
            if channel in ('pos','web'):
                rows=db.execute('SELECT * FROM orders WHERE shop_id=? AND channel=? ORDER BY id DESC LIMIT 80',(shop,channel))
            else:
                rows=db.execute('SELECT * FROM orders WHERE shop_id=? ORDER BY id DESC LIMIT 80',(shop,))
            return {'orders':[order_payload(db,o)|{'channel':o['channel']} for o in rows]}
        if path in ('/api/pos/events','/api/web/events'):
            channel='pos' if path.startswith('/api/pos') else 'web'
            try:
                after=max(0,int((q.get('after')or ['0'])[0]));limit=min(200,max(1,int((q.get('limit')or['50'])[0])))
            except ValueError: raise ValueError('after and limit must be integers')
            rows=list(db.execute('SELECT seq,payload FROM source_events WHERE shop_id=? AND channel=? AND seq>? ORDER BY seq LIMIT ?',
                                 (shop,channel,after,limit)))
            return {'events':[{'cursor':r['seq'],'payload':json.loads(r['payload'])} for r in rows],
                    'next_cursor':rows[-1]['seq'] if rows else after,'has_more':len(rows)==limit}
        if path=='/api/events':
            rows=db.execute('SELECT seq,channel,event_type,event_id,delivered,attempts,last_error,created_at FROM source_events WHERE shop_id=? ORDER BY seq DESC LIMIT 100',(shop,))
            return {'events':[dict(r) for r in rows]}
        if path=='/health':return {'ok':True,'service':'idrak-lab-sources'}
    raise RouteNotFound(path)

def handle_source_get(principal,x_shop,path,q):
    """Routed GET for the source API: decides the shop from the principal only."""
    if path=='/health':return source_get(None,path,q)
    if path=='/api/shops':
        require_operator(principal);return list_shops()
    if path not in CASHIER_GET:require_owner(principal)
    shop=effective_shop(principal,x_shop)
    if path=='/api/team':
        import lab_users;return lab_users.team(shop)
    return source_get(shop,path,q)

def handle_source_post(principal,x_shop,path,req):
    if path in ('/api/connect/context','/api/connect/approve'):
        import connect_flow  # checks ownership of the chosen shop itself
        return connect_flow.handle(principal,path,req)
    if path not in CASHIER_POST and principal.kind!='integration':require_owner(principal)
    if path=='/api/shops/invite':
        import lab_users
        require_operator(principal)
        if not set(req)<={'shop_id','email','role'}:raise ValueError('Invalid request')
        return lab_users.create_invite(req.get('shop_id'),req.get('email'),req.get('role','owner'),'operator')
    if path=='/api/team/invite':
        import lab_users
        shop=effective_shop(principal,x_shop)
        if not set(req)<={'email','role'} or req.get('role','cashier')!='cashier':raise ValueError('Owners can invite cashiers only')
        return lab_users.create_invite(shop,req.get('email'),'cashier',principal.user_id or 'shop-credential')
    if path=='/api/team/remove':
        import lab_users
        return lab_users.remove_member(effective_shop(principal,x_shop),req.get('user_id'),principal.user_id)
    if path == '/api/pairing-codes':
        import pairing
        effective_shop(principal, x_shop)
        if set(req) != {'intent'}:
            raise LabAuthError(400, 'Expected a pairing intent only')
        return pairing.issue(principal, req.get('intent'))
    if path=='/api/shops':
        require_operator(principal);return create_shop(req.get('name'))
    if path=='/api/shops/rotate-token':
        require_operator(principal);return rotate_token(req.get('shop_id'))
    shop=effective_shop(principal,x_shop)
    if path=='/api/pos/sales':return create_order(shop,'pos',req)
    if path=='/api/web/orders':return create_order(shop,'web',req)
    if path.startswith('/api/orders/') and path.endswith('/status'):
        return change_order(shop,path.split('/')[3],req.get('status'))
    if path=='/api/retry':
        flush_events(None,shop);return {'status':'retried'}
    if path=='/api/redeliver':
        seq=req.get('seq')
        if type(seq) is not int:raise ValueError('seq must be integer')
        with connect(SOURCE_DB) as db:
            r=db.execute('SELECT payload FROM source_events WHERE seq=? AND shop_id=?',(seq,shop)).fetchone()
        if not r:raise ValueError('event not found')
        return {'receiver':post_signed(f'http://127.0.0.1:{RECEIVER_PORT}/ingest',json.loads(r['payload']))}
    raise RouteNotFound(path)

def receiver_get(shop,path):
    with connect(RECEIVER_DB) as db:
        if path=='/api/summary':
            stats=db.execute('SELECT count(*) as n,COALESCE(SUM(CASE WHEN status="completed" THEN total_mils ELSE 0 END),0) as revenue FROM synced_orders WHERE shop_id=?',(shop,)).fetchone()
            by_channel=[dict(x) for x in db.execute('SELECT channel,count(*) as n,COALESCE(SUM(CASE WHEN status="completed" THEN total_mils ELSE 0 END),0) as revenue_mils FROM synced_orders WHERE shop_id=? GROUP BY channel',(shop,))]
            return {'invoices':stats['n'], 'revenue':money(stats['revenue']),
                    'events':db.execute('SELECT count(*) FROM received_events WHERE shop_id=?',(shop,)).fetchone()[0],
                    'channels':[{**v,'revenue':money(v['revenue_mils'])} for v in by_channel]}
        if path=='/api/synced-orders':
            return {'orders':[{**dict(r),'total':money(r['total_mils'])} for r in db.execute('SELECT * FROM synced_orders WHERE shop_id=? ORDER BY updated_at DESC LIMIT 100',(shop,))]}
        if path=='/api/received-events':
            return {'events':[dict(r) for r in db.execute('SELECT id,event_id,source_id,event_type,received_at FROM received_events WHERE shop_id=? ORDER BY id DESC LIMIT 100',(shop,))]}
    raise RouteNotFound(path)

def handle_receiver_get(principal,x_shop,path):
    if path=='/health':return {'ok':True,'service':'idrak-lab-simulator'}
    require_owner(principal)
    return receiver_get(effective_shop(principal,x_shop),path)

class BaseHandler(BaseHTTPRequestHandler):
    server_version='IDRAKLab/1.0'
    def log_message(self, fmt,*args):
        if not self.path.startswith('/api/'):
            return
        super().log_message(fmt,*args)
    def send_json(self,status,data):
        raw=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(raw)
    def serve_file(self,filename):
        file=ROOT/'public'/filename
        if not file.is_file():return self.send_json(404,{'error':'not found'})
        mime='text/css' if filename.endswith('.css') else ('application/javascript' if filename.endswith('.js') else 'text/html')
        raw=file.read_bytes()
        if filename.endswith('.html'):raw=render_html(raw.decode('utf-8'),self.principal_()).encode('utf-8')
        self.send_response(200);self.send_header('Content-Type',mime+'; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(raw)
    def read_json(self):
        size=int(self.headers.get('Content-Length','0'))
        if size<=0 or size>100_000:raise ValueError('Invalid request size')
        return json.loads(self.rfile.read(size))
    def principal_(self):
        return getattr(self,'principal',None) or LOCAL_PRINCIPAL
    def x_shop(self):
        return self.headers.get('X-Lab-Shop')
    def guarded(self,action):
        try: return self.send_json(200,action())
        except LabAuthError as ex:
            self.send_json(ex.status,{'error':str(ex)})
        except RouteNotFound:
            self.send_json(404,{'error':'not found'})
        except (ValueError,sqlite3.Error,TypeError,KeyError) as ex:
            self.send_json(400,{'error':str(ex)})

class SourceHandler(BaseHandler):
    def do_GET(self):
        u=urlparse(self.path);path=u.path
        if path=='/':return self.serve_file('home.html')
        if path=='/pos':return self.serve_file('pos.html')
        if path=='/shop':return self.serve_file('shop.html')
        if path=='/admin':return self.serve_file('admin.html')
        if path=='/connect':return self.serve_file('connect.html')
        if path=='/connect.js':return self.serve_file('connect.js')
        if path=='/style.css':return self.serve_file('style.css')
        if path=='/app.js':return self.serve_file('app.js')
        if path.startswith('/api/') or path=='/health':
            return self.guarded(lambda:handle_source_get(self.principal_(),self.x_shop(),path,parse_qs(u.query)))
        return self.send_json(404,{'error':'not found'})
    def do_POST(self):
        path=urlparse(self.path).path
        try:
            req=self.read_json()
            if not isinstance(req,dict):raise ValueError('Expected a JSON object')
            result=handle_source_post(self.principal_(),self.x_shop(),path,req)
            self.send_json(200,result)
        except LabAuthError as ex:
            self.send_json(ex.status,{'error':str(ex)})
        except RouteNotFound:
            self.send_json(404,{'error':'not found'})
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as ex:
            self.send_json(400,{'error':str(ex)})
        except (HTTPError,URLError,OSError,sqlite3.Error) as ex:
            self.send_json(502,{'error':f'Local delivery error: {str(ex)}'})

class ReceiverHandler(BaseHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/':return self.serve_file('inbox.html')
        if path=='/style.css':return self.serve_file('style.css')
        if path=='/app.js':return self.serve_file('app.js')
        if path.startswith('/api/') or path=='/health':
            return self.guarded(lambda:handle_receiver_get(self.principal_(),self.x_shop(),path))
        return self.send_json(404,{'error':'not found'})
    def do_POST(self):
        if urlparse(self.path).path!='/ingest':return self.send_json(404,{'error':'not found'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=100_000:raise ValueError('Invalid request size')
            raw=self.rfile.read(size)
            status,out=ingest_event(raw,self.headers.get('X-Idrak-Signature'))
            self.send_json(status,out)
        except (ValueError,sqlite3.Error,TypeError,KeyError) as ex:
            self.send_json(400,{'error':str(ex)})

def start():
    init_db()
    receiver=ThreadingHTTPServer((HOST,RECEIVER_PORT),ReceiverHandler)
    source=ThreadingHTTPServer((HOST,SOURCE_PORT),SourceHandler)
    threading.Thread(target=receiver.serve_forever,daemon=True).start()
    print('\n  IDRAK Connect Lab — local test environment only')
    print(f'  POS:           http://{HOST}:{SOURCE_PORT}/pos')
    print(f'  Online shop:   http://{HOST}:{SOURCE_PORT}/shop')
    print(f'  Orders admin:  http://{HOST}:{SOURCE_PORT}/admin')
    print(f'  IDRAK simulator: http://{HOST}:{RECEIVER_PORT}/')
    print('  Stop with Ctrl+C. No payment gateway or real IDRAK integration.\n',flush=True)
    flush_events()
    try:source.serve_forever()
    except KeyboardInterrupt:pass
    finally: source.server_close();receiver.shutdown();receiver.server_close()

if __name__=='__main__': start()
