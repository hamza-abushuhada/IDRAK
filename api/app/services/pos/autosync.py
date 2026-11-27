"""Automatic sync for paired Lab shops, triggered by a signed notification.

The Lab (an independent POS) calls POST /integrations/lab/notify right after a
sale or order change. The notification carries no sales data: it is only a
signed "something changed for shop S" signal. IDRAK then PULLS the new events
through the normal, cursor-based sync with the shop's own credentials, so:

- authenticity: HMAC-SHA256 with the per-shop webhook secret that only the Lab
  and IDRAK hold (stored encrypted in pos_lab_bindings); timestamp window;
- isolation: the shop resolves to exactly one organization through its
  immutable binding, and only that organization's connection for that shop
  and channel can run;
- duplicates: the pull reuses run_sync (per-organization advisory lock plus
  source-record identity), so repeated or concurrent notifications never double
  an invoice;
- opt-in: runs only when the global switch POS_AUTOSYNC_WEBHOOKS=on AND the
  connection has config.autosync == 'webhook' (set by an operator, per
  connection). Everything else, including Demo POS, is unaffected;
- failures: a missed notification loses nothing; the next notification or a
  manual Sync Now pulls everything after the saved cursor.
"""
import hashlib
import hmac
import json
import logging
import os
import re
import time

from ... import db

log = logging.getLogger(__name__)
MAX_BODY = 1024
SKEW_SECONDS = 300
MAX_RUNS_PER_MINUTE = 30
_NONCE = re.compile(r'[A-Za-z0-9_-]{16,64}')
_SHOP = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')
CHANNELS = {'pos': 'lab_pos', 'web': 'lab_web'}
SIG_PREFIX = b'idrak-lab-notify:'


class Rejected(Exception):
    """Unauthenticated or malformed notification (no details are returned)."""


def enabled_globally() -> bool:
    return os.getenv('POS_AUTOSYNC_WEBHOOKS', 'off').strip().lower() == 'on'


def connection_enabled(connection: dict) -> bool:
    return (connection.get('config') or {}).get('autosync') == 'webhook'


def effective(connection: dict) -> bool:
    """Whether this connection really syncs automatically right now (for the UI)."""
    return enabled_globally() and connection_enabled(connection) and connection.get('status') == 'connected'


def signature(secret: str, raw: bytes) -> str:
    return hmac.new(secret.encode(), SIG_PREFIX + raw, hashlib.sha256).hexdigest()


def parse(raw: bytes) -> dict:
    try:
        if not raw or len(raw) > MAX_BODY:
            raise ValueError()
        body = json.loads(raw)
        if not isinstance(body, dict) or set(body) != {'shop_id', 'org_id', 'channel', 'ts', 'nonce'}:
            raise ValueError()
        if not (isinstance(body['shop_id'], str) and _SHOP.fullmatch(body['shop_id'])):
            raise ValueError()
        if body['channel'] not in CHANNELS or type(body['ts']) is not int:
            raise ValueError()
        if not (isinstance(body['nonce'], str) and _NONCE.fullmatch(body['nonce'])):
            raise ValueError()
        from uuid import UUID
        UUID(body['org_id'])
        if abs(time.time() - body['ts']) > SKEW_SECONDS:
            raise ValueError()
        return body
    except (ValueError, TypeError, KeyError):
        raise Rejected() from None


async def verify(raw: bytes, sig: str) -> tuple[dict, dict]:
    """Return (body, binding) for an authentic notification, else raise Rejected."""
    body = parse(raw)
    from . import pairing
    binding = await db.fetchrow('SELECT shop_id, org_id, credentials_encrypted FROM pos_lab_bindings WHERE shop_id=$1', body['shop_id'])
    if not binding or str(binding['org_id']) != body['org_id']:
        raise Rejected()
    try:
        creds = json.loads(pairing.cipher().decrypt(binding['credentials_encrypted'].encode()))
        creds = pairing.validate_credentials(creds, str(binding['org_id']))
    except Exception:  # noqa: BLE001 - never reveal why
        raise Rejected() from None
    if not isinstance(sig, str) or not hmac.compare_digest(signature(creds['webhook_secret'], raw), sig):
        raise Rejected()
    return body, dict(binding)


async def handle_lab_notify(raw: bytes, sig: str) -> dict:
    body, binding = await verify(raw, sig)
    if not enabled_globally():
        return {'status': 'ignored'}
    org_id = str(binding['org_id'])
    conn = await db.fetchrow(
        """select id, org_id, provider_code, account_ref, display_name, status, config, cursor
           from pos_connections
           where org_id=$1 and provider_code=$2 and account_ref=$3 and status='connected'
             and coalesce((config->>'paired_lab')::boolean, false)
           order by created_at limit 1""",
        org_id, CHANNELS[body['channel']], body['shop_id'])
    if not conn or not connection_enabled(dict(conn)):
        return {'status': 'ignored'}
    recent = await db.fetchval(
        "select count(*) from pos_sync_jobs where connection_id=$1 and trigger='webhook' and started_at > now() - interval '1 minute'",
        conn['id'])
    if recent >= MAX_RUNS_PER_MINUTE:
        return {'status': 'rate_limited'}
    from . import pipeline
    try:
        result = await pipeline.run_sync(org_id, None, dict(conn), trigger='webhook')
        return {'status': 'synced', 'imported': result.get('imported', 0), 'updated': result.get('updated', 0)}
    except Exception as exc:  # noqa: BLE001 - recorded without secrets; manual Sync Now still works
        log.warning('automatic sync failed: connection=%s error=%s', conn['id'], type(exc).__name__)
        await db.execute(
            """update pos_connections set last_sync_at=now(),
                 last_error='Automatic sync could not reach the sales system; it will retry on the next sale',
                 updated_at=now()
               where id=$1 and org_id=$2 and status='connected'""", conn['id'], org_id)
        return {'status': 'error'}
