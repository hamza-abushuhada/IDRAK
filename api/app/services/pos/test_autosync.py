"""Automatic sync via signed Lab notifications: authenticity, opt-in flags, isolation, failure handling."""
import json
import os
import time
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.services.pos import autosync, pairing, pipeline

SECRET = 'b' * 64


class AutoSyncTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'IDRAK_LAB_PAIRING_KEY': 'unit-test-pairing-only-' + 'a' * 40,
                                          'IDRAK_CONNECT_ENCRYPTION_KEY': Fernet.generate_key().decode(),
                                          'POS_AUTOSYNC_WEBHOOKS': 'on'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.org, self.shop = str(uuid4()), 'shop-test-a'
        creds = {'shop_id': self.shop, 'org_id': self.org, 'token': 'lc.shop-test-a.' + 's' * 43, 'webhook_secret': SECRET}
        self.binding = {'shop_id': self.shop, 'org_id': self.org,
                        'credentials_encrypted': pairing.cipher().encrypt(json.dumps(creds).encode()).decode()}
        self.conn = {'id': str(uuid4()), 'org_id': self.org, 'provider_code': 'lab_pos', 'account_ref': self.shop, 'status': 'connected',
                     'config': {'paired_lab': True, 'autosync': 'webhook', 'channel': 'in_store'}, 'cursor': {}}

    def body(self, **over):
        b = {'shop_id': self.shop, 'org_id': self.org, 'channel': 'pos', 'ts': int(time.time()), 'nonce': 'n' * 22, **over}
        return json.dumps(b).encode()

    def test_parse_rejects_malformed_old_or_extra(self):
        autosync.parse(self.body())
        for raw in (b'', b'{}', b'x' * 2000, self.body(ts=int(time.time()) - 400), self.body(ts=int(time.time()) + 400),
                    self.body(channel='other'), self.body(nonce='short'), self.body(shop_id='../x'), self.body(org_id='nope'),
                    json.dumps({**json.loads(self.body()), 'extra': 1}).encode(), json.dumps({**json.loads(self.body()), 'ts': '1'}).encode()):
            with self.assertRaises(autosync.Rejected):
                autosync.parse(raw)

    async def test_signature_binding_and_org_must_match(self):
        raw = self.body()
        good = autosync.signature(SECRET, raw)
        with patch.object(db, 'fetchrow', new=AsyncMock(return_value=self.binding)):
            body, binding = await autosync.verify(raw, good)
            self.assertEqual(binding['org_id'], self.org)
            for sig in ('', 'x' * 64, autosync.signature('c' * 64, raw), good[:-1] + ('0' if good[-1] != '0' else '1')):
                with self.assertRaises(autosync.Rejected):
                    await autosync.verify(raw, sig)
            other = self.body(org_id=str(uuid4()))  # a valid shop claiming another organization
            with self.assertRaises(autosync.Rejected):
                await autosync.verify(other, autosync.signature(SECRET, other))
        with patch.object(db, 'fetchrow', new=AsyncMock(return_value=None)):  # unpaired shop
            with self.assertRaises(autosync.Rejected):
                await autosync.verify(raw, good)
        with patch.object(db, 'fetchrow', new=AsyncMock(return_value={**self.binding, 'credentials_encrypted': 'corrupt'})):
            with self.assertRaises(autosync.Rejected):
                await autosync.verify(raw, good)

    async def run_handle(self, conn, global_on=True, recent=0, run=None):
        raw = self.body()
        with patch.dict(os.environ, {'POS_AUTOSYNC_WEBHOOKS': 'on' if global_on else 'off'}), \
                patch.object(db, 'fetchrow', new=AsyncMock(side_effect=[self.binding, conn])) as fetch, \
                patch.object(db, 'fetchval', new=AsyncMock(return_value=recent)), \
                patch.object(db, 'execute', new=AsyncMock()) as write, \
                patch.object(pipeline, 'run_sync', new=run or AsyncMock(return_value={'imported': 1, 'updated': 0})) as sync:
            result = await autosync.handle_lab_notify(raw, autosync.signature(SECRET, raw))
        return result, fetch, write, sync

    async def test_runs_only_when_globally_and_per_connection_enabled(self):
        result, fetch, _, sync = await self.run_handle(self.conn)
        self.assertEqual(result, {'status': 'synced', 'imported': 1, 'updated': 0})
        org, user, conn = sync.await_args.args[:3]
        self.assertEqual((org, user, conn['id'], sync.await_args.kwargs['trigger']), (self.org, None, self.conn['id'], 'webhook'))
        sql, *params = fetch.await_args_list[1].args
        self.assertIn("status='connected'", sql)
        self.assertEqual(params, [self.org, 'lab_pos', self.shop], 'only this org, this shop, this channel')
        for conn, on in ((self.conn, False), ({**self.conn, 'config': {'paired_lab': True}}, True), (None, True)):
            result, _, _, sync = await self.run_handle(conn, global_on=on)
            self.assertEqual(result, {'status': 'ignored'}); sync.assert_not_awaited()

    async def test_rate_limit_and_failure_recorded_without_secrets(self):
        result, _, _, sync = await self.run_handle(self.conn, recent=30)
        self.assertEqual(result, {'status': 'rate_limited'}); sync.assert_not_awaited()
        boom = AsyncMock(side_effect=ValueError('token lc.shop-test-a.SECRET leaked?'))
        result, _, write, _ = await self.run_handle(self.conn, run=boom)
        self.assertEqual(result, {'status': 'error'})
        sql = write.await_args.args[0]
        self.assertIn("status='connected'", sql)
        self.assertNotIn('SECRET', json.dumps([str(a) for a in write.await_args.args]))

    def test_effective_flag_for_ui(self):
        self.assertTrue(autosync.effective(self.conn))
        self.assertFalse(autosync.effective({**self.conn, 'status': 'disconnected'}))
        self.assertFalse(autosync.effective({**self.conn, 'config': {'paired_lab': True, 'auto_sync': True}}))
        with patch.dict(os.environ, {'POS_AUTOSYNC_WEBHOOKS': 'off'}):
            self.assertFalse(autosync.effective(self.conn))

    def test_sync_never_reconnects_a_connection_disconnected_mid_run(self):
        import inspect
        src = inspect.getsource(pipeline.run_sync)
        self.assertIn("case when status='disconnected' then 'disconnected'", src)


class NotifyEndpointTests(unittest.TestCase):
    def setUp(self):
        self.pool = patch.object(db, 'init_pool', new_callable=AsyncMock); self.pool.start()
        app.middleware_stack = None
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close(); self.pool.stop(); app.middleware_stack = None

    def test_no_session_needed_but_signature_is(self):
        with patch.object(autosync, 'handle_lab_notify', new=AsyncMock(side_effect=autosync.Rejected())):
            r = self.client.post('/integrations/lab/notify', content=b'{}')
        self.assertEqual(r.status_code, 401)
        self.assertNotIn('signature', r.text.lower().replace('invalid notification', ''))
        with patch.object(autosync, 'handle_lab_notify', new=AsyncMock(return_value={'status': 'ignored'})):
            r = self.client.post('/integrations/lab/notify', content=b'{}', headers={'X-Idrak-Signature': 'x'})
        self.assertEqual((r.status_code, r.json()), (202, {'status': 'ignored'}))
        self.assertEqual(self.client.post('/integrations/lab/notify', content=b'x' * 5000).status_code, 413)

    def test_public_connection_reports_honest_auto_sync(self):
        from app.routers.integrations import _public
        base = {'id': 'c', 'provider_code': 'lab_pos', 'account_ref': 's', 'status': 'connected', 'cursor': {}}
        with patch.dict(os.environ, {'POS_AUTOSYNC_WEBHOOKS': 'on'}), patch.object(db, 'SERVERLESS', True):
            on = _public({**base, 'config': {'paired_lab': True, 'auto_sync': True, 'autosync': 'webhook'}})
            off = _public({**base, 'config': {'paired_lab': True, 'auto_sync': True}})
            demo = _public({**base, 'provider_code': 'demo', 'config': {'auto_sync': False}})
        self.assertEqual((on['auto_sync_effective'], off['auto_sync_effective'], demo['auto_sync_effective']), (True, False, False))
        self.assertNotIn('autosync', on['config'], 'operator flag is not exposed')
