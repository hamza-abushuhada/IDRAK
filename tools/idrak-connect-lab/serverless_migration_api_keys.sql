-- Additive Lab-only migration: store API keys (hash only). Apply explicitly to the
-- isolated Lab database. No changes to existing shops, orders, events or pairing.
CREATE TABLE IF NOT EXISTS idrak_lab_source.lab_api_keys (
  key_id TEXT PRIMARY KEY, shop_id TEXT NOT NULL REFERENCES idrak_lab_source.shops(shop_id),
  name TEXT NOT NULL, key_hash TEXT NOT NULL, scopes TEXT NOT NULL,
  ttl_days INTEGER, expires_at BIGINT, created_by TEXT, created_at TEXT NOT NULL,
  revoked_at TEXT, last_used_at TEXT, notify INTEGER NOT NULL DEFAULT 0, rotated_from TEXT
);
CREATE INDEX IF NOT EXISTS lab_api_keys_shop_idx ON idrak_lab_source.lab_api_keys(shop_id);
REVOKE ALL ON idrak_lab_source.lab_api_keys FROM PUBLIC;
