create or replace function amman_date(ts timestamptz) returns date
language sql immutable parallel safe as $$ select (ts at time zone 'Asia/Amman')::date $$;

create index if not exists sales_org_localdate_idx on sales(org_id, amman_date(sold_at));

alter table sales add column if not exists upload_id uuid references uploads(id) on delete set null;
alter table customers add column if not exists upload_id uuid references uploads(id) on delete set null;
alter table products add column if not exists upload_id uuid references uploads(id) on delete set null;
alter table organizations add column if not exists monthly_rent numeric(12,3) not null default 900;
alter table organizations add column if not exists opening_cash numeric(14,3) not null default 15000;
alter table cleaning_runs add column if not exists imported_at timestamptz;
alter table cleaning_runs add column if not exists reverted_at timestamptz;
alter table purchases add column if not exists emailed_at timestamptz;

grant execute on function amman_date(timestamptz) to basira_ai_reader;
