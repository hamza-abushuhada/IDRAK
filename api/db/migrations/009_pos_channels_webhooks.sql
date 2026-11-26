-- IDRAK Connect — قنوات البيع الموحّدة + استقبال webhook الموقّع + موصّلات المختبر.
--
-- (أ) sales.channel: قناة كل فاتورة (in_store / online / other) لتوحيد تحليلات
--     القنوات داخل تقارير إدراك الحالية دون لوحة منفصلة ودون ازدواج — كل فاتورة
--     تنتمي لقناة واحدة فمجموع القنوات = الإجمالي.
-- (ب) pos_webhook_deliveries: حماية إعادة التشغيل/التكرار على مستوى النقل —
--     نفس event_id لا يُعالَج مرّتين عبر webhook.
-- (ج) بذر موصّلَي المختبر lab_pos / lab_web (منفّذان، للتجربة المحلية).
--
-- idempotent (if exists/if not exists)، نفس أعراف 001–008. لا يُنفَّذ على الإنتاج.

-- (أ) قناة البيع على الفاتورة.
alter table sales add column if not exists channel text;
create index if not exists sales_channel_idx on sales(org_id, channel) where channel is not null;

-- (ب) سجلّ تسليم الـ webhook: idempotency + replay protection على مستوى النقل.
create table if not exists pos_webhook_deliveries (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  connection_id uuid not null references pos_connections(id) on delete cascade,
  event_id text not null,
  received_at timestamptz not null default now(),
  unique (connection_id, event_id)
);
alter table pos_webhook_deliveries enable row level security;
revoke all on pos_webhook_deliveries from anon, authenticated;
create index if not exists pos_webhook_deliveries_conn_idx on pos_webhook_deliveries(connection_id, received_at desc);

-- (ج) موصّلا المختبر: منفّذان فعلاً (يقرآن من demo_server.py المحلّي). مُعلَّمان
-- بوضوح كموصّلات تجربة، لا كأنظمة POS تجارية حقيقية مدعومة.
insert into pos_providers (code, name, name_ar, category, status, is_implemented, capabilities, description, description_ar, sort) values
  ('lab_pos', 'IDRAK Lab — POS (test)', 'مختبر إدراك — كاشير (تجربة)', 'cloud_api', 'available', true,
     '{"initial_import": true, "incremental": true, "refunds": true, "inventory": true, "webhook": true}'::jsonb,
     'Connects to the local IDRAK Connect Lab POS (demo_server.py) via its documented event API + signed webhooks. Test connector.',
     'يتصل بكاشير مختبر إدراك المحلّي عبر واجهة الأحداث الموثّقة و webhooks موقّعة. موصّل تجربة.', 5),
  ('lab_web', 'IDRAK Lab — Online store (test)', 'مختبر إدراك — متجر أونلاين (تجربة)', 'cloud_api', 'available', true,
     '{"initial_import": true, "incremental": true, "refunds": true, "inventory": true, "webhook": true}'::jsonb,
     'Connects to the local IDRAK Connect Lab online store (demo_server.py). Maps pending/completed/cancelled/refunded to correct financial state. Test connector.',
     'يتصل بمتجر مختبر إدراك المحلّي ويحوّل حالات الطلب (معلّق/مكتمل/ملغى/مرتجع) إلى الحالة المالية الصحيحة. موصّل تجربة.', 6)
on conflict (code) do update set
  name = excluded.name, name_ar = excluded.name_ar, category = excluded.category,
  status = excluded.status, is_implemented = excluded.is_implemented,
  capabilities = excluded.capabilities, description = excluded.description,
  description_ar = excluded.description_ar, sort = excluded.sort;
