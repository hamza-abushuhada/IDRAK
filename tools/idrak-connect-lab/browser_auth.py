"""Short-lived browser sessions; never persist the API bearer credential."""
import base64
import hashlib
import hmac
import json
from http.cookies import SimpleCookie, CookieError
import time

import demo_server as lab

COOKIE = 'idrak_lab_session'
TTL = 8 * 60 * 60


def fingerprint(shop):
    with lab.connect(lab.SOURCE_DB) as db:
        row = db.execute('SELECT token_hash,disabled FROM shops WHERE shop_id=?', (shop,)).fetchone()
    if not row or row['disabled'] or not row['token_hash']:
        return None
    # Do not expose the database token hash in the cookie either.
    return hmac.new(lab.SIGNING_SECRET.encode(), row['token_hash'].encode(), hashlib.sha256).hexdigest()


def signature(payload):
    return hmac.new(lab.SIGNING_SECRET.encode(), b'browser-session:' + payload.encode(), hashlib.sha256).hexdigest()


def login(token):
    if not isinstance(token, str) or len(token) > 512:
        raise lab.LabAuthError(401, 'Invalid shop credential')
    principal = lab.authenticate_bearer('Bearer ' + token)
    payload = base64.urlsafe_b64encode(json.dumps([principal.shop_id, int(time.time()) + TTL, fingerprint(principal.shop_id)]).encode()).decode()
    return payload + '.' + signature(payload)


def authenticate(cookie):
    try:
        jar = SimpleCookie()
        jar.load(cookie or '')
        value = jar[COOKIE].value
        payload, mac = value.rsplit('.', 1)
        if len(value) > 1024 or not hmac.compare_digest(signature(payload), mac):
            return None
        shop, expires, version = json.loads(base64.urlsafe_b64decode(payload))
        if type(expires) is not int or expires <= time.time() or not isinstance(shop, str):
            return None
        current = fingerprint(shop)
        if not current or not hmac.compare_digest(current, version):
            return None
        return lab.Principal('shop', shop)
    except (ValueError, TypeError, KeyError, CookieError):
        return None


def cookie_header(value, secure=True):
    return f'{COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={TTL if value else 0}' + ('; Secure' if secure else '')


def same_origin(headers, origin, cookie_auth=False):
    if headers.get('sec-fetch-site', '').lower() == 'cross-site':
        return False
    supplied = headers.get('origin')
    if supplied:
        return supplied.rstrip('/') == origin.rstrip('/')
    referer = headers.get('referer')
    if referer:
        from urllib.parse import urlsplit
        parsed = urlsplit(referer)
        return f'{parsed.scheme}://{parsed.netloc}' == origin.rstrip('/')
    return not cookie_auth
