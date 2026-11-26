-- Diagnostic only. Not a migration. No customer data or secrets selected.
-- Review before running manually with a read-only database connection.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '10s';

-- Missing entries here explain read failures on the Connect page.
WITH required(table_name, column_name, migration) AS (VALUES
  ('pos_providers','code','007_pos_connect.sql'),
  ('pos_providers','capabilities','007_pos_connect.sql'),
  ('pos_connections','id','007_pos_connect.sql'),
  ('pos_connections','account_ref','008_pos_identity_inventory.sql'),
  ('pos_sync_jobs','id','007_pos_connect.sql'),
  ('pos_sync_errors','status','007_pos_connect.sql'),
  ('pos_source_records','provider_code','008_pos_identity_inventory.sql'),
  ('pos_source_records','account_ref','008_pos_identity_inventory.sql'),
  ('pos_source_records','entity','007_pos_connect.sql'),
  ('sales','pos_connection_id','007_pos_connect.sql'),
  ('products','pos_connection_id','007_pos_connect.sql'),
  ('sales','channel','009_pos_channels_webhooks.sql'),
  ('pos_webhook_deliveries','event_id','009_pos_channels_webhooks.sql')
)
SELECT r.*, c.column_name IS NOT NULL AS present
FROM required r LEFT JOIN information_schema.columns c
  ON c.table_schema='public' AND c.table_name=r.table_name AND c.column_name=r.column_name
ORDER BY r.migration,r.table_name,r.column_name;

-- 010 must leave a UNIQUE identity index using entity, NOT event_type.
SELECT indexname,indexdef FROM pg_indexes
WHERE schemaname='public' AND tablename='pos_source_records';

SELECT tablename,rowsecurity FROM pg_tables
WHERE schemaname='public' AND tablename LIKE 'pos_%';

-- Ledger existence only; inspect full filename entries separately if present.
SELECT to_regclass('public.schema_migrations') AS migration_ledger;
ROLLBACK;
