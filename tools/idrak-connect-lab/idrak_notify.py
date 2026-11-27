"""Tell IDRAK that a PAIRED shop has new sales, so it can pull them right away.

- Sent only for shops bound to an IDRAK organization (lab_bindings), only to the
  single address in IDRAK_CONNECT_NOTIFY_URL (HTTPS, fixed path, no redirects).
  Unset -> nothing is ever sent.
- Carries no sales data: shop id, organization id, channel, time and a random
  nonce, signed with the shop's own webhook secret (the same per-shop key IDRAK
  received at pairing). IDRAK verifies it and pulls the events itself.
- Never breaks a sale: failures are logged (status only) and the next sale or a
  manual "Sync now" in IDRAK catches up from the saved cursor.
"""
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import demo_server as lab

log = logging.getLogger(__name__)
PATH = '/integrations/lab/notify'
TIMEOUT = 20
SIG_PREFIX = b'idrak-lab-notify:'


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def target():
    value = os.environ.get('IDRAK_CONNECT_NOTIFY_URL', '').strip()
    if not value:
        return None
    parts = urlsplit(value)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443)
            or parts.path != PATH or parts.query or parts.fragment):
        log.warning('IDRAK_CONNECT_NOTIFY_URL is not a valid HTTPS notify address; notifications disabled')
        return None
    return f'https://{parts.hostname}{PATH}'


def body_for(shop, org_id, channel):
    return json.dumps({'shop_id': shop, 'org_id': org_id, 'channel': channel, 'ts': int(time.time()),
                       'nonce': secrets.token_urlsafe(16)}, separators=(',', ':')).encode()


def signature(shop, raw):
    return hmac.new(lab.shop_secret(shop).encode(), SIG_PREFIX + raw, hashlib.sha256).hexdigest()


def notify(shop, channel, opener=None):
    """Best effort, never raises. Returns the HTTP status (or None if not sent)."""
    try:
        url = target()
        if not url or channel not in ('pos', 'web'):
            return None
        with lab.connect(lab.SOURCE_DB) as db:
            row = db.execute('SELECT org_id FROM lab_bindings WHERE shop_id=?', (shop,)).fetchone()
        if not row:
            return None  # not linked to IDRAK
        raw = body_for(shop, row['org_id'], channel)
        request = Request(url, data=raw, method='POST', headers={
            'Content-Type': 'application/json', 'X-Idrak-Signature': signature(shop, raw), 'User-Agent': 'IDRAK-Connect-Lab'})
        opener = opener or build_opener(_NoRedirect)
        for attempt in range(2):
            try:
                with opener.open(request, timeout=TIMEOUT) as response:
                    return response.status
            except HTTPError as exc:
                if exc.code < 500:
                    log.warning('IDRAK notify rejected: status=%s', exc.code)
                    return exc.code
                status = exc.code
            except (URLError, TimeoutError, OSError):
                status = 0
            if attempt == 0:
                time.sleep(0.5)
        log.warning('IDRAK notify failed after retry: status=%s', status)
        return status
    except Exception as exc:  # noqa: BLE001 - a sale must never fail because of IDRAK
        log.warning('IDRAK notify error: %s', type(exc).__name__)
        return None
