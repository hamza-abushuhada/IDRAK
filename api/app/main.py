from contextlib import asynccontextmanager
from collections import defaultdict, deque
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db
from .config import settings
from .routers import admin, assistant, data, insights, integrations, me, public, reports, workspace


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    import asyncio
    from .services import insights as I

    async def warm():
        try:
            for (oid,) in [tuple(r.values()) for r in await db.fetch("select id from organizations where slug in ('al-nashama','al-shifa')")]:
                await I.dashboard(oid, 30, None)
                await asyncio.gather(I.leaks(oid), I.reorder(oid, 14, None), I.rfm(oid), I.compliance(oid, 90), I.employees_perf(oid, 30))
                await asyncio.gather(I.forecast(oid, None, None, 90, None), I.basket(oid, 60), I.cashflow(oid, 8, None), I.ramadan_movers(oid))
        except Exception as e:
            print("warm-up failed:", e)
    async def auto_sync_loop():
        """مزامنة تزايدية تلقائية احتياطية لاتصالات POS المفعّلة (config.auto_sync).
        الفاصل = POS_AUTOSYNC_INTERVAL ثانية (افتراضي 15). لا يفقد الطلبات: عند
        تعذّر الوصول للمصدر يفشل الجلب فلا يتقدّم المؤشّر، فتُعاد المحاولة الدورة
        التالية (تعافٍ بعد الانقطاع). الأحداث الفاسدة تُسجَّل في pos_sync_errors."""
        from .services.pos import pipeline as P
        interval = max(5, int(os.getenv("POS_AUTOSYNC_INTERVAL", "15")))
        while True:
            await asyncio.sleep(interval)
            try:
                conns = await db.fetch(
                    """select c.id, c.org_id, c.provider_code, c.account_ref, c.config, c.cursor
                       from pos_connections c
                       where c.status='connected' and coalesce((c.config->>'auto_sync')::boolean, false)""")
            except Exception as e:
                print("auto-sync query failed:", e); continue
            for conn in conns:
                try:
                    await P.run_sync(conn["org_id"], None, dict(conn), trigger="scheduled", initial=False)
                except Exception as e:  # مصدر غير متاح/خطأ: نسجّل ونكمل، المؤشّر لم يتقدّم
                    print("auto-sync error for", conn["id"], ":", str(e)[:200])

    if not db.SERVERLESS:
        asyncio.create_task(warm())
        if os.getenv("POS_AUTOSYNC", "1") != "0":
            asyncio.create_task(auto_sync_loop())
    yield
    await db.close_pool()


app = FastAPI(title="Idrak API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_public_rate_limits = {
    "/public/contact": (10, 60),
    "/public/waitlist": (5, 300),
    "/public/health-check": (3, 600),
}
# ملاحظة: هذا العدّاد في ذاكرة النسخة الواحدة. على Serverless (Vercel) كل نسخة
# لها عدّادها، فالحدّ الفعلي = الحدّ × عدد النسخ الحيّة ويُصفَّر مع كل بداية
# باردة؛ يبقى "أفضل جهد" ضد الإساءة البسيطة. للحماية المتينة في الإنتاج استخدم
# جدار حماية Vercel أو متجراً مشتركاً (Upstash/جدول). حدّ تكلفة الذكاء الاصطناعي
# المدفوع مطبَّق على مستوى قاعدة البيانات (services/ai.over_daily_budget) فيصمد.
_public_requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)


# قائمة عناوين الوكلاء الموثوقين. فقط من هذه العناوين تُقرأ X-Forwarded-For.
# على Vercel اضبط TRUSTED_PROXY_IPS بعناوين حافة Vercel، أو اتركها فارغة
# لاستخدام عنوان الاتصال المباشر فقط (أشدّ لكن قد يرى كل الطلبات تأتي من
# بوابة واحدة). أمثلة: "76.76.21.0/24,127.0.0.1".
_TRUSTED_PROXIES = frozenset(
    p.strip() for p in os.getenv("TRUSTED_PROXY_IPS", "").split(",") if p.strip())


def _client_ip(request: Request) -> str:
    peer = (request.client.host if request.client else "unknown")
    if peer in _TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # نأخذ آخر قفزة قبل الوكيل الموثوق، لا أول قفزة التي تحدّدها
            # ترويسة العميل. كل ما قبلها قد يكون مزوّراً من المتصل.
            return forwarded.split(",")[-1].strip()[:64]
    return peer[:64]


@app.middleware("http")
async def rate_limit_public(request: Request, call_next):
    limit_config = _public_rate_limits.get(request.url.path)
    if limit_config and request.method.upper() == "POST":
        limit, window = limit_config
        now = time.monotonic()
        key = (request.url.path, _client_ip(request))
        timestamps = _public_requests[key]
        while timestamps and now - timestamps[0] >= window:
            timestamps.popleft()
        if len(timestamps) >= limit:
            retry_after = max(1, int(window - (now - timestamps[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(retry_after)},
            )
        timestamps.append(now)
        if len(_public_requests) > 10000:
            stale_before = now - 600
            for request_key in list(_public_requests):
                entries = _public_requests[request_key]
                while entries and now - entries[0] >= 600:
                    entries.popleft()
                if not entries or entries[0] < stale_before:
                    _public_requests.pop(request_key, None)
    return await call_next(request)


@app.middleware("http")
async def ensure_db(request, call_next):
    await db.init_pool()
    return await call_next(request)

for r in (public, me, data, workspace, insights, assistant, reports, admin, integrations):
    app.include_router(r.router)


@app.get("/health")
async def health():
    ok = await db.fetchval("select 1")
    return {"ok": ok == 1, "service": "idrak-api"}

