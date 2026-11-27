-- Additive credential registry for paired Lab shops only. Existing connections
-- and data are unchanged. Review/apply separately; never run automatically.
-- One shop has one organization, including after connection disconnect/purge.
CREATE TABLE IF NOT EXISTS pos_lab_bindings (
  shop_id text PRIMARY KEY CHECK (shop_id ~ '^[a-z0-9][a-z0-9-]{0,63}$'),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  credentials_encrypted text NOT NULL,
  created_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pos_lab_bindings_org_idx ON pos_lab_bindings(org_id);
ALTER TABLE pos_lab_bindings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON pos_lab_bindings FROM PUBLIC, anon, authenticated;
