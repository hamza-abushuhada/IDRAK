"""Browser sessions and two-shop UI/API isolation, using temporary SQLite only."""
import base64
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demo_server as lab
import browser_auth
import postgres_backend as pg
from fastapi.testclient import TestClient


class BrowserLoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch.object(lab, 'SOURCE_DB', root / 's.db'),
                        patch.object(lab, 'RECEIVER_DB', root / 'r.db'), patch.object(lab, 'DATA', root),
                        patch.object(pg, 'install'), patch.dict(os.environ, {
                            'IDRAK_LAB_ACCESS_PASSWORD': 'test-operator-password-long',
                            'IDRAK_LAB_WEBHOOK_SECRET': 'test-signing-secret-long-and-distinct'})]
        for p in self.patches:
            p.start()
        self.old_delivery = lab.post_signed
        lab.init_db()
        spec = importlib.util.spec_from_file_location('browser_test_app', Path(pg.__file__).with_name('serverless_app.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.a, self.b = lab.create_shop('Shop A'), lab.create_shop('Shop B')
        self.ca = TestClient(module.app, base_url='https://testserver')
        self.cb = TestClient(module.app, base_url='https://testserver')
        self.origin = {'Origin': 'https://testserver'}

    def tearDown(self):
        self.ca.close(); self.cb.close()
        lab.post_signed = self.old_delivery
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def login(self, client, shop):
        response = client.post('/auth/login', json={'token': shop['token']}, headers=self.origin)
        self.assertEqual(response.status_code, 200)
        cookie = response.headers['set-cookie']
        for flag in ('HttpOnly', 'Secure', 'SameSite=Strict'):
            self.assertIn(flag, cookie)
        self.assertNotIn(shop['token'].split('.')[1], cookie)
        return response

    def test_two_users_pages_and_api_isolation(self):
        self.assertEqual(self.ca.get('/pos', follow_redirects=False).headers['location'], '/login')
        self.login(self.ca, self.a); self.login(self.cb, self.b)
        for client, name in ((self.ca, 'Shop A'), (self.cb, 'Shop B')):
            for page in ('/pos', '/shop', '/admin'):
                self.assertEqual(client.get(page).status_code, 200)
            self.assertEqual(client.get('/auth/session').json()['name'], name)
            self.assertEqual(client.get('/api/shops').status_code, 403)
        sale = self.ca.post('/api/pos/sales', json={'shop_id': self.b['shop_id'], 'items': [{'sku': 'BRG-001', 'quantity': 2}]}, headers=self.origin)
        self.assertEqual(sale.status_code, 200)
        self.assertEqual(self.cb.get('/api/orders').json()['orders'], [])
        self.assertEqual(len(self.ca.get('/api/orders?shop_id=' + self.b['shop_id']).json()['orders']), 1)
        for client, stock in ((self.ca, 58), (self.cb, 60)):
            products = client.get('/api/products').json()['products']
            self.assertEqual(next(p['stock'] for p in products if p['sku'] == 'BRG-001'), stock)
        self.assertEqual(self.cb.post('/api/orders/POS-000001/status', json={'status': 'refunded'}, headers=self.origin).status_code, 400)
        self.assertEqual(self.ca.get('/api/products', headers={'X-Lab-Shop': self.b['shop_id']}).status_code, 403)
        self.assertEqual(self.cb.get('/simulator/api/summary').json()['invoices'], 0)
        self.assertEqual(lab.source_get(lab.LEGACY_SHOP, '/api/orders', {})['orders'], [])

    def test_expiry_rotation_disable_tampering_and_logout(self):
        self.login(self.ca, self.a)
        original = self.ca.cookies.get(browser_auth.COOKIE)
        with patch.object(browser_auth.time, 'time', return_value=time.time() + browser_auth.TTL + 1):
            self.assertEqual(self.ca.get('/api/products').status_code, 401)
        self.ca.cookies.set(browser_auth.COOKIE, original[:-1] + ('0' if original[-1] != '0' else '1'))
        self.assertEqual(self.ca.get('/api/products').status_code, 401)
        self.ca.cookies.clear(); self.login(self.ca, self.a)
        lab.rotate_token(self.a['shop_id'])
        basic = 'Basic ' + base64.b64encode(b'lab:test-operator-password-long').decode()
        self.assertEqual(self.ca.get('/api/products', headers={'Authorization': basic}).status_code, 401)
        self.login(self.cb, self.b)
        self.assertEqual(self.cb.post('/auth/logout', json={}, headers=self.origin).status_code, 200)
        self.assertEqual(self.cb.get('/api/products').status_code, 401)
        self.login(self.cb, self.b)
        with lab.connect(lab.SOURCE_DB) as db:
            db.execute('UPDATE shops SET disabled=1 WHERE shop_id=?', (self.b['shop_id'],))
        self.assertEqual(self.cb.get('/api/products').status_code, 401)

    def test_login_csrf_and_legacy_operator(self):
        self.assertEqual(self.ca.post('/auth/login', json={'token': self.a['token']}, headers={'Origin': 'https://evil.invalid'}).status_code, 403)
        self.assertEqual(self.ca.post('/auth/login', json={'token': self.a['token']}).status_code, 403)
        self.assertEqual(self.ca.post('/auth/login', json={'token': 'bad'}, headers=self.origin).status_code, 401)
        basic = 'Basic ' + base64.b64encode(b'lab:test-operator-password-long').decode()
        self.assertEqual(self.ca.get('/operator', headers={'Authorization': basic}).status_code, 200)
        self.assertEqual(self.ca.get('/api/products', headers={'Authorization': basic}).status_code, 200)
        self.login(self.ca, self.a)
        self.assertEqual(self.ca.post('/api/pos/sales', json={}, headers={'Origin': 'https://evil.invalid'}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
