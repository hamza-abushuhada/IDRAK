"""IDRAK Connect — راوتر ربط أنظمة نقاط البيع.

كل المسارات محميّة بإطار الصلاحيات نفسه (require): القراءة بـ view_dashboard،
والإدارة (ربط/مزامنة/قطع) بـ manage_integrations (مدير فأعلى). كل استعلام
مقيّد بـ ctx.org_id فلا يرى اتصال مؤسسةٍ أخرى. لا يُرجَع أيّ سرّ أو مرجع
اعتماد للواجهة.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import hashlib
import os

from .. import db
from ..auth import Ctx, require
from ..services.pos import pipeline, registry
from ..services.pos import pairing
from ..services.pos import autosync
from ..services.pos import loyverse_oauth
from ..services.pos import store_key

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.post('/lab/pairing-intents')
async def lab_pairing_intent(ctx: Ctx = Depends(require("manage_integrations"))):
    return JSONResponse(pairing.new_intent(ctx.org_id, ctx.user.id), headers={'Cache-Control': 'no-store'})


class AuthorizeIn(BaseModel):
    locale: str = "ar"


@router.post('/lab/authorize')
async def lab_authorize(body: AuthorizeIn, ctx: Ctx = Depends(require("manage_integrations"))):
    """Start linking a Lab shop by redirect (the owner signs in to the Lab and approves)."""
    org = await db.fetchrow("select name, name_ar from organizations where id=$1", ctx.org_id)
    name = (org["name_ar"] if body.locale == "ar" and org["name_ar"] else org["name"]) if org else ""
    return JSONResponse(pairing.new_authorization(ctx.org_id, ctx.user.id, body.locale, name or ""),
                        headers={'Cache-Control': 'no-store'})


class LoyverseAuthorizeIn(BaseModel):
    locale: str = "ar"


class LoyverseConnectIn(BaseModel):
    code: str
    intent: str
    state: str


@router.post('/loyverse/authorize')
async def loyverse_authorize(body: LoyverseAuthorizeIn, ctx: Ctx = Depends(require("manage_integrations"))):
    """Start Loyverse OAuth: the owner signs in and approves at Loyverse."""
    return JSONResponse(loyverse_oauth.new_authorization(ctx.org_id, ctx.user.id, body.locale), headers={'Cache-Control': 'no-store'})


@router.post('/loyverse/connect')
async def loyverse_connect(body: LoyverseConnectIn, ctx: Ctx = Depends(require("manage_integrations"))):
    """Finish OAuth: server-to-server code exchange; tokens are stored encrypted and never returned."""
    return JSONResponse(await loyverse_oauth.connect(body.code, body.intent, body.state, ctx), headers={'Cache-Control': 'no-store'})


@router.post('/loyverse/webhook')
async def loyverse_webhook(request: Request):
    """Loyverse receipts.update notifications. Verified by X-Loyverse-Signature (HMAC-SHA1, app
    client secret) before anything else; then IDRAK re-fetches receipts from the API."""
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 5_000_000:
            raise HTTPException(413, 'Too large')
    try:
        result = await loyverse_oauth.handle_webhook(bytes(raw), request.headers.get('x-loyverse-signature'))
    except PermissionError:
        raise HTTPException(401, 'Invalid notification') from None
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})


@router.post('/lab/notify', status_code=202)
async def lab_notify(request: Request):
    """Signed "something changed" signal from a paired Lab shop (server-to-server).
    No user session: authenticity is the per-shop HMAC signature. Carries no sales
    data; IDRAK pulls the changes itself. Responses never reveal why a call failed."""
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > autosync.MAX_BODY:
            raise HTTPException(413, 'Too large')
    try:
        result = await autosync.handle_lab_notify(bytes(raw), request.headers.get('x-idrak-signature', ''))
    except autosync.Rejected:
        raise HTTPException(401, 'Invalid notification') from None
    return JSONResponse(result, status_code=202, headers={'Cache-Control': 'no-store'})


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
        if not isinstance(value, dict) or set(value) not in ({'code', 'intent'}, {'code', 'intent', 'state'}):
            raise ValueError()
        if not isinstance(value['code'], str) or not 20 <= len(value['code']) <= 128:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, 'Expected a pairing code and intent only') from None
    return JSONResponse(await pairing.redeem(value['code'], value['intent'], ctx, value.get('state')),
                        headers={'Cache-Control': 'no-store'})

# الحقول الآمنة للعرض من اتصال — لا credential_ref، لا أسرار. مؤهَّلة بالاسم
# المستعار c حتى تعمل مع/بدون انضمام لجدول providers (الذي يشاركها status/config).
_CONN_COLS = ("c.id, c.provider_code, c.account_ref, c.display_name, c.status, c.config, c.cursor, c.last_sync_at, "
             "c.last_success_at, c.last_error, c.sync_count, c.created_at, c.updated_at")


_PUBLIC_CONFIG = ("channel", "auto_sync", "paired_lab", "store_api_key")


def _public(conn, ctx: Ctx | None = None) -> dict:
    """What the browser may see of a connection: no endpoint URLs, cursors or
    credentials; the source account reference only for integration managers."""
    if conn is None:
        return None
    out = dict(conn)
    out.pop("cursor", None)
    cfg = out.get("config") or {}
    out["config"] = {k: cfg[k] for k in _PUBLIC_CONFIG if k in cfg}
    # Opaque key that groups the channels (POS + online store) of one source
    # account for display, without revealing the source's internal id.
    family = "lab" if out.get("provider_code") in ("lab_pos", "lab_web") else out.get("provider_code", "")
    out["group_key"] = hashlib.sha256(f"{family}:{conn.get('account_ref') or out.get('id')}".encode()).hexdigest()[:16]
    if ctx is not None and not ctx.can("manage_integrations"):
        out.pop("account_ref", None)
    # Honest per-connection flag: true only when sales really sync without "Sync now".
    out["auto_sync_effective"] = bool((auto_sync_active() and cfg.get("auto_sync")) or autosync.effective(dict(conn)))
    return out


def auto_sync_active() -> bool:
    """True only when the background scheduler really runs in this deployment.
    It never runs on serverless hosts, and POS_AUTOSYNC=0 disables it."""
    return not db.SERVERLESS and os.getenv("POS_AUTOSYNC", "1") != "0"


@router.get("/status")
async def integration_status(ctx: Ctx = Depends(require("view_dashboard"))):
    # lab_linking: the UI offers the Lab only where linking is really configured
    # (e.g. Staging). Demo POS never depends on it.
    return {"auto_sync_active": auto_sync_active(), "lab_linking": pairing.linking_available(),
            # Hidden from users until a real Loyverse integration is proven (server flag + credentials).
            "loyverse_available": loyverse_oauth.available(),
            # Online store by API key: Staging first (IDRAK_STORE_API_KEYS=on), then production.
            "store_key_available": store_key.available()}


class RenameIn(BaseModel):
    display_name: str


@router.patch("/connections/{conn_id}")
async def rename_connection(conn_id: str, body: RenameIn, ctx: Ctx = Depends(require("manage_integrations"))):
    name = " ".join((body.display_name or "").split())
    if not 1 <= len(name) <= 60 or any(ord(ch) < 32 for ch in name):
        raise HTTPException(400, "Name must be 1-60 characters")
    done = await db.fetchval("update pos_connections set display_name=$3, updated_at=now() where id=$1 and org_id=$2 returning id",
                             conn_id, ctx.org_id, name)
    if not done:
        raise HTTPException(404, "Connection not found")
    await db.audit(ctx.org_id, ctx.user.id, "pos.renamed", "pos_connection", conn_id, {"display_name": name})
    return _public(await _detail(conn_id, ctx.org_id), ctx)


@router.get("/providers")
async def providers(ctx: Ctx = Depends(require("view_dashboard"))):
    """كتالوج الموصّلات: منفَّذ (demo) مقابل مدعوم معماريّاً (coming_soon)."""
    return await db.fetch(
        """select code, name, name_ar, category, status, is_implemented, capabilities,
                  description, description_ar, sort
           from pos_providers order by sort, code""")


@router.get("/connections")
async def list_connections(ctx: Ctx = Depends(require("view_dashboard"))):
    rows = await db.fetch(
        f"""select {_CONN_COLS},
                  p.name as provider_name, p.name_ar as provider_name_ar, p.category as provider_category,
                  (select count(*) from pos_sync_errors e where e.connection_id=c.id and e.status='open') open_errors
           from pos_connections c join pos_providers p on p.code=c.provider_code
           where c.org_id=$1 and c.removed_at is null order by c.created_at desc""", ctx.org_id)
    return [_public(r, ctx) for r in rows]


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
    if body.provider_code in ("lab_pos", "lab_web"):
        # Unpaired Lab connections may only target an allowed Lab URL (loopback in
        # local dev). Elsewhere a Lab shop is linked through pairing instead.
        from ..services.pos.pairing import legacy_lab_base_url
        # On hosted servers a Lab shop is only ever linked with its owner's approval
        # (redirect or pairing code), never by creating or reactivating a connection here.
        if db.SERVERLESS or os.environ.get("VERCEL"):
            raise HTTPException(400, "Connect a Lab shop with its owner's approval")
        try:
            legacy_lab_base_url(_config_for(body.provider_code).get("base_url"))
        except ValueError:
            raise HTTPException(400, "Connect a Lab shop with a pairing code") from None

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
        return {"connection": _public(await _detail(str(cid), ctx.org_id), ctx), "sync": result, "reconnected": True}

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
    return {"connection": _public(await _detail(str(cid), ctx.org_id), ctx), "sync": result, "reconnected": False}


@router.get("/connections/{conn_id}")
async def get_connection(conn_id: str, ctx: Ctx = Depends(require("view_dashboard"))):
    detail = await _detail(conn_id, ctx.org_id)
    if detail is None:
        raise HTTPException(404, "Connection not found")
    return _public(detail, ctx)


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
    return {"connection": _public(await _detail(conn_id, ctx.org_id), ctx), "sync": result}


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
    conn = await db.fetchrow("select id, provider_code, account_ref, config from pos_connections where id=$1 and org_id=$2", conn_id, ctx.org_id)
    if not conn:
        raise HTTPException(404, "Connection not found")
    await _stop_at_source(conn, ctx.org_id)
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


async def _stop_at_source(conn, org_id: str) -> None:
    """Stop the source side too (sales stay): Loyverse webhooks + tokens, store API key + notifications."""
    if conn["provider_code"] == "loyverse":
        await loyverse_oauth.disconnect(dict(conn), org_id)
    elif (conn["config"] or {}).get("store_api_key"):
        await store_key.disconnect(dict(conn), org_id)


@router.post("/connections/{conn_id}/remove")
async def remove_connection(conn_id: str, ctx: Ctx = Depends(require("manage_integrations"))):
    """«إزالة النظام»: قطع الاتصال + إخفاؤه من الأنظمة النشطة. لا يحذف أي فاتورة أو
    مرتجع أو سجلّ مزامنة أو تدقيق؛ وإعادة الربط لاحقًا تستأنف بنفس هوية المصدر فلا تكرار."""
    conn = await db.fetchrow("select id, provider_code, account_ref, config, status from pos_connections where id=$1 and org_id=$2",
                             conn_id, ctx.org_id)
    if not conn:
        raise HTTPException(404, "Connection not found")
    await _stop_at_source(conn, ctx.org_id)
    await db.execute("update pos_connections set status='disconnected', removed_at=now(), updated_at=now() where id=$1 and org_id=$2",
                     conn_id, ctx.org_id)
    kept = await db.fetchval("select count(*) from sales where pos_connection_id=$1 and org_id=$2", conn_id, ctx.org_id)
    await db.audit(ctx.org_id, ctx.user.id, "pos.removed", "pos_connection", conn_id,
                   {"provider": conn["provider_code"], "sales_kept": kept})
    db.cache_clear()
    return {"ok": True, "removed": True, "sales_kept": kept}


class StoreKeyIn(BaseModel):
    store_url: str
    api_key: str


@router.post("/store-key/test")
async def store_key_test(body: StoreKeyIn, ctx: Ctx = Depends(require("manage_integrations"))):
    """Check the store address + API key with the store itself. Nothing is saved."""
    if not store_key.available():
        raise HTTPException(503, "Online store linking is not available")
    return JSONResponse(await store_key.test(body.store_url, body.api_key, ctx), headers={"Cache-Control": "no-store"})


@router.post("/store-key/connect")
async def store_key_connect(body: StoreKeyIn, ctx: Ctx = Depends(require("manage_integrations"))):
    """Link the store to THIS business; the key is stored encrypted and never returned."""
    if not store_key.available():
        raise HTTPException(503, "Online store linking is not available")
    linked = await store_key.connect(body.store_url, body.api_key, ctx)
    conn = await db.fetchrow(f"select {_CONN_COLS} from pos_connections c where c.id=$1 and c.org_id=$2", linked["connection_id"], ctx.org_id)
    # Reconnect resumes from the saved cursor; a new link imports the history. Identity prevents duplicates either way.
    result = await pipeline.run_sync(ctx.org_id, ctx.user.id, dict(conn), trigger="manual" if linked["reconnected"] else "initial",
                                     initial=not linked["reconnected"])
    return JSONResponse({"connection": _public(await _detail(linked["connection_id"], ctx.org_id), ctx), "sync": result,
                         "reconnected": linked["reconnected"], "notifications": linked["notifications"]},
                        headers={"Cache-Control": "no-store"})


@router.post("/store/notify", status_code=202)
async def store_notify(request: Request):
    """Signed "store changed" signal for a store linked by API key (server-to-server).
    Per-key HMAC + time window + single-use nonce; carries no order data."""
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > store_key.MAX_BODY:
            raise HTTPException(413, "Too large")
    try:
        result = await store_key.handle_notify(bytes(raw), request.headers.get("x-idrak-signature", ""))
    except store_key.Rejected:
        raise HTTPException(401, "Invalid notification") from None
    return JSONResponse(result, status_code=202, headers={"Cache-Control": "no-store"})


@router.post("/catch-up")
async def catch_up(ctx: Ctx = Depends(require("view_dashboard"))):
    """Pull stores linked by API key that haven't synced recently (missed notifications)."""
    if not store_key.available():
        return {"checked": 0, "imported": 0}
    return await store_key.catch_up(ctx.org_id)


@router.post("/connections/{conn_id}/test")
async def test_connection(conn_id: str, ctx: Ctx = Depends(require("manage_integrations"))):
    """فحص اتصال حقيقي قبل الاعتماد: الوصول، جلب عيّنة، صحّة التحويل، ودعم
    webhook. لا يكتب أي بيانات (قراءة فقط)."""
    conn = await db.fetchrow(
        f"select {_CONN_COLS} from pos_connections c where c.id=$1 and c.org_id=$2", conn_id, ctx.org_id)
    if not conn:
        raise HTTPException(404, "Connection not found")
    if conn["status"] == "disconnected":
        raise HTTPException(409, "Connection is disconnected")
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
