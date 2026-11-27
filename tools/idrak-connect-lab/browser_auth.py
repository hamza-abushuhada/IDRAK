"""Short-lived browser sessions; never persist a credential in the cookie.

Two kinds of signed, HttpOnly, SameSite=Strict cookie:
- user sessions (primary): email + password accounts from lab_users, bound to
  one shop and re-validated on every request (membership, role, password,
  disabled flag and logout epoch), so revocation is immediate;
- token sessions (restricted admin/test path): the shop token, kept for
  testing only and disabled with IDRAK_LAB_TOKEN_LOGIN=off.
"""
import base64
import hashlib
import hmac
import json
import os
from http.cookies import SimpleCookie, CookieError
import time

import demo_server as lab
import lab_users

COOKIE = 'idrak_lab_session'
TTL = 8 * 60 * 60


def token_login_enabled():
    return os.environ.get('IDRAK_LAB_TOKEN_LOGIN', 'on').lower() != 'off'


def fingerprint(shop):
    with lab.connect(lab.SOURCE_DB) as db:
        row = db.execute('SELECT token_hash,disabled FROM shops WHERE shop_id=?', (shop,)).fetchone()
    if not row or row['disabled'] or not row['token_hash']:
        return None
    # Do not expose the database token hash in the cookie either.
    return hmac.new(lab.SIGNING_SECRET.encode(), row['token_hash'].encode(), hashlib.sha256).hexdigest()


def user_fingerprint(user_id, shop, state):
    material = '\x1f'.join(['user', user_id, shop, state['role'], str(state['epoch']), state['password_hash']])
    return hmac.new(lab.SIGNING_SECRET.encode(), material.encode(), hashlib.sha256).hexdigest()


def signature(payload):
    return hmac.new(lab.SIGNING_SECRET.encode(), b'browser-session:' + payload.encode(), hashlib.sha256).hexdigest()


def _seal(items):
    payload = base64.urlsafe_b64encode(json.dumps(items).encode()).decode()
    return payload + '.' + signature(payload)


def login(token):
    """Token session (restricted admin/test path)."""
    if not token_login_enabled():
        raise lab.LabAuthError(403, 'Token sign-in is disabled')
    if not isinstance(token, str) or len(token) > 512:
        raise lab.LabAuthError(401, 'Invalid shop credential')
    principal = lab.authenticate_bearer('Bearer ' + token)
    return _seal([principal.shop_id, int(time.time()) + TTL, fingerprint(principal.shop_id)])


def user_session(user_id, shop):
    state = lab_users.session_state(user_id, shop)
    if not state:
        raise lab.LabAuthError(401, lab_users.GENERIC_LOGIN_ERROR)
    return _seal(['u', user_id, shop, int(time.time()) + TTL, user_fingerprint(user_id, shop, state)])


def authenticate(cookie):
    try:
        jar = SimpleCookie()
        jar.load(cookie or '')
        value = jar[COOKIE].value
        payload, mac = value.rsplit('.', 1)
        if len(value) > 1024 or not hmac.compare_digest(signature(payload), mac):
            return None
        items = json.loads(base64.urlsafe_b64decode(payload))
        if items and items[0] == 'u':
            _, user_id, shop, expires, version = items
            if type(expires) is not int or expires <= time.time() or not isinstance(user_id, str) or not isinstance(shop, str):
                return None
            state = lab_users.session_state(user_id, shop)
            if not state or not hmac.compare_digest(user_fingerprint(user_id, shop, state), version):
                return None
            return lab.Principal('shop', shop, role=state['role'], user_id=user_id)
        if not token_login_enabled():
            return None
        shop, expires, version = items
        if type(expires) is not int or expires <= time.time() or not isinstance(shop, str):
            return None
        current = fingerprint(shop)
        if not current or not hmac.compare_digest(current, version):
            return None
        return lab.Principal('shop', shop, role='owner')
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


# ---- shared /auth/* handling for both server entrypoints --------------------
PUBLIC_AUTH_PATHS = ('/auth/login', '/auth/activate', '/auth/invite')


def handle_auth_post(path, body, principal, client):
    """Returns (status, json_body, cookie_value_or_None). cookie '' clears it."""
    if path == '/auth/login':
        if 'token' in body:  # restricted admin/test path
            if set(body) != {'token'}:
                raise ValueError('Invalid request')
            return 200, {'ok': True}, login(body.get('token'))
        if not set(body) <= {'email', 'password', 'shop_id'}:
            raise ValueError('Invalid request')
        user_id, shop = lab_users.login(body.get('email'), body.get('password'), client, body.get('shop_id'))
        return 200, {'ok': True}, user_session(user_id, shop)
    if path == '/auth/logout':
        if principal is not None and principal.user_id:
            lab_users.logout(principal.user_id)  # revokes every session of this user
        return 200, {'ok': True}, ''
    if path == '/auth/invite':  # read-only: what an invite link is for
        return 200, lab_users.invite_info(body.get('token')), None
    if path == '/auth/activate':
        if set(body) != {'token', 'password'}:
            raise ValueError('Invalid request')
        user_id, shop = lab_users.activate(body.get('token'), body.get('password'), client)
        return 200, {'ok': True}, user_session(user_id, shop)
    if path == '/auth/switch-shop':
        if principal is None or not principal.user_id:
            raise lab.LabAuthError(403, 'Only signed-in users can switch shops')
        return 200, {'ok': True}, user_session(principal.user_id, body.get('shop_id'))
    raise LookupError(path)


def session_info(principal, x_shop):
    shop = lab.effective_shop(principal, x_shop)
    with lab.connect(lab.SOURCE_DB) as db:
        name = db.execute('SELECT name FROM shops WHERE shop_id=?', (shop,)).fetchone()['name']
        info = {'name': name, 'shop_id': shop, 'kind': principal.kind, 'role': principal.role or 'owner'}
        if principal.user_id:
            info['email'] = db.execute('SELECT email FROM lab_users WHERE user_id=?', (principal.user_id,)).fetchone()['email']
            info['shops'] = lab_users.memberships(db, principal.user_id)
            info['via'] = 'password'
        elif principal.kind == 'shop':
            info['via'] = 'token'
    return info
