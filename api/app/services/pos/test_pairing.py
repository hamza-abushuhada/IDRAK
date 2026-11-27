"""Pairing and credential security tests without network/database access."""
import json
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from urllib.error import HTTPError

from cryptography.fernet import Fernet
from fastapi import HTTPException

from app import db
from app.services.pos import pairing, pipeline


class PairingSecurityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'IDRAK_LAB_PAIRING_KEY': 'unit-test-pairing-only-' + 'a' * 40,
                                          'IDRAK_CONNECT_ENCRYPTION_KEY': Fernet.generate_key().decode()})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.org, self.user = str(uuid4()), str(uuid4())
        self.credentials = {'shop_id': 'shop-test-a', 'org_id': self.org,
                            'token': 'lc.shop-test-a.' + 's' * 43, 'webhook_secret': 'b' * 64}
        self.conn = {'provider_code': 'lab_pos', 'account_ref': 'shop-test-a', 'config': {'paired_lab': True, 'base_url': 'http://evil.invalid'}}

    def test_intent_bound_to_user_organization_and_expiry(self):
        value = pairing.new_intent(self.org, self.user)['intent']
        pairing.validate_intent(value, self.org, self.user)
        for org, user in ((str(uuid4()), self.user), (self.org, str(uuid4()))):
            with self.assertRaises(HTTPException):
                pairing.validate_intent(value, org, user)
        with patch.object(pairing.time, 'time', return_value=10**12):
            with self.assertRaises(HTTPException):
                pairing.validate_intent(value, self.org, self.user)
        with patch.dict(os.environ, {'IDRAK_LAB_PAIRING_KEY': ''}):
            with self.assertRaises(HTTPException) as caught:
                pairing.new_intent(self.org, self.user)
            self.assertEqual(caught.exception.status_code, 503)

    async def test_encryption_and_credential_context_fail_closed(self):
        encrypted = pairing.cipher().encrypt(json.dumps(self.credentials).encode()).decode()
        self.assertNotIn(self.credentials['token'], encrypted)
        with patch.object(db, 'fetchrow', new=AsyncMock(return_value={'credentials_encrypted': encrypted})) as fetch:
            self.assertEqual(await pairing.load_credentials(self.conn, self.org), self.credentials)
            self.assertEqual(fetch.call_args.args[1:], ('shop-test-a', self.org))
            for conn, org in ((self.conn, str(uuid4())), ({**self.conn, 'account_ref': 'shop-other'}, self.org)):
                with self.assertRaises(ValueError):
                    await pairing.load_credentials(conn, org)
        with patch.object(db, 'fetchrow', new=AsyncMock(return_value={'credentials_encrypted': 'corrupted'})):
            with self.assertRaisesRegex(ValueError, '^Paired Lab credentials unavailable$'):
                await pairing.load_credentials(self.conn, self.org)

    def test_fixed_origin_redirect_refusal_and_scoped_webhook(self):
        adp = pipeline.build_adapter({**self.conn, '_lab_credentials': self.credentials}, self.org)
        self.assertEqual(adp.base_url, pairing.LAB_ORIGIN)
        with self.assertRaises(ValueError):
            pipeline.build_adapter({**self.conn, '_lab_credentials': self.credentials}, str(uuid4()))
        opener = Mock()
        opener.open.side_effect = HTTPError('https://evil.invalid/' + self.credentials['token'], 302, 'redirect', {}, None)
        with patch('urllib.request.build_opener', return_value=opener) as build:
            with self.assertRaisesRegex(ValueError, '^Paired Lab event source unavailable$'):
                adp._get(0)
            handlers = build.call_args.args
            self.assertIsNone(handlers[1].redirect_request(None, None, None, None, None, None))
        for source in ({'account_id': 'shop-other', 'channel': 'pos', 'system': 'idrak-lab-pos'},
                       {'account_id': 'shop-test-a', 'channel': 'web', 'system': 'idrak-lab-store'}):
            body = json.dumps({'source': source}).encode()
            self.assertFalse(adp.verify_webhook({'X-Idrak-Signature': adp.signature_for(body)}, body))
