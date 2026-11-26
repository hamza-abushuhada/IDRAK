"""خطّ مزامنة POS — الطبقة التي تلمس قاعدة البيانات.

يأخذ أحداث الموصّل (model.Event)، يطبّعها إلى جداول الأعمال القانونية
(sales / sale_items / products / inventory_levels) بشكل idempotent، ضمن
معاملة واحدة لكل مهمّة، مع تسجيل كامل في pos_sync_jobs / pos_source_records /
pos_sync_errors.

مبادئ لا تُخرَق:
- عزل المستأجر: كل استعلام مقيّد بـ org_id المأخوذ من الاتصال فقط.
- idempotency: الحدث نفسه (بصمة متطابقة) لا يُنتج بيعاً/حركة مكرّرة.
- سلامة المعاملة: ترويسة الفاتورة وبنودها تُكتب معاً أو لا تُكتب.
- خارج الترتيب: الحدث الأقدم من المخزَّن يُتجاهَل (آخر إصدار يفوز).
- فشل آمن: الحدث الفاسد يُسجَّل في pos_sync_errors ويُعاد، والباقي يكمل.

ملاحظة المخزون: حركات المخزون تُطبَّق مرّة واحدة لكل external_id (idempotent)؛
تحديث حركة مخزون سابقة يُسجَّل كـ skipped بدل إعادة تطبيق الفرق — اختيار
محافظ يتفادى أي ازدواج في حسابات المخزون القائمة (موثَّق في docs).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import uuid
from decimal import Decimal

from ... import db
from ...cleaning.arabic import match_key
from . import model, sync_logic, registry

AMMAN = model.AMMAN

# قناة البيع الافتراضية لكل مزوّد (تُكتب في sales.channel للتحليلات الموحّدة).
_DEFAULT_CHANNEL = {"demo": "in_store", "lab_pos": "in_store", "lab_web": "online"}


def _default_channel(provider_code: str) -> str:
    return _DEFAULT_CHANNEL.get(provider_code, "other")


def _seed_for(identity: str) -> int:
    """بذرة حتميّة لهوية المصدر (مؤسسة+حساب) — لا للـ connection_id — حتى تبقى
    بيانات الموصّل التجريبي ثابتة تماماً عبر قطع الاتصال وإعادته."""
    digest = hashlib.sha256((identity or "0").encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _valid_barcode(value: str | None) -> bool:
    if not value:
        return False
    digits = re.sub(r"\D", "", value)
    return 8 <= len(digits) <= 14 and len(set(digits)) > 1


def build_adapter(connection: dict, org_id: str, now: dt.datetime | None = None):
    """يُنشئ موصّلاً منفَّذاً للاتصال، أو يرفع ValueError إن كان المزوّد غير منفَّذ.
    البذرة التجريبية مشتقّة من (org_id + account_ref) لا من connection_id، فتبقى
    البيانات ثابتة عند إعادة الربط."""
    code = connection["provider_code"]
    cls = registry.get_adapter_class(code)
    if cls is None:
        raise ValueError(f"provider '{code}' is supported architecturally but not implemented yet")
    if code == "demo":
        account_ref = connection.get("account_ref") or "default"
        return cls(seed=_seed_for(f"{org_id}:{account_ref}"), now=now or dt.datetime.now(AMMAN))
    if code in ("lab_pos", "lab_web"):
        cfg = connection.get("config") or {}
        from . import lab
        # السرّ يُقرأ من البيئة (لا يُخزَّن في config/قاعدة): نفس سرّ المختبر المحلّي.
        secret = os.environ.get("IDRAK_LAB_WEBHOOK_SECRET") or lab.DEFAULT_SECRET
        authorization = None
        if os.environ.get("IDRAK_ENVIRONMENT") == "staging":
            user = os.environ.get("IDRAK_LAB_ACCESS_USER", "lab")
            password = os.environ.get("IDRAK_LAB_ACCESS_PASSWORD")
            if password:
                import base64
                authorization = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        return cls(base_url=cfg.get("base_url") or lab.DEFAULT_BASE_URL,
                   secret=secret, branch=cfg.get("branch_name") or lab.DEFAULT_BRANCH,
                   authorization=authorization)
    return cls()


# --------------------------------------------------------------------------
# resolvers: ربط الإشارات (اسم/باركود/هاتف) بمعرّفات إدراك داخل المؤسسة.
# كلّها تعمل داخل نفس المعاملة (conn c) ومقيّدة بـ org_id.
# --------------------------------------------------------------------------
async def _resolve_branch(c, org_id: str, name: str | None, cache: dict) -> str | None:
    if not name:
        return None
    k = match_key(name)
    if k in cache:
        return cache[k]
    row = await c.fetchrow("select id from branches where org_id=$1 and lower(name)=lower($2) limit 1", org_id, name)
    bid = row["id"] if row else await c.fetchval(
        "insert into branches(org_id,name,name_ar) values($1,$2,$2) returning id", org_id, name)
    cache[k] = bid
    return bid


async def _resolve_employee(c, org_id: str, branch_id, name: str | None, cache: dict) -> str | None:
    if not name:
        return None
    k = match_key(name)
    if k in cache:
        return cache[k]
    row = await c.fetchrow("select id from employees where org_id=$1 and lower(full_name)=lower($2) limit 1", org_id, name)
    eid = row["id"] if row else await c.fetchval(
        "insert into employees(org_id,branch_id,full_name,full_name_ar,job_title) values($1,$2,$3,$3,'cashier') returning id",
        org_id, branch_id, name)
    cache[k] = eid
    return eid


async def _resolve_customer(c, org_id: str, phone: str | None) -> str | None:
    if not phone:
        return None
    return await c.fetchval("select id from customers where org_id=$1 and phone=$2 limit 1", org_id, phone)


async def _resolve_product(c, org_id: str, connection_id: str, pref: "model.ProductRef",
                           price: Decimal | None, cost: Decimal | None, cache: dict) -> str:
    """يطابق الصنف بالباركود ثم بالاسم داخل المؤسسة، وينشئه إن لزم مع وسم
    مصدره (pos_connection_id). يُبقي السعر/التكلفة إن عُرفت."""
    bc = re.sub(r"\D", "", pref.barcode) if _valid_barcode(pref.barcode) else None
    sku = (pref.sku or "").strip() or None
    if bc:
        key = ("bc", bc)
    elif sku:
        key = ("sku", sku.lower())
    else:
        key = ("nm", match_key(pref.name))
    if key in cache:
        return cache[key]
    row = None
    if bc:
        row = await c.fetchrow("select id from products where org_id=$1 and barcode=$2 limit 1", org_id, bc)
    if row is None and sku:
        row = await c.fetchrow("select id from products where org_id=$1 and lower(sku)=lower($2) limit 1", org_id, sku)
    if row is None:
        row = await c.fetchrow("select id from products where org_id=$1 and lower(name)=lower($2) limit 1", org_id, pref.name)
    if row is not None:
        cache[key] = row["id"]
        return row["id"]
    pid = await c.fetchval(
        """insert into products(org_id,name,name_ar,sku,barcode,cost,price,pos_connection_id)
           values($1,$2,$3,$4,$5,$6,$7,$8) returning id""",
        org_id, pref.name, pref.name_ar, pref.sku, bc,
        cost if cost is not None else Decimal("0"), price if price is not None else Decimal("0"), connection_id)
    cache[key] = pid
    return pid


# --------------------------------------------------------------------------
# حركة المخزون: مصدر واحد للتحريك (upsert آمن على inventory_levels).
# البيع المكتمل يُنقِص المخزون، المرتجع يزيده. عند تحديث فاتورة سابقة يُعكَس
# أثرها القديم أولاً ثم يُطبَّق الجديد — فلا ازدواج. التكرار الحرفيّ لا يصل هنا
# (يُتخطّى كـ idempotent قبلها)، فيبقى الحساب صحيحاً عبر إعادة المزامنة.
# --------------------------------------------------------------------------
def _sale_sign(status: str) -> Decimal:
    if status == "completed":
        return Decimal("-1")   # بيع: يخرج من المخزون
    if status == "returned":
        return Decimal("1")    # مرتجع: يعود للمخزون
    return Decimal("0")        # void: لا أثر مباشر (يُعالَج بالعكس عند الإلغاء)


async def _move_inventory(c, org_id: str, branch_id, product_id, delta: Decimal):
    """يحرّك رصيد صنف في فرع بالدلتا (upsert آمن) ويُعيد معرّف صفّ
    inventory_levels — معرّف داخليّ صالح لخريطة المصدر."""
    if not branch_id or not product_id or delta == 0:
        return None
    return await c.fetchval(
        """insert into inventory_levels(org_id,branch_id,product_id,quantity,updated_at)
           values($1,$2,$3,$4,now())
           on conflict (branch_id,product_id)
           do update set quantity = inventory_levels.quantity + excluded.quantity, updated_at=now()
           returning id""",
        org_id, branch_id, product_id, delta)


async def _set_inventory(c, org_id: str, branch_id, product_id, quantity: Decimal):
    """يضبط رصيد صنف إلى قيمة مطلقة (للمصادر التي ترسل on_hand مطلقاً، كالمختبر).
    يُعيد معرّف صفّ inventory_levels."""
    if not branch_id or not product_id:
        return None
    return await c.fetchval(
        """insert into inventory_levels(org_id,branch_id,product_id,quantity,updated_at)
           values($1,$2,$3,$4,now())
           on conflict (branch_id,product_id)
           do update set quantity = excluded.quantity, updated_at=now()
           returning id""",
        org_id, branch_id, product_id, quantity)


async def _apply_sale_inventory(c, org_id: str, branch_id, status: str,
                                lines: list[tuple]) -> None:
    sign = _sale_sign(status)
    if sign == 0:
        return
    for product_id, qty in lines:
        await _move_inventory(c, org_id, branch_id, product_id, sign * Decimal(qty))


async def _reverse_prior_sale_inventory(c, org_id: str, sale_id: str) -> None:
    """يعكس أثر فاتورة سابقة على المخزون قبل حذفها/تحديثها/إلغائها."""
    prior = await c.fetchrow("select branch_id, status from sales where id=$1 and org_id=$2", sale_id, org_id)
    if not prior:
        return
    sign = _sale_sign(prior["status"])
    if sign == 0:
        return
    items = await c.fetch("select product_id, quantity from sale_items where sale_id=$1 and org_id=$2", sale_id, org_id)
    for it in items:
        await _move_inventory(c, org_id, prior["branch_id"], it["product_id"], -sign * Decimal(it["quantity"]))


# --------------------------------------------------------------------------
# apply: كتابة السجلّ القانوني لحدث واحد (داخل المعاملة).
# --------------------------------------------------------------------------
async def _apply_sale(c, org_id: str, connection_id: str, ev: "model.Event",
                      prev_internal_id: str | None, caches: dict,
                      channel: str | None = None, adjust_inventory: bool = True) -> str:
    """يُدرج/يعيد إدراج فاتورة وبنودها ذرّيّاً. عند التحديث يعكس أثر المخزون
    القديم ويحذف النسخة السابقة (cascade على البنود) ثم يعيد البناء ويطبّق أثر
    المخزون الجديد — فلا بنود قديمة ولا ازدواج في المخزون.

    channel: قناة البيع (in_store/online/other) تُكتب في sales.channel للتحليلات.
    adjust_inventory: إذا كان المصدر يرسل أرصدة مخزون صريحة (كالمختبر) نضبطه False
    فلا يُحتسب نقص المخزون مرّتين."""
    sale: model.Sale = ev.payload
    if prev_internal_id:
        if adjust_inventory:
            await _reverse_prior_sale_inventory(c, org_id, prev_internal_id)
        await c.execute("delete from sales where id=$1 and org_id=$2", prev_internal_id, org_id)
    branch_id = await _resolve_branch(c, org_id, sale.branch, caches["branch"])
    emp_id = await _resolve_employee(c, org_id, branch_id, sale.cashier, caches["emp"])
    cust_id = await _resolve_customer(c, org_id, sale.customer_phone)
    sold_at = model._to_utc(sale.occurred_at)
    status = "returned" if ev.type == model.EVENT_REFUND else ("void" if ev.type == model.EVENT_SALE_VOID else "completed")
    sid = uuid.uuid4()
    await c.execute(
        """insert into sales(id,org_id,branch_id,employee_id,customer_id,invoice_number,sold_at,
                             subtotal,discount,tax,total,payment_method,status,pos_connection_id,channel)
           values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)""",
        sid, org_id, branch_id, emp_id, cust_id, sale.invoice_number, sold_at,
        sale.subtotal(), sale.discount, sale.tax, sale.total(), sale.payment_method, status, connection_id, channel)
    item_recs, inv_lines = [], []
    for line in sale.lines:
        pid = await _resolve_product(c, org_id, connection_id, line.product, line.unit_price, line.unit_cost, caches["prod"])
        item_recs.append((uuid.uuid4(), org_id, sid, pid, line.quantity, line.unit_price,
                          line.unit_cost, line.discount, line.line_total()))
        inv_lines.append((pid, line.quantity))
    if item_recs:
        await c.executemany(
            """insert into sale_items(id,org_id,sale_id,product_id,quantity,unit_price,unit_cost,discount,line_total)
               values($1,$2,$3,$4,$5,$6,$7,$8,$9)""", item_recs)
    if adjust_inventory:
        await _apply_sale_inventory(c, org_id, branch_id, status, inv_lines)
    return str(sid)


async def _apply_product(c, org_id: str, connection_id: str, ev: "model.Event", caches: dict) -> str:
    pu: model.ProductUpdate = ev.payload
    pid = await _resolve_product(c, org_id, connection_id, pu.product, pu.price, pu.cost, caches["prod"])
    sets, args = [], []
    if pu.cost is not None:
        args.append(pu.cost); sets.append(f"cost=${len(args) + 2}")
    if pu.price is not None:
        args.append(pu.price); sets.append(f"price=${len(args) + 2}")
    if sets:
        await c.execute(f"update products set {', '.join(sets)} where id=$1 and org_id=$2", pid, org_id, *args)
    return pid


async def _apply_inventory(c, org_id: str, connection_id: str, ev: "model.Event", caches: dict) -> str:
    """حركة مخزون صريحة (رصيد افتتاحي أو تسوية). تحرّك الكمية بالدلتا على
    inventory_levels الموجود؛ كل حركة لها external_id فريد فتُطبَّق مرّة واحدة
    (idempotent عبر خريطة المصدر)."""
    mv: model.InventoryMovement = ev.payload
    branch_id = await _resolve_branch(c, org_id, mv.branch, caches["branch"])
    pid = await _resolve_product(c, org_id, connection_id, mv.product, None, None, caches["prod"])
    if getattr(mv, "absolute", False):
        inv_id = await _set_inventory(c, org_id, branch_id, pid, Decimal(mv.delta))
    else:
        inv_id = await _move_inventory(c, org_id, branch_id, pid, Decimal(mv.delta))
    return str(inv_id) if inv_id else ""


# --------------------------------------------------------------------------
# معالجة حدث واحد (داخل المعاملة) — مشتركة بين المزامنة بالسحب والـ webhook.
# --------------------------------------------------------------------------
async def _process_event(c, p: dict, ev: "model.Event", counts, job_id) -> None:
    org_id, connection_id = p["org_id"], p["connection_id"]
    try:
        ev.validate()
    except model.InvalidEvent as exc:
        counts.failed += 1
        await _record_error(c, org_id, connection_id, job_id, ev, str(exc))
        return
    try:
        chash = ev.content_hash()
        # هوية المصدر الثابتة (مستقلّة عن connection_id) ومميَّزة بالكيان لا بنوع
        # الحدث: بيع الفاتورة ومرتجعها وإلغاؤها تشترك في سجلّ واحد فلا ازدواج.
        ent = ev.entity()
        existing = await c.fetchrow(
            "select id, connection_id, entity, internal_id, content_hash, source_version"
            " from pos_source_records"
            " where org_id=$1 and provider_code=$2 and account_ref=$3 and entity=$4 and external_id=$5",
            org_id, p["provider_code"], p["account_ref"], ent, ev.external_id)
        prior = sync_logic.ExistingRecord(existing["content_hash"], existing["source_version"] or "") if existing else None
        action = sync_logic.decide(prior, chash, ev.version_key())
        if action in (sync_logic.SKIP_DUPLICATE, sync_logic.SKIP_STALE):
            if existing and str(existing["connection_id"]) != connection_id:
                await _adopt(c, org_id, connection_id, existing)
            counts.record(action)
            return
        prev_internal = existing["internal_id"] if existing else None
        if ev.type in (model.EVENT_SALE, model.EVENT_REFUND):
            internal_id = await _apply_sale(c, org_id, connection_id, ev, prev_internal, p["caches"],
                                            channel=p["channel"], adjust_inventory=p["adjust_inv"])
        elif ev.type == model.EVENT_SALE_VOID:
            if prev_internal:
                if p["adjust_inv"]:
                    await _reverse_prior_sale_inventory(c, org_id, prev_internal)
                await c.execute("update sales set status='void', pos_connection_id=$3 where id=$1 and org_id=$2",
                                prev_internal, org_id, connection_id)
            internal_id = prev_internal or ""
        elif ev.type == model.EVENT_PRODUCT:
            internal_id = await _apply_product(c, org_id, connection_id, ev, p["caches"])
        elif ev.type == model.EVENT_INVENTORY:
            internal_id = await _apply_inventory(c, org_id, connection_id, ev, p["caches"])
        else:
            counts.failed += 1
            return
        await _upsert_source_record(c, org_id, connection_id, p["provider_code"], p["account_ref"], ev, internal_id, chash)
        counts.record(action)
    except Exception as exc:  # فشل غير متوقّع لحدث واحد: سجّله وأكمل
        counts.failed += 1
        await _record_error(c, org_id, connection_id, job_id, ev, f"apply error: {exc}")


def _proc_ctx(connection: dict, org_id: str) -> dict:
    provider_code = connection["provider_code"]
    cfg = connection.get("config") or {}
    return {"org_id": org_id, "connection_id": str(connection["id"]), "provider_code": provider_code,
            "account_ref": connection.get("account_ref") or "default",
            "channel": cfg.get("channel") or _default_channel(provider_code),
            "adjust_inv": bool(cfg.get("sales_adjust_inventory", True)),
            "caches": {"branch": {}, "emp": {}, "prod": {}}}


# --------------------------------------------------------------------------
# المنسّق: تشغيل مزامنة كاملة لاتصال واحد.
# --------------------------------------------------------------------------
async def run_sync(org_id: str, user_id: str | None, connection: dict,
                   trigger: str = "manual", initial: bool = False) -> dict:
    connection_id = str(connection["id"])
    pctx = _proc_ctx(connection, org_id)
    adp = build_adapter(connection, org_id)
    ctx_cursor = connection.get("cursor") or {}

    import anyio
    if initial:
        events = list(await anyio.to_thread.run_sync(adp.initial_events))
        next_cursor = {"initial_done": True, "round": 0}
    else:
        from .adapter import AdapterContext
        ac = AdapterContext(org_id=org_id, config=connection.get("config") or {}, cursor=ctx_cursor)
        events, next_cursor = await anyio.to_thread.run_sync(lambda: adp.fetch_changes(ac))

    # استطلاع تلقائي بلا جديد: نلمس آخر مزامنة ونخرج بلا مهمّة فارغة في السجلّ.
    if not events and trigger == "scheduled" and not initial:
        await db.execute(
            "update pos_connections set last_sync_at=now(), last_success_at=now(), cursor=$2, updated_at=now() where id=$1 and org_id=$3",
            connection_id, next_cursor, org_id)
        return {"job_id": None, "status": "success", "imported": 0, "updated": 0, "skipped": 0, "failed": 0}

    counts = sync_logic.SyncCounts()
    job_id = await db.fetchval(
        """insert into pos_sync_jobs(org_id,connection_id,trigger,status,cursor_before)
           values($1,$2,$3,'running',$4) returning id""",
        org_id, connection_id, "initial" if initial else trigger, ctx_cursor)

    async with db.transaction() as c:
        for ev in events:
            await _process_event(c, pctx, ev, counts, job_id)

    status = counts.status()
    now = dt.datetime.now(dt.timezone.utc)
    await db.execute(
        "update pos_sync_jobs set status=$2, counts=$3, cursor_after=$4, finished_at=now() where id=$1",
        job_id, status, counts.as_dict(), next_cursor)
    await db.execute(
        """update pos_connections set
             status = case when $2='failed' then 'error' else 'connected' end,
             cursor=$3, last_sync_at=$4,
             last_success_at = case when $2 <> 'failed' then $4 else last_success_at end,
             last_error = case when $2='failed' then $5 else null end,
             sync_count = sync_count + 1, updated_at=now()
           where id=$1 and org_id=$6""",
        connection_id, status, next_cursor, now,
        (f"{counts.failed} record(s) failed" if counts.failed else None), org_id)
    await db.audit(org_id, user_id, "pos.sync", "pos_connection", connection_id,
                   {"job": str(job_id), "trigger": trigger, "initial": initial, **counts.as_dict()})
    db.cache_clear()  # اللوحة/التقارير مخبّأة؛ البيع الجديد يجب أن يظهر فوراً
    return {"job_id": str(job_id), "status": status, **counts.as_dict()}


# --------------------------------------------------------------------------
# استقبال webhook موقّع: تحقّق التوقيع + حماية إعادة التشغيل (replay) +
# idempotency ثم تطبيق الحدث الواحد عبر نفس المنطق المعزول بالمؤسسة.
# --------------------------------------------------------------------------
class WebhookRejected(Exception):
    """توقيع webhook غير صالح — يُترجَم إلى 401 في الراوتر."""


async def run_webhook(org_id: str, user_id: str | None, connection: dict,
                      headers: dict, body: bytes) -> dict:
    adp = build_adapter(connection, org_id)
    verify = getattr(adp, "verify_webhook", None)
    if verify is None or not verify(headers, body):
        raise WebhookRejected("invalid webhook signature")
    connection_id = str(connection["id"])
    event_id = getattr(adp, "event_id_of", lambda b: "")(body)
    # حماية إعادة التشغيل/التكرار على مستوى النقل: نفس event_id لا يُعالَج مرّتين.
    if event_id:
        seen = await db.fetchval(
            "select 1 from pos_webhook_deliveries where connection_id=$1 and event_id=$2", connection_id, event_id)
        if seen:
            return {"status": "duplicate_skipped", "event_id": event_id}
    ev = adp.normalize_webhook(body) if hasattr(adp, "normalize_webhook") else None
    pctx = _proc_ctx(connection, org_id)
    counts = sync_logic.SyncCounts()
    job_id = await db.fetchval(
        """insert into pos_sync_jobs(org_id,connection_id,trigger,status,cursor_before)
           values($1,$2,'webhook','running','{}'::jsonb) returning id""", org_id, connection_id)
    async with db.transaction() as c:
        if ev is not None:
            await _process_event(c, pctx, ev, counts, job_id)
        if event_id:
            await c.execute(
                """insert into pos_webhook_deliveries(org_id,connection_id,event_id,received_at)
                   values($1,$2,$3,now()) on conflict (connection_id,event_id) do nothing""",
                org_id, connection_id, event_id)
    status = counts.status()
    now = dt.datetime.now(dt.timezone.utc)
    await db.execute(
        "update pos_sync_jobs set status=$2, counts=$3, finished_at=now() where id=$1",
        job_id, status, counts.as_dict())
    await db.execute(
        """update pos_connections set last_sync_at=$2,
             last_success_at = case when $3 <> 'failed' then $2 else last_success_at end,
             sync_count = sync_count + 1, updated_at=now()
           where id=$1 and org_id=$4""", connection_id, now, status, org_id)
    db.cache_clear()
    return {"status": "accepted" if status != "failed" else "error", "event_id": event_id, **counts.as_dict()}


# --------------------------------------------------------------------------
# فحص اتصال حقيقي (قراءة فقط): الوصول، جلب عيّنة، صحّة التحويل، دعم webhook.
# --------------------------------------------------------------------------
async def test_connection(connection: dict, org_id: str) -> dict:
    checks: list[dict] = []
    try:
        adp = build_adapter(connection, org_id)
    except ValueError as exc:
        return {"ok": False, "checks": [{"name": "adapter", "ok": False, "detail": str(exc)}]}
    caps = getattr(adp, "capabilities", None)
    sample = []
    try:
        from .adapter import AdapterContext
        import anyio
        ctx = AdapterContext(org_id=org_id, config=connection.get("config") or {}, cursor={})
        # الجلب متزامن (urllib) — ننفّذه في خيط حتى لا نحجب حلقة الأحداث.
        sample, _ = await anyio.to_thread.run_sync(lambda: adp.fetch_changes(ctx))
        checks.append({"name": "reachable", "ok": True,
                       "detail": f"fetched {len(sample)} event(s) from source"})
    except Exception as exc:  # شبكة/مصادقة/شكل بيانات
        checks.append({"name": "reachable", "ok": False, "detail": str(exc)[:200]})
    if any(ch["name"] == "reachable" and ch["ok"] for ch in checks):
        bad = 0
        for ev in sample[:50]:
            try:
                ev.validate()
            except Exception:
                bad += 1
        checks.append({"name": "transform", "ok": bad == 0,
                       "detail": f"{len(sample[:50]) - bad}/{len(sample[:50])} sample events valid"})
    checks.append({"name": "webhook", "ok": bool(caps and caps.webhook),
                   "detail": "signed webhook supported" if (caps and caps.webhook) else "pull-only"})
    core_ok = all(ch["ok"] for ch in checks if ch["name"] in ("reachable", "transform"))
    return {"ok": core_ok, "checks": checks, "capabilities": caps.as_dict() if caps else {}}


async def _record_error(c, org_id, connection_id, job_id, ev: "model.Event", message: str) -> None:
    try:
        payload = {"type": ev.type, "external_id": ev.external_id,
                   "payload": ev.payload.canonical() if hasattr(ev.payload, "canonical") else None}
    except Exception:
        payload = {"type": getattr(ev, "type", None), "external_id": getattr(ev, "external_id", None)}
    await c.execute(
        """insert into pos_sync_errors(org_id,connection_id,job_id,event_type,external_id,payload,error)
           values($1,$2,$3,$4,$5,$6,$7)""",
        org_id, connection_id, job_id, getattr(ev, "type", None), getattr(ev, "external_id", None), payload, message)


async def _adopt(c, org_id: str, connection_id: str, existing) -> None:
    """تبنّي سجلّ مصدر قائم للاتصال الحالي: يعيد توجيه السجلّ والسطر الداخلي
    إلى connection_id الجديد دون أي استيراد مكرّر (يُستخدم عند إعادة الربط أو
    عند وجود اتصال ثانٍ لنفس الحساب)."""
    await c.execute("update pos_source_records set connection_id=$1 where id=$2", connection_id, existing["id"])
    iid, ent = existing["internal_id"], existing["entity"]
    if iid and ent == "sales":
        await c.execute("update sales set pos_connection_id=$1 where id=$2 and org_id=$3", connection_id, iid, org_id)
    elif iid and ent == "products":
        await c.execute("update products set pos_connection_id=$1 where id=$2 and org_id=$3", connection_id, iid, org_id)


async def _upsert_source_record(c, org_id, connection_id, provider_code, account_ref,
                                ev: "model.Event", internal_id: str, chash: str) -> None:
    occurred = None
    try:
        occurred = model._to_utc(ev.occurred_at)
    except model.InvalidEvent:
        pass
    await c.execute(
        """insert into pos_source_records(org_id,connection_id,provider_code,account_ref,event_type,external_id,
                                          entity,internal_id,content_hash,source_version,occurred_at,updated_at)
           values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,now())
           on conflict (org_id,provider_code,account_ref,entity,external_id)
           do update set connection_id=excluded.connection_id, event_type=excluded.event_type,
                         internal_id=excluded.internal_id, content_hash=excluded.content_hash,
                         source_version=excluded.source_version, occurred_at=excluded.occurred_at, updated_at=now()""",
        org_id, connection_id, provider_code, account_ref, ev.type, ev.external_id, ev.entity(),
        (internal_id or None), chash, ev.version_key(), occurred)
