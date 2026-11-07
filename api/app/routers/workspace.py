from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..auth import Ctx, require
from ..services import insights as I

router = APIRouter(prefix="/ws", tags=["workspace"])


@router.get("/sales")
async def sales(q: str | None = None, branch_id: str | None = None, status: str | None = None, payment: str | None = None,
                start: str | None = None, end: str | None = None, offset: int = 0, limit: int = 50, ctx: Ctx = Depends(require("view_sales"))):
    where, args = ["s.org_id=$1"], [ctx.org_id]

    def add(cond, v):
        args.append(v)
        where.append(cond.replace("?", f"${len(args)}"))
    if branch_id:
        add("s.branch_id=?", branch_id)
    if status:
        add("s.status=?", status)
    if payment:
        add("s.payment_method=?", payment)
    if start:
        add("amman_date(s.sold_at) >= ?::date", start)
    if end:
        add("amman_date(s.sold_at) <= ?::date", end)
    if q:
        add("(s.invoice_number ilike ? or c.full_name ilike ? or e.full_name ilike ?)", f"%{q}%")
    w = " and ".join(where)
    total = await db.fetchval(f"select count(*) from sales s left join customers c on c.id=s.customer_id left join employees e on e.id=s.employee_id where {w}", *args)
    items = await db.fetch(f"""select s.id, s.invoice_number, s.sold_at, s.total, s.discount, s.tax, s.payment_method, s.status, b.name branch, b.name_ar branch_ar,
            e.full_name cashier, e.full_name_ar cashier_ar, c.full_name customer, c.full_name_ar customer_ar,
            (select count(*) from sale_items si where si.sale_id=s.id) items
        from sales s left join branches b on b.id=s.branch_id left join employees e on e.id=s.employee_id left join customers c on c.id=s.customer_id
        where {w} order by s.sold_at desc offset {int(offset)} limit {min(int(limit), 200)}""", *args)
    return {"total": total, "items": items}


@router.get("/sales/{sale_id}")
async def sale(sale_id: str, ctx: Ctx = Depends(require("view_sales"))):
    s = await db.fetchrow("""select s.*, b.name branch, e.full_name cashier, c.full_name customer, c.phone customer_phone from sales s
        left join branches b on b.id=s.branch_id left join employees e on e.id=s.employee_id left join customers c on c.id=s.customer_id
        where s.id=$1 and s.org_id=$2""", sale_id, ctx.org_id)
    if not s:
        raise HTTPException(404)
    s["lines"] = await db.fetch("""select si.*, p.name, p.name_ar from sale_items si left join products p on p.id=si.product_id where si.sale_id=$1""", sale_id)
    return s


@router.get("/products")
async def products(q: str | None = None, category_id: str | None = None, filter: str | None = None, ctx: Ctx = Depends(require("view_sales"))):
    end = await I.data_end(ctx.org_id)
    rows = await db.fetch("""
        with sold as (select si.product_id, sum(si.quantity) q30, sum(si.line_total) rev30, sum(si.line_total - si.unit_cost*si.quantity) gp30
                      from sale_items si join sales s on s.id=si.sale_id where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) > $2::date - 30 group by 1),
             st as (select product_id, sum(quantity) stock from inventory_levels where org_id=$1 group by 1),
             ex as (select product_id, min(expiry_date) next_expiry from inventory_batches where org_id=$1 and quantity > 0 group by 1)
        select p.id, p.sku, p.barcode, p.name, p.name_ar, p.brand, p.size, p.cost, p.price, p.tax_rate, p.reorder_level, p.is_perishable, p.is_active,
               c.id category_id, c.name category, c.name_ar category_ar, su.name supplier, su.name_ar supplier_ar,
               coalesce(st.stock,0) stock, coalesce(sold.q30,0) sold30, coalesce(sold.rev30,0) revenue30, coalesce(sold.gp30,0) profit30, ex.next_expiry,
               case when p.price > 0 then round((p.price - p.cost)/p.price*100, 1) end margin
        from products p left join categories c on c.id=p.category_id left join suppliers su on su.id=p.supplier_id
        left join sold on sold.product_id=p.id left join st on st.product_id=p.id left join ex on ex.product_id=p.id
        where p.org_id=$1 order by revenue30 desc""", ctx.org_id, end)
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in (r["name"] or "").lower() or ql in (r["name_ar"] or "") or ql in (r["sku"] or "").lower() or ql in (r["barcode"] or "")]
    if category_id:
        rows = [r for r in rows if r["category_id"] == category_id]
    if filter == "below_cost":
        rows = [r for r in rows if r["cost"] > r["price"]]
    elif filter == "low_stock":
        rows = [r for r in rows if r["stock"] <= r["reorder_level"]]
    elif filter == "dead":
        rows = [r for r in rows if r["stock"] > 0 and r["sold30"] <= 0.5]
    elif filter == "expiring":
        lim = (end.toordinal() + 14)
        import datetime as dt
        rows = [r for r in rows if r["next_expiry"] and dt.date.fromisoformat(r["next_expiry"]).toordinal() <= lim]
    cats = await db.fetch("select id, name, name_ar from categories where org_id=$1 order by name", ctx.org_id)
    return {"items": rows, "categories": cats}


@router.get("/products/{pid}")
async def product(pid: str, ctx: Ctx = Depends(require("view_sales"))):
    p = await db.fetchrow("""select p.*, c.name category, c.name_ar category_ar, su.name supplier, su.id supplier_id from products p
        left join categories c on c.id=p.category_id left join suppliers su on su.id=p.supplier_id where p.id=$1 and p.org_id=$2""", pid, ctx.org_id)
    if not p:
        raise HTTPException(404)
    p["stock"] = await db.fetch("""select b.name branch, b.name_ar branch_ar, il.quantity from inventory_levels il join branches b on b.id=il.branch_id where il.product_id=$1""", pid)
    p["batches"] = await db.fetch("""select b.name branch, ib.quantity, ib.expiry_date from inventory_batches ib join branches b on b.id=ib.branch_id where ib.product_id=$1 order by expiry_date""", pid)
    p["weekly"] = await db.fetch("""select date_trunc('week', amman_date(s.sold_at))::date w, sum(si.quantity) q, sum(si.line_total) rev, avg(si.unit_cost) cost, avg(si.unit_price) price
        from sale_items si join sales s on s.id=si.sale_id where si.product_id=$1 and s.status='completed' group by 1 order by 1""", pid)
    p["aliases"] = await db.fetch("select alias, source from product_aliases where product_id=$1", pid)
    p["forecast"] = await I.forecast(ctx.org_id, product_id=pid, horizon=60)
    return p


class ProductPatch(BaseModel):
    price: float | None = None
    cost: float | None = None
    reorder_level: int | None = None
    is_active: bool | None = None


@router.patch("/products/{pid}")
async def patch_product(pid: str, p: ProductPatch, ctx: Ctx = Depends(require("manage_inventory"))):
    data = {k: v for k, v in p.model_dump().items() if v is not None}
    if data:
        sets = ", ".join(f"{k}=${i + 3}" for i, k in enumerate(data))
        await db.execute(f"update products set {sets} where id=$1 and org_id=$2", pid, ctx.org_id, *data.values())
        db.cache_clear()
        await db.audit(ctx.org_id, ctx.user.id, "product.updated", "product", pid, data)
    return {"ok": True}


@router.get("/customers")
async def customers(q: str | None = None, segment: str | None = None, ctx: Ctx = Depends(require("view_sales"))):
    data = await I.rfm(ctx.org_id)
    items = data["customers"]
    if segment:
        items = [c for c in items if c["segment"] == segment]
    if q:
        ql = q.lower()
        items = [c for c in items if ql in (c["full_name"] or "").lower() or ql in (c["full_name_ar"] or "") or ql in (c["phone"] or "")]
    return {"segments": data["segments"], "items": items[:500], "total": len(items)}


@router.get("/customers/{cid}")
async def customer(cid: str, ctx: Ctx = Depends(require("view_sales"))):
    c = await db.fetchrow("select * from customers where id=$1 and org_id=$2", cid, ctx.org_id)
    if not c:
        raise HTTPException(404)
    c["sales"] = await db.fetch("""select s.id, s.invoice_number, s.sold_at, s.total, b.name branch from sales s left join branches b on b.id=s.branch_id
        where s.customer_id=$1 and s.status='completed' order by s.sold_at desc limit 50""", cid)
    c["favorites"] = await db.fetch("""select p.name, p.name_ar, sum(si.quantity) q, sum(si.line_total) rev from sale_items si join sales s on s.id=si.sale_id
        join products p on p.id=si.product_id where s.customer_id=$1 and s.status='completed' group by 1,2 order by q desc limit 8""", cid)
    c["monthly"] = await db.fetch("""select to_char(date_trunc('month', amman_date(sold_at)),'YYYY-MM') m, sum(total) rev, count(*) n from sales
        where customer_id=$1 and status='completed' group by 1 order by 1""", cid)
    return c


@router.get("/suppliers")
async def suppliers(ctx: Ctx = Depends(require("view_sales"))):
    return await db.fetch("""select su.*, (select count(*) from products p where p.supplier_id=su.id) products,
            (select coalesce(sum(total),0) from purchases pu where pu.supplier_id=su.id and pu.ordered_at > now() - interval '90 days') spend90,
            (select max(ordered_at) from purchases pu where pu.supplier_id=su.id) last_order,
            (select count(*) from purchases pu where pu.supplier_id=su.id and pu.status in ('sent','draft')) open_orders
        from suppliers su where su.org_id=$1 order by spend90 desc""", ctx.org_id)


@router.get("/suppliers/{sid}")
async def supplier(sid: str, ctx: Ctx = Depends(require("view_sales"))):
    s = await db.fetchrow("select * from suppliers where id=$1 and org_id=$2", sid, ctx.org_id)
    if not s:
        raise HTTPException(404)
    s["purchases"] = await db.fetch("""select pu.id, pu.po_number, pu.ordered_at, pu.received_at, pu.status, pu.total, b.name branch, pu.emailed_at
        from purchases pu left join branches b on b.id=pu.branch_id where pu.supplier_id=$1 order by ordered_at desc limit 40""", sid)
    s["products"] = await db.fetch("select id, name, name_ar, cost, price from products where supplier_id=$1 order by name", sid)
    s["cost_trend"] = await db.fetch("""select date_trunc('month', pu.ordered_at)::date m, sum(pi.line_total)/nullif(sum(pi.quantity),0) avg_cost
        from purchase_items pi join purchases pu on pu.id=pi.purchase_id where pu.supplier_id=$1 group by 1 order by 1""", sid)
    return s


@router.get("/employees")
async def employees(days: int = 30, ctx: Ctx = Depends(require("view_sales"))):
    return await I.employees_perf(ctx.org_id, days)


@router.get("/branches")
async def branches(ctx: Ctx = Depends(require("view_sales"))):
    end = await I.data_end(ctx.org_id)
    rows = await db.fetch("""
        select b.id, b.name, b.name_ar, b.city, b.area, b.lat, b.lng, b.opened_at,
          coalesce(sum(s.total) filter (where amman_date(s.sold_at) > $2::date - 30),0) revenue30,
          count(s.*) filter (where amman_date(s.sold_at) > $2::date - 30) tx30,
          coalesce(sum(s.total) filter (where amman_date(s.sold_at) between $2::date - 60 and $2::date - 31),0) prev30,
          coalesce(sum(s.discount) filter (where amman_date(s.sold_at) > $2::date - 30),0) disc30,
          (select count(*) from employees e where e.branch_id=b.id) staff,
          (select coalesce(sum(il.quantity*p.cost),0) from inventory_levels il join products p on p.id=il.product_id where il.branch_id=b.id) stock_value
        from branches b left join sales s on s.branch_id=b.id and s.status='completed' and amman_date(s.sold_at) > $2::date - 60
        where b.org_id=$1 group by b.id order by revenue30 desc""", ctx.org_id, end)
    for r in rows:
        r["basket"] = round(r["revenue30"] / r["tx30"], 3) if r["tx30"] else 0
        r["growth"] = round(100 * (r["revenue30"] - r["prev30"]) / r["prev30"], 1) if r["prev30"] else None
        r["margin"] = await db.fetchval("""select round(sum(si.line_total - si.unit_cost*si.quantity)/nullif(sum(si.line_total),0)*100,1) from sale_items si
            join sales s on s.id=si.sale_id where s.branch_id=$1 and s.status='completed' and amman_date(s.sold_at) > $2::date - 30""", r["id"], end)
    trend = await db.fetch("""select b.name, date_trunc('week', amman_date(s.sold_at))::date w, sum(s.total) rev from sales s join branches b on b.id=s.branch_id
        where s.org_id=$1 and s.status='completed' and amman_date(s.sold_at) > $2::date - 120 group by 1,2 order by 2""", ctx.org_id, end)
    return {"items": rows, "trend": trend}


@router.get("/purchases")
async def purchases(status: str | None = None, ctx: Ctx = Depends(require("view_sales"))):
    args = [ctx.org_id]
    w = "pu.org_id=$1"
    if status:
        args.append(status)
        w += " and pu.status=$2"
    return await db.fetch(f"""select pu.id, pu.po_number, pu.ordered_at, pu.received_at, pu.status, pu.total, pu.emailed_at, su.name supplier, su.name_ar supplier_ar, b.name branch,
        (select count(*) from purchase_items pi where pi.purchase_id=pu.id) lines
        from purchases pu left join suppliers su on su.id=pu.supplier_id left join branches b on b.id=pu.branch_id where {w} order by pu.ordered_at desc limit 200""", *args)
