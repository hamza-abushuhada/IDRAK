"""Independent POS accounts: email/password login, invites, owner/cashier roles,
throttling, logout revocation and shop isolation. Temporary SQLite only."""
import base64
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demo_server as lab
import lab_users
import postgres_backend as pg
from fastapi.testclient import TestClient

SECRET = 'test-signing-secret-long-and-distinct'
OWNER_PW = 'Owner-pass-2026!'
CASHIER_PW = 'Cashier-pass-2026!'


class UserLoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch.object(lab, 'SOURCE_DB', root / 's.db'), patch.object(lab, 'RECEIVER_DB', root / 'r.db'),
                        patch.object(lab, 'DATA', root), patch.object(lab, 'SIGNING_SECRET', SECRET), patch.object(pg, 'install'),
                        patch.dict(os.environ, {'IDRAK_LAB_ACCESS_PASSWORD': 'test-operator-password-long',
                                                'IDRAK_LAB_WEBHOOK_SECRET': SECRET,
                                                'IDRAK_LAB_PAIRING_KEY': 'pairing-test-only-' + 'k' * 40})]
        for p in self.patches:
            p.start()
        self.old_delivery = lab.post_signed
        lab.init_db()
        spec = importlib.util.spec_from_file_location('user_login_app', Path(pg.__file__).with_name('serverless_app.py'))
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.a, self.b = lab.create_shop('Shop A'), lab.create_shop('Shop B')
        self.base = 'https://testserver'
        self.O = {'Origin': self.base}
        self.op = {'Authorization': 'Basic ' + base64.b64encode(b'lab:test-operator-password-long').decode(), **self.O}
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        lab.post_signed = self.old_delivery
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def client(self):
        c = TestClient(self.module.app, base_url=self.base)
        self.clients.append(c)
        return c

    def invite(self, shop, email, role='owner'):
        r = self.client().post('/api/shops/invite', json={'shop_id': shop['shop_id'], 'email': email, 'role': role}, headers=self.op)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['token']

    def activate(self, token, password):
        c = self.client()
        r = c.post('/auth/activate', json={'token': token, 'password': password}, headers=self.O)
        return c, r

    def owner(self, shop, email='owner-a@example.org'):
        c, r = self.activate(self.invite(shop, email), OWNER_PW)
        self.assertEqual(r.status_code, 200, r.text)
        return c

    def login(self, email, password, client=None):
        c = client or self.client()
        return c, c.post('/auth/login', json={'email': email, 'password': password}, headers=self.O)

    # ---------------------------------------------------------------
    def test_activation_sets_hashed_password_and_secure_session(self):
        token = self.invite(self.a, 'Owner-A@Example.org')
        info = self.client().post('/auth/invite', json={'token': token}, headers=self.O).json()
        self.assertEqual((info['email'], info['role'], info['has_account']), ('owner-a@example.org', 'owner', False))
        _, weak = self.activate(token, 'short')
        self.assertEqual(weak.status_code, 400)
        c, r = self.activate(token, OWNER_PW)
        self.assertEqual(r.status_code, 200)
        cookie = r.headers['set-cookie']
        for flag in ('HttpOnly', 'Secure', 'SameSite=Strict'):
            self.assertIn(flag, cookie)
        self.assertNotIn(OWNER_PW, cookie)
        s = c.get('/auth/session').json()
        self.assertEqual((s['shop_id'], s['role'], s['email'], s['via']), (self.a['shop_id'], 'owner', 'owner-a@example.org', 'password'))
        with lab.connect(lab.SOURCE_DB) as db:
            stored = db.execute('SELECT password_hash FROM lab_users').fetchone()['password_hash']
            invite_rows = [dict(r) for r in db.execute('SELECT * FROM lab_user_invites')]
        self.assertTrue(stored.startswith('scrypt$')); self.assertNotIn(OWNER_PW, stored)
        self.assertNotIn(token, json.dumps(invite_rows))
        _, again = self.activate(token, OWNER_PW)
        self.assertEqual(again.status_code, 400, 'invite must be single-use')

    def test_password_login_generic_errors_and_throttle(self):
        self.owner(self.a)
        self.client().post('/auth/logout', json={}, headers=self.O)
        c, ok = self.login('OWNER-A@example.org', OWNER_PW)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(c.get('/auth/session').json()['shop_id'], self.a['shop_id'])
        _, wrong = self.login('owner-a@example.org', 'wrong-password-123')
        _, unknown = self.login('nobody@example.org', 'wrong-password-123')
        self.assertEqual((wrong.status_code, unknown.status_code), (401, 401))
        self.assertEqual(wrong.json(), unknown.json(), 'no account enumeration')
        for _ in range(4):
            self.login('owner-a@example.org', 'wrong-password-123')
        _, locked = self.login('owner-a@example.org', OWNER_PW)
        self.assertEqual(locked.status_code, 429, 'account locked after repeated failures, even with the right password')
        with patch.object(lab_users.time, 'time', return_value=time.time() + 16 * 60):
            _, later = self.login('owner-a@example.org', OWNER_PW)
        self.assertEqual(later.status_code, 200)
        cross = self.client().post('/auth/login', json={'email': 'owner-a@example.org', 'password': OWNER_PW},
                                   headers={'Origin': 'https://evil.example.org'})
        self.assertEqual(cross.status_code, 403)
        bad = self.client().post('/auth/login', json={'email': 'owner-a@example.org', 'password': OWNER_PW, 'extra': 1}, headers=self.O)
        self.assertEqual(bad.status_code, 400)

    def test_cashier_role_is_enforced_by_server(self):
        owner = self.owner(self.a)
        r = owner.post('/api/team/invite', json={'email': 'cashier@example.org', 'role': 'cashier'}, headers=self.O)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(owner.post('/api/team/invite', json={'email': 'x@example.org', 'role': 'owner'}, headers=self.O).status_code, 400)
        cashier, act = self.activate(r.json()['token'], CASHIER_PW)
        self.assertEqual(act.status_code, 200)
        self.assertEqual(cashier.get('/auth/session').json()['role'], 'cashier')
        self.assertEqual(cashier.post('/api/pos/sales', json={'items': [{'sku': 'BRG-001', 'quantity': 1}], 'payment_method': 'cash'}, headers=self.O).status_code, 200)
        for path in ('/api/products', '/api/orders'):
            self.assertEqual(cashier.get(path).status_code, 200, path)
        denied_get = ('/api/team', '/api/events', '/simulator/api/summary')
        denied_post = (('/api/web/orders', {'items': [{'sku': 'BRG-001', 'quantity': 1}]}), ('/api/orders/POS-000001/status', {'status': 'refunded'}),
                       ('/api/pairing-codes', {'intent': 'x.y'}), ('/api/team/invite', {'email': 'y@example.org'}), ('/api/retry', {}))
        for path in denied_get:
            self.assertEqual(cashier.get(path).status_code, 403, path)
        for path, body in denied_post:
            self.assertEqual(cashier.post(path, json=body, headers=self.O).status_code, 403, path)
        for page in ('/admin', '/shop', '/simulator/', '/'):
            res = cashier.get(page, follow_redirects=False)
            self.assertEqual((res.status_code, res.headers.get('location')), (303, '/pos'), page)
        self.assertEqual(cashier.get('/pos').status_code, 200)
        # Owner removes the cashier: the existing cashier session stops working at once.
        cid = next(m['user_id'] for m in owner.get('/api/team').json()['members'] if m['role'] == 'cashier')
        self.assertEqual(owner.post('/api/team/remove', json={'user_id': cid}, headers=self.O).status_code, 200)
        self.assertEqual(cashier.get('/api/products').status_code, 401)

    def test_shop_isolation_and_multi_shop_membership(self):
        owner = self.owner(self.a)
        self.assertEqual(owner.get('/api/orders', headers={'X-Lab-Shop': self.b['shop_id']}).status_code, 403)
        self.assertEqual(owner.post('/auth/switch-shop', json={'shop_id': self.b['shop_id']}, headers=self.O).status_code, 401)
        # Same owner invited to shop B: an invite never resets an existing password.
        token_b = self.invite(self.b, 'owner-a@example.org')
        self.assertTrue(self.client().post('/auth/invite', json={'token': token_b}, headers=self.O).json()['has_account'])
        _, wrong = self.activate(token_b, 'not-my-password-1')
        self.assertEqual(wrong.status_code, 401)
        c, ok = self.activate(token_b, OWNER_PW)
        self.assertEqual(ok.status_code, 200)
        s = c.get('/auth/session').json()
        self.assertEqual({x['shop_id'] for x in s['shops']}, {self.a['shop_id'], self.b['shop_id']})
        c.post('/api/pos/sales', json={'items': [{'sku': 'BRG-001', 'quantity': 3}], 'payment_method': 'cash'}, headers=self.O)
        self.assertEqual(c.post('/auth/switch-shop', json={'shop_id': self.a['shop_id']}, headers=self.O).status_code, 200)
        self.assertEqual(c.get('/auth/session').json()['shop_id'], self.a['shop_id'])
        self.assertEqual(c.get('/api/orders').json()['orders'], [], 'shop B sale is not visible in shop A')
        other = self.owner(self.b, 'owner-b@example.org')
        self.assertEqual(other.post('/auth/switch-shop', json={'shop_id': self.a['shop_id']}, headers=self.O).status_code, 401)

    def test_logout_revokes_session_server_side(self):
        owner = self.owner(self.a)
        raw = owner.cookies.get('idrak_lab_session')
        self.assertEqual(owner.post('/auth/logout', json={}, headers=self.O).status_code, 200)
        replay = self.client(); replay.cookies.set('idrak_lab_session', raw)
        self.assertEqual(replay.get('/api/products').status_code, 401, 'a copied cookie must not survive logout')

    def test_token_login_is_restricted_admin_path(self):
        c = self.client()
        r = c.post('/auth/login', json={'token': self.a['token']}, headers=self.O)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c.get('/auth/session').json()['via'], 'token')
        with patch.dict(os.environ, {'IDRAK_LAB_TOKEN_LOGIN': 'off'}):
            self.assertEqual(c.get('/api/products').status_code, 401, 'existing token sessions stop when disabled')
            self.assertEqual(self.client().post('/auth/login', json={'token': self.a['token']}, headers=self.O).status_code, 403)

    def test_owner_session_can_still_pair_with_idrak(self):
        owner = self.owner(self.a)
        import pairing
        data = {'aud': 'idrak-lab-pairing-v1', 'org': str(uuid4()), 'user': str(uuid4()), 'nonce': str(uuid4()), 'exp': int(time.time()) + 300}
        value = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        intent = value + '.' + hmac.new(pairing.key(), b'intent:' + value.encode(), hashlib.sha256).hexdigest()
        r = owner.post('/api/pairing-codes', json={'intent': intent}, headers=self.O)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn('code', r.json())

    def cashier(self):
        owner = self.owner(self.a)
        token = owner.post('/api/team/invite', json={'email': 'cashier@example.org', 'role': 'cashier'}, headers=self.O).json()['token']
        c, r = self.activate(token, CASHIER_PW)
        self.assertEqual(r.status_code, 200)
        return owner, c

    def test_no_owner_markup_sent_to_cashier(self):
        """No authorization UI flash: the role is decided in the HTML the server sends."""
        owner, cashier = self.cashier()
        html = cashier.get('/pos').text
        self.assertIn('data-role="cashier"', html)
        for owner_only in ('data-owner', 'href="/admin"', 'href="/shop"', '/simulator/', 'إدارة الطلبات'):
            self.assertNotIn(owner_only, html, owner_only)
        own = owner.get('/pos').text
        self.assertIn('data-role="owner"', own)
        self.assertIn('data-owner', own)
        self.assertIn('href="/admin"', own)
        self.assertIn('data-role="none"', self.client().get('/login').text)
        css = (Path(lab.ROOT) / 'public/style.css').read_text(encoding='utf-8')
        self.assertIn('[data-owner]{display:none!important}', css, 'owner UI hidden by default')
        js = (Path(lab.ROOT) / 'public/app.js').read_text(encoding='utf-8')
        self.assertIn("document.documentElement.dataset.role==='owner'&&session.role==='owner'", js, 'JS fails closed')

    def test_render_html_roles(self):
        page = '<html lang="ar" dir="rtl"><a href="/pos">P</a><a href="/admin" data-owner>A</a>'
        cases = {lab.Principal('shop', 's', role='cashier', user_id='u'): ('cashier', False),
                 lab.Principal('shop', 's', role='owner', user_id='u'): ('owner', True),
                 lab.Principal('shop', 's'): ('owner', True), lab.Principal('operator'): ('owner', True),
                 lab.Principal('anonymous'): ('none', False), None: ('none', False)}
        for principal, (role, has_owner) in cases.items():
            out = lab.render_html(page, principal)
            self.assertIn(f'data-role="{role}"', out); self.assertEqual('data-owner' in out, has_owner, principal)
            self.assertIn('href="/pos"', out)

    def test_server_enforces_every_owner_action_for_cashier(self):
        _, c = self.cashier()
        gets = ('/api/team', '/api/events', '/simulator/api/summary', '/simulator/api/synced-orders',
                '/simulator/api/received-events', '/api/shops')
        posts = (('/api/web/orders', {'items': [{'sku': 'BRG-001', 'quantity': 1}]}), ('/api/orders/POS-000001/status', {'status': 'cancelled'}),
                 ('/api/pairing-codes', {'intent': 'x.y'}), ('/api/team/invite', {'email': 'y@example.org'}),
                 ('/api/team/remove', {'user_id': 'usr-x'}), ('/api/retry', {}), ('/api/redeliver', {'seq': 1}),
                 ('/api/shops', {'name': 'x'}), ('/api/shops/invite', {'shop_id': self.b['shop_id'], 'email': 'z@example.org'}),
                 ('/api/shops/rotate-token', {'shop_id': self.a['shop_id']}))
        for path in gets:
            self.assertEqual(c.get(path).status_code, 403, path)
        for path, body in posts:
            self.assertEqual(c.post(path, json=body, headers=self.O).status_code, 403, path)
        for page in ('/', '/operator', '/shop', '/admin', '/simulator', '/simulator/'):
            self.assertEqual(c.get(page, follow_redirects=False).headers.get('location'), '/pos', page)
        # Still allowed: selling and reading its own shop's products and orders.
        self.assertEqual(c.post('/api/pos/sales', json={'items': [{'sku': 'BRG-001', 'quantity': 1}], 'payment_method': 'cash'}, headers=self.O).status_code, 200)
        self.assertEqual(len(c.get('/api/orders').json()['orders']), 1)


if __name__ == '__main__':
    unittest.main()
