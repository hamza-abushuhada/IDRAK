from __future__ import annotations

import asyncio
import datetime as dt
import math
import statistics
from collections import defaultdict

from .. import db

RAMADAN = [(dt.date(2025, 3, 1), dt.date(2025, 3, 29)), (dt.date(2026, 2, 18), dt.date(2026, 3, 19)), (dt.date(2027, 2, 8), dt.date(2027, 3, 9)),
           (dt.date(2028, 1, 28), dt.date(2028, 2, 26))]
EVENTS = [
    (dt.date(2026, 11, 14), "National Day weekend", "عطلة نهاية الأسبوع"),
    (dt.date(2026, 12, 25), "Christmas & New Year season", "موسم الأعياد ورأس السنة"),
    (dt.date(2027, 1, 30), "Mid-year school break", "عطلة منتصف العام الدراسي"),
    (dt.date(2027, 2, 8), "Ramadan begins (expected)", "بداية رمضان (متوقع)"),
    (dt.date(2027, 3, 10), "Eid al-Fitr (expected)", "عيد الفطر (متوقع)"),
    (dt.date(2027, 5, 16), "Eid al-Adha (expected)", "عيد الأضحى (متوقع)"),
]


def in_ramadan(d: dt.date) -> bool:
    return any(a <= d <= b for a, b in RAMADAN)


def today() -> dt.date:
    return (dt.datetime.now(dt.timezone(dt.timedelta(hours=3)))).date()


async def data_end(org_id: str) -> dt.date:
    c = db.cache_get(("data_end", org_id), 120)
    if c:
        return c
    v = await db.fetchval("select max(amman_date(sold_at)) from sales where org_id=$1 and amman_date(sold_at) < amman_date(now())", org_id)
    return db.cache_set(("data_end", org_id), dt.date.fromisoformat(v) if v else today())


def _r(x, n=3):
    return None if x is None else round(float(x), n)


def _branch_filter(branch_id, idx):
    return (f" and s.branch_id = ${idx}", [branch_id]) if branch_id else ("", [])


@db.cached(180)
async def dashboard(org_id: str, days: int = 30, branch_id: str | None = None) -> dict:
    end = await data_end(org_id)
    start = end - dt.timedelta(days=days - 1)
    pstart, pend = start - dt.timedelta(days=days), start - dt.timedelta(days=1)
    bf, bargs = _branch_filter(branch_id, 4)

    async def kpis(a, b):
        r = await db.fetchrow(f"""
            with s as (select * from sales s where s.org_id=$1 and amman_date(s.sold_at) between $2 and $3 {bf})
            select (select coalesce(sum(total),0) from s where status='completed') revenue,
                   (select count(*) from s where status='completed') tx,
                   (select coalesce(sum(discount),0) from s where status='completed') discounts,
                   (select count(*) from s where status='void') voids,
                   (select count(distinct customer_id) from s where status='completed') customers,
                   (select coalesce(sum(si.line_total - si.unit_cost*si.quantity),0) from sale_items si join s on s.id=si.sale_id where s.status='completed') profit,
                   (select coalesce(sum(si.quantity),0) from sale_items si join s on s.id=si.sale_id where s.status='completed') units
        """, org_id, a, b, *bargs)
        r["basket"] = r["revenue"] / r["tx"] if r["tx"] else 0
        r["margin"] = 100 * r["profit"] / r["revenue"] if r["revenue"] else 0
        r["units_per_tx"] = r["units"] / r["tx"] if r["tx"] else 0
        return r


    q_series = db.fetch(f"""
        select amman_date(s.sold_at) d, sum(s.total) revenue, count(*) tx,
               sum((select coalesce(sum(si.line_total - si.unit_cost*si.quantity),0) from sale_items si where si.sale_id=s.id)) profit
        from sales s where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) between $2 and $3 {bf}
        group by 1 order by 1""", org_id, start, end, *bargs)
    q_top = db.fetch(f"""
        select p.id, p.name, p.name_ar, sum(si.quantity) qty, sum(si.line_total) revenue, sum(si.line_total - si.unit_cost*si.quantity) profit
        from sale_items si join sales s on s.id=si.sale_id join products p on p.id=si.product_id
        where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) between $2 and $3 {bf}
        group by 1,2,3 order by revenue desc limit 10""", org_id, start, end, *bargs)
    q_cats = db.fetch(f"""
        select c.name, c.name_ar, sum(si.line_total) revenue, sum(si.line_total - si.unit_cost*si.quantity) profit
        from sale_items si join sales s on s.id=si.sale_id join products p on p.id=si.product_id join categories c on c.id=p.category_id
        where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) between $2 and $3 {bf}
        group by 1,2 order by revenue desc""", org_id, start, end, *bargs)
    q_heat = db.fetch(f"""
        select extract(isodow from s.sold_at at time zone 'Asia/Amman')::int dow, extract(hour from s.sold_at at time zone 'Asia/Amman')::int h, count(*) n
        from sales s where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) between $2 and $3 {bf} group by 1,2""", org_id, start, end, *bargs)
    q_pay = db.fetch(f"""select payment_method m, count(*) n, sum(total) revenue from sales s where s.org_id=$1 and s.status='completed'
        and amman_date(s.sold_at) between $2 and $3 {bf} group by 1 order by 2 desc""", org_id, start, end, *bargs)
    q_branches = db.fetch("""
        select b.id, b.name, b.name_ar,
          coalesce(sum(s.total) filter (where amman_date(s.sold_at) between $2 and $3),0) revenue,
          count(*) filter (where amman_date(s.sold_at) between $2 and $3) tx,
          coalesce(sum(s.total) filter (where amman_date(s.sold_at) between $4 and $5),0) prev_revenue
        from branches b left join sales s on s.branch_id=b.id and s.status='completed' and amman_date(s.sold_at) between $4 and $3
        where b.org_id=$1 group by 1,2,3 order by revenue desc""", org_id, start, end, pstart, pend)
    month = end.replace(day=1)
    month = end.replace(day=1)
    q_goals = db.fetch("""
        select g.branch_id, b.name, b.name_ar, g.target,
          (select coalesce(sum(total),0) from sales s where s.branch_id=g.branch_id and s.status='completed'
             and amman_date(s.sold_at) between $2 and $3) actual
        from goals g join branches b on b.id=g.branch_id where g.org_id=$1 and g.period_month=$2""", org_id, month, end)
    cur, prev, series, top, cats, heat, pay, branches, goals = await asyncio.gather(
        kpis(start, end), kpis(pstart, pend), q_series, q_top, q_cats, q_heat, q_pay, q_branches, q_goals)
    for b in branches:
        b["basket"] = b["revenue"] / b["tx"] if b["tx"] else 0
        b["growth"] = round(100 * (b["revenue"] - b["prev_revenue"]) / b["prev_revenue"], 1) if b["prev_revenue"] else None

    def delta(k):
        return round(100 * (cur[k] - prev[k]) / prev[k], 1) if prev[k] else None
    import calendar
    dim = calendar.monthrange(end.year, end.month)[1]
    for g in goals:
        g["pace"] = g["actual"] / end.day * dim if end.day else 0
    return {
        "range": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "kpis": {k: _r(v) for k, v in cur.items()},
        "deltas": {k: delta(k) for k in ("revenue", "profit", "tx", "basket", "margin", "customers", "discounts")},
        "series": series, "top_products": top, "categories": cats, "heatmap": heat, "payments": pay,
        "branches": branches, "goals": goals,
    }


@db.cached(300)
async def leaks(org_id: str) -> list[dict]:
    end = await data_end(org_id)
    out: list[dict] = []

    dead = await db.fetch("""
        select p.id, p.name, p.name_ar, sum(il.quantity) stock, sum(il.quantity*p.cost) value,
          coalesce((select sum(si.quantity) from sale_items si join sales s on s.id=si.sale_id
                    where si.product_id=p.id and s.status='completed' and amman_date(s.sold_at) > $2::date - 60),0) sold60
        from inventory_levels il join products p on p.id=il.product_id
        where il.org_id=$1 and il.quantity > 0 group by 1,2,3 having sum(il.quantity*p.cost) > 5""", org_id, end)
    dead = [d for d in dead if d["sold60"] <= max(1, d["stock"] * 0.05)]
    if dead:
        val = sum(d["value"] for d in dead)
        dead.sort(key=lambda d: -d["value"])
        out.append(_finding("dead_stock", "high" if val > 500 else "medium", val,
                            f"JD {val:,.0f} is stuck in {len(dead)} items that barely sell",
                            f"{val:,.0f} د.أ عالقة في {len(dead)} أصناف ما بتنباع تقريباً",
                            "These items sold almost nothing in the last 60 days. Run a clearance bundle, return them to the supplier, or stop re-ordering.",
                            "هالأصناف ما انباع منها إشي تقريباً آخر 60 يوم. اعمل عرض تصفية، أو رجّعها للمورد، أو وقّف طلبها.",
                            "/app/products?filter=dead", [{"id": d["id"], "name": d["name"], "name_ar": d["name_ar"], "stock": d["stock"], "value": _r(d["value"]), "sold60": d["sold60"]} for d in dead[:15]]))

    bc = await db.fetch("""
        select p.id, p.name, p.name_ar, sum((si.unit_cost - si.unit_price)*si.quantity) loss, sum(si.quantity) qty,
               max(si.unit_cost) cost, max(si.unit_price) price, min(amman_date(s.sold_at)) since
        from sale_items si join sales s on s.id=si.sale_id join products p on p.id=si.product_id
        where si.org_id=$1 and s.status='completed' and si.unit_cost > si.unit_price and amman_date(s.sold_at) > $2::date - 90
        group by 1,2,3 order by loss desc""", org_id, end)
    if bc:
        loss = sum(x["loss"] for x in bc)
        monthly = loss / 3
        out.append(_finding("below_cost", "high", monthly,
                            f"{len(bc)} products are sold below cost — about JD {monthly:,.0f} lost every month",
                            f"{len(bc)} أصناف عم تنباع بأقل من سعر التكلفة — خسارة تقريباً {monthly:,.0f} د.أ كل شهر",
                            "The supplier raised the cost but the shelf price was never updated. Update the selling price or renegotiate.",
                            "المورد رفع السعر وسعر البيع ما تعدّل. عدّل سعر البيع أو فاوض المورد.",
                            "/app/products?filter=below_cost",
                            [{"id": x["id"], "name": x["name"], "name_ar": x["name_ar"], "cost": _r(x["cost"]), "price": _r(x["price"]), "loss_90d": _r(x["loss"]), "since": x["since"]} for x in bc]))

    emp = await db.fetch("""
        select e.id, e.full_name, e.full_name_ar, b.name branch, b.name_ar branch_ar, count(*) filter (where s.status='completed') tx,
               coalesce(sum(s.discount) filter (where s.status='completed'),0) disc, coalesce(sum(s.subtotal) filter (where s.status='completed'),0) sub,
               count(*) filter (where s.status='void') voids, coalesce(sum(s.total) filter (where s.status='void'),0) void_value,
               count(*) filter (where s.discount > 0 and s.status='completed') disc_tx
        from sales s join employees e on e.id=s.employee_id left join branches b on b.id=e.branch_id
        where s.org_id=$1 and amman_date(s.sold_at) > $2::date - 90 group by 1,2,3,4,5 having count(*) > 50""", org_id, end)
    if len(emp) >= 3:
        rates = [x["disc"] / x["sub"] for x in emp if x["sub"]]
        vrates = [x["voids"] / (x["tx"] + x["voids"]) for x in emp]
        med, vmed = statistics.median(rates), statistics.median(vrates)
        for x in emp:
            rate = x["disc"] / x["sub"] if x["sub"] else 0
            vr = x["voids"] / (x["tx"] + x["voids"])
            if rate > max(med * 3, 0.02) or vr > max(vmed * 3, 0.015):
                excess = (rate - med) * x["sub"] + max(0, (vr - vmed)) * (x["tx"] + x["voids"]) * (x["void_value"] / max(1, x["voids"]))
                monthly = excess / 3
                out.append(_finding("cashier_anomaly", "high", monthly,
                                    f"{x['full_name']} ({x['branch']}) gives {rate * 100:.1f}% discounts vs {med * 100:.1f}% for others",
                                    f"{x['full_name_ar']} ({x['branch_ar'] or x['branch']}) بيعطي خصومات {rate * 100:.1f}% مقابل {med * 100:.1f}% لباقي الكاشيرية",
                                    f"{x['disc_tx']} discounted sales and {x['voids']} voided receipts in 90 days ({vr * 100:.1f}% void rate). Review the receipts and set a discount approval limit.",
                                    f"{x['disc_tx']} عملية بخصم و {x['voids']} فاتورة ملغية خلال 90 يوم (نسبة إلغاء {vr * 100:.1f}%). راجع الفواتير وحط حد للخصم بموافقة المدير.",
                                    f"/app/employees?highlight={x['id']}",
                                    [{"employee_id": x["id"], "name": x["full_name"], "discount_rate": round(rate * 100, 2), "peer_rate": round(med * 100, 2),
                                      "voids": x["voids"], "void_rate": round(vr * 100, 2), "excess_90d": _r(excess)}]))

    shr = await db.fetch("""
        with recv as (select pu.branch_id, pi.product_id, sum(pi.quantity) q from purchase_items pi join purchases pu on pu.id=pi.purchase_id
                      where pu.org_id=$1 and pu.status='received' group by 1,2),
             sold as (select s.branch_id, si.product_id, sum(si.quantity) q from sale_items si join sales s on s.id=si.sale_id
                      where s.org_id=$1 and s.status='completed' group by 1,2)
        select b.id branch_id, b.name branch, b.name_ar branch_ar, p.name, p.name_ar, c.name category, c.name_ar category_ar,
               (r.q - coalesce(sd.q,0)) expected, il.quantity actual, ((r.q - coalesce(sd.q,0)) - il.quantity) * p.cost loss
        from recv r join inventory_levels il on il.branch_id=r.branch_id and il.product_id=r.product_id
        left join sold sd on sd.branch_id=r.branch_id and sd.product_id=r.product_id
        join products p on p.id=r.product_id join branches b on b.id=r.branch_id left join categories c on c.id=p.category_id
        where (r.q - coalesce(sd.q,0)) - il.quantity >= 2""", org_id)
    by_b = defaultdict(list)
    for x in shr:
        by_b[(x["branch_id"], x["branch"], x["branch_ar"])].append(x)
    for (bid, bname, bname_ar), xs in by_b.items():
        loss = sum(x["loss"] for x in xs)
        if loss < 50:
            continue
        cats = defaultdict(float)
        cat_ar = {}
        for x in xs:
            cats[x["category"]] += x["loss"]
            cat_ar[x["category"]] = x.get("category_ar") or x["category"]
        topcat = max(cats, key=cats.get)
        out.append(_finding("shrinkage", "high" if loss > 300 else "medium", loss / 12,
                            f"JD {loss:,.0f} of stock is missing at {bname} — mostly {topcat}",
                            f"{loss:,.0f} د.أ بضاعة مفقودة بفرع {bname_ar} — أغلبها {cat_ar[topcat]}",
                            f"Counted stock is lower than (received − sold) for {len(xs)} items. Typical causes: theft of small high-value items, unrecorded damage, receiving errors. Do a spot count and move these items near the cashier.",
                            f"الجرد الفعلي أقل من (المستلم − المباع) لـ {len(xs)} صنف. الأسباب المعتادة: سرقة أصناف صغيرة وغالية، تالف ما انسجّل، أو أخطاء استلام. اعمل جرد سريع وانقل هالأصناف جنب الكاشير.",
                            f"/app/branches?highlight={bid}",
                            [{"name": x["name"], "name_ar": x["name_ar"], "category": x["category"], "expected": x["expected"], "actual": x["actual"], "loss": _r(x["loss"])}
                             for x in sorted(xs, key=lambda x: -x["loss"])[:12]]))

    exp = await db.fetch("""
        select p.id, p.name, p.name_ar, b.name branch, ib.quantity, ib.expiry_date, ib.quantity*p.cost value
        from inventory_batches ib join products p on p.id=ib.product_id join branches b on b.id=ib.branch_id
        where ib.org_id=$1 and ib.quantity>0 and ib.expiry_date <= $2::date + 14 order by ib.expiry_date""", org_id, end)
    if exp:
        val = sum(x["value"] for x in exp)
        expired = sum(1 for x in exp if x["expiry_date"] < end.isoformat())
        out.append(_finding("expiring", "medium" if val < 300 else "high", val,
                            f"{len(exp)} batches expire within 14 days (JD {val:,.0f} at cost)",
                            f"{len(exp)} دفعة بتنتهي صلاحيتها خلال 14 يوم ({val:,.0f} د.أ بسعر التكلفة)",
                            f"{expired} are already past their date. Move them to the front, bundle them, or ask the supplier for a swap.",
                            f"منها {expired} منتهية فعلاً. قدّمها عالرف، اعمل عليها عرض، أو اطلب من المورد يبدّلها.",
                            "/app/products?filter=expiring",
                            [{"id": x["id"], "name": x["name"], "name_ar": x["name_ar"], "branch": x["branch"], "quantity": x["quantity"], "expiry_date": x["expiry_date"], "value": _r(x["value"])} for x in exp[:20]]))

    sup = await db.fetch("""
        with x as (select pu.supplier_id, pi.product_id,
                     avg(pi.unit_cost) filter (where pu.ordered_at >= ($2::date - 45)) new_c,
                     avg(pi.unit_cost) filter (where pu.ordered_at < ($2::date - 60) and pu.ordered_at >= ($2::date - 150)) old_c,
                     sum(pi.quantity) filter (where pu.ordered_at >= ($2::date - 45)) q
                   from purchase_items pi join purchases pu on pu.id=pi.purchase_id where pu.org_id=$1 group by 1,2)
        select su.id, su.name, su.name_ar, count(*) items, avg((new_c-old_c)/old_c)*100 pct, sum((new_c-old_c)*q) extra
        from x join suppliers su on su.id=x.supplier_id where old_c > 0 and new_c > old_c * 1.04 group by 1,2,3 order by extra desc""", org_id, end)
    for s in sup[:3]:
        monthly = s["extra"] / 1.5
        out.append(_finding("supplier_price", "medium", monthly,
                            f"{s['name']} raised prices {s['pct']:.0f}% on {s['items']} items",
                            f"{s['name_ar']} رفع الأسعار {s['pct']:.0f}% على {s['items']} أصناف",
                            "Compare with another distributor or negotiate a volume discount before the next order.",
                            "قارن مع موزع ثاني أو فاوض على خصم كمية قبل الطلبية الجاية.",
                            f"/app/suppliers?highlight={s['id']}", [{"supplier_id": s["id"], "name": s["name"], "pct": _r(s["pct"], 1), "extra_45d": _r(s["extra"])}]))

    so = await db.fetch("""
        with v as (select si.product_id, s.branch_id, sum(si.line_total)/28.0 daily from sale_items si join sales s on s.id=si.sale_id
                   where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) > $2::date - 28 group by 1,2)
        select p.id, p.name, p.name_ar, b.name branch, v.daily, il.quantity from v join inventory_levels il on il.product_id=v.product_id and il.branch_id=v.branch_id
        join products p on p.id=v.product_id join branches b on b.id=v.branch_id where il.quantity <= 0 and v.daily > 1.5 order by v.daily desc""", org_id, end)
    if so:
        lost = sum(x["daily"] for x in so) * 7
        out.append(_finding("stockout", "high" if lost > 200 else "medium", lost * 30 / 7,
                            f"{len(so)} best sellers are out of stock — about JD {lost:,.0f} of sales lost per week",
                            f"{len(so)} من أكثر الأصناف مبيعاً خلصت — خسارة مبيعات تقريباً {lost:,.0f} د.أ بالأسبوع",
                            "Open the reorder planner to send purchase orders now.", "افتح مخطط إعادة الطلب وابعث الطلبيات هلأ.",
                            "/app/insights/reorder", [{"id": x["id"], "name": x["name"], "name_ar": x["name_ar"], "branch": x["branch"], "daily_sales": _r(x["daily"])} for x in so[:15]]))
    out.sort(key=lambda f: -(f["amount_jod"] or 0))
    return out


def _finding(kind, severity, amount, title, title_ar, body, body_ar, link, items):
    return {"kind": kind, "severity": severity, "amount_jod": _r(amount, 2), "title": title, "title_ar": title_ar,
            "body": body, "body_ar": body_ar, "link": link, "items": items}


@db.cached(300)
async def forecast(org_id: str, product_id: str | None = None, category_id: str | None = None, horizon: int = 90, branch_id: str | None = None) -> dict:
    end = await data_end(org_id)
    start = end - dt.timedelta(days=400)
    where, args = "", [org_id, start, end]
    if product_id:
        where += f" and si.product_id = ${len(args) + 1}"
        args.append(product_id)
    if category_id:
        where += f" and p.category_id = ${len(args) + 1}"
        args.append(category_id)
    if branch_id:
        where += f" and s.branch_id = ${len(args) + 1}"
        args.append(branch_id)
    rows = await db.fetch(f"""
        select amman_date(s.sold_at) d, sum(si.quantity) q, sum(si.line_total) rev
        from sale_items si join sales s on s.id=si.sale_id join products p on p.id=si.product_id
        where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) between $2 and $3 {where} group by 1 order by 1""", *args)
    hist = {dt.date.fromisoformat(r["d"]): (r["q"], r["rev"]) for r in rows}
    first = min(hist) if hist else end
    days = [first + dt.timedelta(days=i) for i in range((end - first).days + 1)]
    q = [hist.get(d, (0, 0))[0] for d in days]
    rev = [hist.get(d, (0, 0))[1] for d in days]
    price = (sum(rev) / sum(q)) if sum(q) else 0
    normal = [(d, v) for d, v in zip(days, q) if not in_ramadan(d)]
    recent = [v for d, v in normal[-28:]] or [0]
    base = statistics.mean(recent)
    wk = defaultdict(list)
    for d, v in normal[-84:]:
        wk[d.weekday()].append(v)
    allv = [v for d, v in normal[-84:]] or [1]
    m_all = statistics.mean(allv) or 1
    wf = {k: (statistics.mean(v) / m_all if m_all else 1) for k, v in wk.items()}
    mo = defaultdict(list)
    for d, v in normal:
        mo[d.month].append(v)
    m_year = statistics.mean([v for _, v in normal]) if normal else 1
    mf = {k: (statistics.mean(v) / m_year if m_year else 1) for k, v in mo.items()}
    cur_mf = mf.get(end.month, 1) or 1
    ram = [v for d, v in zip(days, q) if in_ramadan(d)]
    pre = [v for d, v in zip(days, q) if any(a - dt.timedelta(days=60) <= d < a for a, b in RAMADAN)]
    uplift = (statistics.mean(ram) / statistics.mean(pre)) if ram and pre and statistics.mean(pre) > 0 else 1.0
    resid = [v - base * wf.get(d.weekday(), 1) for d, v in normal[-56:]]
    sd = statistics.pstdev(resid) if len(resid) > 2 else base * 0.3
    fc = []
    for i in range(1, horizon + 1):
        d = end + dt.timedelta(days=i)
        f = base * wf.get(d.weekday(), 1) * ((mf.get(d.month, cur_mf) / cur_mf) if len(mo) >= 10 else 1)
        if in_ramadan(d):
            f *= uplift
        f = max(0.0, f)
        band = 1.28 * sd * math.sqrt(1 + i / 30)
        fc.append({"d": d.isoformat(), "q": round(f, 2), "low": round(max(0, f - band), 2), "high": round(f + band, 2), "ramadan": in_ramadan(d)})
    actual = [{"d": d.isoformat(), "q": v, "ramadan": in_ramadan(d)} for d, v in zip(days[-120:], q[-120:])]
    next30 = sum(x["q"] for x in fc[:30])
    events = [{"d": e[0].isoformat(), "en": e[1], "ar": e[2], "in_days": (e[0] - end).days} for e in EVENTS if 0 < (e[0] - end).days <= horizon]
    return {"actual": actual, "forecast": fc, "uplift_ramadan": round(uplift, 2), "avg_daily": round(base, 2), "next30_qty": round(next30, 1),
            "next30_revenue": round(next30 * price, 2), "unit_price": round(price, 3), "events": events,
            "ramadan_in_days": next(((a - end).days for a, b in RAMADAN if a > end), None)}


@db.cached(900)
async def ramadan_movers(org_id: str) -> list[dict]:
    rows = await db.fetch("""
        with r as (select si.product_id, sum(si.quantity)/30.0 q from sale_items si join sales s on s.id=si.sale_id
                   where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) between '2026-02-18' and '2026-03-19' group by 1),
             b as (select si.product_id, sum(si.quantity)/60.0 q from sale_items si join sales s on s.id=si.sale_id
                   where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) between '2025-12-19' and '2026-02-17' group by 1)
        select p.id, p.name, p.name_ar, r.q ram_daily, b.q base_daily, r.q/nullif(b.q,0) uplift
        from r join b on b.product_id=r.product_id join products p on p.id=r.product_id
        where b.q > 0.05 order by uplift desc limit 12""", org_id)
    return [{**x, "uplift": _r(x["uplift"], 2), "ram_daily": _r(x["ram_daily"], 2), "base_daily": _r(x["base_daily"], 2)} for x in rows]


@db.cached(180)
async def reorder(org_id: str, cover_days: int = 14, branch_id: str | None = None) -> dict:
    end = await data_end(org_id)
    bf = " and il.branch_id = $3" if branch_id else ""
    args = [org_id, end] + ([branch_id] if branch_id else [])
    rows = await db.fetch(f"""
        with v as (select si.product_id, s.branch_id, sum(si.quantity)/28.0 daily from sale_items si join sales s on s.id=si.sale_id
                   where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) > $2::date - 28 group by 1,2),
             onorder as (select pu.branch_id, pi.product_id, sum(pi.quantity) q from purchase_items pi join purchases pu on pu.id=pi.purchase_id
                   where pu.org_id=$1 and pu.status in ('sent','draft') group by 1,2)
        select p.id product_id, p.name, p.name_ar, p.cost, p.price, p.reorder_level, b.id branch_id, b.name branch, b.name_ar branch_ar,
               su.id supplier_id, su.name supplier, su.name_ar supplier_ar, su.email supplier_email, su.payment_terms_days,
               il.quantity stock, coalesce(v.daily,0) daily, coalesce(o.q,0) on_order
        from inventory_levels il join products p on p.id=il.product_id join branches b on b.id=il.branch_id
        left join suppliers su on su.id=p.supplier_id
        left join v on v.product_id=il.product_id and v.branch_id=il.branch_id
        left join onorder o on o.product_id=il.product_id and o.branch_id=il.branch_id
        where il.org_id=$1 and p.is_active {bf}""", *args)
    end_ram = next(((a - end).days for a, b in RAMADAN if a > end), 999)
    lines = []
    for r in rows:
        daily = r["daily"]
        need = daily * (cover_days + 2)
        cover = r["stock"] / daily if daily > 0 else None
        if (r["stock"] + r["on_order"] < max(need, r["reorder_level"] if daily > 0.2 else 0)) and daily > 0.05:
            qty = math.ceil(max(need, r["reorder_level"] * 1.5) - r["stock"] - r["on_order"])
            if qty <= 0:
                continue
            urgency = "critical" if (cover is not None and cover < 2) or r["stock"] <= 0 else "soon" if cover is not None and cover < 6 else "planned"
            lines.append({**r, "suggested_qty": qty, "cover_days": None if cover is None else round(cover, 1), "urgency": urgency,
                          "amount": round(qty * r["cost"], 3), "daily": round(daily, 2)})
    by_sup = defaultdict(list)
    for l in lines:
        by_sup[(l["supplier_id"], l["supplier"], l["supplier_ar"], l["supplier_email"])].append(l)
    groups = []
    for (sid, name, name_ar, email), ls in by_sup.items():
        ls.sort(key=lambda x: {"critical": 0, "soon": 1, "planned": 2}[x["urgency"]])
        groups.append({"supplier_id": sid, "supplier": name, "supplier_ar": name_ar, "email": email, "lines": ls,
                       "total": round(sum(x["amount"] for x in ls), 3), "critical": sum(1 for x in ls if x["urgency"] == "critical")})
    groups.sort(key=lambda g: (-g["critical"], -g["total"]))
    return {"groups": groups, "total": round(sum(g["total"] for g in groups), 3), "lines": len(lines),
            "critical": sum(1 for l in lines if l["urgency"] == "critical"), "ramadan_in_days": end_ram}


@db.cached(300)
async def rfm(org_id: str) -> dict:
    end = await data_end(org_id)
    rows = await db.fetch("""
        select c.id, c.full_name, c.full_name_ar, c.phone, c.area, c.loyalty_points,
               max(amman_date(s.sold_at)) last_visit, count(*) filter (where amman_date(s.sold_at) > $2::date - 180) freq,
               coalesce(sum(s.total) filter (where amman_date(s.sold_at) > $2::date - 180),0) monetary, count(*) lifetime_tx, sum(s.total) lifetime
        from customers c join sales s on s.customer_id=c.id and s.status='completed'
        where c.org_id=$1 group by 1,2,3,4,5,6""", org_id, end)
    if not rows:
        return {"segments": [], "customers": [], "at_risk": []}

    def q(vals, v):
        s = sorted(vals)
        return 1 + sum(1 for x in (s[len(s) // 5], s[2 * len(s) // 5], s[3 * len(s) // 5], s[4 * len(s) // 5]) if v > x)
    rec = [(end - dt.date.fromisoformat(r["last_visit"])).days for r in rows]
    freqs = [r["freq"] for r in rows]
    mons = [r["monetary"] for r in rows]
    seg_names = {"champions": ("Champions", "الأبطال"), "loyal": ("Loyal", "الأوفياء"), "at_risk": ("At risk", "معرّضين للخسارة"),
                 "new": ("New", "جداد"), "lost": ("Lost", "خسرناهم"), "regular": ("Regular", "عاديين")}
    out = []
    for r, rd in zip(rows, rec):
        R = 6 - q(rec, rd)
        F, M = q(freqs, r["freq"]), q(mons, r["monetary"])
        if R >= 4 and F >= 4:
            seg = "champions"
        elif rd > 75:
            seg = "lost"
        elif R <= 2 and F >= 3 or (rd > 30 and r["lifetime_tx"] >= 25):
            seg = "at_risk"
        elif F >= 4:
            seg = "loyal"
        elif r["lifetime_tx"] <= 3:
            seg = "new"
        else:
            seg = "regular"
        out.append({**r, "recency_days": rd, "R": R, "F": F, "M": M, "segment": seg, "monetary": _r(r["monetary"]), "lifetime": _r(r["lifetime"])})
    segs = defaultdict(lambda: {"count": 0, "revenue": 0.0})
    for c in out:
        segs[c["segment"]]["count"] += 1
        segs[c["segment"]]["revenue"] += c["monetary"]
    segments = [{"key": k, "en": seg_names[k][0], "ar": seg_names[k][1], "count": v["count"], "revenue": round(v["revenue"], 2)} for k, v in segs.items()]
    at_risk = sorted([c for c in out if c["segment"] == "at_risk"], key=lambda c: -c["lifetime"])
    return {"segments": sorted(segments, key=lambda s: -s["revenue"]), "customers": sorted(out, key=lambda c: -c["monetary"]), "at_risk": at_risk[:30]}


@db.cached(600)
async def basket(org_id: str, days: int = 60) -> list[dict]:
    end = await data_end(org_id)
    rows = await db.fetch("""
        with s as (select id from sales where org_id=$1 and status='completed' and amman_date(sold_at) > $2::date - $3::int),
             it as (select distinct si.sale_id, si.product_id from sale_items si join s on s.id=si.sale_id),
             n as (select count(*)::float n from s),
             pc as (select product_id, count(*) c from it group by 1),
             pairs as (select a.product_id a, b.product_id b, count(*) ab from it a join it b on a.sale_id=b.sale_id and a.product_id < b.product_id group by 1,2 having count(*) >= 25)
        select pa.name a_name, pa.name_ar a_name_ar, pb.name b_name, pb.name_ar b_name_ar, pairs.ab together,
               pairs.ab / n.n support, pairs.ab::float / pca.c conf_ab, (pairs.ab * n.n) / (pca.c * pcb.c) lift
        from pairs cross join n join pc pca on pca.product_id=pairs.a join pc pcb on pcb.product_id=pairs.b
        join products pa on pa.id=pairs.a join products pb on pb.id=pairs.b
        order by lift desc limit 20""", org_id, end, days)
    return [{**r, "support": _r(r["support"] * 100, 2), "conf_ab": _r(r["conf_ab"] * 100, 1), "lift": _r(r["lift"], 2)} for r in rows]


async def simulate(org_id: str, product_ids: list[str] | None, category_id: str | None, price_pct: float, cost_pct: float, discount_pct: float, elasticity: float = -1.3) -> dict:
    end = await data_end(org_id)
    where, args = "", [org_id, end]
    if product_ids:
        where = " and si.product_id = any($3::uuid[])"
        args.append(product_ids)
    elif category_id:
        where = " and p.category_id = $3"
        args.append(category_id)
    r = await db.fetchrow(f"""select coalesce(sum(si.quantity),0) q, coalesce(sum(si.line_total),0) rev, coalesce(sum(si.unit_cost*si.quantity),0) cost
        from sale_items si join sales s on s.id=si.sale_id join products p on p.id=si.product_id
        where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) > $2::date - 30 {where}""", *args)
    q0, rev0, cost0 = r["q"], r["rev"], r["cost"]
    eff_price = (1 + price_pct / 100) * (1 - discount_pct / 100)
    q1 = q0 * (eff_price ** elasticity) if q0 else 0
    p0 = rev0 / q0 if q0 else 0
    c0 = cost0 / q0 if q0 else 0
    rev1 = q1 * p0 * eff_price
    cost1 = q1 * c0 * (1 + cost_pct / 100)
    return {"baseline": {"qty": _r(q0, 1), "revenue": _r(rev0, 2), "profit": _r(rev0 - cost0, 2), "margin": _r(100 * (rev0 - cost0) / rev0 if rev0 else 0, 1)},
            "scenario": {"qty": _r(q1, 1), "revenue": _r(rev1, 2), "profit": _r(rev1 - cost1, 2), "margin": _r(100 * (rev1 - cost1) / rev1 if rev1 else 0, 1)},
            "elasticity": elasticity, "period_days": 30}


@db.cached(300)
async def cashflow(org_id: str, weeks: int = 8, opening: float | None = None) -> dict:
    end = await data_end(org_id)
    org = await db.fetchrow("select monthly_rent, opening_cash from organizations where id=$1", org_id)
    nb = await db.fetchval("select count(*) from branches where org_id=$1", org_id)
    weekly = await db.fetch("""select date_trunc('week', amman_date(sold_at))::date w, sum(total) rev from sales
        where org_id=$1 and status='completed' and amman_date(sold_at) > $2::date - 56 group by 1 order by 1""", org_id, end)
    avg_week = statistics.mean([w["rev"] for w in weekly[1:-1]]) if len(weekly) > 3 else (weekly[0]["rev"] if weekly else 0)
    cogs_ratio = await db.fetchval("""select sum(si.unit_cost*si.quantity)/nullif(sum(si.line_total),0) from sale_items si join sales s on s.id=si.sale_id
        where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) > $2::date - 56""", org_id, end) or 0.75
    payroll = await db.fetchval("select coalesce(sum(monthly_salary),0) from employees where org_id=$1 and is_active", org_id)
    dues = await db.fetch("""select pu.received_at::date + su.payment_terms_days due, sum(pu.total) amt from purchases pu join suppliers su on su.id=pu.supplier_id
        where pu.org_id=$1 and pu.status='received' and pu.received_at::date + su.payment_terms_days > $2 group by 1""", org_id, end)
    bal = opening if opening is not None else org["opening_cash"]
    out = []
    for i in range(weeks):
        ws, we = end + dt.timedelta(days=1 + 7 * i), end + dt.timedelta(days=7 * (i + 1))
        inflow = avg_week * (1.12 if any(in_ramadan(ws + dt.timedelta(days=k)) for k in range(7)) else 1)
        sup = sum(d["amt"] for d in dues if ws.isoformat() <= d["due"] <= we.isoformat())
        future_purchases = avg_week * cogs_ratio * (1 if i >= 4 else 0.35 * i / 4)
        month_start = any((ws + dt.timedelta(days=k)).day == 1 for k in range(7))
        sal = payroll if month_start else 0
        rent = org["monthly_rent"] * nb if month_start else 0
        outflow = sup + future_purchases + sal + rent
        bal += inflow - outflow
        out.append({"week_start": ws.isoformat(), "inflow": _r(inflow, 2), "supplier_payments": _r(sup + future_purchases, 2), "salaries": _r(sal, 2),
                    "rent": _r(rent, 2), "outflow": _r(outflow, 2), "net": _r(inflow - outflow, 2), "balance": _r(bal, 2)})
    low = min(out, key=lambda x: x["balance"]) if out else None
    return {"weeks": out, "opening": _r(opening if opening is not None else org["opening_cash"], 2), "lowest": low, "payroll": _r(payroll, 2)}


@db.cached(300)
async def compliance(org_id: str, days: int = 90) -> dict:
    end = await data_end(org_id)
    org = await db.fetchrow("select tax_number, name from organizations where id=$1", org_id)
    rows = await db.fetch("""select s.id, s.invoice_number, s.branch_id, b.name branch, s.sold_at, s.total, s.tax, s.status,
            (select coalesce(sum(si.line_total - si.line_total/(1+p.tax_rate/100)),0) from sale_items si join products p on p.id=si.product_id where si.sale_id=s.id) expected_tax
        from sales s join branches b on b.id=s.branch_id where s.org_id=$1 and amman_date(s.sold_at) > $2::date - $3::int""", org_id, end, days)
    issues = []
    dup_count = defaultdict(list)
    seqs = defaultdict(list)
    tax_bad = []
    for r in rows:
        dup_count[r["invoice_number"]].append(r)
        try:
            pre, yr, n = r["invoice_number"].rsplit("-", 2)
            seqs[(r["branch"], pre, yr)].append(int(n))
        except (ValueError, AttributeError):
            pass
        if r["status"] == "completed" and r["expected_tax"] and abs(r["tax"] - r["expected_tax"] * (r["total"] / max(r["total"], 0.001))) > 0.05 and abs(r["tax"] - r["expected_tax"]) > 0.05 * max(r["expected_tax"], 0.01):
            if r["tax"] == 0 or abs(r["tax"] - r["expected_tax"]) / max(r["expected_tax"], 0.01) > 0.3:
                tax_bad.append(r)
    dups = [v for v in dup_count.values() if len(v) > 1]
    gaps = []
    for (branch, pre, yr), ns in seqs.items():
        ns = sorted(ns)
        core = [n for n in ns if n < 800000]
        jumps = [n for n in ns if n >= 800000]
        s = set(core)
        if core:
            missing = [n for n in range(core[0], core[-1]) if n not in s]
            if missing:
                gaps.append({"branch": branch, "prefix": f"{pre}-{yr}", "missing": len(missing), "examples": missing[:5]})
        if jumps:
            gaps.append({"branch": branch, "prefix": f"{pre}-{yr}", "missing": 0, "out_of_sequence": len(jumps), "examples": jumps[:5]})
    score = 100.0
    if not org["tax_number"]:
        score -= 25
        issues.append({"key": "no_tax_number", "severity": "high", "en": "Your business tax number is missing", "ar": "الرقم الضريبي للمنشأة غير مُدخل", "count": 1, "link": "/app/settings"})
    if tax_bad:
        score -= min(25, 3 + len(tax_bad))
        issues.append({"key": "tax_mismatch", "severity": "high", "en": "Invoices where sales tax doesn't add up", "ar": "فواتير ضريبة المبيعات فيها مش مظبوطة",
                       "count": len(tax_bad), "items": [{"invoice": x["invoice_number"], "branch": x["branch"], "total": _r(x["total"]), "tax": _r(x["tax"]), "expected": _r(x["expected_tax"])} for x in tax_bad[:20]]})
    if dups:
        score -= min(20, 4 * len(dups))
        issues.append({"key": "duplicate_numbers", "severity": "high", "en": "Duplicate invoice numbers", "ar": "أرقام فواتير مكررة", "count": len(dups),
                       "items": [{"invoice": d[0]["invoice_number"], "branch": d[0]["branch"], "times": len(d)} for d in dups[:20]]})
    gap_total = sum(g.get("missing", 0) + g.get("out_of_sequence", 0) for g in gaps)
    if gap_total:
        score -= min(20, 2 + gap_total)
        issues.append({"key": "sequence_gaps", "severity": "medium", "en": "Gaps or jumps in invoice numbering", "ar": "فجوات أو قفزات بترقيم الفواتير", "count": gap_total, "items": gaps})
    voids = sum(1 for r in rows if r["status"] == "void")
    if rows and voids / len(rows) > 0.01:
        score -= 5
        issues.append({"key": "voids", "severity": "low", "en": "High share of voided invoices — keep a reason for each void", "ar": "نسبة عالية من الفواتير الملغية — سجّل سبب لكل إلغاء", "count": voids})
    return {"score": max(0, round(score, 1)), "invoices_checked": len(rows), "days": days, "issues": issues, "tax_number": org["tax_number"],
            "checklist": [
                {"en": "Business registered on the national e-invoicing portal", "ar": "تسجيل المنشأة على نظام الفوترة الوطني", "ok": bool(org["tax_number"])},
                {"en": "Every invoice has a unique sequential number", "ar": "كل فاتورة إلها رقم متسلسل فريد", "ok": not dups and not gap_total},
                {"en": "Sales tax calculated correctly per line", "ar": "ضريبة المبيعات محسوبة صح لكل سطر", "ok": not tax_bad},
                {"en": "Voids and returns documented", "ar": "الإلغاءات والمرتجعات موثّقة", "ok": not (rows and voids / len(rows) > 0.01)},
            ]}


@db.cached(300)
async def employees_perf(org_id: str, days: int = 30) -> list[dict]:
    end = await data_end(org_id)
    rows = await db.fetch("""
        select e.id, e.full_name, e.full_name_ar, e.job_title, e.phone, e.hired_at, e.monthly_salary, b.name branch, b.name_ar branch_ar,
          count(s.*) filter (where s.status='completed') tx, coalesce(sum(s.total) filter (where s.status='completed'),0) revenue,
          coalesce(sum(s.discount) filter (where s.status='completed'),0) discounts, coalesce(sum(s.subtotal) filter (where s.status='completed'),0) subtotal,
          count(s.*) filter (where s.status='void') voids
        from employees e left join branches b on b.id=e.branch_id
        left join sales s on s.employee_id=e.id and amman_date(s.sold_at) > $2::date - $3::int
        where e.org_id=$1 group by e.id, b.name, b.name_ar order by revenue desc""", org_id, end, days)
    for r in rows:
        r["basket"] = _r(r["revenue"] / r["tx"]) if r["tx"] else None
        r["discount_rate"] = _r(100 * r["discounts"] / r["subtotal"], 2) if r["subtotal"] else 0
        r["void_rate"] = _r(100 * r["voids"] / (r["tx"] + r["voids"]), 2) if (r["tx"] + r["voids"]) else 0
    rates = [r["discount_rate"] for r in rows if r["tx"]]
    med = statistics.median(rates) if rates else 0
    for r in rows:
        r["flag"] = bool(r["tx"]) and (r["discount_rate"] > max(3 * med, 2) or r["void_rate"] > 1.5)
    return rows
