create table if not exists import_batches (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  created_by uuid references auth.users(id) on delete set null,
  status text not null default 'staged' check (status in ('staged', 'review', 'imported', 'failed')),
  contract jsonb not null default '{}'::jsonb,
  link_report jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table uploads add column if not exists batch_id uuid references import_batches(id) on delete set null;
alter table products alter column tax_rate set default 0;
create index if not exists uploads_batch_idx on uploads(batch_id);
create index if not exists import_batches_org_idx on import_batches(org_id, created_at desc);

alter table import_batches enable row level security;
revoke all on import_batches from anon, authenticated;
