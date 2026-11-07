from fastapi import APIRouter, Depends

from .. import db
from ..auth import User, super_admin

router = APIRouter(prefix="/admin", tags=["admin"])
PLAN_PRICE = {"starter": 19, "growth": 49, "business": 99}


@router.get("/overview")
async def overview(user: User = Depends(super_admin)):
    orgs = await db.fetch("""select o.id, o.name, o.name_ar, o.industry, o.city, o.plan, o.created_at, o.is_demo,
            (select count(*) from memberships m where m.org_id=o.id) members,
            (select count(*) from branches b where b.org_id=o.id) branches,
            (select count(*) from sales s where s.org_id=o.id) sales,
            (select count(*) from uploads u where u.org_id=o.id) uploads,
            (select coalesce(sum(cost_usd),0) from ai_usage a where a.org_id=o.id and a.created_at > now() - interval '30 days') ai_cost_30d
        from organizations o order by o.created_at desc""")
    mrr = sum(PLAN_PRICE.get(o["plan"], 0) for o in orgs)
    signups = await db.fetch("""select to_char(date_trunc('week', created_at),'YYYY-MM-DD') w, count(*) n from organizations
        where created_at > now() - interval '120 days' group by 1 order by 1""")
    wl = await db.fetch("select * from waitlist order by created_at desc limit 100")
    wl_weekly = await db.fetch("select to_char(date_trunc('week', created_at),'YYYY-MM-DD') w, count(*) n from waitlist group by 1 order by 1")
    ai = await db.fetch("""select to_char(date_trunc('day', created_at),'YYYY-MM-DD') d, count(*) calls, sum(input_tokens) tin, sum(output_tokens) tout, sum(cost_usd) cost
        from ai_usage where created_at > now() - interval '30 days' group by 1 order by 1""")
    hc = await db.fetchrow("select count(*) n, avg(score) avg_score from health_checks")
    by_plan = {}
    for o in orgs:
        by_plan[o["plan"]] = by_plan.get(o["plan"], 0) + 1
    contacts = await db.fetch("select * from contact_messages order by created_at desc limit 30")
    return {"tenants": orgs, "mrr_jod": mrr, "arr_jod": mrr * 12, "by_plan": by_plan, "signups": signups, "waitlist": wl, "waitlist_total": await db.fetchval("select count(*) from waitlist"),
            "waitlist_weekly": wl_weekly, "ai_daily": ai, "ai_cost_30d": round(sum(a["cost"] or 0 for a in ai), 4), "health_checks": hc, "contacts": contacts,
            "users": await db.fetchval("select count(*) from profiles")}
