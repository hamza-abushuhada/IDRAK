-- Additive Lab-only migration. Apply explicitly to the isolated Lab database.
-- No updates to existing shops, products, orders, events or credentials.
CREATE TABLE IF NOT EXISTS idrak_lab_source.lab_pairing_codes (
  code_hash TEXT PRIMARY KEY, shop_id TEXT NOT NULL REFERENCES idrak_lab_source.shops(shop_id),
  org_id TEXT NOT NULL, user_id TEXT NOT NULL, intent_hash TEXT NOT NULL,
  expires_at BIGINT NOT NULL, used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS idrak_lab_source.lab_bindings (
  shop_id TEXT PRIMARY KEY REFERENCES idrak_lab_source.shops(shop_id), org_id TEXT NOT NULL,
  integration_token_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
REVOKE ALL ON idrak_lab_source.lab_pairing_codes,idrak_lab_source.lab_bindings FROM PUBLIC;
