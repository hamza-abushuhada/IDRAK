"""Durable PostgreSQL backend for the existing standalone Lab domain logic.

Only IDRAK_LAB_DATABASE_URL is accepted. No IDRAK application database fallback.
"""
from contextlib import contextmanager
import os
import re

import psycopg

import demo_server as lab


def database_url():
    url = os.environ.get('IDRAK_LAB_DATABASE_URL', '')
    if not url or os.environ.get('IDRAK_LAB_ISOLATED_DATABASE') != 'yes':
        raise ValueError('Configure a dedicated Lab database and confirm IDRAK_LAB_ISOLATED_DATABASE=yes')
    if any(os.environ.get(k) for k in ('SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_JWT_SECRET', 'VERCEL_TOKEN')):
        raise ValueError('Production credentials must not be present in the standalone Lab environment')
    return url


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


def row_factory(cursor):
    names = [c.name for c in cursor.description] if cursor.description else []
    return lambda values: Row(zip(names, values))


class Connection:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, args=()):
        if sql == 'BEGIN IMMEDIATE':
            return None  # Transaction and lock already acquired by connect().
        sql = sql.replace('?', '%s').replace('status="completed"', "status='completed'")
        returning = None
        if re.match(r'INSERT INTO source_events\(', sql, re.I):
            returning = 'seq'
        elif re.match(r'INSERT INTO orders\(', sql, re.I):
            returning = 'id'
        if returning:
            cursor = self.conn.execute(sql + ' RETURNING ' + returning, args)
            value = cursor.fetchone()[returning]
            # Keep the small SQLite cursor interface used by the domain model.
            return type('Inserted', (), {'lastrowid': value})()
        return self.conn.execute(sql, args)


@contextmanager
def connect(path):
    schema = 'idrak_lab_source' if path == lab.SOURCE_DB else 'idrak_lab_receiver'
    with psycopg.connect(database_url(), row_factory=row_factory, connect_timeout=10) as conn:
        conn.execute('SET LOCAL statement_timeout = 10000')
        conn.execute('SET LOCAL lock_timeout = 5000')
        conn.execute('SET LOCAL search_path TO ' + schema + ', public')
        # Serialize source stock/order transitions and receiver idempotency within
        # each database transaction, including across serverless instances.
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (schema,))
        yield Connection(conn)


def install():
    database_url()  # Validate isolation before replacing the local backend.
    lab.connect = connect


def initialize():
    """Explicit setup command; never run automatically on a request/cold start."""
    from pathlib import Path
    with psycopg.connect(database_url()) as conn:
        # Base (original) layout, then the idempotent multi-shop upgrade; a fresh
        # database and an existing one take the same path.
        conn.execute((Path(__file__).with_name('serverless_schema.sql')).read_text(encoding='utf-8'))
        conn.execute((Path(__file__).with_name('serverless_migration_shops.sql')).read_text(encoding='utf-8'))
        conn.execute((Path(__file__).with_name('serverless_migration_pairing.sql')).read_text(encoding='utf-8'))
        conn.execute((Path(__file__).with_name('serverless_migration_users.sql')).read_text(encoding='utf-8'))
        conn.execute((Path(__file__).with_name('serverless_migration_api_keys.sql')).read_text(encoding='utf-8'))
        for row in lab.SEED_PRODUCTS:
            conn.execute('INSERT INTO idrak_lab_source.products(shop_id,sku,name_ar,name_en,emoji,price_mils,stock) '
                         'VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(shop_id,sku) DO NOTHING', (lab.LEGACY_SHOP, *row))


if __name__ == '__main__':
    initialize()
    print('Dedicated Lab database initialized.')
