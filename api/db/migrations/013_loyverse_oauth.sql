-- Loyverse POS connector (additive). Review/apply separately; never run automatically.
-- Existing connections, sales and the Lab/Demo connectors are unchanged.

-- Encrypted OAuth credentials per vendor account. One vendor account belongs to
-- exactly one organization (primary key), including after disconnect; tokens are
-- wiped (NULL) on disconnect, the binding stays.
CREATE TABLE IF NOT EXISTS pos_oauth_credentials (
  provider_code text NOT NULL REFERENCES pos_providers(code),
  account_ref text NOT NULL CHECK (account_ref ~ '^[A-Za-z0-9-]{1,64}$'),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  credentials_encrypted text,
  webhook_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (provider_code, account_ref)
);
CREATE INDEX IF NOT EXISTS pos_oauth_credentials_org_idx ON pos_oauth_credentials(org_id);
ALTER TABLE pos_oauth_credentials ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON pos_oauth_credentials FROM PUBLIC, anon, authenticated;

-- Catalog entry. Deliberately NOT "available"/implemented for users: the wizard
-- only offers Loyverse when the server is configured (LOYVERSE_ENABLED=on with
-- registered app credentials) after a real integration has been proven.
INSERT INTO pos_providers (code, name, name_ar, category, status, is_implemented, capabilities, description, description_ar, sort)
VALUES ('loyverse', 'Loyverse POS', 'Loyverse POS', 'cloud_api', 'coming_soon', false,
        '{"initial_import": true, "incremental": true, "refunds": true, "webhook": true, "inventory": false}'::jsonb,
        'Loyverse POS via OAuth 2.0: receipts, refunds and cancellations, with signed webhooks.',
        'Loyverse POS عبر OAuth 2.0: الفواتير والمرتجعات والإلغاءات مع إشعارات موقّعة.', 40)
ON CONFLICT (code) DO NOTHING;
