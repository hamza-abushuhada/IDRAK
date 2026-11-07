import json
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any
from uuid import UUID
import datetime as dt

import asyncpg

from .config import settings

_pool: asyncpg.Pool | None = None


async def _init_conn(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


SERVERLESS = bool(__import__("os").getenv("VERCEL"))


async def init_pool() -> asyncpg.Pool:
    global _pool
    import asyncio
    loop = asyncio.get_running_loop()
    if _pool is not None and getattr(_pool, "_loop", loop) is not loop:
        _pool = None
    if _pool is None:
        url = settings.database_url
        txn_pooler = ":6543/" in url
        _pool = await asyncpg.create_pool(
            url, min_size=1 if SERVERLESS else 2, max_size=4 if SERVERLESS else 8, max_inactive_connection_lifetime=60,
            init=_init_conn, command_timeout=60, **({"statement_cache_size": 0} if txn_pooler else {}),
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    assert _pool is not None, "DB pool not initialised"
    return _pool


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    return v


def row(r: asyncpg.Record | None) -> dict | None:
    return None if r is None else {k: _jsonable(v) for k, v in r.items()}


def rows(rs: list[asyncpg.Record]) -> list[dict]:
    return [{k: _jsonable(v) for k, v in r.items()} for r in rs]


async def fetch(sql: str, *args) -> list[dict]:
    async with pool().acquire() as c:
        return rows(await c.fetch(sql, *args))


async def fetchrow(sql: str, *args) -> dict | None:
    async with pool().acquire() as c:
        return row(await c.fetchrow(sql, *args))


async def fetchval(sql: str, *args):
    async with pool().acquire() as c:
        return _jsonable(await c.fetchval(sql, *args))


async def execute(sql: str, *args) -> str:
    async with pool().acquire() as c:
        return await c.execute(sql, *args)


@asynccontextmanager
async def transaction():
    async with pool().acquire() as c:
        async with c.transaction():
            yield c


async def audit(org_id: str | None, user_id: str | None, action: str, entity: str | None = None,
                entity_id: str | None = None, details: dict | None = None) -> None:
    try:
        await execute(
            "insert into audit_log(org_id,user_id,action,entity,entity_id,details) values($1,$2,$3,$4,$5,$6)",
            org_id, user_id, action, entity, entity_id, details or {},
        )
    except Exception:
        pass


import time as _time

_cache: dict = {}


def cache_get(key, ttl: float):
    v = _cache.get(key)
    if v and _time.monotonic() - v[0] < ttl:
        return v[1]
    return None


def cache_set(key, value):
    _cache[key] = (_time.monotonic(), value)
    return value


def cache_clear(prefix=None):
    for k in list(_cache):
        if prefix is None or (isinstance(k, tuple) and k[0] == prefix):
            _cache.pop(k, None)


def cached(ttl: float):
    import functools

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            key = (fn.__name__, args, tuple(sorted(kwargs.items())))
            hit = cache_get(key, ttl)
            if hit is not None:
                return hit
            return cache_set(key, await fn(*args, **kwargs))
        return wrapper
    return deco
