"""Opt-in pairing integration test: two NEW localhost idrak_lab_test_* databases.

No dotenv credentials, remote hosts, application lifespan, deployment or production
migration runner is used. Initializes a disposable baseline plus additive migrations.
Run with IDRAK_PAIRING_TEST_DATABASE_URL and IDRAK_LAB_TEST_DATABASE_URL.
"""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import secrets
import re
import sys
import time
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient
import httpx

ROOT = Path(__file__).resolve().parents[2]


def local_url(name):
    value = os.environ.get(name, '')
    url = urlsplit(value)
    if url.scheme not in ('postgres', 'postgresql') or url.hostname not in ('localhost', '127.0.0.1') or not re.fullmatch(r'/idrak_lab_test_[a-zA-Z0-9_]+', url.path) or url.query or url.fragment:
        raise SystemExit('Only new localhost idrak_lab_test_* databases are permitted')
    return value


async def main():
    api_url = local_url('IDRAK_PAIRING_TEST_DATABASE_URL')
    lab_url = local_url('IDRAK_LAB_TEST_DATABASE_URL')
    assert api_url != lab_url
    for name in ('SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_JWT_SECRET', 'VERCEL_TOKEN'):
        os.environ.pop(name, None)
    os.environ.update(IDRAK_LAB_DATABASE_URL=lab_url, IDRAK_LAB_ISOLATED_DATABASE='yes',
                      IDRAK_LAB_PAIRING_KEY=secrets.token_urlsafe(48),
                      IDRAK_CONNECT_ENCRYPTION_KEY=Fernet.generate_key().decode(),
                      IDRAK_LAB_WEBHOOK_SECRET=secrets.token_urlsafe(48),
                      IDRAK_LAB_ACCESS_PASSWORD=secrets.token_urlsafe(32))
    sys.path.insert(0, str(ROOT / 'tools/idrak-connect-lab'))
    sys.path.insert(0, str(ROOT / 'api'))
    import postgres_backend as pg
    import pairing as lab_pairing
    from app import db
    from app.auth import current_user, User
    from app.routers.integrations import router
    from app.services.pos import pairing, pipeline, lab as adapters
    lab = pg.lab
    # Guard both databases before any schema writes.
    for url, schema in ((api_url, 'public'), (lab_url, 'idrak_lab_source')):
        c = await asyncpg.connect(url)
        assert await c.fetchval('SELECT count(*) FROM information_schema.tables WHERE table_schema=$1', schema) == 0, 'Use empty test databases'
        await c.close()
    c = await asyncpg.connect(api_url)
    try:
        await c.execute("CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY)")
        for role in ('anon', 'authenticated'):
            if not await c.fetchval('SELECT 1 FROM pg_roles WHERE rolname=$1', role):
                await c.execute('CREATE ROLE ' + role)
        migrations = ROOT / 'api/db/migrations'
        for name in ('001_core.sql', '007_pos_connect.sql', '008_pos_identity_inventory.sql',
                     '009_pos_channels_webhooks.sql', '010_pos_identity_by_entity.sql', '011_lab_pairing.sql'):
            async with c.transaction():
                await c.execute((migrations / name).read_text(encoding='utf-8'))
        await c.execute((migrations / '011_lab_pairing.sql').read_text(encoding='utf-8'))  # replay
    finally:
        await c.close()
    pg.initialize(); pg.initialize()  # Lab additive migration is idempotent too.
    spec = importlib.util.spec_from_file_location('pairing_lab_test_app', ROOT / 'tools/idrak-connect-lab/serverless_app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ca = TestClient(module.app, base_url=pairing.LAB_ORIGIN)
    cb = TestClient(module.app, base_url=pairing.LAB_ORIGIN)
    service_client = TestClient(module.app, base_url=pairing.LAB_ORIGIN)
    lab.create_order(lab.LEGACY_SHOP, 'pos', {'items': [{'sku': 'DRK-001', 'quantity': 1}]})
    pg.initialize()
    origin = {'Origin': pairing.LAB_ORIGIN}
    shop_a, shop_b = lab.create_shop('Pairing A'), lab.create_shop('Pairing B')
    for client, shop in ((ca, shop_a), (cb, shop_b)):
        assert client.post('/auth/login', json={'token': shop['token']}, headers=origin).status_code == 200
    db._pool = await asyncpg.create_pool(api_url, min_size=1, max_size=4, init=db._init_conn)
    uid_a, uid_b, uid_c, org_a, org_b = [str(uuid4()) for _ in range(5)]
    for uid in (uid_a, uid_b, uid_c):
        await db.execute('INSERT INTO auth.users VALUES($1)', uid)
    for oid, name in ((org_a, 'Org A'), (org_b, 'Org B')):
        await db.execute('INSERT INTO organizations(id,name) VALUES($1,$2)', oid, name)
    for uid, oid in ((uid_a, org_a), (uid_b, org_b), (uid_c, org_a)):
        await db.execute("INSERT INTO memberships(org_id,user_id,role) VALUES($1,$2,'manager')", oid, uid)
    api = FastAPI()
    api.include_router(router)

    async def test_user(request: Request):
        uid = request.headers.get('authorization', '').removeprefix('Bearer ')
        if uid not in (uid_a, uid_b, uid_c):
            raise HTTPException(401, 'Not signed in')
        return User(uid, 'test@example.invalid', 'Test', False)

    api.dependency_overrides[current_user] = test_user
    original_client = httpx.AsyncClient
    service_requests = []

    def remote(request):
        assert str(request.url) == pairing.LAB_ORIGIN + '/service/pairing/exchange'
        service_requests.append(1)
        response = service_client.post('/service/pairing/exchange', content=request.content,
                           headers={'Authorization': request.headers['authorization']})
        return httpx.Response(response.status_code, content=response.content)

    def client_factory(*args, **kwargs):
        if kwargs.get('trust_env') is False:
            kwargs['transport'] = httpx.MockTransport(remote)
        return original_client(*args, **kwargs)

    ha, hb = {'Authorization': 'Bearer ' + uid_a, 'X-Org-Id': org_a}, {'Authorization': 'Bearer ' + uid_b, 'X-Org-Id': org_b}
    try:
        async with original_client(transport=httpx.ASGITransport(app=api), base_url='https://idrak.test') as client:
            with patch.object(pairing.httpx, 'AsyncClient', client_factory):
                assert (await client.post('/integrations/lab/pairing-intents')).status_code == 401
                assert (await client.post('/integrations/lab/pairing-intents', headers={**ha, 'X-Org-Id': org_b})).status_code == 403
                await db.execute("UPDATE memberships SET role='cashier' WHERE user_id=$1", uid_c)
                hc = {'Authorization': 'Bearer ' + uid_c, 'X-Org-Id': org_a}
                assert (await client.post('/integrations/lab/pairing-intents', headers=hc)).status_code == 403
                assert (await client.post('/integrations/lab/pair', json={}, headers=hc)).status_code == 403
                intent_a = (await client.post('/integrations/lab/pairing-intents', headers=ha)).json()['intent']
                intent_b = (await client.post('/integrations/lab/pairing-intents', headers=hb)).json()['intent']
                code_a = ca.post('/api/pairing-codes', json={'intent': intent_a}, headers=origin).json()['code']
                code_b = cb.post('/api/pairing-codes', json={'intent': intent_b}, headers=origin).json()['code']
                assert (await client.post('/integrations/lab/pair', headers=hb, json={'code': code_a, 'intent': intent_a})).status_code == 400
                assert (await client.post('/integrations/lab/pair', headers=hb, json={'code': code_a, 'intent': intent_b})).status_code == 409
                assert (await client.post('/integrations/lab/pair', headers=ha, json={'code': code_a, 'intent': intent_a, 'base_url': 'http://127.0.0.1'})).status_code == 400
                await db.execute("UPDATE memberships SET role='manager' WHERE user_id=$1", uid_c)
                db.cache_clear()
                assert (await client.post('/integrations/lab/pair', headers=hc, json={'code': code_a, 'intent': intent_a})).status_code == 400
                results = []
                for headers, code, intent in ((ha, code_a, intent_a), (hb, code_b, intent_b)):
                    response = await client.post('/integrations/lab/pair', headers=headers, json={'code': code, 'intent': intent})
                    assert response.status_code == 200, response.text
                    assert 'token' not in response.text and 'webhook_secret' not in response.text
                    results.append(response.json())
                    assert (await client.post('/integrations/lab/pair', headers=headers, json={'code': code, 'intent': intent})).status_code == 409
                assert ca.post('/api/pairing-codes', json={'intent': intent_b}, headers=origin).status_code == 409
                # IDRAK's own registry independently rejects a conflicting shop,
                # even if the upstream service were to return inconsistent data.
                from app.auth import Ctx
                from unittest.mock import AsyncMock
                fake = {'shop_id': shop_a['shop_id'], 'org_id': org_b,
                        'token': 'lc.' + shop_a['shop_id'] + '.' + secrets.token_urlsafe(32),
                        'webhook_secret': 'a' * 64}
                with patch.object(pairing, 'exchange_remote', new=AsyncMock(return_value=fake)):
                    try:
                        await pairing.redeem('x' * 40, intent_b, Ctx(User(uid_b, '', None, False), org_b, 'manager'))
                    except HTTPException as exc:
                        assert exc.status_code == 409
                    else:
                        raise AssertionError('IDRAK accepted a conflicting organization')
                cid_b = results[1]['connections'][0]['id']
                assert (await client.get('/integrations/connections/' + cid_b, headers=ha)).status_code == 404
                assert (await client.post('/integrations/connections/' + cid_b + '/sync', headers=ha)).status_code == 404
                assert (await client.get('/integrations/connections', headers=ha)).status_code == 200
                assert all(c['account_ref'] == shop_a['shop_id'] for c in (await client.get('/integrations/connections', headers=ha)).json())
                # Each browser creates sales only in its own Lab shop.
                for browser, path, qty in ((ca, '/api/pos/sales', 2), (cb, '/api/pos/sales', 1), (cb, '/api/web/orders', 1)):
                    assert browser.post(path, json={'items': [{'sku': 'BRG-001', 'quantity': qty}]}, headers=origin).status_code == 200
                connections = await db.fetch('SELECT * FROM pos_connections ORDER BY provider_code')
                credentials = {}
                for conn in connections:
                    secret = await pairing.load_credentials(conn, conn['org_id'])
                    credentials[(conn['org_id'], conn['provider_code'])] = secret
                    stored = await db.fetchrow('SELECT credentials_encrypted FROM pos_lab_bindings WHERE shop_id=$1', conn['account_ref'])
                    assert secret['token'] not in stored['credentials_encrypted'] and secret['webhook_secret'] not in stored['credentials_encrypted']
                    detail = await client.get('/integrations/connections/' + conn['id'], headers=ha if conn['org_id'] == org_a else hb)
                    assert detail.status_code == 200
                    assert secret['token'] not in detail.text and secret['webhook_secret'] not in detail.text
                # Integration token cannot sell, administer shops, read catalog or select another shop.
                secret_a = credentials[(org_a, 'lab_pos')]
                with TestClient(module.app, base_url=pairing.LAB_ORIGIN) as service:
                    token_headers = {'Authorization': 'Bearer ' + secret_a['token']}
                    for path in ('/api/products', '/api/shops', '/simulator/api/summary', '/pos'):
                        assert service.get(path, headers=token_headers, follow_redirects=False).status_code == 401
                    assert service.post('/api/pos/sales', json={}, headers=token_headers).status_code == 401
                    assert service.get('/api/pos/events', headers={**token_headers, 'X-Lab-Shop': shop_b['shop_id']}).status_code == 403
                def pull(adapter, after, limit=100):
                    channel = 'pos' if adapter.channel == 'pos' else 'web'
                    with TestClient(module.app, base_url=pairing.LAB_ORIGIN) as service:
                        r = service.get(f'/api/{channel}/events?after={after}&limit={limit}', headers={'Authorization': adapter.authorization})
                        assert r.status_code == 200
                        return r.json()
                with patch.object(adapters._LabAdapter, '_get', pull):
                    # Concurrent syncs must not duplicate canonical sales.
                    await asyncio.gather(*(pipeline.run_sync(c['org_id'], None, c) for c in connections),
                                         *(pipeline.run_sync(c['org_id'], None, c) for c in connections))
                    assert await db.fetchval('SELECT count(*) FROM sales WHERE org_id=$1', org_a) == 1
                    assert await db.fetchval('SELECT count(*) FROM sales WHERE org_id=$1', org_b) == 2
                    assert await db.fetchval('SELECT sum(total) FROM sales WHERE org_id=$1', org_a) == 8.5
                    assert await db.fetchval('SELECT sum(total) FROM sales WHERE org_id=$1', org_b) == 8.5
                    assert await db.fetchval('SELECT count(*) FROM pos_sync_errors') == 0
                    for oid in (org_a, org_b):
                        assert await db.fetchval('SELECT count(*) FROM products WHERE org_id=$1', oid) == 1
                        assert await db.fetchval('SELECT count(*) FROM inventory_levels WHERE org_id=$1', oid) == 1
                        assert await db.fetchval('SELECT quantity FROM inventory_levels WHERE org_id=$1', oid) == 58
                    # Re-pairing the same shop/org resumes existing connections and cursors.
                    original_ids = {c['id'] for c in connections if c['org_id'] == org_a}
                    cursor_before = await db.fetch('SELECT id,cursor FROM pos_connections WHERE org_id=$1 ORDER BY id', org_a)
                    assert (await client.delete('/integrations/connections/' + next(iter(original_ids)), headers=ha)).status_code == 200
                    again = (await client.post('/integrations/lab/pairing-intents', headers=ha)).json()['intent']
                    code = ca.post('/api/pairing-codes', json={'intent': again}, headers=origin).json()['code']
                    response = await client.post('/integrations/lab/pair', headers=ha, json={'code': code, 'intent': again})
                    assert response.status_code == 200
                    assert {r['id'] for r in response.json()['connections']} == original_ids
                    assert await db.fetch('SELECT id,cursor FROM pos_connections WHERE org_id=$1 ORDER BY id', org_a) == cursor_before
                    await asyncio.gather(*(pipeline.run_sync(c['org_id'], None, c) for c in connections))
                    assert await db.fetchval('SELECT count(*) FROM sales') == 3
                conn_a = next(c for c in connections if c['org_id'] == org_a and c['provider_code'] == 'lab_pos')
                payload = ca.get('/api/pos/events').json()['events'][0]['payload']
                raw = json.dumps(payload, separators=(',', ':')).encode()
                adp = await pipeline._adapter_for(conn_a, org_a)
                assert adp.base_url == pairing.LAB_ORIGIN
                signature = adp.signature_for(raw)
                first = await pipeline.run_webhook(org_a, None, conn_a, {'X-Idrak-Signature': signature}, raw)
                second = await pipeline.run_webhook(org_a, None, conn_a, {'X-Idrak-Signature': signature}, raw)
                assert first['skipped'] == 1 and second['status'] == 'duplicate_skipped'
                assert await db.fetchval('SELECT count(*) FROM sales WHERE org_id=$1', org_a) == 1
                forged = {**payload, 'source': {**payload['source'], 'account_id': shop_b['shop_id']}}
                forged_raw = json.dumps(forged).encode()
                assert not adp.verify_webhook({'X-Idrak-Signature': adp.signature_for(forged_raw)}, forged_raw)
                assert not adp.verify_webhook({'X-Idrak-Signature': signature}, raw + b' ')
                adp._transport = lambda url: {'events': [{'payload': forged}], 'has_more': False}
                try:
                    adp._pull(0)
                except ValueError:
                    pass
                else:
                    raise AssertionError('cross-shop pull payload was accepted')
                # Ciphertext cannot be transplanted across tenants, even if a DB row is corrupted.
                with patch.object(db, 'fetchrow', return_value={'credentials_encrypted': stored['credentials_encrypted']}):
                    try:
                        await pairing.load_credentials({**conn_a, 'account_ref': 'shop-other'}, org_a)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('credential transplant was accepted')
                # Single-use redemption is atomic under simultaneous Lab requests.
                intent = pairing.new_intent(org_a, uid_a)['intent']
                code = ca.post('/api/pairing-codes', json={'intent': intent}, headers=origin).json()['code']
                raw = json.dumps({'code': code, 'intent': intent, 'timestamp': int(time.time())}).encode()
                with ThreadPoolExecutor(max_workers=2) as pool:
                    def redeem_once(_):
                        try:
                            lab_pairing.exchange(raw, lab_pairing.service_signature(raw))
                            return 200
                        except lab.LabAuthError as exc:
                            return exc.status
                    assert sorted(pool.map(redeem_once, range(2))) == [200, 409]
                # Expired code, forged intent, and browser/operator exchange without service auth.
                intent = pairing.new_intent(org_a, uid_a)['intent']
                code = ca.post('/api/pairing-codes', json={'intent': intent}, headers=origin).json()['code']
                with lab.connect(lab.SOURCE_DB) as c:
                    c.execute('UPDATE lab_pairing_codes SET expires_at=0 WHERE code_hash=?', (lab_pairing.digest(code),))
                assert (await client.post('/integrations/lab/pair', headers=ha, json={'code': code, 'intent': intent})).status_code == 409
                assert ca.post('/api/pairing-codes', json={'intent': intent + 'x'}, headers=origin).status_code == 400
                assert service_client.post('/service/pairing/exchange', json={}).status_code == 401
                assert len(lab.source_get(lab.LEGACY_SHOP, '/api/orders', {})['orders']) == 1
                print('PASS: two shops/two organizations; manager permission; stolen/expired/replayed codes; atomic redemption; immutable binding; encrypted secrets; restricted scoped polling; concurrent sync idempotency; signed and scoped webhooks; migration replay; legacy data retained')
    finally:
        ca.close(); cb.close(); service_client.close()
        await db.close_pool()


if __name__ == '__main__':
    asyncio.run(main())
