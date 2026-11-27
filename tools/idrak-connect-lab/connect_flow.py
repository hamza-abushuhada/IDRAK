"""Redirect authorization for linking a Lab shop to IDRAK (no copy/paste).

Flow: IDRAK sends the browser to /connect#request=<signed intent>&state=<random>.
The shop owner signs in with their own Lab account (never an IDRAK account),
picks one of the shops they own, and explicitly approves. The Lab then issues
the same single-use pairing code as the manual flow and sends the browser back
to a FIXED IDRAK callback (configured here, never taken from the request):

    <IDRAK_CONNECT_RETURN_ORIGIN>/<ar|en>/app/integrations/callback#code=..&state=..

IDRAK's server then redeems the code server-to-server (pairing.exchange).

Built on the pairing-code protections, plus:
- the intent is HMAC-signed by IDRAK and bound to its org + user, carries
  sha256(state), and is single-use: one approval per request, ever;
- the state must hash to the value signed into the intent, so neither the
  state nor the return target can be swapped;
- approval needs an email/password Lab user who is an OWNER of the chosen
  shop at that moment (membership re-checked in the same transaction), so
  cashiers, removed users and other shops' owners cannot approve;
- a shop bound to another IDRAK organization is refused;
- parameters travel only in URL fragments (never sent to servers or logs).
"""
import hashlib
import hmac
import os
import re
import secrets
import time
from urllib.parse import urlencode

import demo_server as lab
import pairing

RETURN_ENV = 'IDRAK_CONNECT_RETURN_ORIGIN'
STATE_RE = re.compile(r'[A-Za-z0-9_-]{43}')
LOCALES = ('ar', 'en')
CALLBACK_PATH = '/app/integrations/callback'


def return_origin():
    """The only IDRAK origin the browser may be sent back to. Unset/invalid → disabled."""
    value = os.environ.get(RETURN_ENV, '')
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(value)
        host = parts.hostname or ''
        if (parts.scheme != 'https' or not host or parts.username or parts.password or parts.port not in (None, 443)
                or parts.path not in ('', '/') or parts.query or parts.fragment or value != value.strip()
                or not re.fullmatch(r'[a-z0-9.-]{1,253}', host) or '.' not in host):
            raise ValueError()
        return 'https://' + host
    except ValueError:
        raise lab.LabAuthError(503, 'Linking with IDRAK is not configured') from None


def read_request(intent, state):
    data = pairing.read_intent(intent)
    if data.get('flow') != 'redirect' or data.get('lang') not in LOCALES:
        raise lab.LabAuthError(400, 'Invalid or expired pairing request')
    sh = data.get('sh')
    if not isinstance(state, str) or not STATE_RE.fullmatch(state) or not isinstance(sh, str) \
            or not hmac.compare_digest(hashlib.sha256(state.encode()).hexdigest(), sh):
        raise lab.LabAuthError(400, 'Invalid or expired pairing request')
    return data


def callback_url(data, params):
    return f"{return_origin()}/{data['lang']}{CALLBACK_PATH}#{urlencode(params)}"


def require_user(principal):
    """Only email/password Lab accounts can authorize (not tokens or operators)."""
    if principal is None or principal.kind != 'shop' or not principal.user_id:
        raise lab.LabAuthError(401, 'Sign in to your POS account first')
    return principal.user_id


def _consumed(db, intent):
    return db.execute('SELECT 1 FROM lab_pairing_codes WHERE intent_hash=?', (pairing.digest(intent),)).fetchone() is not None


def _business_name(data):
    name = data.get('name')
    return ' '.join(name.split())[:80] if isinstance(name, str) else ''


def context(principal, body):
    """What the consent screen shows. Never reveals another user's shops."""
    if set(body) != {'intent', 'state'}:
        raise lab.LabAuthError(400, 'Invalid request')
    origin = return_origin()
    user_id = require_user(principal)
    data = read_request(body['intent'], body['state'])
    import lab_users
    with lab.connect(lab.SOURCE_DB) as db:
        if _consumed(db, body['intent']):
            raise lab.LabAuthError(409, 'This request was already used')
        email = db.execute('SELECT email FROM lab_users WHERE user_id=?', (user_id,)).fetchone()['email']
        shops = []
        for m in lab_users.memberships(db, user_id):
            bound = db.execute('SELECT org_id FROM lab_bindings WHERE shop_id=?', (m['shop_id'],)).fetchone()
            other = bool(bound and bound['org_id'] != data['org'])
            shops.append({'shop_id': m['shop_id'], 'name': m['name'], 'role': m['role'],
                          'linked_here': bool(bound and not other), 'linked_elsewhere': other,
                          'can_approve': m['role'] == 'owner' and not other})
    return {'business': _business_name(data), 'lang': data['lang'], 'email': email, 'expires_at': data['exp'],
            'shops': shops, 'idrak_origin': origin,
            'cancel_url': callback_url(data, {'error': 'access_denied', 'state': body['state']}),
            # Start over from IDRAK (e.g. the request expired while on this page). No parameters.
            'retry_url': f"{origin}/{data['lang']}/app/integrations?connect=lab"}


def approve(principal, body):
    """Explicit owner approval → single-use code, returned only inside the fixed callback URL."""
    if set(body) != {'intent', 'state', 'shop_id'}:
        raise lab.LabAuthError(400, 'Invalid request')
    return_origin()
    user_id = require_user(principal)
    intent, state, shop = body['intent'], body['state'], body['shop_id']
    data = read_request(intent, state)
    if not isinstance(shop, str) or not lab.SHOP_ID_RE.fullmatch(shop):
        raise lab.LabAuthError(400, 'Choose a shop')
    code = secrets.token_urlsafe(32)
    now = int(time.time())
    expires = min(data['exp'], now + pairing.TTL)
    with lab.connect(lab.SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        member = db.execute('SELECT m.role FROM lab_user_shops m JOIN lab_users u ON u.user_id=m.user_id '
                            'JOIN shops s ON s.shop_id=m.shop_id WHERE m.user_id=? AND m.shop_id=? '
                            'AND u.disabled=0 AND s.disabled=0', (user_id, shop)).fetchone()
        if not member:
            raise lab.LabAuthError(403, 'You do not have access to this shop')
        if member['role'] != 'owner':
            raise lab.LabAuthError(403, 'Only the shop owner can approve linking')
        if _consumed(db, intent):
            raise lab.LabAuthError(409, 'This request was already used')
        binding = db.execute('SELECT org_id FROM lab_bindings WHERE shop_id=?', (shop,)).fetchone()
        if binding and binding['org_id'] != data['org']:
            raise lab.LabAuthError(409, 'Shop is already linked to another organization')
        db.execute('DELETE FROM lab_pairing_codes WHERE expires_at<?', (now,))
        # Supersede (but keep, so they can never be approved again) other pending codes for this shop.
        db.execute('UPDATE lab_pairing_codes SET used=1 WHERE shop_id=? AND used=0', (shop,))
        db.execute('INSERT INTO lab_pairing_codes(code_hash,shop_id,org_id,user_id,intent_hash,expires_at) VALUES(?,?,?,?,?,?)',
                   (pairing.digest(code), shop, data['org'], data['user'], pairing.digest(intent), expires))
    return {'redirect': callback_url(data, {'code': code, 'state': state})}


def handle(principal, path, body):
    if path == '/api/connect/context':
        return context(principal, body)
    if path == '/api/connect/approve':
        return approve(principal, body)
    raise lab.RouteNotFound(path)


PATHS = ('/api/connect/context', '/api/connect/approve')
