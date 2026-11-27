"""Applies the multi-shop migration to a Lab DB that holds PRE-multi-shop data.

Requires IDRAK_LAB_TEST_DATABASE_URL (localhost idrak_lab_test_* only) and
IDRAK_LAB_LEGACY_SCHEMA_SQL (path to the previous serverless_schema.sql). The
database must be new/empty. Verifies data preserved, idempotence and isolation.
"""
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

import psycopg


def main():
    url = os.environ.get('IDRAK_LAB_TEST_DATABASE_URL', '')
    parsed = urlsplit(url)
    if parsed.hostname not in ('localhost', '127.0.0.1') or not parsed.path.startswith('/idrak_lab_test_'):
        raise SystemExit('A new localhost idrak_lab_test_* database is required')
    old = Path(os.environ['IDRAK_LAB_LEGACY_SCHEMA_SQL']).read_text(encoding='utf-8')
    os.environ.update(IDRAK_LAB_DATABASE_URL=url, IDRAK_LAB_ISOLATED_DATABASE='yes',
                      IDRAK_LAB_WEBHOOK_SECRET=secrets.token_urlsafe(48))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import postgres_backend as pg
    lab = pg.lab
    with psycopg.connect(url) as c:
        assert c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='idrak_lab_source'").fetchone()[0] == 0, 'use an empty DB'
        c.execute(old)  # previous release layout
        for r in lab.SEED_PRODUCTS:
            c.execute('INSERT INTO idrak_lab_source.products VALUES(%s,%s,%s,%s,%s,%s)', r)
        c.execute("UPDATE idrak_lab_source.products SET stock=44 WHERE sku='BRG-001'")
        for i, ch in ((1, 'pos'), (2, 'web')):
            c.execute("INSERT INTO idrak_lab_source.orders(external_id,channel,status,payment_method,customer,total_mils,created_at,updated_at) "
                      "VALUES(%s,%s,'completed','cash','c',4250,'t','t')", (('POS-%06d' if ch == 'pos' else 'WEB-%06d') % i, ch))
            c.execute("INSERT INTO idrak_lab_source.order_items VALUES(%s,'BRG-001','x',1,4250)", (i,))
            c.execute("INSERT INTO idrak_lab_source.source_events(channel,event_id,event_type,payload,created_at,delivered) "
                      "VALUES(%s,%s,'sale.created','{}','t',1)", (ch, f'ev-{i}'))
        c.execute("INSERT INTO idrak_lab_receiver.received_events(event_id,source_id,event_type,payload,received_at) VALUES('ev-1','idrak-lab-pos','sale.created','{}','t')")
        c.execute("INSERT INTO idrak_lab_receiver.synced_orders VALUES('idrak-lab-pos','POS-000001','pos','completed',4250,1,'t')")
        c.execute("INSERT INTO idrak_lab_receiver.synced_inventory VALUES('idrak-lab-pos','BRG-001',44,2,'t')")
    pg.initialize()
    pg.initialize()  # idempotent
    legacy = lab.LEGACY_SHOP
    with psycopg.connect(url) as c:
        q = lambda sql: c.execute(sql).fetchall()
        assert q("SELECT id,order_no,external_id,shop_id FROM idrak_lab_source.orders ORDER BY id") == [(1, 1, 'POS-000001', legacy), (2, 2, 'WEB-000002', legacy)]
        assert q("SELECT stock FROM idrak_lab_source.products WHERE sku='BRG-001'") == [(44,)]
        assert q("SELECT seq,shop_id FROM idrak_lab_source.source_events ORDER BY seq") == [(1, legacy), (2, legacy)]
        assert q("SELECT count(*) FROM idrak_lab_source.order_items WHERE shop_id='%s'" % legacy) == [(2,)]
        assert q("SELECT shop_id,count(*) FROM idrak_lab_receiver.synced_orders GROUP BY 1") == [(legacy, 1)]
        assert q("SELECT count(*) FROM idrak_lab_receiver.received_events WHERE shop_id='%s'" % legacy) == [(1,)]
        assert q("SELECT count(*) FROM idrak_lab_source.products") == [(len(lab.SEED_PRODUCTS),)]  # no duplicate seeding
    lab.connect = pg.connect
    shop = lab.create_shop('B')['shop_id']
    from unittest.mock import patch
    with patch.object(lab, 'flush_events', lambda *a, **k: None):
        assert lab.create_order(shop, 'pos', {'items': [{'sku': 'BRG-001', 'quantity': 1}]})['order_id'] == 'POS-000001'
        assert lab.create_order(legacy, 'pos', {'items': [{'sku': 'BRG-001', 'quantity': 1}]})['order_id'] == 'POS-000003'  # sequence continues
    assert {p['sku']: p['stock'] for p in lab.source_get(legacy, '/api/products', {})['products']}['BRG-001'] == 43
    assert {p['sku']: p['stock'] for p in lab.source_get(shop, '/api/products', {})['products']}['BRG-001'] == 59
    assert len(lab.source_get(shop, '/api/orders', {})['orders']) == 1
    try:
        lab.change_order(shop, 'POS-000003', 'refunded')
    except ValueError:
        pass
    else:
        raise AssertionError('cross-shop order change was allowed')
    print('PASS: legacy PostgreSQL data migrated in place, idempotent, isolated per shop')


if __name__ == '__main__':
    main()
