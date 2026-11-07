import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db
from ..auth import Ctx, org_ctx
from ..services import assistant as A

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ChatIn(BaseModel):
    message: str
    session_id: str | None = None
    locale: str = "ar"
    page: dict | None = None


@router.post("/chat")
async def chat(body: ChatIn, ctx: Ctx = Depends(org_ctx)):
    q: asyncio.Queue = asyncio.Queue()

    async def emit(e: dict):
        await q.put(e)

    async def worker():
        try:
            await A.chat(ctx.org_id, ctx.user, ctx.role, body.message[:4000], body.session_id, body.locale, body.page, emit)
        except Exception as e:
            await q.put({"type": "error", "text": str(e)[:300]})
            await q.put({"type": "done"})

    task = asyncio.create_task(worker())

    async def gen():
        try:
            while True:
                e = await q.get()
                yield f"data: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"
                if e.get("type") == "done":
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/sessions")
async def sessions(ctx: Ctx = Depends(org_ctx)):
    return await db.fetch("select id, title, created_at, updated_at from chat_sessions where org_id=$1 and user_id=$2 order by updated_at desc limit 30", ctx.org_id, ctx.user.id)


@router.get("/sessions/{sid}")
async def session(sid: str, ctx: Ctx = Depends(org_ctx)):
    return await db.fetch("""select m.role, m.content, m.events, m.created_at from chat_messages m join chat_sessions s on s.id=m.session_id
                             where s.id=$1 and s.user_id=$2 and m.role in ('user','assistant') order by m.created_at""", sid, ctx.user.id)


@router.delete("/sessions/{sid}")
async def delete_session(sid: str, ctx: Ctx = Depends(org_ctx)):
    await db.execute("delete from chat_sessions where id=$1 and user_id=$2", sid, ctx.user.id)
    return {"ok": True}


@router.get("/screens")
async def screens():
    return {p: {"description": d, "elements": e} for p, (d, e) in A.SCREENS.items()}
