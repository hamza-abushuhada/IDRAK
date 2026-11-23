-- المرحلة 3 من ربط الأعمدة: التعلّم من تأكيدات الشركات، وبصمة الملف.
-- يُطبَّق بتشغيل: python db/migrate.py
--
-- 1) mapping_votes: صوت واحد لكل شركة لكل اسم عمود مطبَّع (match_key).
--    يُكتب لما المستخدم يغيّر ربط عمود أو يأكّد عموداً أصفر (set_mapping).
--    الاسم المطبَّع والحقل فقط؛ لا قيم خلايا ولا أسماء ملفات.
--    الاسم يصير "مرادفاً مشتركاً" يستفيد منه الكل لما يأكّده ≥3 شركات مختلفة
--    (و≥3 مستخدمين مختلفين) على نفس الحقل بنسبة ≥80% من الشركات اللي صوّتت
--    عليه. الحساب في api/app/cleaning/learning.py (promote).
--    org_id هنا ضروري لعدّ الشركات المختلفة (مش عدد الرفعات) ولحذف أصوات
--    الشركة إذا انحذفت، لكنه ما بيطلع أبداً: الـ API بيقرأ أعداداً مجمّعة فقط.
create table if not exists mapping_votes (
  org_id uuid not null references organizations(id) on delete cascade,
  header_key text not null check (length(header_key) between 1 and 80),
  field text not null,                 -- '' = "لا تستخدم" (يُعدّ اعتراضاً، وما بينتشر)
  voted_by uuid references auth.users(id) on delete set null,
  updated_at timestamptz not null default now(),
  primary key (org_id, header_key)
);
create index if not exists mapping_votes_key_idx on mapping_votes(header_key, field);

-- 2) mapping_fingerprints: بصمة ملف الشركة = مجموعة أسماء أعمدته المطبَّعة
--    (مرتّبة، sha256). عند التنظيف نحفظ الربط المؤكَّد ونوع الملف المؤكَّد،
--    فالملف الجاي بنفس الشكل من نفس الشركة يترابط فوراً بلا ذكاء اصطناعي.
--    columns: {header_key: {"field": text|null, "fit": رقم 0..1|null}}
--    fit = نسبة القيم اللي كانت تشبه نوع الحقل وقت التأكيد (رقم فقط، بلا قيم)،
--    حتى نكتشف إذا تغيّر التصدير فنرجّع العمود للمراجعة.
--    خاص بالشركة نفسها، وما بيتشارك مع أي شركة.
create table if not exists mapping_fingerprints (
  org_id uuid not null references organizations(id) on delete cascade,
  fingerprint text not null check (length(fingerprint) = 64),
  columns jsonb not null,
  entity text,                         -- النوع المؤكَّد، null إذا ما احتاج تأكيد
  signature jsonb,                     -- [[header_key, field], ...] اللي التأكيد صالح له
  confirmed_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (org_id, fingerprint)
);

-- نفس نمط 002 و006: RLS مفعّل بلا سياسات، فما بيوصلها إلا دور التطبيق
-- (postgres) اللي بيتجاوز RLS. anon/authenticated ما إلهم أي صلاحية، و
-- basira_ai_reader (دور مساعد الذكاء الاصطناعي) ما إله grant ولا policy،
-- وsql_guard كمان بيرفض أي جدول برّا الـ views المسموحة.
alter table mapping_votes enable row level security;
alter table mapping_fingerprints enable row level security;
revoke all on mapping_votes, mapping_fingerprints from anon, authenticated;
revoke all on mapping_votes, mapping_fingerprints from basira_ai_reader;
