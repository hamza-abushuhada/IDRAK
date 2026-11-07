from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_origin_regex=r"https://([a-z0-9-]+\.)*vercel\.app",
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


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

