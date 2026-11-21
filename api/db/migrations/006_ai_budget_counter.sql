-- عدّاد ذرّي لتكلفة الذكاء الاصطناعي لكل مؤسسة في اليوم (توقيت عمّان).
-- يغلق سباق «الفحص ثم التنفيذ» في حدّ الميزانية: الحجز والفحص يتمّان بجملة
-- واحدة ذرّية (services/ai.budget_reserve)، فالدفعات المتزامنة تتسلسل على قفل
-- صفّ (org_id, day) ولا تتجاوز السقف دفعةً واحدة. التكلفة الفعلية تُضاف عبر
-- services/ai.track، والحجز يُحرَّر عند انتهاء الطلب.
-- يُطبَّق بتشغيل: python db/migrate.py
create table if not exists ai_budget_day (
  org_id uuid not null references organizations(id) on delete cascade,
  day date not null,
  spent_usd numeric(12,5) not null default 0,
  updated_at timestamptz not null default now(),
  primary key (org_id, day)
);

-- نفس نمط 002_security: RLS مفعّل بلا سياسات، فلا يصل إليه إلا دور التطبيق
-- (postgres) الذي يتجاوز RLS؛ anon/authenticated لا يملكان أي صلاحية.
alter table ai_budget_day enable row level security;
revoke all on ai_budget_day from anon, authenticated;
