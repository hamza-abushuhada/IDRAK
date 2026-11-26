"""Server-only pairing and encrypted Lab credentials. No caller-supplied origins."""
import base64
import hashlib
import hmac
import json
import os
import time
from uuid import uuid4, UUID

from cryptography.fernet import Fernet, InvalidToken
import httpx
from fastapi import HTTPException

from ... import db

LAB_ORIGIN = 'https://idrak-connect-lab.vercel.app'
TTL = 300


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


def new_intent(org_id, user_id):
    cipher()  # Fail before issuing a request that cannot be persisted securely.
    data = {'aud': 'idrak-lab-pairing-v1', 'org': str(org_id), 'user': str(user_id),
            'nonce': str(uuid4()), 'exp': int(time.time()) + TTL}
    encoded = base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode()).decode()
    signature = hmac.new(key(), b'intent:' + encoded.encode(), hashlib.sha256).hexdigest()
    return {'intent': encoded + '.' + signature, 'expires_at': data['exp']}


def validate_intent(value, org_id, user_id):
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
        if type(data['exp']) is not int or not time.time() < data['exp'] <= time.time() + TTL + 5:
            raise ValueError()
        UUID(data['nonce'])
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


async def exchange_remote(code, intent):
    raw = json.dumps({'code': code, 'intent': intent, 'timestamp': int(time.time())}, separators=(',', ':')).encode()
    authorization = 'LabPairing ' + hmac.new(key(), b'exchange:' + raw, hashlib.sha256).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = await client.post(LAB_ORIGIN + '/service/pairing/exchange', content=raw,
                                         headers={'Authorization': authorization, 'Content-Type': 'application/json'})
        if response.status_code in (400, 401, 403, 409):
            raise HTTPException(409, 'Pairing code is invalid, expired, already used or belongs to another organization')
        if response.status_code != 200 or len(response.content) > 10000:
            raise ValueError()
        return response.json()
    except (httpx.HTTPError, ValueError):
        # Never include upstream bodies, headers, credentials or exception strings.
        raise HTTPException(502, 'Lab pairing service unavailable; request a new pairing code') from None


async def redeem(code, intent, ctx):
    validate_intent(intent, ctx.org_id, ctx.user.id)
    encryption = cipher()
    credentials = validate_credentials(await exchange_remote(code, intent), ctx.org_id)
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
                      'auto_sync': True, 'base_url': LAB_ORIGIN}
            if row:
                cid = row['id']
                await c.execute("UPDATE pos_connections SET status='connected',config=$3,updated_at=now() WHERE id=$1 AND org_id=$2",
                                cid, ctx.org_id, config)
            else:
                cid = await c.fetchval('''INSERT INTO pos_connections(org_id,provider_code,account_ref,display_name,status,config,created_by)
                                          VALUES($1,$2,$3,$4,'connected',$5,$6) RETURNING id''',
                                       ctx.org_id, provider, shop, 'Paired Lab ' + provider, config, ctx.user.id)
            connections.append({'id': str(cid), 'provider_code': provider})
    await db.audit(ctx.org_id, ctx.user.id, 'pos.lab_paired', 'lab_shop', shop, {'connections': connections})
    return {'shop_id': shop, 'connections': connections}


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
