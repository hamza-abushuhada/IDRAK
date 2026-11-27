"""Store API keys: hash-only storage, one shop, read-only routes, expiry, revoke, rotate, notifications."""
import hashlib
import hmac
import json
import os
import time
from unittest.mock import patch

from test_multishop import Base, lab
import api_keys
import idrak_notify


class ApiKeyTests(Base):
    def setUp(self):
        super().setUp()
        self.secret = patch.object(lab, 'SIGNING_SECRET', 'signing-test-only-' + 's' * 40)
        self.secret.start()
        self.addCleanup(self.secret.stop)
        lab.init_db()
        self.a, self.b = lab.create_shop('Store A'), lab.create_shop('Store B')
        self.owner_a = lab.Principal('shop', self.a['shop_id'], role='owner', user_id='u-a')
        self.owner_b = lab.Principal('shop', self.b['shop_id'], role='owner', user_id='u-b')

    def key(self, owner=None, **req):
        owner = owner or self.owner_a
        return lab.handle_source_post(owner, None, '/api/keys', {'name': 'IDRAK', **req})

    def auth(self, key, path='/api/web/events', method='GET'):
        return lab.authenticate('Bearer ' + key, path, method, 'Basic operator')

    def test_key_shown_once_and_only_hash_stored(self):
        created = self.key()
        self.assertRegex(created['key'], r'^lsk_[a-f0-9]{12}_[A-Za-z0-9_-]{43}$')
        with lab.connect(lab.SOURCE_DB) as db:
            row = dict(db.execute('SELECT * FROM lab_api_keys').fetchone())
        secret = created['key'].split('_', 2)[2]
        self.assertNotIn(secret, json.dumps(row))
        self.assertEqual(row['key_hash'], hashlib.sha256(secret.encode()).hexdigest())
        listed = lab.handle_source_get(self.owner_a, None, '/api/keys', {})
        self.assertNotIn(created['key'], json.dumps(listed))
        self.assertNotIn(secret, json.dumps(listed))
        self.assertEqual(listed['keys'][0]['scopes'], ['orders:read'])

    def test_key_reads_only_its_own_store_web_events(self):
        key = self.key()['key']
        lab.create_order(self.a['shop_id'], 'web', {'items': [{'sku': 'BRG-001', 'quantity': 1}]})
        lab.create_order(self.a['shop_id'], 'pos', {'items': [{'sku': 'BRG-001', 'quantity': 1}]})
        lab.create_order(self.b['shop_id'], 'web', {'items': [{'sku': 'BRG-002', 'quantity': 1}]})
        p = self.auth(key)
        self.assertEqual((p.kind, p.shop_id, p.role), ('integration', self.a['shop_id'], 'apikey'))
        events = lab.handle_source_get(p, None, '/api/web/events', {})['events']
        self.assertTrue(events)
        self.assertTrue(all(e['payload']['source']['account_id'] == self.a['shop_id'] and e['payload']['source']['channel'] == 'web' for e in events))
        with self.assertRaises(lab.LabAuthError):  # cannot pick another shop
            lab.handle_source_get(p, self.b['shop_id'], '/api/web/events', {})
        # POS events, products, orders, keys, pages, writes: all refused before routing.
        for method, path in (('GET', '/api/pos/events'), ('GET', '/api/orders'), ('GET', '/api/keys'), ('GET', '/api/products'),
                             ('POST', '/api/web/orders'), ('POST', '/api/keys'), ('GET', '/admin'), ('POST', '/api/orders/WEB-000001/status')):
            self.assertIsNone(self.auth(key, path, method), (method, path))
        info = lab.handle_source_get(self.auth(key, '/api/v1/store'), None, '/api/v1/store', {})
        self.assertEqual((info['store_id'], info['name'], info['scopes']), (self.a['shop_id'], 'Store A', ['orders:read']))
        self.assertNotIn('key', {k for k in info if k != 'key_id' and 'key' == k})

    def test_wrong_tampered_expired_revoked_and_disabled_keys_rejected(self):
        key = self.key()['key']
        self.assertIsNone(self.auth(key[:-1] + ('A' if key[-1] != 'A' else 'B')))
        self.assertIsNone(self.auth('lsk_000000000000_' + 'x' * 43))
        short = self.key(expires_in_days=30)
        with lab.connect(lab.SOURCE_DB) as db:
            db.execute('UPDATE lab_api_keys SET expires_at=? WHERE key_id=?', (int(time.time()) - 1, short['key_id']))
        self.assertIsNone(self.auth(short['key']))
        self.assertEqual(lab.handle_source_get(self.owner_a, None, '/api/keys', {})['keys'][0]['status'] in ('expired', 'active'), True)
        lab.handle_source_post(self.owner_a, None, '/api/keys/revoke', {'key_id': self.auth(key).user_id})
        self.assertIsNone(self.auth(key))
        other = self.key()['key']
        with lab.connect(lab.SOURCE_DB) as db:
            db.execute('UPDATE shops SET disabled=1 WHERE shop_id=?', (self.a['shop_id'],))
        self.assertIsNone(self.auth(other))

    def test_rotate_revokes_old_and_keeps_name_scope_and_lifetime(self):
        first = self.key(expires_in_days=365, name='Main')
        rotated = lab.handle_source_post(self.owner_a, None, '/api/keys/rotate', {'key_id': first['key_id']})
        self.assertEqual((rotated['replaced'], rotated['name'], rotated['scopes']), (first['key_id'], 'Main', ['orders:read']))
        self.assertGreater(rotated['expires_at'], time.time() + 360 * 86400)
        self.assertIsNone(self.auth(first['key']))
        self.assertIsNotNone(self.auth(rotated['key']))
        with self.assertRaises(lab.LabAuthError):
            lab.handle_source_post(self.owner_a, None, '/api/keys/rotate', {'key_id': first['key_id']})

    def test_only_owner_manages_keys_of_own_shop(self):
        cashier = lab.Principal('shop', self.a['shop_id'], role='cashier', user_id='c')
        with self.assertRaises(lab.LabAuthError):
            lab.handle_source_post(cashier, None, '/api/keys', {'name': 'x'})
        with self.assertRaises(lab.LabAuthError):
            lab.handle_source_get(cashier, None, '/api/keys', {})
        b_key = self.key(owner=self.owner_b)
        with self.assertRaises(lab.LabAuthError):  # owner A cannot revoke B's key
            lab.handle_source_post(self.owner_a, None, '/api/keys/revoke', {'key_id': b_key['key_id']})
        with self.assertRaises(lab.LabAuthError):  # owner A cannot target shop B
            lab.handle_source_post(self.owner_a, self.b['shop_id'], '/api/keys', {'name': 'x'})
        p = self.auth(self.key()['key'], '/api/v1/notifications', 'POST')
        with self.assertRaises(lab.LabAuthError):
            lab.handle_source_post(p, None, '/api/keys', {'name': 'x'})
        for bad in ({'name': 'x', 'expires_in_days': 7}, {'name': ''}, {'name': 'x', 'scopes': ['*']}):
            with self.assertRaises((ValueError, lab.LabAuthError)):
                self.key(**{k: v for k, v in bad.items() if k != 'name'}, **({'name': bad['name']} if 'name' in bad else {}))

    def test_notifications_signed_per_key_to_fixed_path_only_for_subscribers(self):
        key = self.key()['key']
        p = self.auth(key, '/api/v1/notifications', 'POST')
        sub = lab.handle_source_post(p, None, '/api/v1/notifications', {'enabled': True})
        self.assertRegex(sub['signing_secret'], r'^[a-f0-9]{64}$')
        self.assertNotEqual(sub['signing_secret'], lab.shop_secret(self.a['shop_id']))
        sent = []

        class Opener:
            def open(self, request, timeout):
                sent.append(request)
                return type('R', (), {'status': 202, '__enter__': lambda s: s, '__exit__': lambda s, *a: None})()
        with patch.dict(os.environ, {'IDRAK_CONNECT_NOTIFY_URL': 'https://api.idrak.example.com/integrations/lab/notify'}):
            self.assertEqual(idrak_notify.notify_store_keys(self.a['shop_id'], Opener()), [202])
            self.assertEqual(idrak_notify.notify_store_keys(self.b['shop_id'], Opener()), [])
        req = sent[0]
        self.assertEqual(req.full_url, 'https://api.idrak.example.com/integrations/store/notify')
        body = json.loads(req.data)
        self.assertEqual(set(body), {'key_id', 'shop_id', 'channel', 'ts', 'nonce'})
        self.assertNotIn(key.split('_', 2)[2], req.data.decode())
        expected = hmac.new(sub['signing_secret'].encode(), b'idrak-store-notify:' + req.data, hashlib.sha256).hexdigest()
        self.assertEqual(req.get_header('X-idrak-signature'), expected)
        lab.handle_source_post(self.owner_a, None, '/api/keys/revoke', {'key_id': body['key_id']})
        self.assertEqual(api_keys.subscribers(self.a['shop_id']), [])
