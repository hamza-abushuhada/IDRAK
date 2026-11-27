"""Store API keys for the Lab's online store (owner-issued, read-only, per shop).

- A key belongs to exactly ONE shop and carries fixed scopes (orders:read). It can
  read that shop's online-store events and store identity, and ask for signed
  change notifications. Nothing else: no POS events, no other shop, no writes.
- Only a SHA-256 digest of the secret is stored. The full key is returned once,
  at creation/rotation, to the shop owner's browser session.
- Keys can expire, be revoked, or be rotated (old revoked, new shown once).
- Notifications for a key are signed with a per-key secret derived from the
  deployment signing secret (never stored); revoking the key ends them.
"""
import hashlib
import hmac
import re
import secrets
import time

import demo_server as lab

SCOPES = ('orders:read',)
MAX_ACTIVE_KEYS = 10
EXPIRY_CHOICES = (30, 90, 365, None)  # days; None = no expiry
KEY_RE = re.compile(r'lsk_([a-f0-9]{12})_([A-Za-z0-9_-]{43})')
KEY_ID_RE = re.compile(r'[a-f0-9]{12}')
# Exactly what an API key may call (method, path).
ALLOWED = {('GET', '/api/v1/store'), ('GET', '/api/web/events'), ('POST', '/api/v1/notifications')}
NOTIFY_PREFIX = b'idrak-lab-apikey-notify:'

DDL = '''
CREATE TABLE IF NOT EXISTS lab_api_keys (
  key_id TEXT PRIMARY KEY, shop_id TEXT NOT NULL REFERENCES shops(shop_id),
  name TEXT NOT NULL, key_hash TEXT NOT NULL, scopes TEXT NOT NULL,
  ttl_days INTEGER, expires_at BIGINT, created_by TEXT, created_at TEXT NOT NULL,
  revoked_at TEXT, last_used_at TEXT, notify INTEGER NOT NULL DEFAULT 0, rotated_from TEXT
);
CREATE INDEX IF NOT EXISTS lab_api_keys_shop_idx ON lab_api_keys(shop_id);
'''


def _digest(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def _clean_name(value):
    if value is None:
        return 'IDRAK'
    if not isinstance(value, str):
        raise ValueError('Invalid key name')
    value = ' '.join(''.join(ch for ch in value if ch.isprintable()).split())
    if not 1 <= len(value) <= 60:
        raise ValueError('Key name must be 1-60 characters')
    return value


def _expiry(days):
    if days not in EXPIRY_CHOICES:
        raise ValueError('Expiry must be 30, 90 or 365 days, or none')
    return None if days is None else int(time.time()) + days * 86400


def _require_key_manager(principal):
    # Shop owner session, shop credential or the Lab operator. Never an API key or a cashier.
    if principal.kind == 'integration':
        raise lab.LabAuthError(403, 'API keys cannot manage API keys')
    lab.require_owner(principal)


def _public(row, now=None):
    now = now or time.time()
    state = 'revoked' if row['revoked_at'] else 'expired' if row['expires_at'] and row['expires_at'] <= now else 'active'
    return {'key_id': row['key_id'], 'name': row['name'], 'prefix': f"lsk_{row['key_id']}_…", 'scopes': row['scopes'].split(','),
            'created_at': row['created_at'], 'expires_at': row['expires_at'], 'revoked_at': row['revoked_at'],
            'last_used_at': row['last_used_at'], 'status': state, 'notifications': bool(row['notify']) and state == 'active'}


def _insert(db, shop, name, ttl_days, created_by, rotated_from=None):
    key_id = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    db.execute('INSERT INTO lab_api_keys(key_id,shop_id,name,key_hash,scopes,ttl_days,expires_at,created_by,created_at,rotated_from) '
               'VALUES(?,?,?,?,?,?,?,?,?,?)',
               (key_id, shop, name, _digest(secret), ','.join(SCOPES), ttl_days, _expiry(ttl_days), created_by, lab.iso_now(), rotated_from))
    return key_id, f'lsk_{key_id}_{secret}'


def _active_count(db, shop):
    return db.execute('SELECT count(*) FROM lab_api_keys WHERE shop_id=? AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>?)',
                      (shop, int(time.time()))).fetchone()[0]


def list_keys(principal, shop):
    _require_key_manager(principal)
    with lab.connect(lab.SOURCE_DB) as db:
        rows = db.execute('SELECT * FROM lab_api_keys WHERE shop_id=? ORDER BY created_at DESC, key_id', (shop,)).fetchall()
    return {'keys': [_public(r) for r in rows], 'scopes': list(SCOPES)}


def create(principal, shop, req):
    _require_key_manager(principal)
    if not isinstance(req, dict) or not set(req) <= {'name', 'expires_in_days'}:
        raise ValueError('Invalid request')
    name = _clean_name(req.get('name'))
    days = req.get('expires_in_days', 90)
    _expiry(days)
    with lab.connect(lab.SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        if _active_count(db, shop) >= MAX_ACTIVE_KEYS:
            raise lab.LabAuthError(409, 'Too many active keys; revoke one first')
        key_id, key = _insert(db, shop, name, days, principal.user_id or principal.kind)
        row = db.execute('SELECT * FROM lab_api_keys WHERE key_id=?', (key_id,)).fetchone()
    # The only time the full key leaves the server.
    return {'key': key, **_public(row)}


def revoke(principal, shop, req):
    _require_key_manager(principal)
    key_id = (req or {}).get('key_id')
    if not isinstance(key_id, str) or not KEY_ID_RE.fullmatch(key_id) or set(req) != {'key_id'}:
        raise ValueError('Invalid key id')
    with lab.connect(lab.SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT revoked_at FROM lab_api_keys WHERE key_id=? AND shop_id=?', (key_id, shop)).fetchone()
        if not row:
            raise lab.LabAuthError(404, 'Key not found')
        if not row['revoked_at']:
            db.execute('UPDATE lab_api_keys SET revoked_at=?, notify=0 WHERE key_id=? AND shop_id=?', (lab.iso_now(), key_id, shop))
    return {'key_id': key_id, 'status': 'revoked'}


def rotate(principal, shop, req):
    """Revoke the key and issue a replacement with the same name, scopes and lifetime."""
    _require_key_manager(principal)
    key_id = (req or {}).get('key_id')
    if not isinstance(key_id, str) or not KEY_ID_RE.fullmatch(key_id) or set(req) != {'key_id'}:
        raise ValueError('Invalid key id')
    with lab.connect(lab.SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT * FROM lab_api_keys WHERE key_id=? AND shop_id=?', (key_id, shop)).fetchone()
        if not old:
            raise lab.LabAuthError(404, 'Key not found')
        if old['revoked_at']:
            raise lab.LabAuthError(409, 'Key is already revoked')
        db.execute('UPDATE lab_api_keys SET revoked_at=?, notify=0 WHERE key_id=? AND shop_id=?', (lab.iso_now(), key_id, shop))
        new_id, key = _insert(db, shop, old['name'], old['ttl_days'], principal.user_id or principal.kind, rotated_from=key_id)
        row = db.execute('SELECT * FROM lab_api_keys WHERE key_id=?', (new_id,)).fetchone()
    return {'key': key, 'replaced': key_id, **_public(row)}


def principal(authorization, path, method):
    """Principal for 'Bearer lsk_…' on the allowed routes only; None otherwise (401)."""
    if (method, path) not in ALLOWED:
        return None
    match = KEY_RE.fullmatch(authorization[7:].strip()) if authorization.startswith('Bearer ') else None
    if not match:
        return None
    key_id, secret = match.groups()
    now = int(time.time())
    with lab.connect(lab.SOURCE_DB) as db:
        row = db.execute('SELECT k.key_hash, k.shop_id, k.revoked_at, k.expires_at FROM lab_api_keys k JOIN shops s ON s.shop_id=k.shop_id '
                         'WHERE k.key_id=? AND s.disabled=0', (key_id,)).fetchone()
        expected = row['key_hash'] if row else '0' * 64
        ok = hmac.compare_digest(_digest(secret), expected)
        if not (ok and row and not row['revoked_at'] and (row['expires_at'] is None or row['expires_at'] > now)):
            return None
        db.execute('UPDATE lab_api_keys SET last_used_at=? WHERE key_id=?', (lab.iso_now(), key_id))
    return lab.Principal('integration', row['shop_id'], role='apikey', user_id=key_id)


def is_api_key(principal):
    return principal is not None and principal.kind == 'integration' and principal.role == 'apikey'


def notify_secret(key_id):
    if not lab.signing_secret_is_safe():
        raise lab.LabAuthError(503, 'Notifications are not configured')
    return hmac.new(lab.SIGNING_SECRET.encode(), NOTIFY_PREFIX + key_id.encode(), hashlib.sha256).hexdigest()


def store_info(principal):
    with lab.connect(lab.SOURCE_DB) as db:
        shop = db.execute('SELECT shop_id, name FROM shops WHERE shop_id=? AND disabled=0', (principal.shop_id,)).fetchone()
        key = db.execute('SELECT expires_at FROM lab_api_keys WHERE key_id=?', (principal.user_id,)).fetchone()
    if not shop:
        raise lab.LabAuthError(404, 'Store unavailable')
    return {'api_version': '1', 'store_id': shop['shop_id'], 'name': shop['name'], 'currency': 'JOD', 'channel': 'web',
            'source_system': lab.source_id('web'), 'key_id': principal.user_id, 'scopes': list(SCOPES),
            'key_expires_at': key['expires_at'] if key else None}


def notifications(principal, req):
    """Turn signed change notifications on/off for THIS key. Returns the per-key
    signing secret when turning them on (server-to-server response only)."""
    if not isinstance(req, dict) or set(req) != {'enabled'} or type(req['enabled']) is not bool:
        raise ValueError('Expected {"enabled": true|false}')
    secret = notify_secret(principal.user_id) if req['enabled'] else None
    with lab.connect(lab.SOURCE_DB) as db:
        db.execute('UPDATE lab_api_keys SET notify=? WHERE key_id=? AND shop_id=? AND revoked_at IS NULL',
                   (1 if req['enabled'] else 0, principal.user_id, principal.shop_id))
    return {'enabled': req['enabled'], **({'signing_secret': secret} if secret else {})}


def subscribers(shop):
    """Active keys of this shop that asked for notifications."""
    with lab.connect(lab.SOURCE_DB) as db:
        rows = db.execute('SELECT key_id FROM lab_api_keys WHERE shop_id=? AND notify=1 AND revoked_at IS NULL '
                          'AND (expires_at IS NULL OR expires_at>?)', (shop, int(time.time()))).fetchall()
    return [r['key_id'] for r in rows]
