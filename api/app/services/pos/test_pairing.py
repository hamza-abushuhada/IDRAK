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
        self.conn = {'provider_code': 'lab_pos', 'account_ref': 'shop-test-a', 'config': {'paired_lab': True, 'base_url': pairing.LAB_ORIGIN}}

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
        # A connection paired against another Lab is never contacted with these credentials.
        for stored in ('http://evil.invalid', 'https://other-lab.example.org', None):
            with self.assertRaisesRegex(ValueError, 'origin changed'):
                pipeline.build_adapter({**self.conn, 'config': {'paired_lab': True, 'base_url': stored},
                                        '_lab_credentials': self.credentials}, self.org)
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


class LabOriginTests(unittest.IsolatedAsyncioTestCase):
    STAGING = 'https://idrak-lab-staging.vercel.app'

    def env(self, **values):
        base = {'IDRAK_LAB_ORIGIN': '', 'IDRAK_LAB_ALLOWED_ORIGINS': ''}
        return patch.dict(os.environ, {**base, **values})

    def test_default_is_published_lab(self):
        with self.env():
            self.assertEqual(pairing.lab_origin(), 'https://idrak-connect-lab.vercel.app')
        with self.env(IDRAK_LAB_ORIGIN='https://idrak-connect-lab.vercel.app'):
            self.assertEqual(pairing.lab_origin(), pairing.LAB_ORIGIN)

    def test_staging_origin_requires_explicit_allowlist(self):
        with self.env(IDRAK_LAB_ORIGIN=self.STAGING):
            with self.assertRaises(ValueError):
                pairing.lab_origin()
        with self.env(IDRAK_LAB_ORIGIN=self.STAGING, IDRAK_LAB_ALLOWED_ORIGINS='https://a.example.org, ' + self.STAGING):
            self.assertEqual(pairing.lab_origin(), self.STAGING)
        with self.env(IDRAK_LAB_ORIGIN=self.STAGING + ':443/', IDRAK_LAB_ALLOWED_ORIGINS=self.STAGING):
            self.assertEqual(pairing.lab_origin(), self.STAGING)
        # No wildcard/suffix matching: a sibling host is not allowed.
        with self.env(IDRAK_LAB_ORIGIN='https://evil-idrak-lab-staging.vercel.app', IDRAK_LAB_ALLOWED_ORIGINS=self.STAGING):
            with self.assertRaises(ValueError):
                pairing.lab_origin()

    def test_unsafe_origins_rejected_even_when_allowlisted(self):
        bad = ['http://idrak-lab-staging.vercel.app', 'https://idrak-lab-staging.vercel.app/path',
               'https://idrak-lab-staging.vercel.app/?x=1', 'https://idrak-lab-staging.vercel.app#f',
               'https://user:pw@idrak-lab-staging.vercel.app', 'https://idrak-lab-staging.vercel.app:8443',
               'https://127.0.0.1', 'https://[::1]', 'https://10.0.0.5', 'https://169.254.169.254',
               'https://127.1', 'https://2130706433', 'https://localhost', 'https://lab.localhost',
               'https://metadata.internal', 'https://lab.local', ' https://idrak-lab-staging.vercel.app',
               'https://idrak-lab-staging.vercel.app@evil.example.org', 'file:///etc/passwd', 'ftp://x.example.org',
               'https://exa_mple.org', 'https://-bad.example.org', 'javascript:alert(1)']
        for value in bad:
            with self.env(IDRAK_LAB_ORIGIN=value, IDRAK_LAB_ALLOWED_ORIGINS=value):
                with self.assertRaises(ValueError, msg=value):
                    pairing.lab_origin()
        # One bad allowlist entry fails closed instead of being silently skipped.
        with self.env(IDRAK_LAB_ORIGIN=self.STAGING, IDRAK_LAB_ALLOWED_ORIGINS=self.STAGING + ',http://127.0.0.1'):
            with self.assertRaises(ValueError):
                pairing.lab_origin()

    async def test_misconfigured_origin_fails_closed_without_network(self):
        keys = {'IDRAK_LAB_PAIRING_KEY': 'unit-test-pairing-only-' + 'a' * 40,
                'IDRAK_CONNECT_ENCRYPTION_KEY': Fernet.generate_key().decode()}
        with self.env(IDRAK_LAB_ORIGIN='https://169.254.169.254', **keys),                 patch.object(pairing.httpx, 'AsyncClient') as client:
            with self.assertRaises(HTTPException) as caught:
                pairing.new_intent(str(uuid4()), str(uuid4()))
            self.assertEqual(caught.exception.status_code, 503)
            client.assert_not_called()

    async def test_redeem_contacts_and_binds_configured_origin(self):
        org, user = str(uuid4()), str(uuid4())
        keys = {'IDRAK_LAB_PAIRING_KEY': 'unit-test-pairing-only-' + 'a' * 40,
                'IDRAK_CONNECT_ENCRYPTION_KEY': Fernet.generate_key().decode()}
        with self.env(IDRAK_LAB_ORIGIN=self.STAGING, IDRAK_LAB_ALLOWED_ORIGINS=self.STAGING, **keys):
            intent = pairing.new_intent(org, user)['intent']
            seen = []

            class Client:
                def __init__(self, **kwargs):
                    assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
                async def __aenter__(self):
                    return self
                async def __aexit__(self, *exc):
                    return False
                async def post(self, url, **kwargs):
                    seen.append(url)
                    raise pairing.httpx.ConnectError('offline')

            from app.auth import Ctx, User
            with patch.object(pairing.httpx, 'AsyncClient', Client):
                with self.assertRaises(HTTPException) as caught:
                    await pairing.redeem('c' * 43, intent, Ctx(User(user, '', None, False), org, 'manager'))
            self.assertEqual(caught.exception.status_code, 502)
            self.assertEqual(seen, [self.STAGING + '/service/pairing/exchange'])


class LegacyLabUrlGuardTests(unittest.IsolatedAsyncioTestCase):
    PUBLISHED = 'https://idrak-connect-lab.vercel.app'
    STAGING = 'https://idrak-connect-lab-staging.vercel.app'

    def staging_env(self, **extra):
        return patch.dict(os.environ, {'IDRAK_LAB_ORIGIN': self.STAGING, 'IDRAK_LAB_ALLOWED_ORIGINS': self.STAGING,
                                       'VERCEL': '', **extra})

    def test_loopback_only_for_local_dev(self):
        with patch.dict(os.environ, {'VERCEL': '', 'IDRAK_LAB_ORIGIN': ''}):
            self.assertEqual(pairing.legacy_lab_base_url(None), 'http://127.0.0.1:8765')
            self.assertEqual(pairing.legacy_lab_base_url('http://localhost:8765/'), 'http://localhost:8765')
        with patch.dict(os.environ, {'VERCEL': '1'}):
            for url in (None, 'http://127.0.0.1:8765', 'http://localhost:9000'):
                with self.assertRaises(ValueError):
                    pairing.legacy_lab_base_url(url)

    def test_published_lab_blocked_when_other_origin_configured(self):
        with self.staging_env():
            with self.assertRaises(ValueError):
                pairing.legacy_lab_base_url(self.PUBLISHED)
            self.assertEqual(pairing.legacy_lab_base_url(self.STAGING + '/'), self.STAGING)

    def test_arbitrary_and_internal_targets_blocked(self):
        with self.staging_env():
            for url in ('https://evil.example.org', 'http://169.254.169.254', 'https://10.0.0.5',
                        'http://127.0.0.1@evil.example.org', 'http://127.0.0.1:8765/path', 'http://[::1]:8765',
                        'https://' + self.STAGING[8:] + ':8443', 'file:///etc/passwd', 'gopher://127.0.0.1', 42):
                with self.assertRaises(ValueError, msg=str(url)):
                    pairing.legacy_lab_base_url(url)

    def test_stored_published_url_never_contacted(self):
        conn = {'provider_code': 'lab_pos', 'account_ref': 'default', 'status': 'connected',
                'config': {'base_url': self.PUBLISHED}}
        with self.staging_env(), patch('urllib.request.urlopen') as urlopen:
            with self.assertRaisesRegex(ValueError, 'not allowed'):
                pipeline.build_adapter(conn, str(uuid4()))
            urlopen.assert_not_called()

    async def test_pipeline_test_connection_skips_disconnected_and_blocked(self):
        conn = {'provider_code': 'lab_pos', 'account_ref': 'default', 'config': {'base_url': self.PUBLISHED}}
        with self.staging_env(), patch('urllib.request.urlopen') as urlopen:
            r = await pipeline.test_connection({**conn, 'status': 'disconnected'}, str(uuid4()))
            self.assertFalse(r['ok']); self.assertEqual(r['checks'][0]['name'], 'connection')
            r = await pipeline.test_connection({**conn, 'status': 'connected'}, str(uuid4()))
            self.assertFalse(r['ok']); self.assertIn('not allowed', r['checks'][0]['detail'])
            urlopen.assert_not_called()
