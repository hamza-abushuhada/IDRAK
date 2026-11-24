-- رفع الملفات الكبيرة على أجزاء.
-- يُطبَّق بتشغيل: python db/migrate.py
--
-- الاستضافة (Vercel) بترفض أي طلب أكبر من 4.5 ميغا قبل ما يوصل للـ API، والمتصفح
-- كان يعرضها "network". الواجهة الحين بتضغط الملف (gzip) وبتقسمه لأجزاء ≤ 4 ميغا،
-- كل جزء بطلب لحاله، وبعدين طلب "finish" بيجمعها ويكمّل الرفع العادي.
-- الأجزاء مؤقتة: بتنحذف أول ما ينجمع الملف، والمتروكة (رفع انقطع) بتنحذف بعد يوم.
create table if not exists upload_parts (
  transfer_id uuid not null,           -- يولّده المتصفح لكل ملف
  seq integer not null check (seq between 0 and 63),
  org_id uuid not null references organizations(id) on delete cascade,
  data bytea not null,
  created_at timestamptz not null default now(),
  primary key (transfer_id, seq)
);
create index if not exists upload_parts_created_idx on upload_parts(created_at);

-- نفس نمط 002 و007: RLS مفعّل بلا سياسات، فما بيوصلها إلا دور التطبيق.
alter table upload_parts enable row level security;
revoke all on upload_parts from anon, authenticated;
revoke all on upload_parts from basira_ai_reader;

-- شاشة المراجعة بتجيب تعديلات صفحة صفوف وحدة (row_index ضمن الصفحة) بدل كل
-- تعديلات الملف؛ ملف 99 ألف صف فيه ~318 ألف تعديل.
create index if not exists cleaning_changes_run_row_idx on cleaning_changes(run_id, row_index);
