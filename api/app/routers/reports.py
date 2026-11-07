from fastapi import APIRouter, Depends

from .. import db
from ..auth import Ctx, require
from ..config import settings
from ..services import email
from ..services import insights as I

router = APIRouter(prefix="/reports", tags=["reports"])


async def build_summary(org_id: str, days: int) -> dict:
    dash = await I.dashboard(org_id, days)
    leaks = await I.leaks(org_id)
    reo = await I.reorder(org_id)
    org = await db.fetchrow("select name, name_ar, city, tax_number from organizations where id=$1", org_id)
    comp = await I.compliance(org_id, 90)
    return {"org": org, "period_days": days, "dashboard": dash, "leaks": leaks[:6], "reorder": {"total": reo["total"], "lines": reo["lines"], "critical": reo["critical"],
            "suppliers": [{"supplier": g["supplier"], "supplier_ar": g["supplier_ar"], "total": g["total"], "lines": len(g["lines"])} for g in reo["groups"][:6]]},
            "compliance": {"score": comp["score"], "issues": [{"en": i["en"], "ar": i["ar"], "count": i["count"]} for i in comp["issues"]]}}


@router.get("/summary")
async def summary(days: int = 7, ctx: Ctx = Depends(require("view_dashboard"))):
    await db.audit(ctx.org_id, ctx.user.id, "report.viewed", "report", f"{days}d")
    return await build_summary(ctx.org_id, max(7, min(days, 90)))


@router.post("/digest")
async def send_digest(locale: str = "ar", ctx: Ctx = Depends(require("view_dashboard"))):
    s = await build_summary(ctx.org_id, 7)
    k, dlt = s["dashboard"]["kpis"], s["dashboard"]["deltas"]
    ar = locale == "ar"
    org_name = s["org"]["name_ar"] if ar and s["org"]["name_ar"] else s["org"]["name"]

    def arrow(v):
        return "" if v is None else (f"▲ {v:.1f}%" if v >= 0 else f"▼ {abs(v):.1f}%")
    kpi = lambda label, val, d: (f"<td style='padding:12px;border:1px solid #E2D6C3;border-radius:10px;width:33%'><div style='font-size:12px;color:#8A786A'>{label}</div>"
                                f"<div style='font-size:20px;font-weight:700;font-family:IBM Plex Mono,monospace'>{val}</div><div style='font-size:12px;color:{'#6B7A3A' if (d or 0) >= 0 else '#B3412E'}'>{arrow(d)}</div></td>")
    leaks_html = "".join(f"<li style='margin-bottom:8px'><b>{l['title_ar'] if ar else l['title']}</b></li>" for l in s["leaks"][:3])
    top = "".join(f"<li>{(p['name_ar'] if ar and p['name_ar'] else p['name'])} — {p['revenue']:,.0f} {'د.أ' if ar else 'JD'}</li>" for p in s["dashboard"]["top_products"][:5])
    body = (f"<p>{'هاد ملخص أسبوعك في' if ar else 'Here is your week at'} <b>{org_name}</b>.</p>"
            f"<table width='100%' cellspacing='6'><tr>{kpi('المبيعات' if ar else 'Revenue', f'{k['revenue']:,.0f}', dlt['revenue'])}"
            f"{kpi('الربح الإجمالي' if ar else 'Gross profit', f'{k['profit']:,.0f}', dlt['profit'])}{kpi('متوسط السلة' if ar else 'Avg basket', f'{k['basket']:.3f}', dlt['basket'])}</tr></table>"
            f"<h3 style='margin:22px 0 8px'>{'وين عم تخسر' if ar else 'Where you are losing money'}</h3><ul style='padding-inline-start:18px'>{leaks_html}</ul>"
            f"<h3 style='margin:22px 0 8px'>{'الأكثر مبيعاً' if ar else 'Best sellers'}</h3><ul style='padding-inline-start:18px'>{top}</ul>"
            f"<p>{'طلبيات مقترحة' if ar else 'Suggested reorders'}: <b>{s['reorder']['lines']}</b> ({s['reorder']['critical']} {'عاجلة' if ar else 'critical'})</p>")
    res = await email.send(ctx.user.email, ("ملخص إدراك الأسبوعي — " if ar else "Your Idrak weekly digest — ") + org_name,
                           email.layout("ملخصك الأسبوعي" if ar else "Your weekly digest", body, locale, ("افتح لوحة التحكم" if ar else "Open dashboard", f"{settings.web_url}/{locale}/app")))
    await db.audit(ctx.org_id, ctx.user.id, "digest.sent", "report", "weekly", {"ok": res.get("ok"), "error": res.get("error")})
    return {"ok": res.get("ok"), "email": res}
