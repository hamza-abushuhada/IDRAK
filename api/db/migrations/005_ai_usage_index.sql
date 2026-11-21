-- فهرس لدعم استعلام حدّ تكلفة الذكاء الاصطناعي اليومي لكل مؤسسة
-- (services/ai.over_daily_budget: مجموع cost_usd خلال آخر ٢٤ ساعة).
-- idempotent وآمن على جدول صغير؛ يُطبَّق بتشغيل: python db/migrate.py
create index if not exists ai_usage_org_time_idx on ai_usage(org_id, created_at desc) include (cost_usd);
