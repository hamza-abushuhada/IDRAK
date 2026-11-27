-- Additive Lab-only migration: independent POS user accounts (email + password,
-- per-shop owner/cashier roles), single-use invites and login throttling.
-- Apply only to the isolated Lab database. No existing rows are changed.
-- Passwords are stored as scrypt hashes; invite tokens as SHA-256 only.
CREATE TABLE IF NOT EXISTS idrak_lab_source.lab_users (
  user_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT,
  disabled INTEGER NOT NULL DEFAULT 0, session_epoch INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idrak_lab_source.lab_user_shops (
  user_id TEXT NOT NULL REFERENCES idrak_lab_source.lab_users(user_id),
  shop_id TEXT NOT NULL REFERENCES idrak_lab_source.shops(shop_id),
  role TEXT NOT NULL CHECK (role IN ('owner','cashier')), created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, shop_id)
);
CREATE INDEX IF NOT EXISTS lab_user_shops_shop_idx ON idrak_lab_source.lab_user_shops(shop_id);
CREATE TABLE IF NOT EXISTS idrak_lab_source.lab_user_invites (
  token_hash TEXT PRIMARY KEY, email TEXT NOT NULL,
  shop_id TEXT NOT NULL REFERENCES idrak_lab_source.shops(shop_id),
  role TEXT NOT NULL CHECK (role IN ('owner','cashier')), expires_at BIGINT NOT NULL,
  used_at BIGINT, created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idrak_lab_source.lab_login_throttle (
  key TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0,
  window_start BIGINT NOT NULL, locked_until BIGINT NOT NULL DEFAULT 0
);
REVOKE ALL ON idrak_lab_source.lab_users, idrak_lab_source.lab_user_shops,
  idrak_lab_source.lab_user_invites, idrak_lab_source.lab_login_throttle FROM PUBLIC;
