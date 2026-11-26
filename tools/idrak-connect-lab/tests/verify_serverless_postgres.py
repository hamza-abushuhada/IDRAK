"""Explicit integration check against a NEW localhost-only disposable Lab DB.

Set IDRAK_LAB_TEST_DATABASE_URL to a database named idrak_lab_test_* owned by
a restricted test role. This script refuses remote or non-test databases.
Run separately from the SQLite unittest suite; no production env is loaded.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import importlib
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit


def main():
    url = os.environ.get('IDRAK_LAB_TEST_DATABASE_URL', '')
    parsed = urlsplit(url)
    if parsed.hostname not in ('localhost', '127.0.0.1') or not parsed.path.startswith('/idrak_lab_test_'):
        raise SystemExit('A new localhost idrak_lab_test_* database is required')
    for key in ('SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_JWT_SECRET', 'VERCEL_TOKEN'):
        os.environ.pop(key, None)
    os.environ.update(IDRAK_LAB_DATABASE_URL=url, IDRAK_LAB_ISOLATED_DATABASE='yes',
                      IDRAK_LAB_ACCESS_PASSWORD=secrets.token_urlsafe(32),
                      IDRAK_LAB_WEBHOOK_SECRET=secrets.token_urlsafe(48))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import postgres_backend as pg
    from fastapi.testclient import TestClient
    pg.initialize()
    with pg.connect(pg.lab.SOURCE_DB) as db:
        assert db.execute('SELECT count(*) FROM orders').fetchone()[0] == 0, 'Use a new empty test DB'
    import serverless_app
    auth = {'Authorization': 'Basic ' + base64.b64encode(('lab:' + os.environ['IDRAK_LAB_ACCESS_PASSWORD']).encode()).decode()}
    with TestClient(serverless_app.app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/api/products').status_code == 401
        for path in ('/pos', '/shop', '/simulator/'):
            r = client.get(path, headers=auth)
            assert r.status_code == 200 and 'http://127.0.0.1:8765' not in r.text

        def post(path, body):
            r = client.post(path, json=body, headers=auth)
            assert r.status_code == 200, (path, r.status_code)
            return r.json()

        post('/api/pos/sales', {'items': [{'sku': 'BRG-001', 'quantity': 2}]})
        web = post('/api/web/orders', {'items': [{'sku': 'FRY-001', 'quantity': 1}], 'payment_method': 'cash_on_delivery'})
        for status in ('completed', 'refunded'):
            post('/api/orders/' + web['order_id'] + '/status', {'status': status})
        stats = client.get('/simulator/api/summary', headers=auth).json()
        assert stats['invoices'] == 2 and stats['revenue'] == '8.500'
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: client.post('/api/pos/sales', json={
                'items': [{'sku': 'SLD-001', 'quantity': 30}]}, headers=auth), range(4)))
        assert [r.status_code for r in responses].count(200) == 1
        assert [r.status_code for r in responses].count(400) == 3
        before = client.get('/simulator/api/summary', headers=auth).json()
    pg.initialize()
    serverless_app = importlib.reload(serverless_app)  # Simulated fresh invocation/module load.
    with TestClient(serverless_app.app) as client:
        assert client.get('/simulator/api/summary', headers=auth).json() == before
    print('PASS: PostgreSQL POS/store/refund, authentication, concurrent stock, cold start and setup replay')


if __name__ == '__main__':
    main()
