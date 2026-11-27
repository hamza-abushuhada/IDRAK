"""Independent POS user accounts for the Lab: email + password, per-shop roles.

The Lab is a standalone POS. These accounts have nothing to do with IDRAK or its
Supabase Auth; linking a shop to IDRAK stays a separate pairing step.

- Passwords: stdlib scrypt (n=2^14, r=8, p=1), random 16-byte salt, never stored
  or logged in clear. Verification is constant time.
- Roles per shop: 'owner' (everything for that shop) and 'cashier' (POS only).
- Accounts are created through single-use, expiring invite links; the server
  stores only a SHA-256 of the invite token.
- Brute force: per-account and per-client throttles persisted in the database
  (works across serverless instances), generic errors, dummy hashing for
  unknown emails.
- Sessions carry a per-user epoch; logout bumps it and revokes every session.
"""
import base64
import hashlib
import hmac
import re
import secrets
import time

import demo_server as lab

ROLES = ('owner', 'cashier')
INVITE_TTL = 48 * 3600
EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}$')
PASSWORD_MIN, PASSWORD_MAX = 10, 128
# Throttles: (max failures, window seconds, lock seconds)
ACCOUNT_LIMIT = (5, 15 * 60, 15 * 60)
CLIENT_LIMIT = (30, 15 * 60, 15 * 60)
GENERIC_LOGIN_ERROR = 'Email or password is incorrect'

DDL = '''
CREATE TABLE IF NOT EXISTS lab_users (
  user_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT,
  disabled INTEGER NOT NULL DEFAULT 0, session_epoch INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_user_shops (
  user_id TEXT NOT NULL REFERENCES lab_users(user_id), shop_id TEXT NOT NULL REFERENCES shops(shop_id),
  role TEXT NOT NULL CHECK (role IN ('owner','cashier')), created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, shop_id)
);
CREATE TABLE IF NOT EXISTS lab_user_invites (
  token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, shop_id TEXT NOT NULL REFERENCES shops(shop_id),
  role TEXT NOT NULL CHECK (role IN ('owner','cashier')), expires_at BIGINT NOT NULL,
  used_at BIGINT, created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_login_throttle (
  key TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0,
  window_start BIGINT NOT NULL, locked_until BIGINT NOT NULL DEFAULT 0
);
'''


# ---- passwords ---------------------------------------------------------------
def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return 'scrypt$16384$8$1$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()


def verify_password(password, stored):
    try:
        scheme, n, r, p, salt, digest = stored.split('$')
        if scheme != 'scrypt':
            return False
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(actual, base64.b64decode(digest))
    except (ValueError, AttributeError, TypeError):
        return False


_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def check_password_policy(password):
    if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise ValueError(f'Password must be {PASSWORD_MIN}-{PASSWORD_MAX} characters')
    if password.strip() != password or len(set(password)) < 4:
        raise ValueError('Choose a stronger password')


def normalize_email(email):
    if not isinstance(email, str):
        raise ValueError('Invalid email')
    email = email.strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ValueError('Invalid email')
    return email


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


# ---- throttling --------------------------------------------------------------
def _throttle_keys(email, client):
    keys = [('acct:' + _digest(email), ACCOUNT_LIMIT)]
    if client:
        keys.append(('client:' + _digest(str(client)[:100]), CLIENT_LIMIT))
    return keys


def _locked(db, keys, now):
    for key, _ in keys:
        row = db.execute('SELECT locked_until FROM lab_login_throttle WHERE key=?', (key,)).fetchone()
        if row and row['locked_until'] > now:
            return True
    return False


def _record_failure(db, keys, now):
    for key, (limit, window, lock) in keys:
        row = db.execute('SELECT failures, window_start FROM lab_login_throttle WHERE key=?', (key,)).fetchone()
        if not row or now - row['window_start'] > window:
            failures, start = 1, now
        else:
            failures, start = row['failures'] + 1, row['window_start']
        locked = now + lock if failures >= limit else 0
        db.execute('INSERT INTO lab_login_throttle(key, failures, window_start, locked_until) VALUES(?,?,?,?) '
                   'ON CONFLICT(key) DO UPDATE SET failures=excluded.failures, window_start=excluded.window_start, '
                   'locked_until=excluded.locked_until', (key, failures, start, locked))


def _clear_account(db, email):
    db.execute('DELETE FROM lab_login_throttle WHERE key=?', ('acct:' + _digest(email),))


# ---- membership / sessions ---------------------------------------------------
def memberships(db, user_id):
    rows = db.execute('SELECT m.shop_id, m.role, s.name FROM lab_user_shops m JOIN shops s ON s.shop_id=m.shop_id '
                      'WHERE m.user_id=? AND s.disabled=0 ORDER BY s.name, m.shop_id', (user_id,))
    return [{'shop_id': r['shop_id'], 'role': r['role'], 'name': r['name']} for r in rows]


def session_state(user_id, shop_id):
    """Current authoritative state for a user session, or None if no longer valid."""
    with lab.connect(lab.SOURCE_DB) as db:
        row = db.execute('SELECT u.email, u.password_hash, u.disabled, u.session_epoch, m.role FROM lab_users u '
                         'JOIN lab_user_shops m ON m.user_id=u.user_id JOIN shops s ON s.shop_id=m.shop_id '
                         'WHERE u.user_id=? AND m.shop_id=? AND s.disabled=0', (user_id, shop_id)).fetchone()
    if not row or row['disabled'] or not row['password_hash']:
        return None
    return {'email': row['email'], 'role': row['role'], 'epoch': row['session_epoch'], 'password_hash': row['password_hash']}


def login(email, password, client=None, shop_id=None):
    """Return (user_id, shop_id) for valid credentials; raise LabAuthError otherwise."""
    try:
        email = normalize_email(email)
    except ValueError:
        raise lab.LabAuthError(401, GENERIC_LOGIN_ERROR) from None
    if not isinstance(password, str) or not 1 <= len(password) <= PASSWORD_MAX:
        raise lab.LabAuthError(401, GENERIC_LOGIN_ERROR)
    now = int(time.time())
    keys = _throttle_keys(email, client)
    with lab.connect(lab.SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        if _locked(db, keys, now):
            raise lab.LabAuthError(429, 'Too many attempts. Try again later.')
        user = db.execute('SELECT user_id, password_hash, disabled FROM lab_users WHERE email=?', (email,)).fetchone()
        ok = verify_password(password, user['password_hash'] if user and user['password_hash'] else _DUMMY_HASH)
        shops = memberships(db, user['user_id']) if user and ok and not user['disabled'] else []
        if not (user and ok and not user['disabled'] and shops):
            _record_failure(db, keys, now)
    # The failure count must persist even though login is refused, so the
    # transaction above commits before raising.
    if not shops:
        raise lab.LabAuthError(401, GENERIC_LOGIN_ERROR)
    with lab.connect(lab.SOURCE_DB) as db:
        _clear_account(db, email)
    chosen = next((s for s in shops if s['shop_id'] == shop_id), shops[0])
    return user['user_id'], chosen['shop_id']


def logout(user_id):
    """Revoke every session of this user (bumps the session epoch)."""
    with lab.connect(lab.SOURCE_DB) as db:
        db.execute('UPDATE lab_users SET session_epoch=session_epoch+1, updated_at=? WHERE user_id=?', (lab.iso_now(), user_id))


# ---- invites / activation ----------------------------------------------------
def create_invite(shop_id, email, role, created_by):
    """Single-use, expiring invite. Returns the raw token ONCE; only its hash is stored."""
    email = normalize_email(email)
    if role not in ROLES:
        raise ValueError('Invalid role')
    if not isinstance(shop_id, str) or not lab.SHOP_ID_RE.match(shop_id) or not lab.shop_exists(shop_id):
        raise ValueError('Unknown shop')
    token = secrets.token_urlsafe(32)
    with lab.connect(lab.SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        # A new invite for the same email/shop replaces older unused ones.
        db.execute('DELETE FROM lab_user_invites WHERE email=? AND shop_id=? AND used_at IS NULL', (email, shop_id))
        db.execute('INSERT INTO lab_user_invites(token_hash,email,shop_id,role,expires_at,created_by,created_at) VALUES(?,?,?,?,?,?,?)',
                   (_digest(token), email, shop_id, role, int(time.time()) + INVITE_TTL, created_by, lab.iso_now()))
    return {'token': token, 'email': email, 'shop_id': shop_id, 'role': role, 'expires_in_hours': INVITE_TTL // 3600}


def invite_info(token):
    if not isinstance(token, str) or not 20 <= len(token) <= 128:
        raise lab.LabAuthError(400, 'Invalid or expired invitation')
    with lab.connect(lab.SOURCE_DB) as db:
        row = db.execute('SELECT i.email, i.role, i.expires_at, i.used_at, s.name, '
                         '(SELECT password_hash IS NOT NULL FROM lab_users u WHERE u.email=i.email) AS has_account '
                         'FROM lab_user_invites i JOIN shops s ON s.shop_id=i.shop_id WHERE i.token_hash=? AND s.disabled=0',
                         (_digest(token),)).fetchone()
    if not row or row['used_at'] or row['expires_at'] <= time.time():
        raise lab.LabAuthError(400, 'Invalid or expired invitation')
    return {'email': row['email'], 'role': row['role'], 'shop_name': row['name'], 'has_account': bool(row['has_account'])}


def activate(token, password, client=None):
    """Accept an invite. New account: sets the password. Existing account: the
    current password must be supplied (an invite never resets a password)."""
    if not isinstance(token, str) or not 20 <= len(token) <= 128:
        raise lab.LabAuthError(400, 'Invalid or expired invitation')
    now = int(time.time())
    with lab.connect(lab.SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        # Same connection only: the PostgreSQL backend holds a schema-wide
        # advisory lock per transaction, so a nested lab.connect() would deadlock.
        inv = db.execute('SELECT i.* FROM lab_user_invites i JOIN shops s ON s.shop_id=i.shop_id '
                         'WHERE i.token_hash=? AND s.disabled=0', (_digest(token),)).fetchone()
        if not inv or inv['used_at'] or inv['expires_at'] <= now:
            raise lab.LabAuthError(400, 'Invalid or expired invitation')
        user = db.execute('SELECT user_id, password_hash, disabled FROM lab_users WHERE email=?', (inv['email'],)).fetchone()
        if user and user['disabled']:
            raise lab.LabAuthError(403, 'This account is disabled')
        if user and user['password_hash']:
            keys = _throttle_keys(inv['email'], client)
            if _locked(db, keys, now):
                raise lab.LabAuthError(429, 'Too many attempts. Try again later.')
            if not verify_password(password if isinstance(password, str) else '', user['password_hash']):
                _record_failure(db, keys, now)
                failed = True
            else:
                failed = False
            user_id = user['user_id']
        else:
            check_password_policy(password)
            failed = False
            if user:
                user_id = user['user_id']
                db.execute('UPDATE lab_users SET password_hash=?, updated_at=? WHERE user_id=?', (hash_password(password), lab.iso_now(), user_id))
            else:
                user_id = 'usr-' + secrets.token_hex(8)
                db.execute('INSERT INTO lab_users(user_id,email,password_hash,created_at,updated_at) VALUES(?,?,?,?,?)',
                           (user_id, inv['email'], hash_password(password), lab.iso_now(), lab.iso_now()))
        if not failed:
            db.execute('INSERT INTO lab_user_shops(user_id,shop_id,role,created_at) VALUES(?,?,?,?) '
                       'ON CONFLICT(user_id, shop_id) DO UPDATE SET role=excluded.role', (user_id, inv['shop_id'], inv['role'], lab.iso_now()))
            db.execute('UPDATE lab_user_invites SET used_at=? WHERE token_hash=?', (now, inv['token_hash']))
    if failed:
        raise lab.LabAuthError(401, 'Enter your existing password to accept this invitation')
    return user_id, inv['shop_id']


# ---- owner team management ---------------------------------------------------
def team(shop_id):
    with lab.connect(lab.SOURCE_DB) as db:
        members = [{'user_id': r['user_id'], 'email': r['email'], 'role': r['role'], 'active': not r['disabled']}
                   for r in db.execute('SELECT u.user_id, u.email, u.disabled, m.role FROM lab_user_shops m JOIN lab_users u '
                                       'ON u.user_id=m.user_id WHERE m.shop_id=? ORDER BY m.role DESC, u.email', (shop_id,))]
        pending = [{'email': r['email'], 'role': r['role']} for r in db.execute(
            'SELECT email, role FROM lab_user_invites WHERE shop_id=? AND used_at IS NULL AND expires_at>? ORDER BY created_at',
            (shop_id, int(time.time())))]
    return {'members': members, 'pending_invites': pending}


def remove_member(shop_id, user_id, acting_user_id):
    if user_id == acting_user_id:
        raise ValueError('You cannot remove yourself')
    with lab.connect(lab.SOURCE_DB) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT role FROM lab_user_shops WHERE shop_id=? AND user_id=?', (shop_id, user_id)).fetchone()
        if not row:
            raise ValueError('Not a member of this shop')
        if row['role'] != 'cashier':
            raise lab.LabAuthError(403, 'Only cashiers can be removed here')
        db.execute('DELETE FROM lab_user_shops WHERE shop_id=? AND user_id=?', (shop_id, user_id))
    return team(shop_id)
