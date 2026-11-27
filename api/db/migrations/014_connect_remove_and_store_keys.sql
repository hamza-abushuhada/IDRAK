-- IDRAK Connect: "Remove system" + online-store API keys (additive). Review/apply
-- separately; never run automatically. No existing row, sale, cursor or credential
-- is modified by this migration.

-- 1) Remove = disconnect + hide from the active systems list. Sales, returns, sync
--    history, source records and audit entries are kept. Any reconnect of the same
--    connection (status leaves 'disconnected') clears the flag automatically.
ALTER TABLE pos_connections ADD COLUMN IF NOT EXISTS removed_at timestamptz;

CREATE OR REPLACE FUNCTION pos_connections_clear_removed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.removed_at := NULL;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS pos_connections_clear_removed ON pos_connections;
CREATE TRIGGER pos_connections_clear_removed
  BEFORE UPDATE ON pos_connections
  FOR EACH ROW WHEN (NEW.status <> 'disconnected' AND NEW.removed_at IS NOT NULL)
  EXECUTE FUNCTION pos_connections_clear_removed();

-- 2) Encrypted API-key credentials for an online store (IDRAK Connect Lab store
--    first). One store belongs to exactly one organization, including after
--    disconnect: the key itself is wiped (NULL) on disconnect, the binding stays.
CREATE TABLE IF NOT EXISTS pos_store_key_credentials (
  shop_id text PRIMARY KEY CHECK (shop_id ~ '^[a-z0-9][a-z0-9-]{0,63}$'),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  key_id text NOT NULL CHECK (key_id ~ '^[a-f0-9]{12}$'),
  credentials_encrypted text,
  created_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pos_store_key_credentials_org_idx ON pos_store_key_credentials(org_id);
ALTER TABLE pos_store_key_credentials ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON pos_store_key_credentials FROM PUBLIC, anon, authenticated;

-- 3) Replay protection for signed store notifications (each nonce accepted once).
CREATE TABLE IF NOT EXISTS pos_notify_nonces (
  nonce text PRIMARY KEY,
  seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pos_notify_nonces_seen_idx ON pos_notify_nonces(seen_at);
ALTER TABLE pos_notify_nonces ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON pos_notify_nonces FROM PUBLIC, anon, authenticated;
