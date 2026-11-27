"""Pairing security regressions with temporary SQLite, no remote services."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
import time
from uuid import uuid4
from unittest.mock import patch

from test_multishop import Base, lab
import pairing


class PairingTests(Base):
    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {'IDRAK_LAB_PAIRING_KEY': 'pairing-test-only-' + 'k' * 40})
        self.env.start()
        self.addCleanup(self.env.stop)
        lab.init_db()
        self.a, self.b = lab.create_shop('A'), lab.create_shop('B')
        self.pa = lab.Principal('shop', self.a['shop_id'])
        self.org, self.user = str(uuid4()), str(uuid4())

    def intent(self, org=None):
        data = {'aud': 'idrak-lab-pairing-v1', 'org': org or self.org, 'user': self.user,
                'nonce': str(uuid4()), 'exp': int(time.time()) + 300}
        value = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        return value + '.' + hmac.new(pairing.key(), b'intent:' + value.encode(), hashlib.sha256).hexdigest()

    def exchange(self, code, intent):
        raw = json.dumps({'code': code, 'intent': intent, 'timestamp': int(time.time())}).encode()
        return pairing.exchange(raw, pairing.service_signature(raw))

    def test_single_use_concurrent_redemption_and_hash_only_storage(self):
        intent = self.intent()
        code = pairing.issue(self.pa, intent)['code']
        with lab.connect(lab.SOURCE_DB) as db:
            row = dict(db.execute('SELECT * FROM lab_pairing_codes').fetchone())
        self.assertNotIn(code, json.dumps(row))
        def redeem(_):
            try:
                self.exchange(code, intent)
                return 200
            except lab.LabAuthError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(redeem, range(2))), [200, 409])
        with self.assertRaises(lab.LabAuthError) as caught:
            pairing.issue(self.pa, self.intent(str(uuid4())))
        self.assertEqual(caught.exception.status, 409)

    def test_stolen_code_wrong_intent_and_expired_code(self):
        intent = self.intent()
        code = pairing.issue(self.pa, intent)['code']
        with self.assertRaises(lab.LabAuthError):
            self.exchange(code, self.intent(str(uuid4())))
        # The failed theft did not consume the rightful owner's code.
        result = self.exchange(code, intent)
        self.assertEqual(result['shop_id'], self.a['shop_id'])
        self.assertEqual(result['org_id'], self.org)
        newer = self.intent()
        code = pairing.issue(self.pa, newer)['code']
        with lab.connect(lab.SOURCE_DB) as db:
            db.execute('UPDATE lab_pairing_codes SET expires_at=0')
        with self.assertRaises(lab.LabAuthError):
            self.exchange(code, newer)

    def test_only_shop_can_issue_and_service_must_authenticate(self):
        intent = self.intent()
        for kind in ('operator', 'anonymous', 'local', 'integration'):
            with self.assertRaises(lab.LabAuthError):
                pairing.issue(lab.Principal(kind, self.a['shop_id']), intent)
        with self.assertRaises(lab.LabAuthError):
            pairing.issue(self.pa, intent + 'x')
        with self.assertRaises(lab.LabAuthError):
            pairing.exchange(b'{}', 'Bearer ' + self.a['token'])
        with patch.dict(os.environ, {'IDRAK_LAB_PAIRING_KEY': ''}):
            with self.assertRaises(lab.LabAuthError) as caught:
                pairing.issue(self.pa, intent)
            self.assertEqual(caught.exception.status, 503)

    def test_integration_credential_is_read_only_and_scoped(self):
        intent = self.intent()
        result = self.exchange(pairing.issue(self.pa, intent)['code'], intent)
        authorization = 'Bearer ' + result['token']
        for path, method in (('/api/products', 'GET'), ('/api/shops', 'GET'), ('/api/pos/sales', 'POST'),
                             ('/pos', 'GET'), ('/api/pairing-codes', 'POST')):
            self.assertIsNone(lab.authenticate(authorization, path, method, 'operator'))
        principal = lab.authenticate(authorization, '/api/pos/events', 'GET', 'operator')
        self.assertEqual(principal.shop_id, self.a['shop_id'])
        with self.assertRaises(lab.LabAuthError):
            lab.effective_shop(principal, self.b['shop_id'])
        with lab.connect(lab.SOURCE_DB) as db:
            db.execute('UPDATE shops SET disabled=1 WHERE shop_id=?', (self.a['shop_id'],))
        self.assertIsNone(lab.authenticate(authorization, '/api/pos/events', 'GET', 'operator'))
