-- Tax is a one-time business fact (like tax_number), not a per-import-batch
-- choice. Moves tax_mode/tax_rate off import_batches.contract onto the org.
alter table organizations
  add column if not exists tax_mode text not null default 'none',
  add column if not exists tax_rate numeric(5,2);

-- ADD CONSTRAINT has no IF NOT EXISTS in Postgres; drop first (if present) so
-- this migration can be re-run, matching the drop-before-add pattern used
-- elsewhere (e.g. 008_pos_identity_inventory.sql).
alter table organizations
  drop constraint if exists organizations_tax_mode_check;

alter table organizations
  add constraint organizations_tax_mode_check
    check (tax_mode in ('none','from_file','included','excluded'));
