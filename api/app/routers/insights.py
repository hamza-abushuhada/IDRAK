import datetime as dt
import html

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..auth import Ctx, require
from ..config import settings
from ..services import email
from ..services import insights as I

router = APIRouter(tags=["insights"])


@router.get("/insights/dashboard")
async def dashboard(days: int = 30, branch_id: str | None = None, ctx: Ctx = Depends(require("view_dashboard"))):
    return await I.dashboard(ctx.org_id, max(7, min(days, 365)), branch_id)


@router.get("/insights/leaks")
async def leaks(ctx: Ctx = Depends(require("view_dashboard"))):
    items = await I.leaks(ctx.org_id)
    return {"items": items, "total_monthly": round(sum(i["amount_jod"] or 0 for i in items if i["kind"] not in ("dead_stock", "expiring")), 2),
            "tied_up": round(sum(i["amount_jod"] or 0 for i in items if i["kind"] in ("dead_stock", "expiring")), 2)}


@router.get("/insights/forecast")
async def forecast(product_id: str | None = None, category_id: str | None = None, horizon: int = 120, branch_id: str | None = None,
                   ctx: Ctx = Depends(require("view_dashboard"))):
    res = await I.forecast(ctx.org_id, product_id, category_id, max(14, min(horizon, 200)), branch_id)
    res["ramadan_movers"] = await I.ramadan_movers(ctx.org_id)
    res["products"] = await db.fetch("select id, name, name_ar from products where org_id=$1 and is_active order by name", ctx.org_id)
    res["categories"] = await db.fetch("select id, name, name_ar from categories where org_id=$1 order by name", ctx.org_id)
    return res


@router.get("/insights/reorder")
async def reorder(cover_days: int = 14, branch_id: str | None = None, ctx: Ctx = Depends(require("view_dashboard"))):
    return await I.reorder(ctx.org_id, cover_days, branch_id)


class POLine(BaseModel):
    product_id: str
    branch_id: str
    quantity: float


class POIn(BaseModel):
    supplier_id: str
    lines: list[POLine]
    note: str | None = None
    send_email: bool = True
    locale: str = "ar"


@router.post("/insights/reorder/send")
async def send_po(p: POIn, ctx: Ctx = Depends(require("send_supplier_email"))):
    sup = await db.fetchrow("select * from suppliers where id=$1 and org_id=$2", p.supplier_id, ctx.org_id)
    if not sup:
        raise HTTPException(404, "Supplier not found")
    org = await db.fetchrow("select name, name_ar from organizations where id=$1", ctx.org_id)
    by_branch: dict[str, list[POLine]] = {}
    for l in p.lines:
        by_branch.setdefault(l.branch_id, []).append(l)
    pos = []
    for bid, lines in by_branch.items():
        n = await db.fetchval("select count(*) from purchases where org_id=$1", ctx.org_id)
        po_number = f"PO-{dt.date.today().year}-{n + 1:05d}"
        async with db.transaction() as c:
            pid = await c.fetchval("insert into purchases(org_id,branch_id,supplier_id,po_number,status,notes) values($1,$2,$3,$4,'sent',$5) returning id",
                                   ctx.org_id, bid, p.supplier_id, po_number, p.note)
            total = 0.0
            rows = []
            for l in lines:
                pr = await c.fetchrow("select name, name_ar, cost from products where id=$1 and org_id=$2", l.product_id, ctx.org_id)
                lt = round(l.quantity * pr["cost"], 3)
                total += lt
                rows.append((pr, l.quantity, lt))
                await c.execute("insert into purchase_items(org_id,purchase_id,product_id,quantity,unit_cost,line_total) values($1,$2,$3,$4,$5,$6)",
                                ctx.org_id, pid, l.product_id, l.quantity, pr["cost"], lt)
            await c.execute("update purchases set total=$2 where id=$1", pid, round(total, 3))
        branch = await db.fetchrow("select name, name_ar from branches where id=$1", bid)
        ar = p.locale == "ar"
        table = "".join(f"<tr><td style='padding:6px 8px;border-bottom:1px solid #E2D6C3'>{html.escape(pr['name_ar'] if ar and pr['name_ar'] else pr['name'])}</td>"
                        f"<td style='padding:6px 8px;border-bottom:1px solid #E2D6C3;text-align:center'>{q:g}</td></tr>" for pr, q, lt in rows)
        body = (f"<p>{'مرحبا' if ar else 'Hello'} {html.escape(sup['contact_name'] or '')},</p><p>"
                + (f"نرجو تجهيز الطلبية التالية لفرع <b>{html.escape(branch['name_ar'] or branch['name'])}</b> — {html.escape(org['name_ar'] or org['name'])}:" if ar else
                   f"Please prepare the following order for our <b>{html.escape(branch['name'])}</b> branch — {html.escape(org['name'])}:") + "</p>"
                + f"<table style='border-collapse:collapse;width:100%;font-size:14px'><tr><th style='text-align:start;padding:6px 8px'>{'الصنف' if ar else 'Item'}</th>"
                f"<th style='padding:6px 8px'>{'الكمية' if ar else 'Qty'}</th></tr>{table}</table>"
                + (f"<p>{html.escape(p.note)}</p>" if p.note else "") + f"<p>{'رقم الطلبية' if ar else 'PO number'}: <b>{po_number}</b></p>")
        res = {"ok": False, "error": "not sent"}
        if p.send_email and sup["email"]:
            res = await email.send(sup["email"], f"{'طلبية' if ar else 'Purchase order'} {po_number} — {org['name_ar'] if ar else org['name']}",
                                   email.layout(f"{'طلبية' if ar else 'Purchase order'} {po_number}", body, p.locale), reply_to=ctx.user.email)
            if res.get("ok"):
                await db.execute("update purchases set emailed_at=now() where id=$1", pid)
        await db.audit(ctx.org_id, ctx.user.id, "purchase.emailed", "purchase", str(pid), {"supplier": sup["name"], "email_ok": res.get("ok"), "error": res.get("error")})
        pos.append({"id": str(pid), "po_number": po_number, "total": round(total, 3), "email": res, "branch": branch["name"]})
    return {"ok": True, "purchase_orders": pos}


@router.get("/insights/customers")
async def customers(ctx: Ctx = Depends(require("view_dashboard"))):
    return await I.rfm(ctx.org_id)


@router.get("/insights/basket")
async def basket(days: int = 60, ctx: Ctx = Depends(require("view_dashboard"))):
    return {"pairs": await I.basket(ctx.org_id, days)}


class SimIn(BaseModel):
    product_ids: list[str] | None = None
    category_id: str | None = None
    price_pct: float = 0
    cost_pct: float = 0
    discount_pct: float = 0
    elasticity: float = -1.3


@router.post("/insights/simulate")
async def simulate(s: SimIn, ctx: Ctx = Depends(require("view_dashboard"))):
    return await I.simulate(ctx.org_id, s.product_ids, s.category_id, s.price_pct, s.cost_pct, s.discount_pct, s.elasticity)


@router.get("/insights/cashflow")
async def cashflow(weeks: int = 8, opening: float | None = None, ctx: Ctx = Depends(require("view_finance"))):
    return await I.cashflow(ctx.org_id, max(4, min(weeks, 16)), opening)


@router.get("/compliance")
async def compliance(days: int = 90, ctx: Ctx = Depends(require("view_finance"))):
    return await I.compliance(ctx.org_id, days)


@router.get("/goals")
async def goals(ctx: Ctx = Depends(require("view_dashboard"))):
    end = await I.data_end(ctx.org_id)
    return await db.fetch("""select g.id, g.branch_id, b.name branch, b.name_ar branch_ar, g.metric, g.period_month, g.target,
        (select coalesce(sum(total),0) from sales s where s.branch_id=g.branch_id and s.status='completed'
           and date_trunc('month', amman_date(s.sold_at)) = g.period_month and amman_date(s.sold_at) <= $2) actual
        from goals g left join branches b on b.id=g.branch_id where g.org_id=$1 order by g.period_month desc, b.name""", ctx.org_id, end)


class GoalIn(BaseModel):
    branch_id: str
    period_month: str
    target: float


@router.post("/goals")
async def add_goal(g: GoalIn, ctx: Ctx = Depends(require("manage_alerts"))):
    m = dt.date.fromisoformat(g.period_month[:7] + "-01")
    await db.execute("delete from goals where org_id=$1 and branch_id=$2 and period_month=$3", ctx.org_id, g.branch_id, m)
    await db.execute("insert into goals(org_id,branch_id,metric,period_month,target) values($1,$2,'revenue',$3,$4)", ctx.org_id, g.branch_id, m, g.target)
    return {"ok": True}


async def _evaluate(org_id: str, rule: dict) -> dict:
    end = await I.data_end(org_id)
    m, val = rule["metric"], None
    if m == "stock_below_reorder":
        val = await db.fetchval("select count(*) from inventory_levels il join products p on p.id=il.product_id where il.org_id=$1 and il.quantity <= p.reorder_level", org_id)
    elif m == "daily_sales_drop_pct":
        r = await db.fetchrow("""select sum(total) filter (where amman_date(sold_at)=$2) y, sum(total) filter (where amman_date(sold_at) between $2::date - 28 and $2::date - 1)/28.0 avg
            from sales where org_id=$1 and status='completed' and amman_date(sold_at) >= $2::date - 28""", org_id, end)
        val = round(100 * (r["avg"] - (r["y"] or 0)) / r["avg"], 1) if r["avg"] else 0
    elif m == "discount_rate_pct":
        val = await db.fetchval("""select round(sum(discount)/nullif(sum(subtotal),0)*100, 2) from sales where org_id=$1 and status='completed' and amman_date(sold_at) > $2::date - 7""", org_id, end) or 0
    elif m == "expiring_items":
        val = await db.fetchval("select count(*) from inventory_batches where org_id=$1 and quantity>0 and expiry_date <= $2::date + 7", org_id, end)
    elif m == "revenue_below":
        val = await db.fetchval("select coalesce(sum(total),0) from sales where org_id=$1 and status='completed' and amman_date(sold_at)=$2", org_id, end)
    thr = rule["threshold"]
    trig = val is not None and ((val > thr) if rule["operator"] == ">" else (val < thr))
    return {**rule, "current": val, "triggered": trig}


@router.get("/alerts")
async def alerts(ctx: Ctx = Depends(require("view_dashboard"))):
    rules = await db.fetch("select * from alert_rules where org_id=$1 order by created_at", ctx.org_id)
    return [await _evaluate(ctx.org_id, r) for r in rules]


class AlertIn(BaseModel):
    name: str
    metric: str
    operator: str = ">"
    threshold: float
    channel: str = "in_app"


@router.post("/alerts")
async def add_alert(a: AlertIn, ctx: Ctx = Depends(require("manage_alerts"))):
    await db.execute("insert into alert_rules(org_id,name,metric,operator,threshold,channel,created_by) values($1,$2,$3,$4,$5,$6,$7)",
                     ctx.org_id, a.name, a.metric, a.operator, a.threshold, a.channel, ctx.user.id)
    await db.audit(ctx.org_id, ctx.user.id, "alert.created", "alert", a.name)
    return {"ok": True}


@router.patch("/alerts/{aid}")
async def toggle_alert(aid: str, body: dict, ctx: Ctx = Depends(require("manage_alerts"))):
    await db.execute("update alert_rules set is_active=$3 where id=$1 and org_id=$2", aid, ctx.org_id, bool(body.get("is_active")))
    return {"ok": True}


@router.delete("/alerts/{aid}")
async def del_alert(aid: str, ctx: Ctx = Depends(require("manage_alerts"))):
    await db.execute("delete from alert_rules where id=$1 and org_id=$2", aid, ctx.org_id)
    return {"ok": True}


@router.post("/alerts/run")
async def run_alerts(ctx: Ctx = Depends(require("manage_alerts"))):
    rules = await db.fetch("select * from alert_rules where org_id=$1 and is_active", ctx.org_id)
    fired = []
    for r in rules:
        ev = await _evaluate(ctx.org_id, r)
        if ev["triggered"]:
            fired.append(ev)
            await db.execute("insert into notifications(org_id,kind,title,link) values($1,'alert',$2,'/app/alerts')", ctx.org_id, f"{r['name']}: {ev['current']}")
            await db.execute("update alert_rules set last_triggered_at=now() where id=$1", r["id"])
            if r["channel"] == "email":
                await email.send(ctx.user.email, f"Idrak alert: {r['name']}",
                                 email.layout(r["name"], f"<p>Current value: <b>{ev['current']}</b> (threshold {r['operator']} {r['threshold']})</p>", "en",
                                              ("Open alerts", f"{settings.web_url}/en/app/alerts")))
    return {"fired": fired}
