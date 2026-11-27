"""Lab-only pairing protocol. No IDRAK imports, arbitrary destinations or plaintext credentials."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

import demo_server as lab

TTL = 300
DDL = '''
CREATE TABLE IF NOT EXISTS lab_pairing_codes (
  code_hash TEXT PRIMARY KEY, shop_id TEXT NOT NULL REFERENCES shops(shop_id),
  org_id TEXT NOT NULL, user_id TEXT NOT NULL, intent_hash TEXT NOT NULL,
  expires_at BIGINT NOT NULL, used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS lab_bindings (
  shop_id TEXT PRIMARY KEY REFERENCES shops(shop_id), org_id TEXT NOT NULL,
  integration_token_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
'''


def key():
    value = os.environ.get('IDRAK_LAB_PAIRING_KEY', '')
    if len(value) < 32 or value == lab.SIGNING_SECRET:
        raise lab.LabAuthError(503, 'Pairing is not configured')
    return value.encode()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def read_intent(value):
    signing_key = key()
    try:
        if not isinstance(value, str) or len(value) > 2048:
            raise ValueError()
        encoded, signature = value.split('.')
        expected = hmac.new(signing_key, b'intent:' + encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(encoded))
        if data['aud'] != 'idrak-lab-pairing-v1' or type(data['exp']) is not int or not time.time() < data['exp'] <= time.time() + TTL + 5:
            raise ValueError()
        from uuid import UUID
        for field in ('org', 'user', 'nonce'):
            UUID(data[field])
        return data
    except (ValueError, KeyError, TypeError):
        raise lab.LabAuthError(400, 'Invalid or expired pairing request') from None


def issue(principal, intent):
    if principal.kind != 'shop':
        raise lab.LabAuthError(403, 'Sign in to the shop first')
    data = read_intent(intent)
    code = secrets.token_urlsafe(32)
    expires = min(data['exp'], int(time.time()) + TTL)
    with lab.connect(lab.SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        binding = db.execute('SELECT org_id FROM lab_bindings WHERE shop_id=?', (principal.shop_id,)).fetchone()
        if binding and binding['org_id'] != data['org']:
            raise lab.LabAuthError(409, 'Shop is already linked to another organization')
        # A new request supersedes outstanding codes for this shop.
        db.execute('DELETE FROM lab_pairing_codes WHERE shop_id=? OR expires_at<?', (principal.shop_id, int(time.time())))
        db.execute('INSERT INTO lab_pairing_codes(code_hash,shop_id,org_id,user_id,intent_hash,expires_at) VALUES(?,?,?,?,?,?)',
                   (digest(code), principal.shop_id, data['org'], data['user'], digest(intent), expires))
    return {'code': code, 'expires_at': expires}


def service_signature(raw):
    return 'LabPairing ' + hmac.new(key(), b'exchange:' + raw, hashlib.sha256).hexdigest()


def exchange(raw, authorization):
    if not hmac.compare_digest(service_signature(raw), authorization or ''):
        raise lab.LabAuthError(401, 'Invalid pairing service authentication')
    try:
        body = json.loads(raw)
        if set(body) != {'code', 'intent', 'timestamp'} or type(body['timestamp']) is not int or abs(time.time() - body['timestamp']) > 60:
            raise ValueError()
        code, intent = body['code'], body['intent']
        if not isinstance(code, str) or not 20 <= len(code) <= 128:
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise lab.LabAuthError(400, 'Invalid pairing exchange') from None
    data = read_intent(intent)
    with lab.connect(lab.SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM lab_pairing_codes WHERE code_hash=?', (digest(code),)).fetchone()
        if not row or row['used'] or row['expires_at'] <= time.time() or row['intent_hash'] != digest(intent) or row['org_id'] != data['org'] or row['user_id'] != data['user']:
            raise lab.LabAuthError(409, 'Pairing code is invalid, expired or already used')
        shop = row['shop_id']
        enabled = db.execute('SELECT 1 FROM shops WHERE shop_id=? AND disabled=0', (shop,)).fetchone()
        if not enabled:
            raise lab.LabAuthError(409, 'Shop is unavailable')
        binding = db.execute('SELECT org_id FROM lab_bindings WHERE shop_id=?', (shop,)).fetchone()
        if binding and binding['org_id'] != data['org']:
            raise lab.LabAuthError(409, 'Shop is already linked to another organization')
        secret = secrets.token_urlsafe(32)
        db.execute('INSERT INTO lab_bindings(shop_id,org_id,integration_token_hash,created_at) VALUES(?,?,?,?) '
                   'ON CONFLICT(shop_id) DO UPDATE SET integration_token_hash=excluded.integration_token_hash',
                   (shop, data['org'], digest(secret), lab.iso_now()))
        db.execute('UPDATE lab_pairing_codes SET used=1 WHERE code_hash=?', (digest(code),))
    # This response is server-to-server only. Never forward it to the browser.
    return {'shop_id': shop, 'org_id': data['org'], 'token': f'lc.{shop}.{secret}', 'webhook_secret': lab.shop_secret(shop)}


def integration_principal(authorization, path, method):
    if not authorization.startswith('Bearer lc.'):
        return None
    if method != 'GET' or path not in ('/api/pos/events', '/api/web/events'):
        return None
    parts = authorization[7:].split('.')
    if len(parts) != 3 or not lab.SHOP_ID_RE.fullmatch(parts[1]):
        return None
    with lab.connect(lab.SOURCE_DB) as db:
        row = db.execute('SELECT b.integration_token_hash FROM lab_bindings b JOIN shops s ON s.shop_id=b.shop_id '
                         'WHERE b.shop_id=? AND s.disabled=0', (parts[1],)).fetchone()
    if row and hmac.compare_digest(row['integration_token_hash'], digest(parts[2])):
        return lab.Principal('integration', parts[1])
    return None
