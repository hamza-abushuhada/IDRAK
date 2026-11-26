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
        # Pairing requires a deployment-specific signing secret (never the public default).
        self.secret = patch.object(lab, 'SIGNING_SECRET', 'signing-test-only-' + 's' * 40)
        self.secret.start()
        self.addCleanup(self.secret.stop)
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

    def test_pairing_refuses_known_or_weak_signing_secret(self):
        # The per-shop webhook key returned to IDRAK derives from SIGNING_SECRET,
        # so a public/short secret must stop both code issue and exchange.
        intent = self.intent()
        code = pairing.issue(self.pa, intent)['code']
        for unsafe in (lab.DEFAULT_SIGNING_SECRET, 'x' * 31):
            with patch.object(lab, 'SIGNING_SECRET', unsafe):
                with self.assertRaises(lab.LabAuthError) as caught:
                    pairing.issue(self.pa, intent)
                self.assertEqual(caught.exception.status, 503)
                with self.assertRaises(lab.LabAuthError) as caught:
                    pairing.exchange(b'{}', 'LabPairing x')
                self.assertEqual(caught.exception.status, 503)
        # A pairing key reused as the signing secret or access password is rejected too.
        for reused in (lab.SIGNING_SECRET, 'access-password-' + 'p' * 30):
            with patch.dict(os.environ, {'IDRAK_LAB_PAIRING_KEY': reused, 'IDRAK_LAB_ACCESS_PASSWORD': 'access-password-' + 'p' * 30}):
                with self.assertRaises(lab.LabAuthError):
                    pairing.key()
        # With a safe secret, the code issued earlier still redeems normally.
        self.assertEqual(self.exchange(code, intent)['shop_id'], self.a['shop_id'])

    def test_serverless_entrypoint_refuses_unsafe_signing_secret(self):
        import importlib
        import sys
        safe = {'IDRAK_LAB_DATABASE_URL': 'postgresql://lab@127.0.0.1/idrak_lab_test_unused',
                'IDRAK_LAB_ISOLATED_DATABASE': 'yes', 'IDRAK_LAB_ACCESS_PASSWORD': 'access-test-' + 'a' * 30}
        saved_connect = lab.connect
        try:
            for secret in ('', lab.DEFAULT_SIGNING_SECRET, 'short'):
                env = {**safe, **({'IDRAK_LAB_WEBHOOK_SECRET': secret} if secret else {})}
                with patch.dict(os.environ, env, clear=True), patch.object(lab, 'SIGNING_SECRET', secret or lab.DEFAULT_SIGNING_SECRET):
                    sys.modules.pop('serverless_app', None)
                    with self.assertRaises(ValueError):
                        importlib.import_module('serverless_app')
            good = 'webhook-test-' + 'w' * 40
            with patch.dict(os.environ, {**safe, 'IDRAK_LAB_WEBHOOK_SECRET': good}, clear=True), patch.object(lab, 'SIGNING_SECRET', good):
                sys.modules.pop('serverless_app', None)
                self.assertTrue(hasattr(importlib.import_module('serverless_app'), 'app'))
        finally:
            sys.modules.pop('serverless_app', None)
            lab.connect = saved_connect  # install() swaps in the PostgreSQL backend
            lab.post_signed = __import__('hosted_server').deliver_to_simulator

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
