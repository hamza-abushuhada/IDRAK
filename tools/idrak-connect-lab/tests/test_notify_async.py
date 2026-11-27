"""Store orders never wait for IDRAK: notifications are sent after the response, API-key
notifications are bounded (5 s, one attempt), one subscription per store, approval-link
notifications unchanged. Temporary SQLite only; the network is replaced by a fake opener."""
import asyncio
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demo_server as lab
import postgres_backend as pg
import idrak_notify
import api_keys

SECRET = 'test-signing-secret-long-and-distinct'
PASSWORD = 'test-operator-password-long'
NOTIFY = 'https://api.idrak.example.com/integrations/lab/notify'


class Opener:
    """Fake network: records each call (url, timeout, time); behavior per test."""
    def __init__(self, behavior='ok', delay=0.0):
        self.calls, self.behavior, self.delay = [], behavior, delay

    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout, time.monotonic()))
        if self.delay:
            time.sleep(self.delay)
        if self.behavior == 'down':
            raise URLError('connection refused')
        if self.behavior == 'timeout':
            raise TimeoutError()
        if self.behavior == '503':
            raise HTTPError(request.full_url, 503, 'unavailable', {}, None)
        return type('R', (), {'status': 202, '__enter__': lambda s: s, '__exit__': lambda s, *a: None})()


class NotifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch.object(lab, 'SOURCE_DB', root / 's.db'), patch.object(lab, 'RECEIVER_DB', root / 'r.db'),
                        patch.object(lab, 'DATA', root), patch.object(lab, 'SIGNING_SECRET', SECRET), patch.object(pg, 'install'),
                        patch.object(idrak_notify.time, 'sleep', lambda s: None),
                        patch.dict(os.environ, {'IDRAK_LAB_ACCESS_PASSWORD': PASSWORD, 'IDRAK_LAB_WEBHOOK_SECRET': SECRET,
                                                'IDRAK_CONNECT_NOTIFY_URL': NOTIFY})]
        for p in self.patches:
            p.start()
        self.old_delivery = lab.post_signed
        lab.post_signed = lambda url, payload: 200  # local simulator receiver not under test
        lab.init_db()
        spec = importlib.util.spec_from_file_location('notify_test_app', Path(pg.__file__).with_name('serverless_app.py'))
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.shop = lab.create_shop('Store')['shop_id']
        self.other = lab.create_shop('Other')['shop_id']
        self.owner = lab.Principal('shop', self.shop, role='owner', user_id='o')

    def tearDown(self):
        lab.post_signed = self.old_delivery
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def subscribe(self, shop=None, owner=None):
        key = lab.handle_source_post(owner or self.owner, None, '/api/keys', {'name': 'IDRAK'})['key']
        p = api_keys.principal('Bearer ' + key, '/api/v1/notifications', 'POST')
        api_keys.notifications(p, {'enabled': True})
        return key, p.user_id

    def pair(self):
        with lab.connect(lab.SOURCE_DB) as db:  # an approval-link (paired) shop, as created by pairing.exchange
            db.execute('INSERT INTO lab_bindings(shop_id,org_id,integration_token_hash,created_at) VALUES(?,?,?,?)',
                       (self.shop, '11111111-1111-1111-1111-111111111111', '0' * 64, lab.iso_now()))

    def order_via_web_entrypoint(self, opener):
        """Raw ASGI call to the serverless app: records when the response body is sent."""
        auth = 'Basic ' + base64.b64encode(f'lab:{PASSWORD}'.encode()).decode()
        body = json.dumps({'items': [{'sku': 'BRG-001', 'quantity': 1}], 'payment_method': 'demo_card'}).encode()
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'POST', 'scheme': 'https',
                 'path': '/api/web/orders', 'raw_path': b'/api/web/orders', 'query_string': b'', 'root_path': '',
                 'server': ('testserver', 443), 'client': ('127.0.0.1', 5000),
                 'headers': [(b'host', b'testserver'), (b'authorization', auth.encode()), (b'x-lab-shop', self.shop.encode()),
                             (b'origin', b'https://testserver'), (b'content-type', b'application/json')]}
        events = {'status': None, 'body': b'', 'sent_at': None}
        start = time.monotonic()

        async def receive():
            return {'type': 'http.request', 'body': body, 'more_body': False}

        async def send(message):
            if message['type'] == 'http.response.start':
                events['status'] = message['status']
            elif message['type'] == 'http.response.body':
                events['body'] += message.get('body', b'')
                if not message.get('more_body') and events['sent_at'] is None:
                    events['sent_at'] = time.monotonic()
        with patch.object(idrak_notify, 'build_opener', lambda *a: opener):
            asyncio.run(self.mod.app(scope, receive, send))
        return events, start

    def orders(self):
        with lab.connect(lab.SOURCE_DB) as db:
            return [r['external_id'] for r in db.execute('SELECT external_id FROM orders WHERE shop_id=? ORDER BY id', (self.shop,))]

    def test_slow_idrak_does_not_delay_the_order_response(self):
        self.subscribe(); self.pair()
        opener = Opener(delay=1.5)  # IDRAK answers slowly
        ev, start = self.order_via_web_entrypoint(opener)
        self.assertEqual(ev['status'], 200)
        self.assertEqual(json.loads(ev['body'])['status'], 'completed')
        self.assertLess(ev['sent_at'] - start, 1.0, 'the customer gets the order confirmation without waiting for IDRAK')
        self.assertEqual(len(opener.calls), 2, 'store-key + approval-link notifications were still sent')
        self.assertTrue(all(t >= ev['sent_at'] for _, _, t in opener.calls), 'notifications start only after the response is sent')
        self.assertEqual(self.orders(), ['WEB-000001'])

    def test_idrak_down_never_fails_a_saved_sale_and_recovers(self):
        key, kid = self.subscribe()
        down = Opener('down')
        ev, _ = self.order_via_web_entrypoint(down)
        self.assertEqual((ev['status'], self.orders()), (200, ['WEB-000001']))
        self.assertEqual([(u.rsplit('/', 2)[-2:], t) for u, t, _ in down.calls], [(['store', 'notify'], 5)], 'one attempt, 5 s cap')
        for behavior in ('timeout', '503'):
            ev, _ = self.order_via_web_entrypoint(Opener(behavior))
            self.assertEqual(ev['status'], 200)
        up = Opener('ok')
        ev, _ = self.order_via_web_entrypoint(up)   # IDRAK is back: the next change notifies again
        self.assertEqual((ev['status'], len(up.calls)), (200, 1))
        self.assertEqual(self.orders(), ['WEB-000001', 'WEB-000002', 'WEB-000003', 'WEB-000004'])
        self.assertEqual(api_keys.subscribers(self.shop), [kid], 'a failed notification never drops the subscription')

    def test_store_key_bounds_and_paired_behavior_unchanged(self):
        _, kid = self.subscribe(); self.pair()
        o = Opener('timeout')
        self.assertEqual(idrak_notify.notify_store_keys(self.shop, o), [0])
        self.assertEqual([t for _, t, _ in o.calls], [5])
        o = Opener('503')
        self.assertEqual(idrak_notify.notify(self.shop, 'pos', o), 503)   # approval-link path
        self.assertEqual([t for _, t, _ in o.calls], [20, 20], 'paired notifications keep 20 s and one retry')

    def test_one_active_subscription_per_store(self):
        _, k1 = self.subscribe()
        _, k2 = self.subscribe()
        self.assertEqual(api_keys.subscribers(self.shop), [k2], 're-linking with another key moves the subscription')
        other_owner = lab.Principal('shop', self.other, role='owner', user_id='x')
        _, k3 = self.subscribe(owner=other_owner)
        self.assertEqual((api_keys.subscribers(self.shop), api_keys.subscribers(self.other)), ([k2], [k3]), 'stores are independent')
        with lab.connect(lab.SOURCE_DB) as db:
            n = db.execute('SELECT count(*) FROM lab_api_keys WHERE shop_id=? AND notify=1', (self.shop,)).fetchone()[0]
        self.assertEqual(n, 1)
        rotated = lab.handle_source_post(self.owner, None, '/api/keys/rotate', {'key_id': k2})
        self.assertEqual(api_keys.subscribers(self.shop), [], 'rotation stops notifications until IDRAK re-links with the new key')
        p = api_keys.principal('Bearer ' + rotated['key'], '/api/v1/notifications', 'POST')
        api_keys.notifications(p, {'enabled': True})
        self.assertEqual(api_keys.subscribers(self.shop), [rotated['key_id']])

    def test_local_runner_without_deferral_still_sends_inline(self):
        self.assertFalse(idrak_notify.defer(self.shop, 'web'))
        q = idrak_notify.start_deferring()
        self.assertTrue(idrak_notify.defer(self.shop, 'web'))
        self.assertTrue(idrak_notify.defer(self.shop, 'web'))
        self.assertEqual(q, [(self.shop, 'web')], 'one notification per shop/channel per request')
        idrak_notify._DEFERRED.set(None)
