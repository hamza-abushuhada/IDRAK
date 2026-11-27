"""Server-only pairing and encrypted Lab credentials. No caller-supplied origins."""
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit
from uuid import uuid4, UUID

from cryptography.fernet import Fernet, InvalidToken
import httpx
from fastapi import HTTPException

from ... import db

# The published Lab. Used when IDRAK_LAB_ORIGIN is unset, which is how
# production must be configured.
LAB_ORIGIN = 'https://idrak-connect-lab.vercel.app'
TTL = 300
# The redirect flow lets the owner sign in to their POS first; the code itself still lives TTL.
REDIRECT_TTL = 600
LOCALES = ('ar', 'en')
_STATE_RE = re.compile(r'[A-Za-z0-9_-]{43}')
_HOST_RE = re.compile(r'(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+')
_RESERVED_SUFFIXES = ('.localhost', '.local', '.internal', '.test', '.invalid', '.example', '.lan', '.home.arpa')


def _canonical_origin(value):
    """Return 'https://host' for a bare public HTTPS origin, else raise ValueError.

    No credentials, path, query, fragment, non-443 port, IP literal or
    local/reserved hostname, so the server can only ever call a named host.
    """
    if not isinstance(value, str) or len(value) > 300 or value != value.strip():
        raise ValueError()
    parts = urlsplit(value)
    host = parts.hostname or ''
    if (parts.scheme != 'https' or parts.username is not None or parts.password is not None
            or parts.path not in ('', '/') or parts.query or parts.fragment or '@' in parts.netloc):
        raise ValueError()
    if parts.port not in (None, 443) or parts.netloc.lower() not in (host, host + ':443'):
        raise ValueError()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError()  # IP literals are never allowed
    # The top-level label must contain a letter: blocks shorthand IPs like 127.1 or 2130706433.
    if (not _HOST_RE.fullmatch(host) or host == 'localhost' or host.endswith(_RESERVED_SUFFIXES)
            or not re.search('[a-z]', host.rsplit('.', 1)[-1])):
        raise ValueError()
    return 'https://' + host


def lab_origin():
    """The single Lab origin this server may contact.

    Unset → the published Lab. Otherwise IDRAK_LAB_ORIGIN must exactly match the
    published Lab or an origin listed in IDRAK_LAB_ALLOWED_ORIGINS (comma
    separated, exact origins, no wildcards), e.g. a dedicated staging Lab.
    Any invalid value fails closed; it never falls back to another origin.
    """
    configured = os.environ.get('IDRAK_LAB_ORIGIN', '')
    if not configured:
        return LAB_ORIGIN
    origin = _canonical_origin(configured)
    allowed = {LAB_ORIGIN} | {_canonical_origin(item.strip())
                              for item in os.environ.get('IDRAK_LAB_ALLOWED_ORIGINS', '').split(',') if item.strip()}
    if origin not in allowed:
        raise ValueError()
    return origin


LOOPBACK_HOSTS = ('127.0.0.1', 'localhost')


def legacy_lab_base_url(stored):
    """Validate the stored base_url of an UNPAIRED (local-demo) Lab connection.

    Allowed: a plain-HTTP loopback Lab for local development (never on a
    serverless host, where loopback is meaningless and only an SSRF risk), or
    exactly the active configured Lab origin. Anything else, including the
    published Lab whenever a different Lab origin is configured, raises
    ValueError before any request is made. Paired connections are validated
    separately against lab_origin().
    """
    from . import lab
    value = stored or lab.DEFAULT_BASE_URL
    if not isinstance(value, str):
        raise ValueError('Lab URL not allowed')
    parts = urlsplit(value)
    if (parts.scheme == 'http' and parts.hostname in LOOPBACK_HOSTS and parts.username is None
            and parts.password is None and not parts.query and not parts.fragment and parts.path in ('', '/')):
        if os.environ.get('VERCEL'):
            raise ValueError('Lab URL not allowed on this server')
        return value.rstrip('/')
    try:
        origin = _canonical_origin(value.rstrip('/'))
        active = lab_origin()
    except ValueError:
        raise ValueError('Lab URL not allowed') from None
    if origin != active:
        raise ValueError('Lab URL not allowed')
    return origin


def configured_origin():
    try:
        return lab_origin()
    except ValueError:
        raise HTTPException(503, 'Lab pairing is not configured') from None


def key():
    value = os.environ.get('IDRAK_LAB_PAIRING_KEY', '')
    if len(value) < 32 or value == os.environ.get('IDRAK_LAB_WEBHOOK_SECRET'):
        raise HTTPException(503, 'Lab pairing is not configured')
    return value.encode()


def cipher():
    try:
        value = os.environ['IDRAK_CONNECT_ENCRYPTION_KEY']
        if value == os.environ.get('IDRAK_LAB_PAIRING_KEY'):
            raise ValueError()
        return Fernet(value.encode())
    except (KeyError, ValueError):
        raise HTTPException(503, 'Connection encryption is not configured') from None


def _sign(data):
    encoded = base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':'), ensure_ascii=False).encode()).decode()
    return encoded + '.' + hmac.new(key(), b'intent:' + encoded.encode(), hashlib.sha256).hexdigest()


def new_intent(org_id, user_id):
    cipher()  # Fail before issuing a request that cannot be persisted securely.
    configured_origin()  # ...or redeemed against a valid Lab origin.
    data = {'aud': 'idrak-lab-pairing-v1', 'org': str(org_id), 'user': str(user_id),
            'nonce': str(uuid4()), 'exp': int(time.time()) + TTL}
    return {'intent': _sign(data), 'expires_at': data['exp']}


def clean_name(value, limit=80):
    if not isinstance(value, str):
        return ''
    value = ''.join(ch for ch in value if ch.isprintable())
    return ' '.join(value.split())[:limit]


def new_authorization(org_id, user_id, locale, org_name=''):
    """Start the redirect flow: a signed request bound to this org + user and to
    sha256(state). Returns the Lab address to send the browser to; the request
    and state travel only in the URL fragment (never sent to servers or logs).
    The browser keeps intent + state for the callback; the server re-checks both."""
    cipher()
    origin = configured_origin()
    state = secrets.token_urlsafe(32)
    data = {'aud': 'idrak-lab-pairing-v1', 'org': str(org_id), 'user': str(user_id), 'nonce': str(uuid4()),
            'exp': int(time.time()) + REDIRECT_TTL, 'flow': 'redirect',
            'sh': hashlib.sha256(state.encode()).hexdigest(), 'lang': locale if locale in LOCALES else 'ar',
            'name': clean_name(org_name)}
    intent = _sign(data)
    return {'authorize_url': origin + '/connect#' + urlencode({'request': intent, 'state': state}),
            'intent': intent, 'state': state, 'expires_at': data['exp']}


def validate_intent(value, org_id, user_id, state=None):
    signing_key = key()
    try:
        if not isinstance(value, str) or len(value) > 2048:
            raise ValueError()
        encoded, signature = value.split('.')
        expected = hmac.new(signing_key, b'intent:' + encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(encoded))
        if data['aud'] != 'idrak-lab-pairing-v1' or data['org'] != str(org_id) or data['user'] != str(user_id):
            raise ValueError()
        redirect = data.get('flow') == 'redirect'
        ttl = REDIRECT_TTL if redirect else TTL
        if type(data['exp']) is not int or not time.time() < data['exp'] <= time.time() + ttl + 5:
            raise ValueError()
        UUID(data['nonce'])
        # Redirect requests are redeemable only with the state they were issued with;
        # manual pairing requests never take one.
        if redirect != (state is not None):
            raise ValueError()
        if redirect and (not isinstance(state, str) or not _STATE_RE.fullmatch(state) or not hmac.compare_digest(
                hashlib.sha256(state.encode()).hexdigest(), data.get('sh') or '')):
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, 'Invalid or expired pairing request for this user and organization') from None


def validate_credentials(data, org_id):
    import re
    try:
        shop = data['shop_id']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', shop) or data['org_id'] != str(org_id):
            raise ValueError()
        if not re.fullmatch(r'lc\.' + re.escape(shop) + r'\.[A-Za-z0-9_-]{40,64}', data['token']):
            raise ValueError()
        if not re.fullmatch(r'[a-f0-9]{64}', data['webhook_secret']):
            raise ValueError()
        return {k: data[k] for k in ('shop_id', 'org_id', 'token', 'webhook_secret')}
    except (KeyError, ValueError, TypeError):
        raise HTTPException(502, 'Invalid Lab pairing response') from None


async def exchange_remote(code, intent, origin):
    raw = json.dumps({'code': code, 'intent': intent, 'timestamp': int(time.time())}, separators=(',', ':')).encode()
    authorization = 'LabPairing ' + hmac.new(key(), b'exchange:' + raw, hashlib.sha256).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = await client.post(origin + '/service/pairing/exchange', content=raw,
                                         headers={'Authorization': authorization, 'Content-Type': 'application/json'})
        if response.status_code in (400, 401, 403, 409):
            raise HTTPException(409, 'Pairing code is invalid, expired, already used or belongs to another organization')
        if response.status_code != 200 or len(response.content) > 10000:
            raise ValueError()
        return response.json()
    except (httpx.HTTPError, ValueError):
        # Never include upstream bodies, headers, credentials or exception strings.
        raise HTTPException(502, 'Lab pairing service unavailable; request a new pairing code') from None


async def redeem(code, intent, ctx, state=None):
    validate_intent(intent, ctx.org_id, ctx.user.id, state)
    origin = configured_origin()
    encryption = cipher()
    response = await exchange_remote(code, intent, origin)
    credentials = validate_credentials(response, ctx.org_id)
    shop_name = clean_name(response.get('shop_name'), 60)
    shop = credentials['shop_id']
    encrypted = encryption.encrypt(json.dumps(credentials).encode()).decode()
    connections = []
    async with db.transaction() as c:
        await c.execute('SELECT pg_advisory_xact_lock(hashtext($1))', 'lab-pairing:' + shop)
        existing = await c.fetchrow('SELECT org_id FROM pos_lab_bindings WHERE shop_id=$1 FOR UPDATE', shop)
        if existing and str(existing['org_id']) != str(ctx.org_id):
            raise HTTPException(409, 'Shop is already linked to another organization')
        await c.execute('''INSERT INTO pos_lab_bindings(shop_id,org_id,credentials_encrypted,created_by)
                           VALUES($1,$2,$3,$4) ON CONFLICT(shop_id) DO UPDATE
                           SET credentials_encrypted=excluded.credentials_encrypted,updated_at=now()''',
                        shop, ctx.org_id, encrypted, ctx.user.id)
        for provider, channel in (('lab_pos', 'in_store'), ('lab_web', 'online')):
            row = await c.fetchrow('''SELECT id FROM pos_connections WHERE org_id=$1 AND provider_code=$2
                                      AND account_ref=$3 ORDER BY created_at LIMIT 1 FOR UPDATE''', ctx.org_id, provider, shop)
            config = {'paired_lab': True, 'channel': channel, 'sales_adjust_inventory': False,
                      'auto_sync': True, 'base_url': origin}  # binds these credentials to this Lab
            if row:
                cid = row['id']
                await c.execute("UPDATE pos_connections SET status='connected',config=$3,updated_at=now() WHERE id=$1 AND org_id=$2",
                                cid, ctx.org_id, config)
            else:
                cid = await c.fetchval('''INSERT INTO pos_connections(org_id,provider_code,account_ref,display_name,status,config,created_by)
                                          VALUES($1,$2,$3,$4,'connected',$5,$6) RETURNING id''',
                                       ctx.org_id, provider, shop, shop_name or 'Paired Lab ' + provider, config, ctx.user.id)
            connections.append({'id': str(cid), 'provider_code': provider})
    await db.audit(ctx.org_id, ctx.user.id, 'pos.lab_paired', 'lab_shop', shop, {'connections': connections})
    return {'shop_id': shop, 'name': shop_name, 'connections': connections}


async def load_credentials(connection, org_id):
    if str(connection.get('org_id', org_id)) != str(org_id):
        raise ValueError('Lab organization mismatch')
    row = await db.fetchrow('SELECT credentials_encrypted FROM pos_lab_bindings WHERE shop_id=$1 AND org_id=$2',
                            connection['account_ref'], org_id)
    if not row:
        raise ValueError('Paired Lab credentials unavailable')
    try:
        data = json.loads(cipher().decrypt(row['credentials_encrypted'].encode()))
        data = validate_credentials(data, org_id)
        if data['shop_id'] != connection['account_ref']:
            raise ValueError()
        return data
    except (InvalidToken, ValueError, TypeError, HTTPException):
        raise ValueError('Paired Lab credentials unavailable') from None
