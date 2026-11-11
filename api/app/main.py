from contextlib import asynccontextmanager
from collections import defaultdict, deque
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db
from .config import settings
from .routers import admin, assistant, data, insights, me, public, reports, workspace


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
    if not db.SERVERLESS:
        asyncio.create_task(warm())
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
_public_requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


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

for r in (public, me, data, workspace, insights, assistant, reports, admin):
    app.include_router(r.router)


@app.get("/health")
async def health():
    ok = await db.fetchval("select 1")
    return {"ok": ok == 1, "service": "idrak-api"}

