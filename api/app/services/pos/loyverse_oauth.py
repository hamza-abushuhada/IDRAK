"""Loyverse OAuth 2.0 (authorization code), encrypted tokens, account binding, webhooks.

Flow (same protections as the Lab redirect flow):
1. authorize: signed request bound to org + user + sha256(state), 10 minutes;
   the browser goes to https://api.loyverse.com/oauth/authorize with the EXACT
   registered redirect_uri and the state.
2. Loyverse sends the owner back to the IDRAK callback page (?code&state); the
   page checks the state it stored and posts code + request + state here.
3. connect: re-verifies request + state against the signed-in user and org,
   exchanges the code SERVER-TO-SERVER with the client secret, reads the
   merchant (currency must match the organization) and its stores, binds the
   Loyverse account to this organization ONLY, stores tokens encrypted
   (Fernet, IDRAK_CONNECT_ENCRYPTION_KEY), and registers a receipts.update
   webhook owned by the app (signed by Loyverse).
Tokens never reach the browser or logs. Access tokens are refreshed under a
per-account advisory lock (refresh tokens may rotate). A revoked or lapsed
account marks the connection as needing reconnection.

Configuration (server only): LOYVERSE_ENABLED=on, LOYVERSE_CLIENT_ID,
LOYVERSE_CLIENT_SECRET, LOYVERSE_REDIRECT_URI (exact registered HTTPS URL),
LOYVERSE_WEBHOOK_URL (HTTPS URL of /integrations/loyverse/webhook).
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException

from ... import db
from . import loyverse, pairing

AUTHORIZE_URL = 'https://api.loyverse.com/oauth/authorize'
TOKEN_URL = 'https://api.loyverse.com/oauth/token'
# Least privilege: merchant (currency/name), stores (branches), receipts (sales).
SCOPES = ('MERCHANT_READ', 'STORES_READ', 'RECEIPTS_READ')
TTL = 600
IMPORT_DAYS = 30
_STATE = re.compile(r'[A-Za-z0-9_-]{43}')
_ACCOUNT = re.compile(r'[A-Za-z0-9-]{1,64}')
PROVIDER = 'loyverse'


def _https(name):
    value = os.environ.get(name, '').strip()
    parts = urlsplit(value)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError(name)
    return value


def config() -> dict:
    """All-or-nothing server configuration; never echoed to clients."""
    if os.environ.get('LOYVERSE_ENABLED', 'off').strip().lower() != 'on':
        raise HTTPException(503, 'Loyverse is not available')
    try:
        cid, secret = os.environ['LOYVERSE_CLIENT_ID'].strip(), os.environ['LOYVERSE_CLIENT_SECRET'].strip()
        if not cid or len(secret) < 16:
            raise ValueError()
        return {'client_id': cid, 'client_secret': secret, 'redirect_uri': _https('LOYVERSE_REDIRECT_URI'),
                'webhook_url': _https('LOYVERSE_WEBHOOK_URL')}
    except (KeyError, ValueError):
        raise HTTPException(503, 'Loyverse is not available') from None


def available() -> bool:
    try:
        config(); pairing.cipher()
        return True
    except HTTPException:
        return False


def _state_key() -> bytes:
    # Derived from the encryption key; separate purpose label.
    pairing.cipher()  # validates the configured key
    return hmac.new(os.environ['IDRAK_CONNECT_ENCRYPTION_KEY'].encode(), b'idrak-loyverse-oauth-v1', hashlib.sha256).digest()


def new_authorization(org_id, user_id, locale) -> dict:
    cfg = config()
    state = secrets.token_urlsafe(32)
    data = {'aud': 'idrak-loyverse-oauth-v1', 'org': str(org_id), 'user': str(user_id), 'nonce': str(uuid4()),
            'exp': int(time.time()) + TTL, 'sh': hashlib.sha256(state.encode()).hexdigest(), 'lang': locale if locale in ('ar', 'en') else 'ar'}
    encoded = base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode()).decode()
    intent = encoded + '.' + hmac.new(_state_key(), encoded.encode(), hashlib.sha256).hexdigest()
    url = AUTHORIZE_URL + '?' + urlencode({'client_id': cfg['client_id'], 'scope': ' '.join(SCOPES), 'response_type': 'code',
                                            'redirect_uri': cfg['redirect_uri'], 'state': state})
    return {'authorize_url': url, 'intent': intent, 'state': state, 'expires_at': data['exp']}


def validate_intent(intent, state, org_id, user_id) -> dict:
    try:
        if not isinstance(intent, str) or len(intent) > 2048 or not isinstance(state, str) or not _STATE.fullmatch(state):
            raise ValueError()
        encoded, sig = intent.split('.')
        if not hmac.compare_digest(hmac.new(_state_key(), encoded.encode(), hashlib.sha256).hexdigest(), sig):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(encoded))
        if data['aud'] != 'idrak-loyverse-oauth-v1' or data['org'] != str(org_id) or data['user'] != str(user_id):
            raise ValueError()
        if type(data['exp']) is not int or not time.time() < data['exp'] <= time.time() + TTL + 5:
            raise ValueError()
        if not hmac.compare_digest(hashlib.sha256(state.encode()).hexdigest(), data['sh']):
            raise ValueError()
        UUID(data['nonce'])
        return data
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, 'Invalid or expired Loyverse authorization for this user and organization') from None


def _tokens_from(resp: dict) -> dict:
    try:
        access, refresh = resp['access_token'], resp.get('refresh_token')
        expires = int(resp.get('expires_in') or 0)
        if not isinstance(access, str) or not 8 <= len(access) <= 4096 or str(resp.get('token_type', 'Bearer')).lower() != 'bearer':
            raise ValueError()
        if refresh is not None and (not isinstance(refresh, str) or len(refresh) > 4096):
            raise ValueError()
        return {'access_token': access, 'refresh_token': refresh, 'expires_at': int(time.time()) + max(60, expires),
                'scope': str(resp.get('scope') or '')}
    except (KeyError, ValueError, TypeError):
        raise HTTPException(502, 'Unexpected Loyverse token response') from None


async def _token_request(form: dict, transport=None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False, transport=transport) as c:
            r = await c.post(TOKEN_URL, data=form, headers={'Accept': 'application/json'})
    except httpx.HTTPError:
        raise HTTPException(502, 'Loyverse is unreachable; try again') from None
    if r.status_code in (400, 401):
        raise loyverse.SourceAuthError('Loyverse rejected the authorization')
    if r.status_code != 200 or len(r.content) > 20000:
        raise HTTPException(502, 'Loyverse token service unavailable; try again')
    return _tokens_from(r.json())


def _encrypt(tokens: dict) -> str:
    return pairing.cipher().encrypt(json.dumps(tokens).encode()).decode()


def _decrypt(blob: str) -> dict:
    return json.loads(pairing.cipher().decrypt(blob.encode()))


async def connect(code: str, intent: str, state: str, ctx, transport=None, api_transport=None) -> dict:
    validate_intent(intent, state, ctx.org_id, ctx.user.id)
    cfg = config()
    if not isinstance(code, str) or not 8 <= len(code) <= 512:
        raise HTTPException(400, 'Invalid authorization code')
    try:
        tokens = await _token_request({'client_id': cfg['client_id'], 'client_secret': cfg['client_secret'],
                                       'redirect_uri': cfg['redirect_uri'], 'code': code, 'grant_type': 'authorization_code'}, transport)
    except loyverse.SourceAuthError:
        raise HTTPException(409, 'The Loyverse approval is invalid, expired or already used') from None
    import anyio
    client = loyverse.Client(tokens['access_token'], transport=api_transport)
    try:
        merchant = await anyio.to_thread.run_sync(client.merchant)
        stores = await anyio.to_thread.run_sync(client.stores)
    except loyverse.SourceAuthError:
        raise HTTPException(403, 'Loyverse did not grant the required permissions') from None
    except loyverse.SourceTemporaryError:
        raise HTTPException(502, 'Loyverse is unreachable; try again') from None
    merchant_id = str(merchant.get('id') or '')
    if not _ACCOUNT.fullmatch(merchant_id):
        raise HTTPException(502, 'Unexpected Loyverse merchant response')
    currency = ((merchant.get('currency') or {}).get('code') or '').upper()
    org_currency = await db.fetchval('select currency from organizations where id=$1', ctx.org_id)
    if not currency or currency != (org_currency or '').upper():
        raise HTTPException(409, f'This Loyverse account uses {currency or "an unknown currency"}, but this business uses {org_currency}')
    active = [s for s in stores if isinstance(s, dict) and s.get('id') and not s.get('deleted_at')]
    names = {str(s['id']): str(s.get('name') or 'Store')[:60] for s in active}
    encrypted = _encrypt(tokens)
    async with db.transaction() as c:
        await c.execute('SELECT pg_advisory_xact_lock(hashtext($1))', 'loyverse:' + merchant_id)
        bound = await c.fetchrow('SELECT org_id FROM pos_oauth_credentials WHERE provider_code=$1 AND account_ref=$2 FOR UPDATE', PROVIDER, merchant_id)
        if bound and str(bound['org_id']) != str(ctx.org_id):
            raise HTTPException(409, 'This Loyverse account is already linked to another business')
        await c.execute('''INSERT INTO pos_oauth_credentials(provider_code,account_ref,org_id,credentials_encrypted,created_by)
                           VALUES($1,$2,$3,$4,$5) ON CONFLICT(provider_code,account_ref) DO UPDATE
                           SET credentials_encrypted=excluded.credentials_encrypted, updated_at=now()''',
                        PROVIDER, merchant_id, ctx.org_id, encrypted, ctx.user.id)
        row = await c.fetchrow('''SELECT id, config FROM pos_connections WHERE org_id=$1 AND provider_code=$2 AND account_ref=$3
                                  ORDER BY created_at LIMIT 1 FOR UPDATE''', ctx.org_id, PROVIDER, merchant_id)
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=IMPORT_DAYS)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        conf = {'channel': 'in_store', 'auto_sync': True, 'autosync': 'webhook', 'store_names': names,
                'allowed_store_ids': sorted(names), 'currency': currency, 'import_since': since}
        if row:
            cid = row['id']
            await c.execute("UPDATE pos_connections SET status='connected', config=$3, last_error=null, updated_at=now() WHERE id=$1 AND org_id=$2",
                            cid, ctx.org_id, {**(row['config'] or {}), **conf, 'import_since': (row['config'] or {}).get('import_since', since)})
        else:
            cid = await c.fetchval('''INSERT INTO pos_connections(org_id,provider_code,account_ref,display_name,status,config,created_by)
                                      VALUES($1,$2,$3,$4,'connected',$5,$6) RETURNING id''',
                                   ctx.org_id, PROVIDER, merchant_id, str(merchant.get('business_name') or 'Loyverse')[:60], conf, ctx.user.id)
    webhook = await ensure_webhook(merchant_id, tokens['access_token'], cfg, api_transport)
    await db.audit(ctx.org_id, ctx.user.id, 'pos.loyverse_connected', 'pos_connection', str(cid),
                   {'stores': len(names), 'webhook': bool(webhook)})
    return {'connection_id': str(cid), 'name': str(merchant.get('business_name') or 'Loyverse')[:60],
            'stores': [{'name': n} for n in names.values()], 'automatic_updates': bool(webhook)}


async def ensure_webhook(merchant_id, access_token, cfg, api_transport=None):
    """Create (or reuse) the app-owned receipts.update webhook. Failure is not fatal: Sync now still works."""
    try:
        async with httpx.AsyncClient(base_url=loyverse.API_BASE, timeout=20, follow_redirects=False, trust_env=False,
                                     transport=api_transport, headers={'Authorization': 'Bearer ' + access_token}) as c:
            existing = await c.get('/webhooks/')
            if existing.status_code == 200:
                for w in existing.json() or []:
                    if w.get('type') == 'receipts.update' and w.get('url') == cfg['webhook_url'] and w.get('status') == 'ENABLED':
                        hook = w['id']; break
                else:
                    hook = None
            else:
                hook = None
            if not hook:
                r = await c.post('/webhooks/', json={'url': cfg['webhook_url'], 'type': 'receipts.update', 'status': 'ENABLED'})
                hook = r.json().get('id') if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        hook = None
    if hook:
        await db.execute("UPDATE pos_oauth_credentials SET webhook_ids=$3, updated_at=now() WHERE provider_code=$1 AND account_ref=$2",
                         PROVIDER, merchant_id, [str(hook)])
    return hook


async def access_token(connection: dict, org_id: str, transport=None) -> str:
    """A valid access token for this connection's account, refreshed under a lock when near expiry."""
    account = connection['account_ref']
    row = await db.fetchrow('SELECT org_id, credentials_encrypted FROM pos_oauth_credentials WHERE provider_code=$1 AND account_ref=$2', PROVIDER, account)
    if not row or str(row['org_id']) != str(org_id) or not row['credentials_encrypted']:
        raise loyverse.SourceAuthError('Loyverse is not connected; reconnect it')
    tokens = _decrypt(row['credentials_encrypted'])
    if tokens['expires_at'] - time.time() > 300:
        return tokens['access_token']
    cfg = config()
    async with db.transaction() as c:
        await c.execute('SELECT pg_advisory_xact_lock(hashtext($1))', 'loyverse-token:' + account)
        row = await c.fetchrow('SELECT credentials_encrypted FROM pos_oauth_credentials WHERE provider_code=$1 AND account_ref=$2 AND org_id=$3', PROVIDER, account, org_id)
        tokens = _decrypt(row['credentials_encrypted'])
        if tokens['expires_at'] - time.time() > 300:   # refreshed by a concurrent run
            return tokens['access_token']
        if not tokens.get('refresh_token'):
            raise loyverse.SourceAuthError('Loyverse access expired; reconnect it')
        fresh = await _token_request({'client_id': cfg['client_id'], 'client_secret': cfg['client_secret'],
                                      'refresh_token': tokens['refresh_token'], 'grant_type': 'refresh_token'}, transport)
        fresh['refresh_token'] = fresh['refresh_token'] or tokens['refresh_token']
        await c.execute('UPDATE pos_oauth_credentials SET credentials_encrypted=$3, updated_at=now() WHERE provider_code=$1 AND account_ref=$2',
                        PROVIDER, account, _encrypt(fresh))
        return fresh['access_token']


async def disconnect(connection: dict, org_id: str, api_transport=None) -> None:
    """Stop: remove our webhooks at Loyverse (best effort) and wipe the stored tokens."""
    row = await db.fetchrow('SELECT credentials_encrypted, webhook_ids FROM pos_oauth_credentials WHERE provider_code=$1 AND account_ref=$2 AND org_id=$3',
                            PROVIDER, connection['account_ref'], org_id)
    if not row:
        return
    if row['credentials_encrypted']:
        try:
            token = _decrypt(row['credentials_encrypted'])['access_token']
            async with httpx.AsyncClient(base_url=loyverse.API_BASE, timeout=15, follow_redirects=False, trust_env=False,
                                         transport=api_transport, headers={'Authorization': 'Bearer ' + token}) as c:
                for hook in row['webhook_ids'] or []:
                    await c.delete(f'/webhooks/{hook}')
        except Exception:  # noqa: BLE001 - tokens are wiped regardless
            pass
    await db.execute("UPDATE pos_oauth_credentials SET credentials_encrypted=NULL, webhook_ids='[]'::jsonb, updated_at=now() "
                     "WHERE provider_code=$1 AND account_ref=$2 AND org_id=$3", PROVIDER, connection['account_ref'], org_id)


async def handle_webhook(raw: bytes, signature: str | None) -> dict:
    """Verify Loyverse's signature, then re-fetch through the API (payload is only a trigger)."""
    cfg = config()
    if not loyverse.verify_signature(cfg['client_secret'], raw, signature):
        raise PermissionError()
    try:
        body = json.loads(raw)
        merchant_id, kind = str(body.get('merchant_id') or ''), body.get('type')
    except (ValueError, AttributeError):
        return {'status': 'ignored'}
    if kind != 'receipts.update' or not _ACCOUNT.fullmatch(merchant_id):
        return {'status': 'ignored'}
    from . import autosync, pipeline
    bound = await db.fetchrow('SELECT org_id FROM pos_oauth_credentials WHERE provider_code=$1 AND account_ref=$2 AND credentials_encrypted IS NOT NULL',
                              PROVIDER, merchant_id)
    if not bound:
        return {'status': 'ignored'}
    conn = await db.fetchrow('''select id, org_id, provider_code, account_ref, display_name, status, config, cursor from pos_connections
                                where org_id=$1 and provider_code=$2 and account_ref=$3 and status='connected' order by created_at limit 1''',
                             bound['org_id'], PROVIDER, merchant_id)
    if not conn or not autosync.enabled_globally() or not autosync.connection_enabled(dict(conn)):
        return {'status': 'ignored'}
    recent = await db.fetchval("select count(*) from pos_sync_jobs where connection_id=$1 and trigger='webhook' and started_at > now() - interval '1 minute'", conn['id'])
    if recent >= autosync.MAX_RUNS_PER_MINUTE:
        return {'status': 'rate_limited'}
    result = await pipeline.run_sync(str(bound['org_id']), None, dict(conn), trigger='webhook')
    return {'status': 'synced' if result.get('status') != 'failed' else 'error'}
