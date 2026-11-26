"""Multi-shop isolation, authorization and legacy-data migration (SQLite test DBs)."""
import base64
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hosted_server as hosted

lab = hosted.lab
LEGACY = lab.LEGACY_SHOP

# The exact pre-multi-shop layout (verbatim from the previous release).
LEGACY_SOURCE = '''
CREATE TABLE products (sku TEXT PRIMARY KEY, name_ar TEXT NOT NULL, name_en TEXT NOT NULL,
  emoji TEXT NOT NULL, price_mils INTEGER NOT NULL, stock INTEGER NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, external_id TEXT UNIQUE,
  channel TEXT NOT NULL, status TEXT NOT NULL, payment_method TEXT NOT NULL,
  customer TEXT NOT NULL DEFAULT '', total_mils INTEGER NOT NULL,
  inventory_applied INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE order_items (order_id INTEGER NOT NULL REFERENCES orders(id), sku TEXT NOT NULL,
  name_ar TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price_mils INTEGER NOT NULL);
CREATE TABLE source_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT NOT NULL,
  event_id TEXT UNIQUE NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL,
  created_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, delivered INTEGER NOT NULL DEFAULT 0,
  last_error TEXT);
'''
LEGACY_RECEIVER = '''
CREATE TABLE received_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
  source_id TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL, received_at TEXT NOT NULL);
CREATE TABLE synced_orders (source_id TEXT NOT NULL, external_id TEXT NOT NULL, channel TEXT NOT NULL,
  status TEXT NOT NULL, total_mils INTEGER NOT NULL, revision INTEGER NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(source_id, external_id));
CREATE TABLE synced_inventory (source_id TEXT NOT NULL, sku TEXT NOT NULL, stock INTEGER NOT NULL,
  revision INTEGER NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(source_id, sku));
'''


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.patches = [patch.object(lab, 'SOURCE_DB', d / 's.sqlite3'), patch.object(lab, 'RECEIVER_DB', d / 'r.sqlite3'),
                        patch.object(lab, 'DATA', d), patch.object(lab, 'post_signed', hosted.deliver_to_simulator)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def stock(self, shop, sku):
        return {p['sku']: p['stock'] for p in lab.source_get(shop, '/api/products', {})['products']}[sku]


class LegacyMigrationTests(Base):
    def make_legacy(self):
        db = sqlite3.connect(lab.SOURCE_DB)
        db.executescript(LEGACY_SOURCE)
        db.executemany('INSERT INTO products VALUES(?,?,?,?,?,?)', lab.SEED_PRODUCTS)
        db.execute("UPDATE products SET stock=55 WHERE sku='BRG-001'")
        for i, (ch, st) in enumerate([('pos', 'completed'), ('web', 'pending'), ('pos', 'refunded')], 1):
            db.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (i, ('POS-%06d' if ch == 'pos' else 'WEB-%06d') % i, ch, st, 'cash', 'c', 4250, 1, 2, 'x', 'y'))
            db.execute('INSERT INTO order_items VALUES(?,?,?,?,?)', (i, 'BRG-001', 'برغر', 1, 4250))
            payload = {'event_id': f'idrak-lab-pos:E{i}:r1:sale.created', 'source': {'account_id': LEGACY, 'system': 'idrak-lab-pos', 'channel': ch}}
            db.execute('INSERT INTO source_events(channel,event_id,event_type,payload,created_at,delivered) VALUES(?,?,?,?,?,1)',
                       (ch, payload['event_id'], 'sale.created', json.dumps(payload), 'z'))
        db.commit(); db.close()
        db = sqlite3.connect(lab.RECEIVER_DB)
        db.executescript(LEGACY_RECEIVER)
        db.execute("INSERT INTO received_events VALUES(1,'e1','idrak-lab-pos','sale.created','{}','t')")
        db.execute("INSERT INTO synced_orders VALUES('idrak-lab-pos','POS-000001','pos','completed',4250,1,'t')")
        db.execute("INSERT INTO synced_inventory VALUES('idrak-lab-pos','BRG-001',55,3,'t')")
        db.commit(); db.close()

    def test_legacy_data_preserved_and_assigned_to_legacy_shop(self):
        self.make_legacy()
        lab.init_db()
        with lab.connect(lab.SOURCE_DB) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual([tuple(r) for r in db.execute('SELECT id,order_no,external_id,shop_id,status FROM orders ORDER BY id')],
                             [(1, 1, 'POS-000001', LEGACY, 'completed'), (2, 2, 'WEB-000002', LEGACY, 'pending'),
                              (3, 3, 'POS-000003', LEGACY, 'refunded')])
            self.assertEqual(db.execute('SELECT count(*) FROM order_items WHERE shop_id=?', (LEGACY,)).fetchone()[0], 3)
            self.assertEqual([r['seq'] for r in db.execute('SELECT seq FROM source_events ORDER BY seq')], [1, 2, 3])
        self.assertEqual(self.stock(LEGACY, 'BRG-001'), 55)  # existing stock kept, not re-seeded
        # old cursors keep working through the API, and the invoice sequence continues
        self.assertEqual(len(lab.source_get(LEGACY, '/api/pos/events', {'after': ['1']})['events']), 1)
        with patch.object(lab, 'flush_events', lambda *a, **k: None):
            self.assertEqual(lab.create_order(LEGACY, 'pos', {'items': [{'sku': 'DRK-001', 'quantity': 1}]})['order_id'], 'POS-000004')
        self.assertEqual(lab.receiver_get(LEGACY, '/api/summary')['invoices'], 1)
        self.assertEqual(lab.receiver_get(LEGACY, '/api/summary')['events'], 1)

    def test_migration_is_idempotent_and_matches_fresh_layout(self):
        self.make_legacy()
        lab.init_db(); lab.init_db()
        migrated = self.layout()
        self.tmp2 = tempfile.TemporaryDirectory()
        with patch.object(lab, 'SOURCE_DB', Path(self.tmp2.name) / 's'), patch.object(lab, 'RECEIVER_DB', Path(self.tmp2.name) / 'r'):
            lab.init_db()
            fresh = self.layout()
        self.tmp2.cleanup()
        self.assertEqual(migrated, fresh)

    def layout(self):
        out = {}
        for path in (lab.SOURCE_DB, lab.RECEIVER_DB):
            db = sqlite3.connect(path)
            for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                out[t] = sorted((r[1], r[2], r[3], r[5]) for r in db.execute(f'PRAGMA table_info({t})'))
            db.close()
        return out

    def test_failed_migration_rolls_back_completely(self):
        self.make_legacy()
        db = sqlite3.connect(lab.SOURCE_DB)
        db.execute("INSERT INTO products VALUES('NEG','n','n','x',1,-5)")  # violates new CHECK(stock>=0)
        db.commit(); db.close()
        with self.assertRaises(sqlite3.IntegrityError):
            lab.init_db()
        db = sqlite3.connect(lab.SOURCE_DB)
        cols = [r[1] for r in db.execute('PRAGMA table_info(products)')]
        self.assertNotIn('shop_id', cols)  # untouched legacy layout, nothing lost
        self.assertEqual(db.execute('SELECT count(*) FROM orders').fetchone()[0], 3)
        db.close()


class IsolationTests(Base):
    def setUp(self):
        super().setUp()
        lab.init_db()
        self.a = lab.create_shop('Shop A')
        self.b = lab.create_shop('Shop B')

    def test_stock_invoices_and_events_are_independent(self):
        A, B = self.a['shop_id'], self.b['shop_id']
        ra = lab.create_order(A, 'pos', {'items': [{'sku': 'BRG-001', 'quantity': 10}]})
        rb = lab.create_order(B, 'pos', {'items': [{'sku': 'BRG-001', 'quantity': 1}]})
        self.assertEqual((ra['order_id'], rb['order_id']), ('POS-000001', 'POS-000001'))  # per-shop numbering
        self.assertEqual((self.stock(A, 'BRG-001'), self.stock(B, 'BRG-001'), self.stock(LEGACY, 'BRG-001')), (50, 59, 60))
        ea = lab.source_get(A, '/api/pos/events', {})['events']
        eb = lab.source_get(B, '/api/pos/events', {})['events']
        self.assertTrue(all(e['payload']['source']['account_id'] == A for e in ea))
        self.assertTrue(all(e['payload']['source']['account_id'] == B for e in eb))
        self.assertFalse({e['cursor'] for e in ea} & {e['cursor'] for e in eb})
        self.assertEqual(lab.source_get(LEGACY, '/api/pos/events', {})['events'], [])
        self.assertEqual(len(lab.source_get(B, '/api/orders', {})['orders']), 1)
        # same event_id in both shops is accepted independently by the receiver
        self.assertEqual(lab.receiver_get(A, '/api/summary')['revenue'], '42.500')
        self.assertEqual(lab.receiver_get(B, '/api/summary')['revenue'], '4.250')
        self.assertEqual(lab.receiver_get(LEGACY, '/api/summary')['invoices'], 0)

    def test_cannot_touch_other_shops_orders_or_events(self):
        A, B = self.a['shop_id'], self.b['shop_id']
        o = lab.create_order(A, 'web', {'items': [{'sku': 'FRY-001', 'quantity': 2}], 'payment_method': 'cash_on_delivery'})
        with self.assertRaises(ValueError):
            lab.change_order(B, o['order_id'], 'completed')  # same invoice number, other shop
        self.assertEqual(lab.source_get(A, '/api/orders', {})['orders'][0]['status'], 'pending')
        seq = lab.source_get(A, '/api/web/events', {})['events'][0]['cursor']
        with self.assertRaises(ValueError):
            lab.handle_source_post(lab.Principal('shop', B), None, '/api/redeliver', {'seq': seq})

    def test_receiver_rejects_cross_shop_signature(self):
        A, B = self.a['shop_id'], self.b['shop_id']
        lab.create_order(A, 'pos', {'items': [{'sku': 'DRK-001', 'quantity': 1}]})
        payload = lab.source_get(A, '/api/pos/events', {})['events'][0]['payload']
        raw = json.dumps(payload).encode()
        self.assertEqual(lab.ingest_event(raw, lab.sign(raw, B))[0], 401)       # B's key on A's event
        forged = json.dumps({**payload, 'source': {**payload['source'], 'account_id': B}}).encode()
        self.assertEqual(lab.ingest_event(forged, lab.sign(raw, A))[0], 401)     # A's key, relabelled as B
        self.assertEqual(lab.ingest_event(forged, lab.sign(forged, A))[0], 401)
        self.assertEqual(lab.receiver_get(B, '/api/summary')['events'], 0)

    def test_concurrent_orders_in_one_shop_get_unique_numbers(self):
        A = self.a['shop_id']
        with patch.object(lab, 'flush_events', lambda *a, **k: None):
            ids = []
            def go():
                for _ in range(5):
                    ids.append(lab.create_order(A, 'pos', {'items': [{'sku': 'DRK-001', 'quantity': 1}]})['order_id'])
            ts = [threading.Thread(target=go) for _ in range(4)]
            [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(len(set(ids)), 20)

    def test_db_rejects_item_with_wrong_shop(self):
        A, B = self.a['shop_id'], self.b['shop_id']
        lab.create_order(A, 'pos', {'items': [{'sku': 'DRK-001', 'quantity': 1}]})
        with self.assertRaises(sqlite3.IntegrityError):
            with lab.connect(lab.SOURCE_DB) as db:
                db.execute('INSERT INTO order_items(order_id,shop_id,sku,name_ar,quantity,unit_price_mils) VALUES(1,?,?,?,?,?)', (B, 'x', 'x', 1, 1))


class HttpAuthTests(Base):
    def setUp(self):
        super().setUp()
        lab.init_db()
        self.server = hosted.ThreadingHTTPServer(('127.0.0.1', 0), hosted.HostedHandler)
        self.server.access_user, self.server.access_password = 'op', 'operator-password-for-tests'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.op = {'Authorization': 'Basic ' + base64.b64encode(b'op:operator-password-for-tests').decode()}
        self.a = self.call('POST', '/api/shops', {'name': 'A'}, self.op)[1]
        self.b = self.call('POST', '/api/shops', {'name': 'B'}, self.op)[1]
        self.ha = {'Authorization': 'Bearer ' + self.a['token']}
        self.hb = {'Authorization': 'Bearer ' + self.b['token']}

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        super().tearDown()

    def call(self, method, path, body=None, headers=None):
        req = Request(self.base + path, data=None if body is None else json.dumps(body).encode(), headers=headers or {}, method=method)
        try:
            with urlopen(req, timeout=3) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw[:1] in (b'{', b'[') else raw)
        except HTTPError as e:
            raw = e.read()
            return e.code, (json.loads(raw) if raw[:1] == b'{' else raw)

    def test_shop_token_sees_only_its_shop_and_cannot_impersonate(self):
        code, sale = self.call('POST', '/api/pos/sales', {'items': [{'sku': 'BRG-001', 'quantity': 3}], 'shop_id': self.b['shop_id']}, self.ha)
        self.assertEqual(code, 200)
        self.assertEqual([p for p in self.call('GET', '/api/products', None, self.ha)[1]['products'] if p['sku'] == 'BRG-001'][0]['stock'], 57)
        self.assertEqual([p for p in self.call('GET', '/api/products', None, self.hb)[1]['products'] if p['sku'] == 'BRG-001'][0]['stock'], 60)
        self.assertEqual(len(self.call('GET', '/api/orders', None, self.hb)[1]['orders']), 0)  # body shop_id ignored
        for path in ('/api/products', '/api/orders', '/api/pos/events', '/simulator/api/summary', '/api/events'):
            c, _ = self.call('GET', path, None, {**self.ha, 'X-Lab-Shop': self.b['shop_id']})
            self.assertEqual(c, 403, path)
        c, _ = self.call('POST', '/api/pos/sales', {'items': [{'sku': 'BRG-001', 'quantity': 1}]}, {**self.hb, 'X-Lab-Shop': self.a['shop_id']})
        self.assertEqual(c, 403)
        self.assertEqual(self.call('POST', f"/api/orders/{sale['order_id']}/status", {'status': 'refunded'}, self.hb)[0], 400)
        self.assertEqual(self.call('POST', f"/api/orders/{sale['order_id']}/status", {'status': 'refunded'}, self.ha)[0], 200)
        self.assertEqual(self.call('GET', '/simulator/api/summary', None, self.hb)[1]['invoices'], 0)

    def test_bad_credentials_and_admin_endpoints(self):
        sid, secret = self.a['token'].split('.', 1)
        for h in ({}, {'Authorization': 'Bearer nope'}, {'Authorization': f'Bearer {sid}.wrong'},
                  {'Authorization': f'Bearer {sid}.'}, {'Authorization': 'Bearer shop-ffffffffffff.' + secret},
                  {'Authorization': 'Bearer ' + sid}, {'Authorization': f'Bearer {LEGACY}.x'}):
            self.assertEqual(self.call('GET', '/api/products', None, h)[0], 401, h)
        # shop tokens never open pages or shop administration
        for path in ('/', '/pos', '/admin', '/api/shops'):
            self.assertEqual(self.call('GET', path, None, self.ha)[0], 401, path)
        self.assertEqual(self.call('POST', '/api/shops', {'name': 'X'}, self.ha)[0], 401)
        self.assertEqual(self.call('POST', '/api/shops/rotate-token', {'shop_id': self.b['shop_id']}, self.ha)[0], 401)
        self.assertEqual(self.call('GET', '/api/shops', None, self.op)[0], 200)
        listing = json.dumps(self.call('GET', '/api/shops', None, self.op)[1])
        self.assertNotIn(secret, listing)
        self.assertNotIn('token_hash', listing)

    def test_operator_default_and_selection_and_rotation(self):
        # operator without a header = legacy shop (existing Basic-auth clients keep working)
        self.assertEqual(self.call('GET', '/api/orders', None, self.op)[0], 200)
        c, r = self.call('GET', '/api/products', None, {**self.op, 'X-Lab-Shop': self.a['shop_id']})
        self.assertEqual(c, 200)
        self.assertEqual(self.call('GET', '/api/products', None, {**self.op, 'X-Lab-Shop': 'shop-000000000000'})[0], 404)
        self.assertEqual(self.call('GET', '/api/products', None, {**self.op, 'X-Lab-Shop': "x' OR '1'='1"})[0], 404)
        c, new = self.call('POST', '/api/shops/rotate-token', {'shop_id': self.a['shop_id']}, self.op)
        self.assertEqual(c, 200)
        self.assertEqual(self.call('GET', '/api/products', None, self.ha)[0], 401)  # old token revoked
        self.assertEqual(self.call('GET', '/api/products', None, {'Authorization': 'Bearer ' + new['token']})[0], 200)

    def test_disabled_shop_token_rejected_and_health_public(self):
        with lab.connect(lab.SOURCE_DB) as db:
            db.execute('UPDATE shops SET disabled=1 WHERE shop_id=?', (self.a['shop_id'],))
        self.assertEqual(self.call('GET', '/api/products', None, self.ha)[0], 401)
        self.assertEqual(self.call('GET', '/health')[0], 200)


if __name__ == '__main__':
    unittest.main()
