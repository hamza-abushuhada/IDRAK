"""IDRAK Connect — راوتر ربط أنظمة نقاط البيع.

كل المسارات محميّة بإطار الصلاحيات نفسه (require): القراءة بـ view_dashboard،
والإدارة (ربط/مزامنة/قطع) بـ manage_integrations (مدير فأعلى). كل استعلام
مقيّد بـ ctx.org_id فلا يرى اتصال مؤسسةٍ أخرى. لا يُرجَع أيّ سرّ أو مرجع
اعتماد للواجهة.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os

from .. import db
from ..auth import Ctx, require
from ..services.pos import pipeline, registry
from ..services.pos import pairing

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.post('/lab/pairing-intents')
async def lab_pairing_intent(ctx: Ctx = Depends(require("manage_integrations"))):
    return JSONResponse(pairing.new_intent(ctx.org_id, ctx.user.id), headers={'Cache-Control': 'no-store'})


@router.post('/lab/pair')
async def pair_lab(request: Request, ctx: Ctx = Depends(require("manage_integrations"))):
    import json
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise HTTPException(413, 'Pairing request too large')
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or set(value) != {'code', 'intent'}:
            raise ValueError()
        if not isinstance(value['code'], str) or not 20 <= len(value['code']) <= 128:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, 'Expected a pairing code and intent only') from None
    return JSONResponse(await pairing.redeem(value['code'], value['intent'], ctx), headers={'Cache-Control': 'no-store'})

# الحقول الآمنة للعرض من اتصال — لا credential_ref، لا أسرار. مؤهَّلة بالاسم
# المستعار c حتى تعمل مع/بدون انضمام لجدول providers (الذي يشاركها status/config).
_CONN_COLS = ("c.id, c.provider_code, c.account_ref, c.display_name, c.status, c.config, c.cursor, c.last_sync_at, "
             "c.last_success_at, c.last_error, c.sync_count, c.created_at, c.updated_at")


@router.get("/providers")
async def providers(ctx: Ctx = Depends(require("view_dashboard"))):
    """كتالوج الموصّلات: منفَّذ (demo) مقابل مدعوم معماريّاً (coming_soon)."""
    return await db.fetch(
        """select code, name, name_ar, category, status, is_implemented, capabilities,
                  description, description_ar, sort
           from pos_providers order by sort, code""")


@router.get("/connections")
async def list_connections(ctx: Ctx = Depends(require("view_dashboard"))):
    return await db.fetch(
        f"""select {_CONN_COLS},
                  p.name as provider_name, p.name_ar as provider_name_ar, p.category as provider_category,
                  (select count(*) from pos_sync_errors e where e.connection_id=c.id and e.status='open') open_errors
           from pos_connections c join pos_providers p on p.code=c.provider_code
           where c.org_id=$1 order by c.created_at desc""", ctx.org_id)


class ConnectIn(BaseModel):
    provider_code: str
    display_name: str | None = None
    account_ref: str | None = None  # حساب/تاجر المصدر (هوية ثابتة). للتجريبي 'demo'.


def _account_ref_for(provider_code: str, requested: str | None) -> str:
    """هوية الحساب الثابتة للمصدر. حساب ثابت لكل مصدر تجريبي حتى تتطابق الهوية
    عبر إعادة الربط؛ للمورّد الحقيقي تُشتقّ من إعداد الاتصال."""
    if provider_code == "demo":
        return "demo"
    if provider_code in ("lab_pos", "lab_web"):
        return "idrak-test-shop-001"  # account_id الثابت لمختبر إدراك
    return (requested or "default").strip() or "default"


def _config_for(provider_code: str) -> dict:
    """إعداد غير سرّي افتراضي للاتصال (قناة البيع، مصدر المخزون، المزامنة التلقائية).
    موصّلات المختبر ترسل أرصدة مخزون صريحة فنعطّل اشتقاق المخزون من البيع (لا ازدواج)."""
    if provider_code == "demo":
        # التجريبي يدويّ (Sync now) — مزامنته التلقائية تولّد مبيعات اصطناعية بلا توقّف.
        return {"channel": "in_store", "auto_sync": False}
    lab_url = "http://127.0.0.1:8765"
    if os.environ.get("IDRAK_ENVIRONMENT") == "staging":
        lab_url = os.environ.get("IDRAK_LAB_BASE_URL") or lab_url
    if provider_code == "lab_pos":
        return {"channel": "in_store", "sales_adjust_inventory": False, "auto_sync": True,
                "base_url": lab_url}
    if provider_code == "lab_web":
        return {"channel": "online", "sales_adjust_inventory": False, "auto_sync": True,
                "base_url": lab_url}
    return {}


@router.post("/connections")
async def create_connection(body: ConnectIn, ctx: Ctx = Depends(require("manage_integrations"))):
    provider = await db.fetchrow("select * from pos_providers where code=$1", body.provider_code)
    if not provider:
        raise HTTPException(404, "Unknown connector")
    # الموصّل غير المنفَّذ لا يُنشئ اتصالاً فعّالاً: نرفض بوضوح بدل زرّ وهمي.
    if not provider["is_implemented"] or not registry.is_implemented(body.provider_code):
        raise HTTPException(400, "This connector type is supported architecturally but not available to connect yet")

    account_ref = _account_ref_for(body.provider_code, body.account_ref)
    # إعادة ربط نفس المصدر (مؤسسة+مزوّد+حساب): نعيد تفعيل الاتصال القائم بدل
    # إنشاء اتصال جديد — فلا تُعاد المبيعات القديمة. الهوية الثابتة في خريطة
    # المصدر تضمن أن المزامنة التالية لا تُنتج أي تكرار. (إصلاح 49→96.)
    existing = await db.fetchrow(
        """select id, status from pos_connections
           where org_id=$1 and provider_code=$2 and account_ref=$3
           order by created_at desc limit 1""",
        ctx.org_id, body.provider_code, account_ref)
    if existing:
        cid = existing["id"]
        await db.execute(
            """update pos_connections set status='connected',
                 display_name=coalesce($3, display_name), updated_at=now()
               where id=$1 and org_id=$2""",
            cid, ctx.org_id, body.display_name)
        await db.audit(ctx.org_id, ctx.user.id, "pos.reconnected", "pos_connection", str(cid),
                       {"provider": body.provider_code, "account_ref": account_ref})
        conn = await db.fetchrow(f"select {_CONN_COLS} from pos_connections c where c.id=$1 and c.org_id=$2", str(cid), ctx.org_id)
        # استئناف تزايديّ من المؤشّر المحفوظ — لا استيراد أوّلي، فلا تكرار.
        result = await pipeline.run_sync(ctx.org_id, ctx.user.id, conn, trigger="manual", initial=False)
        return {"connection": await _detail(str(cid), ctx.org_id), "sync": result, "reconnected": True}

    cid = await db.fetchval(
        """insert into pos_connections(org_id, provider_code, account_ref, display_name, status, config, created_by)
           values($1,$2,$3,$4,'connected',$5,$6) returning id""",
        ctx.org_id, body.provider_code, account_ref, body.display_name or provider["name"],
        _config_for(body.provider_code), ctx.user.id)
    await db.audit(ctx.org_id, ctx.user.id, "pos.connected", "pos_connection", str(cid),
                   {"provider": body.provider_code, "account_ref": account_ref})
    conn = await db.fetchrow(f"select {_CONN_COLS} from pos_connections c where c.id=$1 and c.org_id=$2", str(cid), ctx.org_id)
    # الاستيراد الأولي يعمل فوراً للموصّل التجريبي (في العملية، سريع).
    result = await pipeline.run_sync(ctx.org_id, ctx.user.id, conn, trigger="initial", initial=True)
    return {"connection": await _detail(str(cid), ctx.org_id), "sync": result, "reconnected": False}


@router.get("/connections/{conn_id}")
async def get_connection(conn_id: str, ctx: Ctx = Depends(require("view_dashboard"))):
    detail = await _detail(conn_id, ctx.org_id)
    if detail is None:
        raise HTTPException(404, "Connection not found")
    return detail


@router.post("/connections/{conn_id}/sync")
async def sync_now(conn_id: str, ctx: Ctx = Depends(require("manage_integrations"))):
    conn = await db.fetchrow(f"select {_CONN_COLS} from pos_connections c where c.id=$1 and c.org_id=$2", conn_id, ctx.org_id)
    if not conn:
        raise HTTPException(404, "Connection not found")
    if conn["status"] == "disconnected":
        raise HTTPException(409, "Connection is disconnected")
    try:
        result = await pipeline.run_sync(ctx.org_id, ctx.user.id, conn, trigger="manual", initial=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"connection": await _detail(conn_id, ctx.org_id), "sync": result}


@router.get("/connections/{conn_id}/jobs")
async def connection_jobs(conn_id: str, ctx: Ctx = Depends(require("view_dashboard"))):
    conn = await db.fetchval("select 1 from pos_connections where id=$1 and org_id=$2", conn_id, ctx.org_id)
    if not conn:
        raise HTTPException(404, "Connection not found")
    return await db.fetch(
        """select id, trigger, status, counts, error, started_at, finished_at
           from pos_sync_jobs where connection_id=$1 and org_id=$2 order by started_at desc limit 50""",
        conn_id, ctx.org_id)


@router.get("/connections/{conn_id}/errors")
async def connection_errors(conn_id: str, ctx: Ctx = Depends(require("view_dashboard"))):
    conn = await db.fetchval("select 1 from pos_connections where id=$1 and org_id=$2", conn_id, ctx.org_id)
    if not conn:
        raise HTTPException(404, "Connection not found")
    return await db.fetch(
        """select id, event_type, external_id, error, status, created_at
           from pos_sync_errors where connection_id=$1 and org_id=$2 and status='open'
           order by created_at desc limit 100""", conn_id, ctx.org_id)


@router.delete("/connections/{conn_id}")
async def disconnect(conn_id: str, purge: bool = False, ctx: Ctx = Depends(require("manage_integrations"))):
    """قطع الاتصال. الافتراضي قطع ناعم (يوقف المزامنة ويُبقي البيانات).
    purge=true يحذف الاتصال وكل مبيعاته وأصنافه التي لم تُستخدم في مبيعات أخرى
    — حذف لا يُتراجَع عنه، تؤكّده الواجهة أولاً."""
    conn = await db.fetchrow("select id from pos_connections where id=$1 and org_id=$2", conn_id, ctx.org_id)
    if not conn:
        raise HTTPException(404, "Connection not found")
    if not purge:
        await db.execute("update pos_connections set status='disconnected', updated_at=now() where id=$1 and org_id=$2",
                         conn_id, ctx.org_id)
        await db.audit(ctx.org_id, ctx.user.id, "pos.disconnected", "pos_connection", conn_id, {"purge": False})
        return {"ok": True, "purged": False}
    async with db.transaction() as c:
        s = await c.execute("delete from sales where pos_connection_id=$1 and org_id=$2", conn_id, ctx.org_id)
        p = await c.execute(
            """delete from products pr where pr.pos_connection_id=$1 and pr.org_id=$2
                 and not exists (select 1 from sale_items si where si.product_id=pr.id)""", conn_id, ctx.org_id)
        # الاتصال: cascade يحذف jobs / source_records / errors. مبيعات أخرى
        # (لو بقيت) تُفقد مرجع المصدر فقط عبر on delete set null.
        await c.execute("delete from pos_connections where id=$1 and org_id=$2", conn_id, ctx.org_id)
    db.cache_clear()
    counts = {"sales": int(s.split()[-1]), "products": int(p.split()[-1])}
    await db.audit(ctx.org_id, ctx.user.id, "pos.purged", "pos_connection", conn_id, counts)
    return {"ok": True, "purged": True, "deleted": counts}


@router.post("/connections/{conn_id}/test")
async def test_connection(conn_id: str, ctx: Ctx = Depends(require("manage_integrations"))):
    """فحص اتصال حقيقي قبل الاعتماد: الوصول، جلب عيّنة، صحّة التحويل، ودعم
    webhook. لا يكتب أي بيانات (قراءة فقط)."""
    conn = await db.fetchrow(
        f"select {_CONN_COLS} from pos_connections c where c.id=$1 and c.org_id=$2", conn_id, ctx.org_id)
    if not conn:
        raise HTTPException(404, "Connection not found")
    return await pipeline.test_connection(dict(conn), ctx.org_id)


# استقبال webhook موقّع: التحقّق من التوقيع (HMAC) + حماية إعادة التشغيل +
# idempotency ثم التطبيق. لا نقطة ابتلاع مفتوحة: الطلب غير الموقّع يُرفَض 401،
# والموصّل بلا تحقّق توقيع (NotImplemented) يُرفَض 501.
@router.post("/webhooks/{provider_code}/{conn_id}")
async def webhook(provider_code: str, conn_id: str, request: Request):
    conn = await db.fetchrow(
        """select c.id, c.org_id, c.provider_code, c.account_ref, c.config, c.status
           from pos_connections c where c.id=$1 and c.provider_code=$2""", conn_id, provider_code)
    if not conn:
        raise HTTPException(404, "Unknown connection")
    if conn["status"] == "disconnected":
        raise HTTPException(409, "Connection is disconnected")
    body = await request.body()
    try:
        result = await pipeline.run_webhook(conn["org_id"], None, dict(conn), dict(request.headers), body)
    except pipeline.WebhookRejected as exc:
        raise HTTPException(401, "Invalid webhook signature") from exc
    except NotImplementedError as exc:
        raise HTTPException(501, "Webhook verification not implemented for this connector") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


async def _detail(conn_id: str, org_id: str) -> dict | None:
    conn = await db.fetchrow(
        f"""select {_CONN_COLS}, p.name as provider_name, p.name_ar as provider_name_ar,
                   p.category as provider_category, p.capabilities as provider_capabilities
            from pos_connections c join pos_providers p on p.code=c.provider_code
            where c.id=$1 and c.org_id=$2""", conn_id, org_id)
    if not conn:
        return None
    conn["recent_jobs"] = await db.fetch(
        """select id, trigger, status, counts, error, started_at, finished_at
           from pos_sync_jobs where connection_id=$1 order by started_at desc limit 10""", conn_id)
    conn["open_errors"] = await db.fetchval(
        "select count(*) from pos_sync_errors where connection_id=$1 and status='open'", conn_id)
    conn["sales_count"] = await db.fetchval(
        "select count(*) from sales where pos_connection_id=$1 and org_id=$2", conn_id, org_id)
    return conn
