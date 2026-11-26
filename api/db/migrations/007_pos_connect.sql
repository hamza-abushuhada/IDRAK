-- IDRAK Connect — ربط أنظمة نقاط البيع (POS)
-- طبقة ربط مستقلة عن المورّد: تطبيع أحداث نقاط البيع إلى نفس جداول
-- الأعمال القانونية (sales / sale_items / products) التي يكتب فيها الاستيراد
-- اليدوي، مع عزل المستأجرين، idempotency، وتدقيق كامل.
--
-- نفس أعراف 001/002/004: جداول idempotent (if not exists)، RLS مفعّل بلا
-- سياسات على الجداول الوصفية (فلا يصل إليها إلا دور التطبيق postgres الذي
-- يتجاوز RLS؛ anon/authenticated بلا صلاحية). يُطبَّق بتشغيل: python db/migrate.py
-- تحذير: لا تنفّذه على قاعدة إنتاج قبل المراجعة.

-- ---------------------------------------------------------------------------
-- كتالوج المزوّدين: تعريف ثابت لفئات الموصّلات وأيّها منفَّذ فعلاً.
-- status: 'demo' (موصّل تجريبي يعمل) | 'available' (موصّل حقيقي منفَّذ)
--         | 'coming_soon' (مدعوم معماريّاً فقط، غير منفَّذ بعد).
-- category: 'demo' | 'cloud_api' | 'local_agent' | 'file_export'.
create table if not exists pos_providers (
  code text primary key,
  name text not null,
  name_ar text,
  category text not null default 'cloud_api'
    check (category in ('demo', 'cloud_api', 'local_agent', 'file_export')),
  status text not null default 'coming_soon'
    check (status in ('demo', 'available', 'coming_soon')),
  is_implemented boolean not null default false,
  capabilities jsonb not null default '{}'::jsonb,
  description text,
  description_ar text,
  sort integer not null default 100
);

-- اتصال واحد لمؤسسة بمزوّد. لا يخزّن أي سرّ نصّاً: credential_ref يشير إلى
-- مرجع في مدير أسرار خارجي (يُنفَّذ لاحقاً)، ويبقى NULL للموصّل التجريبي.
create table if not exists pos_connections (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  provider_code text not null references pos_providers(code),
  display_name text not null,
  status text not null default 'pending'
    check (status in ('pending', 'connected', 'paused', 'error', 'disconnected')),
  config jsonb not null default '{}'::jsonb,        -- إعدادات غير سرّية فقط
  credential_ref text,                              -- مرجع سرّ خارجي، لا السرّ نفسه
  cursor jsonb not null default '{}'::jsonb,         -- نقطة المزامنة التزايدية
  last_sync_at timestamptz,
  last_success_at timestamptz,
  last_error text,
  sync_count integer not null default 0,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- سجلّ كل محاولة مزامنة: المصدر، الحصيلة، المؤشّرات قبل/بعد، والخطأ.
create table if not exists pos_sync_jobs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  connection_id uuid not null references pos_connections(id) on delete cascade,
  trigger text not null default 'manual'
    check (trigger in ('manual', 'scheduled', 'webhook', 'initial')),
  status text not null default 'running'
    check (status in ('running', 'success', 'partial', 'failed')),
  counts jsonb not null default '{}'::jsonb,         -- {imported, updated, skipped, failed}
  cursor_before jsonb,
  cursor_after jsonb,
  error text,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

-- خريطة المصدر: الركيزة الأساسية للـ idempotency ومعالجة الأحداث خارج الترتيب.
-- كل حدث خارجي (external_id + نوعه) يُربط بسجلّ داخلي واحد وبصمة محتواه
-- وإصدار المصدر. إعادة التسليم بنفس البصمة تُتخطّى؛ بإصدار أحدث تُحدِّث؛
-- بإصدار أقدم (حدث متأخّر) تُتجاهَل.
create table if not exists pos_source_records (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  connection_id uuid not null references pos_connections(id) on delete cascade,
  event_type text not null,                          -- sale | sale_void | refund | product | inventory
  external_id text not null,                         -- معرّف السجلّ لدى المصدر
  entity text not null,                              -- الجدول القانوني المتأثّر
  internal_id uuid,                                  -- معرّف السجلّ في جداول إدراك
  content_hash text not null,
  source_version text,                               -- طابع إصدار/تحديث من المصدر
  occurred_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (connection_id, event_type, external_id)
);

-- سجلّات فشلت أثناء المزامنة: تبقى قابلة للفحص وإعادة المحاولة بدل أن تُفقد.
create table if not exists pos_sync_errors (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  connection_id uuid not null references pos_connections(id) on delete cascade,
  job_id uuid references pos_sync_jobs(id) on delete set null,
  event_type text,
  external_id text,
  payload jsonb,
  error text not null,
  status text not null default 'open'
    check (status in ('open', 'retried', 'resolved')),
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);

-- مصدر السجلّ القانوني: من أي اتصال POS أتى (نظير uploads.upload_id للاستيراد).
-- يتيح الفلترة، عرض الحداثة، والفصل النظيف عند قطع الاتصال.
alter table sales add column if not exists pos_connection_id uuid references pos_connections(id) on delete set null;
alter table products add column if not exists pos_connection_id uuid references pos_connections(id) on delete set null;

create index if not exists pos_connections_org_idx on pos_connections(org_id, created_at desc);
create index if not exists pos_sync_jobs_conn_idx on pos_sync_jobs(connection_id, started_at desc);
create index if not exists pos_source_records_conn_idx on pos_source_records(org_id, connection_id);
create index if not exists pos_sync_errors_conn_idx on pos_sync_errors(connection_id, status);
create index if not exists sales_pos_conn_idx on sales(pos_connection_id) where pos_connection_id is not null;

-- RLS مفعّل بلا سياسات (نمط 002): الجداول الوصفية يصل إليها دور التطبيق فقط.
alter table pos_providers enable row level security;
alter table pos_connections enable row level security;
alter table pos_sync_jobs enable row level security;
alter table pos_source_records enable row level security;
alter table pos_sync_errors enable row level security;
revoke all on pos_providers, pos_connections, pos_sync_jobs, pos_source_records, pos_sync_errors from anon, authenticated;

-- بذر الكتالوج: الموصّل التجريبي (منفَّذ) + فئات مدعومة معماريّاً (غير منفَّذة).
-- لا يُدرَج أي مورّد حقيقي كـ"متاح" لأن لا تكامل موثَّق وعامل له بعد.
insert into pos_providers (code, name, name_ar, category, status, is_implemented, capabilities, description, description_ar, sort) values
  ('demo',        'Demo POS (synthetic)', 'نقطة بيع تجريبية',       'demo',       'demo',        true,
     '{"initial_import": true, "incremental": true, "refunds": true, "inventory": true, "webhook": false}'::jsonb,
     'A fully working reference connector using synthetic data. Demonstrates the real sync pipeline end to end.',
     'موصّل مرجعي يعمل بالكامل ببيانات اصطناعية. يوضّح خط المزامنة الحقيقي من البداية للنهاية.', 1),
  ('cloud_api',   'Cloud POS (API / Webhook)', 'نقطة بيع سحابية (API)', 'cloud_api',  'coming_soon', false,
     '{"initial_import": true, "incremental": true, "webhook": true}'::jsonb,
     'Architecture for vendors that expose an official API and/or webhooks. Not implemented yet.',
     'بنية جاهزة للمورّدين الذين يوفّرون API و/أو webhooks رسميّة. غير منفّذة بعد.', 10),
  ('local_agent', 'Local POS agent', 'وكيل نقطة بيع محلّي',        'local_agent', 'coming_soon', false,
     '{"incremental": true, "secure_submit": true}'::jsonb,
     'Architecture for a future on-premises agent that securely submits supported changes to IDRAK.',
     'بنية لوكيل محلّي مستقبلي يرسل التغييرات المدعومة إلى إدراك بأمان.', 20),
  ('file_export', 'Automatic file export', 'تصدير ملفّات تلقائي',    'file_export', 'coming_soon', false,
     '{"file_import": true}'::jsonb,
     'Architecture for POS systems that generate scheduled CSV/Excel exports, reusing the existing import pipeline.',
     'بنية لأنظمة تصدّر ملفّات CSV/Excel دوريّاً، بإعادة استخدام خط الاستيراد الحالي.', 30)
on conflict (code) do update set
  name = excluded.name, name_ar = excluded.name_ar, category = excluded.category,
  status = excluded.status, is_implemented = excluded.is_implemented,
  capabilities = excluded.capabilities, description = excluded.description,
  description_ar = excluded.description_ar, sort = excluded.sort;
