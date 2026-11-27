import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hosted_server as hosted

lab = hosted.lab


class HostedLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name) / 'source.sqlite3'
        self.receiver = Path(self.tmp.name) / 'receiver.sqlite3'
        self.patches = [patch.object(lab, 'SOURCE_DB', self.source),
                        patch.object(lab, 'RECEIVER_DB', self.receiver),
                        patch.object(lab, 'DATA', Path(self.tmp.name)),
                        patch.object(lab, 'post_signed', hosted.deliver_to_simulator)]
        for p in self.patches:
            p.start()
        lab.init_db()
        self.server = hosted.ThreadingHTTPServer(('127.0.0.1', 0), hosted.HostedHandler)
        self.server.access_user = 'test'
        self.server.access_password = 'temporary-test-password-only'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.auth = 'Basic ' + base64.b64encode(b'test:temporary-test-password-only').decode()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def request(self, path, body=None, auth=True):
        headers = {'Authorization': self.auth} if auth else {}
        data = None if body is None else json.dumps(body).encode()
        return urlopen(Request(self.base + path, data=data, headers=headers), timeout=3)

    def test_health_public_but_pages_and_mutations_protected(self):
        with self.request('/health', auth=False) as r:
            self.assertTrue(json.load(r)['ok'])
        with self.request('/pos', auth=False) as r:
            self.assertTrue(r.url.endswith('/login'))
        for path, body in [('/api/products', None),
                           ('/simulator/api/summary', None), ('/api/pos/sales', {})]:
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as caught:
                    self.request(path, body=body, auth=False)
                self.assertEqual(caught.exception.code, 401)
        with self.request('/simulator/') as r:
            html = r.read().decode()
            self.assertNotIn('127.0.0.1:8765', html)
            self.assertIn('href="/pos"', html)
        with self.request('/') as r:
            self.assertIn('href="/simulator/"', r.read().decode())

    def test_sale_refund_and_restart_use_only_lab_storage(self):
        with self.request('/api/pos/sales', {'items': [{'sku': 'BRG-001', 'quantity': 1}]}) as r:
            order = json.load(r)
        with self.request('/simulator/api/summary') as r:
            self.assertEqual(json.load(r)['revenue'], '4.250')
        with self.request(f"/api/orders/{order['order_id']}/status", {'status': 'refunded'}) as r:
            self.assertEqual(json.load(r)['status'], 'refunded')
        lab.init_db()  # Reinitialization preserves existing volume data.
        with self.request('/simulator/api/summary') as r:
            stats = json.load(r)
        self.assertEqual(stats['invoices'], 1)
        self.assertEqual(stats['revenue'], '0.000')
        with self.assertRaises(ValueError):
            hosted.deliver_to_simulator('https://api.idrak.online/anything', {})

    def test_hosted_startup_requires_separate_secrets(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                hosted.validate_settings()
        with patch.dict(os.environ, {'IDRAK_LAB_ACCESS_PASSWORD': 'a' * 24,
                                     'IDRAK_LAB_WEBHOOK_SECRET': 'b' * 40}, clear=True), \
                patch.object(lab, 'SIGNING_SECRET', 'b' * 40):
            self.assertEqual(hosted.validate_settings()[0], 'lab')
        # The value used for signing must be the validated one, never the public default.
        for effective in (lab.DEFAULT_SIGNING_SECRET, 'c' * 40):
            with patch.dict(os.environ, {'IDRAK_LAB_ACCESS_PASSWORD': 'a' * 24,
                                         'IDRAK_LAB_WEBHOOK_SECRET': 'b' * 40}, clear=True), \
                    patch.object(lab, 'SIGNING_SECRET', effective):
                with self.assertRaises(ValueError):
                    hosted.validate_settings()
        for secret in (lab.DEFAULT_SIGNING_SECRET, 'short-secret'):
            with patch.dict(os.environ, {'IDRAK_LAB_ACCESS_PASSWORD': 'a' * 24,
                                         'IDRAK_LAB_WEBHOOK_SECRET': secret}, clear=True), \
                    patch.object(lab, 'SIGNING_SECRET', secret):
                with self.assertRaises(ValueError):
                    hosted.validate_settings()
        with patch.dict(os.environ, {'IDRAK_LAB_ACCESS_PASSWORD': 'a' * 40,
                                     'IDRAK_LAB_WEBHOOK_SECRET': 'a' * 40}, clear=True):
            with self.assertRaises(ValueError):
                hosted.validate_settings()
