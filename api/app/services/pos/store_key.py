"""Online store linked with an API key (IDRAK Connect Lab store first).

The owner creates a read-only key in their store, then enters the store address
and the key in IDRAK. IDRAK:

- only ever contacts an allow-listed HTTPS store origin (no IPs, no private or
  reserved names, no redirects, no proxies) -> no SSRF through the address field;
- checks the key with the store itself (identity, scope, read access) and that
  every event it returns belongs to that store before saving anything;
- binds the store to ONE organization (refuses if another organization holds it,
  by approval link or by key);
- stores the key encrypted (Fernet, IDRAK_CONNECT_ENCRYPTION_KEY); it is never
  returned to a browser, logged, or put in an error message;
- reuses the Lab online-store adapter and the normal sync pipeline, so the stable
  source identity (store + order id) prevents duplicates across reconnects,
  including a store that was linked by approval before;
- receives signed "store changed" notifications (per-key secret, timestamp window,
  single-use nonce) and then pulls through the saved cursor; a missed notification
  is caught up by the next one, by "Sync now" or by the catch-up on page visits.

Adding a real third-party store later = a new adapter + an allow-listed origin;
nothing here claims that any other store's key works.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import InvalidToken
from fastapi import HTTPException

from ... import db
from . import adapter, lab, pairing

PROVIDER = 'lab_web'
KEY_RE = re.compile(r'lsk_([a-f0-9]{12})_[A-Za-z0-9_-]{43}')
STORE_RE = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')
SCOPES = ['orders:read']
SIG_PREFIX = b'idrak-store-notify:'
SKEW_SECONDS = 300
MAX_BODY = 1024
MAX_RUNS_PER_MINUTE = 30
CATCH_UP_AFTER_SECONDS = 600
_NONCE = re.compile(r'[A-Za-z0-9_-]{16,64}')
TIMEOUT = 10
MAX_RESPONSE = 2_000_000


class KeyRejected(Exception):
    """The store refused the key (wrong, revoked, expired or not for this store)."""


class Rejected(Exception):
    """Unauthenticated or malformed notification (no details are returned)."""


def available() -> bool:
    """Offered only where explicitly enabled (Staging first) and really usable."""
    if os.getenv('IDRAK_STORE_API_KEYS', 'off').strip().lower() != 'on':
        return False
    try:
        pairing.cipher()
        pairing.lab_origin()
        return True
    except (HTTPException, ValueError):
        return False


def store_origin(value) -> str:
    """The owner's store address -> the allow-listed origin, or ValueError.
    Accepts 'https://host', with an optional trailing '/', or the store page '/shop'."""
    if not isinstance(value, str) or len(value) > 300:
        raise ValueError('Store address not allowed')
    value = value.strip()
    parts = urlsplit(value)
    if parts.path not in ('', '/', '/shop', '/shop/') or parts.query or parts.fragment:
        raise ValueError('Store address not allowed')
    try:
        origin = pairing._canonical_origin(f'{parts.scheme}://{parts.netloc}')
        allowed = pairing.lab_origin()
    except ValueError:
        raise ValueError('Store address not allowed') from None
    if origin != allowed:
        raise ValueError('Store address not allowed')
    return origin


def key_id_of(key) -> str:
    match = KEY_RE.fullmatch(key) if isinstance(key, str) else None
    if not match:
        raise ValueError('Invalid API key format')
    return match.group(1)


def _client(origin: str, key: str, transport=None, sync=False):
    opts = dict(base_url=origin, timeout=TIMEOUT, follow_redirects=False, trust_env=False, transport=transport,
                headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json', 'User-Agent': 'IDRAK-Connect'})
    return httpx.Client(**opts) if sync else httpx.AsyncClient(**opts)


def _json(response) -> dict:
    if response.status_code in (401, 403):
        raise KeyRejected()
    if response.status_code != 200 or len(response.content) > MAX_RESPONSE:
        raise ValueError()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError()
    return data


async def probe(origin: str, key: str, transport=None) -> dict:
    """Verify the key with the store: identity + scope + read access + ownership of events.
    Read-only; nothing is saved. Raises KeyRejected or HTTPException(502) with fixed text."""
    key_id = key_id_of(key)
    try:
        async with _client(origin, key, transport) as c:
            info = _json(await c.get('/api/v1/store'))
            store = info.get('store_id')
            if (not isinstance(store, str) or not STORE_RE.fullmatch(store) or info.get('key_id') != key_id
                    or info.get('scopes') != SCOPES or info.get('channel') != 'web' or info.get('api_version') != '1'):
                raise ValueError()
            sample = _json(await c.get('/api/web/events', params={'after': 0, 'limit': 20}))
            events = sample.get('events')
            if not isinstance(events, list):
                raise ValueError()
            for row in events:
                src = ((row or {}).get('payload') or {}).get('source') or {}
                if src.get('account_id') != store or src.get('channel') != 'web' or src.get('system') != 'idrak-lab-store':
                    raise ValueError()
    except KeyRejected:
        raise
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        # Never include upstream bodies, headers, the key or exception strings.
        raise HTTPException(502, 'The store could not be reached or returned an unexpected answer') from None
    name = pairing.clean_name(info.get('name'), 60)
    return {'store_id': store, 'name': name, 'key_id': key_id, 'currency': info.get('currency'),
            'key_expires_at': info.get('key_expires_at') if type(info.get('key_expires_at')) is int else None,
            'sample_events': len(events)}


async def _subscribe(origin: str, key: str, enabled: bool, transport=None) -> str | None:
    """Ask the store for signed change notifications; returns the per-key secret (or None)."""
    try:
        async with _client(origin, key, transport) as c:
            data = _json(await c.post('/api/v1/notifications', json={'enabled': enabled}))
        secret = data.get('signing_secret')
        if enabled and isinstance(secret, str) and re.fullmatch(r'[a-f0-9]{64}', secret):
            return secret
    except Exception:  # noqa: BLE001 - sync still works without notifications (pull)
        pass
    return None


def _encrypt(data: dict) -> str:
    return pairing.cipher().encrypt(json.dumps(data).encode()).decode()


def _decrypt(value: str) -> dict:
    try:
        return json.loads(pairing.cipher().decrypt(value.encode()))
    except (InvalidToken, ValueError, TypeError):
        raise ValueError('Store credentials unavailable') from None


async def test(url, key, ctx, transport=None) -> dict:
    """"Test connection" before linking: nothing is stored."""
    try:
        origin = store_origin(url)
        key_id_of(key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    try:
        info = await probe(origin, key, transport)
    except KeyRejected:
        raise HTTPException(422, 'The store did not accept this API key (wrong, revoked or expired)') from None
    taken = await _owner_org(info['store_id'])
    return {'ok': True, 'store': {'name': info['name'], 'currency': info['currency'], 'key_expires_at': info['key_expires_at'],
                                  'sample_events': info['sample_events']},
            'already_linked_elsewhere': bool(taken and taken != str(ctx.org_id))}


async def _owner_org(store: str, c=None) -> str | None:
    q = c or db
    for sql in ('SELECT org_id FROM pos_lab_bindings WHERE shop_id=$1', 'SELECT org_id FROM pos_store_key_credentials WHERE shop_id=$1'):
        row = await q.fetchrow(sql, store)
        if row:
            return str(row['org_id'])
    return None


async def connect(url, key, ctx, transport=None) -> dict:
    try:
        origin = store_origin(url)
        key_id = key_id_of(key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    pairing.cipher()
    try:
        info = await probe(origin, key, transport)
    except KeyRejected:
        raise HTTPException(422, 'The store did not accept this API key (wrong, revoked or expired)') from None
    store = info['store_id']
    async with db.transaction() as c:
        await c.execute('SELECT pg_advisory_xact_lock(hashtext($1))', 'lab-pairing:' + store)
        owner = await _owner_org(store, c)
        if owner and owner != str(ctx.org_id):
            raise HTTPException(409, 'This store is already linked to another business')
        row = await c.fetchrow('''SELECT id, status, config FROM pos_connections WHERE org_id=$1 AND provider_code=$2 AND account_ref=$3
                                  ORDER BY created_at LIMIT 1 FOR UPDATE''', ctx.org_id, PROVIDER, store)
        if row and row['status'] != 'disconnected' and (row['config'] or {}).get('paired_lab'):
            raise HTTPException(409, 'This store is already linked to this business by owner approval')
    # Notifications are requested outside the DB transaction (network call).
    secret = await _subscribe(origin, key, True, transport)
    creds = {'store_id': store, 'org_id': str(ctx.org_id), 'key_id': key_id, 'api_key': key, 'origin': origin,
             'signing_secret': secret}
    config = {'store_api_key': True, 'channel': 'online', 'sales_adjust_inventory': False, 'auto_sync': False,
              'base_url': origin, **({'autosync': 'webhook'} if secret else {})}
    async with db.transaction() as c:
        await c.execute('SELECT pg_advisory_xact_lock(hashtext($1))', 'lab-pairing:' + store)
        owner = await _owner_org(store, c)
        if owner and owner != str(ctx.org_id):
            raise HTTPException(409, 'This store is already linked to another business')
        await c.execute('''INSERT INTO pos_store_key_credentials(shop_id,org_id,key_id,credentials_encrypted,created_by)
                           VALUES($1,$2,$3,$4,$5) ON CONFLICT(shop_id) DO UPDATE
                           SET key_id=excluded.key_id, credentials_encrypted=excluded.credentials_encrypted, updated_at=now()
                           WHERE pos_store_key_credentials.org_id=excluded.org_id''',
                        store, ctx.org_id, key_id, _encrypt(creds), ctx.user.id)
        row = await c.fetchrow('''SELECT id, cursor FROM pos_connections WHERE org_id=$1 AND provider_code=$2 AND account_ref=$3
                                  ORDER BY created_at LIMIT 1 FOR UPDATE''', ctx.org_id, PROVIDER, store)
        if row:
            cid, reused = row['id'], True
            await c.execute("""UPDATE pos_connections SET status='connected', config=$3, last_error=null, updated_at=now()
                               WHERE id=$1 AND org_id=$2""", cid, ctx.org_id, config)
        else:
            cid, reused = await c.fetchval('''INSERT INTO pos_connections(org_id,provider_code,account_ref,display_name,status,config,created_by)
                                              VALUES($1,$2,$3,$4,'connected',$5,$6) RETURNING id''',
                                           ctx.org_id, PROVIDER, store, info['name'] or 'Online store', config, ctx.user.id), False
    await db.audit(ctx.org_id, ctx.user.id, 'pos.store_key_connected', 'pos_connection', str(cid),
                   {'store': store, 'key_id': key_id, 'notifications': bool(secret), 'reconnected': reused})
    return {'connection_id': str(cid), 'reconnected': reused, 'name': info['name'], 'notifications': bool(secret)}


async def load_credentials(connection: dict, org_id: str) -> dict:
    row = await db.fetchrow('SELECT key_id, credentials_encrypted FROM pos_store_key_credentials WHERE shop_id=$1 AND org_id=$2',
                            connection['account_ref'], org_id)
    if not row or not row['credentials_encrypted']:
        raise adapter.SourceAuthError('The store API key was removed; connect the store again with a new key')
    data = _decrypt(row['credentials_encrypted'])
    if (data.get('store_id') != connection['account_ref'] or data.get('org_id') != str(org_id)
            or data.get('key_id') != row['key_id'] or not KEY_RE.fullmatch(data.get('api_key') or '')):
        raise ValueError('Store credentials unavailable')
    if data.get('origin') != (connection.get('config') or {}).get('base_url') or data.get('origin') != store_origin(data.get('origin')):
        raise ValueError('Store address changed; connect the store again')
    return data


class LabStoreKeyAdapter(lab.LabWebAdapter):
    """The Lab online-store adapter, authenticated with the owner's API key.
    Same events, same mapping, same stable identity (lab_web + store + order)."""

    def __init__(self, credentials: dict, branch: str, transport=None):
        super().__init__(base_url=credentials['origin'], secret=credentials.get('signing_secret') or 'unused',
                         branch=branch, account_ref=credentials['store_id'])
        self._key = credentials['api_key']
        self._http_transport = transport

    def _get(self, after: int, limit: int = 100) -> dict:
        try:
            with _client(self.base_url, self._key, self._http_transport, sync=True) as c:
                return _json(c.get('/api/web/events', params={'after': int(after), 'limit': int(limit)}))
        except KeyRejected:
            raise adapter.SourceAuthError('The store refused the API key (revoked or expired); connect the store again with a new key') from None
        except (httpx.HTTPError, ValueError, TypeError):
            raise adapter.SourceTemporaryError('The store could not be reached; it will be retried') from None


async def disconnect(connection: dict, org_id: str, transport=None) -> None:
    """Stop at the source (turn notifications off, best effort) and wipe the stored key.
    The store stays bound to this organization so it cannot be split across businesses."""
    row = await db.fetchrow('SELECT credentials_encrypted FROM pos_store_key_credentials WHERE shop_id=$1 AND org_id=$2',
                            connection['account_ref'], org_id)
    if not row:
        return
    if row['credentials_encrypted']:
        try:
            data = _decrypt(row['credentials_encrypted'])
            await _subscribe(data['origin'], data['api_key'], False, transport)
        except Exception:  # noqa: BLE001 - the key is wiped regardless
            pass
    await db.execute('UPDATE pos_store_key_credentials SET credentials_encrypted=NULL, updated_at=now() WHERE shop_id=$1 AND org_id=$2',
                     connection['account_ref'], org_id)


# ---- signed "store changed" notifications --------------------------------------
def signature(secret: str, raw: bytes) -> str:
    return hmac.new(secret.encode(), SIG_PREFIX + raw, hashlib.sha256).hexdigest()


def parse(raw: bytes) -> dict:
    try:
        if not raw or len(raw) > MAX_BODY:
            raise ValueError()
        body = json.loads(raw)
        if not isinstance(body, dict) or set(body) != {'key_id', 'shop_id', 'channel', 'ts', 'nonce'}:
            raise ValueError()
        if not (isinstance(body['shop_id'], str) and STORE_RE.fullmatch(body['shop_id'])):
            raise ValueError()
        if not (isinstance(body['key_id'], str) and re.fullmatch(r'[a-f0-9]{12}', body['key_id'])):
            raise ValueError()
        if body['channel'] != 'web' or type(body['ts']) is not int or abs(time.time() - body['ts']) > SKEW_SECONDS:
            raise ValueError()
        if not (isinstance(body['nonce'], str) and _NONCE.fullmatch(body['nonce'])):
            raise ValueError()
        return body
    except (ValueError, TypeError, KeyError):
        raise Rejected() from None


async def handle_notify(raw: bytes, sig: str) -> dict:
    body = parse(raw)
    row = await db.fetchrow('SELECT org_id, key_id, credentials_encrypted FROM pos_store_key_credentials WHERE shop_id=$1', body['shop_id'])
    if not row or not row['credentials_encrypted'] or row['key_id'] != body['key_id']:
        raise Rejected()
    try:
        creds = _decrypt(row['credentials_encrypted'])
    except ValueError:
        raise Rejected() from None
    secret = creds.get('signing_secret')
    if not secret or not isinstance(sig, str) or not hmac.compare_digest(signature(secret, raw), sig):
        raise Rejected()
    # Single use: a captured notification cannot be replayed, even inside the time window.
    fresh = await db.fetchval('INSERT INTO pos_notify_nonces(nonce) VALUES($1) ON CONFLICT DO NOTHING RETURNING 1',
                              f"{body['key_id']}:{body['nonce']}")
    if not fresh:
        raise Rejected()
    await db.execute("DELETE FROM pos_notify_nonces WHERE seen_at < now() - interval '1 hour'")
    from . import autosync
    if not autosync.enabled_globally():
        return {'status': 'ignored'}
    org_id = str(row['org_id'])
    conn = await db.fetchrow(
        """select id, org_id, provider_code, account_ref, display_name, status, config, cursor
           from pos_connections where org_id=$1 and provider_code=$2 and account_ref=$3 and status='connected'
             and coalesce((config->>'store_api_key')::boolean, false) order by created_at limit 1""",
        org_id, PROVIDER, body['shop_id'])
    if not conn or (conn['config'] or {}).get('autosync') != 'webhook':
        return {'status': 'ignored'}
    return await _sync(org_id, dict(conn), 'webhook')


async def _sync(org_id: str, conn: dict, trigger: str) -> dict:
    recent = await db.fetchval(
        "select count(*) from pos_sync_jobs where connection_id=$1 and trigger=$2 and started_at > now() - interval '1 minute'",
        conn['id'], trigger)
    if recent >= MAX_RUNS_PER_MINUTE:
        return {'status': 'rate_limited'}
    from . import pipeline
    try:
        result = await pipeline.run_sync(org_id, None, conn, trigger=trigger)
        return {'status': 'synced' if result.get('status') != 'failed' else 'error',
                'imported': result.get('imported', 0), 'updated': result.get('updated', 0)}
    except Exception:  # noqa: BLE001 - recorded without secrets; "Sync now" still works
        return {'status': 'error'}


async def catch_up(org_id: str, limit: int = 3) -> dict:
    """Compensation for missed notifications: pull API-key stores of this organization
    that have not synced recently. Cheap no-op when everything is fresh."""
    rows = await db.fetch(
        """select id, org_id, provider_code, account_ref, display_name, status, config, cursor
           from pos_connections where org_id=$1 and provider_code=$2 and status='connected'
             and coalesce((config->>'store_api_key')::boolean, false)
             and (last_sync_at is null or last_sync_at < now() - make_interval(secs => $3))
           order by last_sync_at nulls first limit $4""", org_id, PROVIDER, CATCH_UP_AFTER_SECONDS, limit)
    out = [await _sync(org_id, dict(r), 'scheduled') for r in rows]
    return {'checked': len(out), 'imported': sum(r.get('imported', 0) for r in out)}
