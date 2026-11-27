"""Lab -> IDRAK sale notifications: only paired shops, only the configured HTTPS address,
signed with the shop's key, retried once, and never able to break a sale."""
import hashlib
import hmac
import json
import os
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from test_multishop import Base, lab
import idrak_notify

URL = 'https://api.idrak.example.com/integrations/lab/notify'


class Resp:
    def __init__(self, status): self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


class Opener:
    def __init__(self, *outcomes):
        self.outcomes, self.requests = list(outcomes), []
    def open(self, request, timeout=None):
        self.requests.append(request)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception): raise out
        return Resp(out)


class NotifyTests(Base):
    def setUp(self):
        super().setUp()
        self.secret = patch.object(lab, 'SIGNING_SECRET', 'signing-test-only-' + 's' * 40); self.secret.start(); self.addCleanup(self.secret.stop)
        self.env = patch.dict(os.environ, {'IDRAK_CONNECT_NOTIFY_URL': URL}); self.env.start(); self.addCleanup(self.env.stop)
        lab.init_db()
        import pairing
        with lab.connect(lab.SOURCE_DB) as db:
            db.executescript(pairing.DDL)
        self.a, self.b = lab.create_shop('A'), lab.create_shop('B')
        with lab.connect(lab.SOURCE_DB) as db:
            db.execute('INSERT INTO lab_bindings(shop_id,org_id,integration_token_hash,created_at) VALUES(?,?,?,?)',
                       (self.a['shop_id'], '11111111-1111-1111-1111-111111111111', 'x' * 64, lab.iso_now()))

    def test_signed_body_for_paired_shop_only(self):
        op = Opener(202)
        self.assertEqual(idrak_notify.notify(self.a['shop_id'], 'pos', opener=op), 202)
        req = op.requests[0]
        body = json.loads(req.data)
        self.assertEqual((req.full_url, body['shop_id'], body['org_id'], body['channel']), (URL, self.a['shop_id'], '11111111-1111-1111-1111-111111111111', 'pos'))
        self.assertEqual(set(body), {'shop_id', 'org_id', 'channel', 'ts', 'nonce'}, 'no sales data in the signal')
        expected = hmac.new(lab.shop_secret(self.a['shop_id']).encode(), b'idrak-lab-notify:' + req.data, hashlib.sha256).hexdigest()
        self.assertEqual(req.get_header('X-idrak-signature'), expected)
        op_b = Opener(202)
        self.assertIsNone(idrak_notify.notify(self.b['shop_id'], 'pos', opener=op_b)); self.assertEqual(op_b.requests, [], 'unpaired shop never notifies')

    def test_only_a_valid_https_notify_address(self):
        for bad in ('', 'http://api.idrak.example.com/integrations/lab/notify', 'https://api.idrak.example.com/other',
                    'https://user@api.idrak.example.com/integrations/lab/notify', 'https://api.idrak.example.com:8443/integrations/lab/notify',
                    'https://api.idrak.example.com/integrations/lab/notify?x=1'):
            with patch.dict(os.environ, {'IDRAK_CONNECT_NOTIFY_URL': bad}):
                op = Opener(202)
                self.assertIsNone(idrak_notify.notify(self.a['shop_id'], 'pos', opener=op)); self.assertEqual(op.requests, [])

    def test_retry_once_on_server_or_network_error_never_on_rejection(self):
        with patch.object(idrak_notify.time, 'sleep'):
            op = Opener(HTTPError(URL, 503, 'x', {}, None), 202)
            self.assertEqual(idrak_notify.notify(self.a['shop_id'], 'web', opener=op), 202); self.assertEqual(len(op.requests), 2)
            op = Opener(URLError('down'), URLError('down'))
            self.assertEqual(idrak_notify.notify(self.a['shop_id'], 'web', opener=op), 0)
            op = Opener(HTTPError(URL, 401, 'x', {}, None), 202)
            self.assertEqual(idrak_notify.notify(self.a['shop_id'], 'web', opener=op), 401); self.assertEqual(len(op.requests), 1)

    def test_a_sale_never_fails_because_of_idrak(self):
        with patch.object(idrak_notify, 'build_opener', side_effect=RuntimeError('boom')):
            order = lab.create_order(self.a['shop_id'], 'pos', {'items': [{'sku': 'FRY-001', 'quantity': 1}], 'payment_method': 'cash'})
        self.assertTrue(order['order_id'])
        calls = []
        with patch.object(idrak_notify, 'notify', side_effect=lambda s, c: calls.append((s, c))):
            lab.create_order(self.a['shop_id'], 'web', {'items': [{'sku': 'FRY-001', 'quantity': 1}], 'payment_method': 'cash_on_delivery', 'customer': 'x'})
        self.assertEqual(calls, [(self.a['shop_id'], 'web')], 'notified after the sale committed')
