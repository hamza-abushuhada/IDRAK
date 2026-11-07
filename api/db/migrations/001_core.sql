create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create table if not exists profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text,
  locale text not null default 'ar',
  avatar_url text,
  is_super_admin boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  name_ar text,
  slug text unique,
  industry text not null default 'minimarket',
  city text,
  country text not null default 'JO',
  currency text not null default 'JOD',
  locale text not null default 'ar',
  plan text not null default 'growth',
  tax_number text,
  onboarding_completed boolean not null default false,
  is_demo boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists memberships (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('owner','manager','accountant','cashier')),
  created_at timestamptz not null default now(),
  unique (org_id, user_id)
);

create table if not exists invitations (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  email text not null,
  role text not null check (role in ('owner','manager','accountant','cashier')),
  token text not null unique,
  invited_by uuid references auth.users(id) on delete set null,
  status text not null default 'pending' check (status in ('pending','accepted','revoked')),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '7 days'
);

create table if not exists branches (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  name_ar text,
  city text,
  area text,
  lat double precision,
  lng double precision,
  opened_at date,
  created_at timestamptz not null default now()
);

create table if not exists employees (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  branch_id uuid references branches(id) on delete set null,
  full_name text not null,
  full_name_ar text,
  job_title text not null default 'cashier',
  phone text,
  email text,
  hired_at date,
  monthly_salary numeric(12,3),
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists customers (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  full_name text not null,
  full_name_ar text,
  phone text,
  email text,
  gender text,
  city text,
  area text,
  loyalty_card text,
  loyalty_points integer not null default 0,
  first_seen date,
  created_at timestamptz not null default now()
);

create table if not exists suppliers (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  name_ar text,
  contact_name text,
  phone text,
  email text,
  payment_terms_days integer not null default 30,
  category text,
  created_at timestamptz not null default now()
);

create table if not exists categories (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  name_ar text,
  parent_id uuid references categories(id) on delete set null
);

create table if not exists products (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  category_id uuid references categories(id) on delete set null,
  supplier_id uuid references suppliers(id) on delete set null,
  sku text,
  barcode text,
  name text not null,
  name_ar text,
  brand text,
  unit text not null default 'pcs',
  size text,
  cost numeric(12,3) not null default 0,
  price numeric(12,3) not null default 0,
  tax_rate numeric(5,2) not null default 16,
  reorder_level integer not null default 10,
  is_perishable boolean not null default false,
  shelf_life_days integer,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists product_aliases (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  product_id uuid not null references products(id) on delete cascade,
  alias text not null,
  source text,
  created_at timestamptz not null default now()
);

create table if not exists inventory_levels (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  branch_id uuid not null references branches(id) on delete cascade,
  product_id uuid not null references products(id) on delete cascade,
  quantity numeric(12,3) not null default 0,
  updated_at timestamptz not null default now(),
  unique (branch_id, product_id)
);

create table if not exists inventory_batches (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  branch_id uuid not null references branches(id) on delete cascade,
  product_id uuid not null references products(id) on delete cascade,
  quantity numeric(12,3) not null,
  expiry_date date,
  received_at date
);

create table if not exists sales (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  branch_id uuid references branches(id) on delete set null,
  employee_id uuid references employees(id) on delete set null,
  customer_id uuid references customers(id) on delete set null,
  invoice_number text,
  sold_at timestamptz not null,
  subtotal numeric(12,3) not null default 0,
  discount numeric(12,3) not null default 0,
  tax numeric(12,3) not null default 0,
  total numeric(12,3) not null default 0,
  payment_method text not null default 'cash',
  status text not null default 'completed' check (status in ('completed','void','returned')),
  buyer_tax_number text,
  created_at timestamptz not null default now()
);

create table if not exists sale_items (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  sale_id uuid not null references sales(id) on delete cascade,
  product_id uuid references products(id) on delete set null,
  quantity numeric(12,3) not null,
  unit_price numeric(12,3) not null,
  unit_cost numeric(12,3) not null,
  discount numeric(12,3) not null default 0,
  line_total numeric(12,3) not null
);

create table if not exists purchases (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  branch_id uuid references branches(id) on delete set null,
  supplier_id uuid references suppliers(id) on delete set null,
  po_number text,
  ordered_at timestamptz not null default now(),
  received_at timestamptz,
  total numeric(12,3) not null default 0,
  status text not null default 'received' check (status in ('draft','sent','received','cancelled')),
  notes text,
  created_at timestamptz not null default now()
);

create table if not exists purchase_items (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  purchase_id uuid not null references purchases(id) on delete cascade,
  product_id uuid references products(id) on delete set null,
  quantity numeric(12,3) not null,
  unit_cost numeric(12,3) not null,
  line_total numeric(12,3) not null
);

create table if not exists uploads (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  uploaded_by uuid references auth.users(id) on delete set null,
  file_name text not null,
  file_size integer,
  source text not null default 'upload',
  entity text not null default 'unknown',
  sheet_name text,
  row_count integer not null default 0,
  column_count integer not null default 0,
  columns jsonb not null default '[]',
  mapping jsonb,
  status text not null default 'uploaded',
  health_before numeric(5,1),
  health_after numeric(5,1),
  imported_rows integer,
  created_at timestamptz not null default now()
);

create table if not exists upload_data (
  upload_id uuid primary key references uploads(id) on delete cascade,
  org_id uuid not null references organizations(id) on delete cascade,
  raw_rows jsonb not null,
  clean_rows jsonb
);

create table if not exists cleaning_runs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  upload_id uuid not null references uploads(id) on delete cascade,
  status text not null default 'running',
  score_before jsonb,
  score_after jsonb,
  stats jsonb,
  created_by uuid references auth.users(id) on delete set null,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

create table if not exists cleaning_changes (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  run_id uuid not null references cleaning_runs(id) on delete cascade,
  row_index integer not null,
  column_name text not null,
  old_value text,
  new_value text,
  rule text not null,
  category text not null,
  confidence numeric(4,3) not null default 1,
  group_key text,
  status text not null default 'proposed' check (status in ('proposed','approved','rejected','reverted'))
);
create index if not exists cleaning_changes_run_idx on cleaning_changes(run_id);

create table if not exists cleaning_rules (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  column_kind text not null,
  match_value text not null,
  replace_value text,
  rule_type text not null default 'value_map',
  times_applied integer not null default 0,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (org_id, column_kind, match_value)
);

create table if not exists insights (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  kind text not null,
  severity text not null default 'medium',
  title text not null,
  title_ar text,
  body text,
  body_ar text,
  amount_jod numeric(14,3),
  data jsonb,
  status text not null default 'open' check (status in ('open','dismissed','resolved')),
  detected_at timestamptz not null default now()
);

create table if not exists alert_rules (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  metric text not null,
  operator text not null,
  threshold numeric(14,3) not null,
  branch_id uuid references branches(id) on delete cascade,
  channel text not null default 'in_app',
  is_active boolean not null default true,
  last_triggered_at timestamptz,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

create table if not exists notifications (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  user_id uuid references auth.users(id) on delete cascade,
  kind text not null,
  title text not null,
  body text,
  link text,
  read_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists goals (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  branch_id uuid references branches(id) on delete cascade,
  metric text not null default 'revenue',
  period_month date not null,
  target numeric(14,3) not null,
  created_at timestamptz not null default now()
);

create table if not exists reports (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  sections jsonb not null default '[]',
  schedule text,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

create table if not exists chat_sessions (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  title text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references chat_sessions(id) on delete cascade,
  org_id uuid not null references organizations(id) on delete cascade,
  role text not null,
  content text,
  events jsonb,
  created_at timestamptz not null default now()
);

create table if not exists ai_usage (
  id uuid primary key default gen_random_uuid(),
  org_id uuid references organizations(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  model text,
  kind text,
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  cost_usd numeric(10,5) not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists audit_log (
  id uuid primary key default gen_random_uuid(),
  org_id uuid references organizations(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  action text not null,
  entity text,
  entity_id text,
  details jsonb,
  created_at timestamptz not null default now()
);

create table if not exists waitlist (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  name text,
  business_name text,
  business_type text,
  city text,
  locale text,
  created_at timestamptz not null default now()
);

create table if not exists contact_messages (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  email text not null,
  phone text,
  message text not null,
  locale text,
  created_at timestamptz not null default now()
);

create table if not exists health_checks (
  id uuid primary key default gen_random_uuid(),
  file_name text,
  row_count integer,
  score numeric(5,1),
  created_at timestamptz not null default now()
);

create index if not exists memberships_user_idx on memberships(user_id);
create index if not exists sales_org_time_idx on sales(org_id, sold_at);
create index if not exists sales_branch_idx on sales(branch_id, sold_at);
create index if not exists sale_items_sale_idx on sale_items(sale_id);
create index if not exists sale_items_org_product_idx on sale_items(org_id, product_id);
create index if not exists products_org_idx on products(org_id);
create index if not exists customers_org_idx on customers(org_id);
create index if not exists inventory_org_idx on inventory_levels(org_id);
create index if not exists purchases_org_idx on purchases(org_id, ordered_at);
create index if not exists audit_org_idx on audit_log(org_id, created_at desc);
create index if not exists notifications_org_idx on notifications(org_id, created_at desc);
create index if not exists products_name_trgm on products using gin (name gin_trgm_ops);
