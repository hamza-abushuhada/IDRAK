#!/usr/bin/env python3
"""IDRAK Connect Lab: local-only sample POS + storefront + simulated IDRAK receiver.

No third-party dependencies, no real payments, no production integrations.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
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
SIGNING_SECRET = os.environ.get('IDRAK_LAB_WEBHOOK_SECRET', 'idrak-local-demo-only-secret')
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

def init_db():
    DATA.mkdir(parents=True, exist_ok=True)
    with connect(SOURCE_DB) as db:
        db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS products (
            sku TEXT PRIMARY KEY, name_ar TEXT NOT NULL, name_en TEXT NOT NULL,
            emoji TEXT NOT NULL, price_mils INTEGER NOT NULL, stock INTEGER NOT NULL
          );
          CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, external_id TEXT UNIQUE,
            channel TEXT NOT NULL, status TEXT NOT NULL, payment_method TEXT NOT NULL,
            customer TEXT NOT NULL DEFAULT '', total_mils INTEGER NOT NULL,
            inventory_applied INTEGER NOT NULL DEFAULT 0,
            revision INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS order_items (
            order_id INTEGER NOT NULL REFERENCES orders(id), sku TEXT NOT NULL,
            name_ar TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price_mils INTEGER NOT NULL
          );
          CREATE TABLE IF NOT EXISTS source_events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL, event_id TEXT UNIQUE NOT NULL,
            event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, delivered INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
          );
        ''')
        db.executemany('INSERT OR IGNORE INTO products VALUES(?,?,?,?,?,?)', SEED_PRODUCTS)
    with connect(RECEIVER_DB) as db:
        db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS received_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE, source_id TEXT NOT NULL,
            event_type TEXT NOT NULL, payload TEXT NOT NULL, received_at TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS synced_orders (
            source_id TEXT NOT NULL, external_id TEXT NOT NULL,
            channel TEXT NOT NULL, status TEXT NOT NULL, total_mils INTEGER NOT NULL,
            revision INTEGER NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(source_id, external_id)
          );
          CREATE TABLE IF NOT EXISTS synced_inventory (
            source_id TEXT NOT NULL, sku TEXT NOT NULL, stock INTEGER NOT NULL,
            revision INTEGER NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(source_id, sku)
          );
        ''')

def source_id(channel):
    return 'idrak-lab-pos' if channel == 'pos' else 'idrak-lab-store'

def product_rows(db):
    return [dict(r) for r in db.execute('SELECT * FROM products ORDER BY sku')]

def order_payload(db, row):
    items = [
        {'sku': r['sku'], 'name': r['name_ar'], 'quantity': r['quantity'],
         'unit_price': money(r['unit_price_mils'])}
        for r in db.execute('SELECT * FROM order_items WHERE order_id=?', (row['id'],))
    ]
    return {
        'external_id':row['external_id'], 'status':row['status'],
        'payment_method':row['payment_method'], 'customer':row['customer'],
        'currency':'JOD', 'total':money(row['total_mils']),
        'items':items, 'created_at':row['created_at'], 'updated_at':row['updated_at'],
        'revision':row['revision']
    }

def append_event(db, channel, event_type, external_id, revision, body):
    payload = {
      'schema_version':'1.0', 'event_id':f'{source_id(channel)}:{external_id}:r{revision}:{event_type}',
      'event_type':event_type, 'occurred_at':iso_now(),
      'source': {'system':source_id(channel), 'account_id':'idrak-test-shop-001',
                 'channel':channel},
      **body
    }
    cur=db.execute('INSERT INTO source_events(channel,event_id,event_type,payload,created_at) VALUES (?,?,?,?,?)',
               (channel,payload['event_id'],event_type,json.dumps(payload,ensure_ascii=False),iso_now()))
    payload['source_sequence']=cur.lastrowid
    db.execute('UPDATE source_events SET payload=? WHERE seq=?', (json.dumps(payload,ensure_ascii=False),cur.lastrowid))
    return payload

def append_inventory_events(db, channel, order_external_id, revision, skus):
    for sku in set(skus):
        p = db.execute('SELECT stock FROM products WHERE sku=?', (sku,)).fetchone()
        append_event(db, channel, 'inventory.updated', f'{order_external_id}:{sku}', revision,
                     {'inventory':{'sku':sku, 'on_hand':p['stock'], 'location_id':'main'}})

def create_order(channel, req):
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
            p=db.execute('SELECT * FROM products WHERE sku=?',(sku,)).fetchone()
            if not p: raise ValueError('المنتج غير موجود')
            if completed and p['stock']<qty: raise ValueError('المخزون غير كافٍ')
            products[sku] = p
            total += p['price_mils']*qty
        now=iso_now()
        cur=db.execute('INSERT INTO orders(external_id,channel,status,payment_method,customer,total_mils,inventory_applied,created_at,updated_at) VALUES(NULL,?,?,?,?,?,?,?,?)',
                   (channel,status,payment,customer,total,1 if completed else 0,now,now))
        oid=cur.lastrowid
        external_id=f'{"POS" if channel=="pos" else "WEB"}-{oid:06d}'
        db.execute('UPDATE orders SET external_id=? WHERE id=?',(external_id,oid))
        for sku,qty in counts.items():
            p=products[sku]
            db.execute('INSERT INTO order_items VALUES(?,?,?,?,?)', (oid,sku,p['name_ar'],qty,p['price_mils']))
            if completed:
                db.execute('UPDATE products SET stock=stock-? WHERE sku=?',(qty,sku))
        row=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
        append_event(db,channel,'sale.created',external_id,1,{'order':order_payload(db,row)})
        if completed: append_inventory_events(db,channel,external_id,1,counts)
    flush_events(channel)
    return {'order_id':external_id, 'total':money(total),'status':status}

def change_order(external_id, status):
    if status not in ('completed','cancelled','refunded'):
        raise ValueError('Invalid status')
    with connect(SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        order=db.execute('SELECT * FROM orders WHERE external_id=?',(external_id,)).fetchone()
        if not order: raise ValueError('Order does not exist')
        old=order['status']
        if (old,status) not in {('pending','completed'),('pending','cancelled'),('completed','refunded')}:
            raise ValueError(f'Cannot change {old} to {status}')
        items=list(db.execute('SELECT sku,quantity FROM order_items WHERE order_id=?',(order['id'],)))
        if status=='completed':
            for it in items:
                p=db.execute('SELECT stock FROM products WHERE sku=?',(it['sku'],)).fetchone()
                if p['stock']<it['quantity']:raise ValueError('المخزون غير كافٍ')
                db.execute('UPDATE products SET stock=stock-? WHERE sku=?',(it['quantity'],it['sku']))
        elif status=='refunded':
            for it in items:
                db.execute('UPDATE products SET stock=stock+? WHERE sku=?',(it['quantity'],it['sku']))
        new_rev=order['revision']+1
        db.execute('UPDATE orders SET status=?, inventory_applied=?, revision=?, updated_at=? WHERE id=?',
                   (status,1 if status=='completed' else 0,new_rev,iso_now(),order['id']))
        row=db.execute('SELECT * FROM orders WHERE id=?',(order['id'],)).fetchone()
        append_event(db,order['channel'],'sale.updated',external_id,new_rev,{'order':order_payload(db,row)})
        if status in ('completed','refunded'):
            append_inventory_events(db,order['channel'],external_id,new_rev,[i['sku'] for i in items])
        channel=order['channel']
    flush_events(channel)
    return {'order_id':external_id, 'status':status}

def sign(raw):
    return 'sha256='+hmac.new(SIGNING_SECRET.encode(),raw,hashlib.sha256).hexdigest()

def post_signed(url, payload):
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    req=Request(url, data=raw,headers={'Content-Type':'application/json',
                'X-Idrak-Signature':sign(raw), 'X-Idrak-Event-Id':payload['event_id']},method='POST')
    with urlopen(req,timeout=2) as response:
        return response.status

def flush_events(channel=None):
    base=f'http://127.0.0.1:{RECEIVER_PORT}/ingest'
    with connect(SOURCE_DB) as db:
        pending=list(db.execute('SELECT * FROM source_events WHERE delivered=0 '+ ('AND channel=? ' if channel else '') +'ORDER BY seq LIMIT 200',
                     (channel,) if channel else ()))
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
    if not hmac.compare_digest(sign(raw),signature or ''):
        return (401,{'error':'invalid webhook signature'})
    try:
        data=json.loads(raw)
        evt_id=data['event_id'];source=data['source']['system']; typ=data['event_type']
        if source not in ('idrak-lab-pos','idrak-lab-store'):
            raise ValueError('unknown source')
        if typ not in ('sale.created','sale.updated','inventory.updated'):
            raise ValueError('unknown event type')
    except (KeyError,TypeError,ValueError,json.JSONDecodeError) as exc:
        return (400,{'error':str(exc)})
    with connect(RECEIVER_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT 1 FROM received_events WHERE event_id=?',(evt_id,)).fetchone()
        if existing:
            return (200,{'status':'duplicate_skipped','event_id':evt_id})
        if typ.startswith('sale.'):
            order=data['order']; oid=order['external_id']; rev=int(order['revision'])
            if order['status'] not in ('completed','pending','cancelled','refunded'):
                return (400,{'error':'unknown sale status'})
            total_mils=int((Decimal(order['total'])*1000).to_integral_exact())
            prev=db.execute('SELECT revision FROM synced_orders WHERE source_id=? AND external_id=?',(source,oid)).fetchone()
            if not prev or rev > prev['revision']:
                db.execute('INSERT INTO synced_orders(source_id,external_id,channel,status,total_mils,revision,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_id,external_id) DO UPDATE SET status=excluded.status,total_mils=excluded.total_mils,revision=excluded.revision,updated_at=excluded.updated_at',
                           (source,oid,data['source']['channel'],order['status'],total_mils,rev,order['updated_at']))
        elif typ=='inventory.updated':
            inventory=data['inventory']; rev=int(data['source_sequence']); sku=inventory['sku']
            prev=db.execute('SELECT revision FROM synced_inventory WHERE source_id=? AND sku=?',(source,sku)).fetchone()
            if not prev or rev >= prev['revision']:
                db.execute('INSERT INTO synced_inventory VALUES(?,?,?,?,?) ON CONFLICT(source_id,sku) DO UPDATE SET stock=excluded.stock,revision=excluded.revision,updated_at=excluded.updated_at',
                           (source,sku,int(inventory['on_hand']),rev,iso_now()))
        db.execute('INSERT INTO received_events(event_id,source_id,event_type,payload,received_at) VALUES(?,?,?,?,?)',
                   (evt_id,source,typ,raw.decode('utf-8'),iso_now()))
    return (201,{'status':'accepted','event_id':evt_id})

def source_get(path,q):
    with connect(SOURCE_DB) as db:
        if path=='/api/products':
            return {'products':[{'sku':p['sku'],'name_ar':p['name_ar'],'name_en':p['name_en'],
                               'emoji':p['emoji'],'price':money(p['price_mils']),'stock':p['stock']}
                               for p in product_rows(db)]}
        if path=='/api/orders':
            channel=(q.get('channel')or[''])[0]
            query='SELECT * FROM orders '+('WHERE channel=? ' if channel in ('pos','web') else '')+'ORDER BY id DESC LIMIT 80'
            rows=db.execute(query,(channel,) if channel in ('pos','web') else ())
            return {'orders':[order_payload(db,o)|{'channel':o['channel']} for o in rows]}
        if path in ('/api/pos/events','/api/web/events'):
            channel='pos' if path.startswith('/api/pos') else 'web'
            try:
                after=max(0,int((q.get('after')or ['0'])[0]));limit=min(200,max(1,int((q.get('limit')or['50'])[0])))
            except ValueError: raise ValueError('after and limit must be integers')
            rows=list(db.execute('SELECT seq,payload FROM source_events WHERE channel=? AND seq>? ORDER BY seq LIMIT ?',
                                 (channel,after,limit)))
            return {'events':[{'cursor':r['seq'],'payload':json.loads(r['payload'])} for r in rows],
                    'next_cursor':rows[-1]['seq'] if rows else after,'has_more':len(rows)==limit}
        if path=='/api/events':
            rows=db.execute('SELECT seq,channel,event_type,event_id,delivered,attempts,last_error,created_at FROM source_events ORDER BY seq DESC LIMIT 100')
            return {'events':[dict(r) for r in rows]}
        if path=='/health':return {'ok':True,'service':'idrak-lab-sources'}
    raise LookupError(path)

def receiver_get(path):
    with connect(RECEIVER_DB) as db:
        if path=='/api/summary':
            stats=db.execute('SELECT count(*) as n,COALESCE(SUM(CASE WHEN status="completed" THEN total_mils ELSE 0 END),0) as revenue FROM synced_orders').fetchone()
            by_channel=[dict(x) for x in db.execute('SELECT channel,count(*) as n,COALESCE(SUM(CASE WHEN status="completed" THEN total_mils ELSE 0 END),0) as revenue_mils FROM synced_orders GROUP BY channel')]
            return {'invoices':stats['n'], 'revenue':money(stats['revenue']),
                    'events':db.execute('SELECT count(*) FROM received_events').fetchone()[0],
                    'channels':[{**v,'revenue':money(v['revenue_mils'])} for v in by_channel]}
        if path=='/api/synced-orders':
            return {'orders':[{**dict(r),'total':money(r['total_mils'])} for r in db.execute('SELECT * FROM synced_orders ORDER BY updated_at DESC LIMIT 100')]}
        if path=='/api/received-events':
            return {'events':[dict(r) for r in db.execute('SELECT id,event_id,source_id,event_type,received_at FROM received_events ORDER BY id DESC LIMIT 100')]}
        if path=='/health':return {'ok':True,'service':'idrak-lab-simulator'}
    raise LookupError(path)

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
        raw=file.read_bytes();self.send_response(200);self.send_header('Content-Type',mime+'; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(raw)
    def read_json(self):
        size=int(self.headers.get('Content-Length','0'))
        if size<=0 or size>100_000:raise ValueError('Invalid request size')
        return json.loads(self.rfile.read(size))
    def guarded(self,action):
        try: return self.send_json(200,action())
        except (ValueError,sqlite3.Error,TypeError,KeyError) as ex:
            self.send_json(400,{'error':str(ex)})

class SourceHandler(BaseHandler):
    def do_GET(self):
        u=urlparse(self.path);path=u.path
        if path=='/':return self.serve_file('home.html')
        if path=='/pos':return self.serve_file('pos.html')
        if path=='/shop':return self.serve_file('shop.html')
        if path=='/admin':return self.serve_file('admin.html')
        if path=='/style.css':return self.serve_file('style.css')
        if path=='/app.js':return self.serve_file('app.js')
        if path.startswith('/api/') or path=='/health':
            return self.guarded(lambda:source_get(path,parse_qs(u.query)))
        return self.send_json(404,{'error':'not found'})
    def do_POST(self):
        path=urlparse(self.path).path
        try:
            req=self.read_json()
            if path=='/api/pos/sales':result=create_order('pos',req)
            elif path=='/api/web/orders':result=create_order('web',req)
            elif path.startswith('/api/orders/') and path.endswith('/status'):
                external_id=path.split('/')[3]
                result=change_order(external_id,req.get('status'))
            elif path=='/api/retry':
                flush_events()
                result={'status':'retried'}
            elif path=='/api/redeliver':
                seq=req.get('seq')
                if type(seq) is not int:raise ValueError('seq must be integer')
                with connect(SOURCE_DB) as db:
                    r=db.execute('SELECT payload FROM source_events WHERE seq=?',(seq,)).fetchone()
                if not r:raise ValueError('event not found')
                result={'receiver':post_signed(f'http://127.0.0.1:{RECEIVER_PORT}/ingest',json.loads(r['payload']))}
            else: return self.send_json(404,{'error':'not found'})
            self.send_json(200,result)
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
        if path.startswith('/api/') or path=='/health':return self.guarded(lambda:receiver_get(path))
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
