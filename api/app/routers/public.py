import html

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import db
from ..cleaning import engine
from ..cleaning.fields import auto_map
from ..cleaning.io import read_table
from ..services import email

router = APIRouter(prefix="/public", tags=["public"])


class Waitlist(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    name: str | None = None
    business_name: str | None = None
    business_type: str | None = None
    city: str | None = None
    locale: str | None = "ar"


@router.post("/waitlist")
async def waitlist(w: Waitlist):
    if "@" not in w.email:
        raise HTTPException(422, "Invalid email")
    await db.execute("""insert into waitlist(email,name,business_name,business_type,city,locale) values($1,$2,$3,$4,$5,$6)
                        on conflict (email) do update set name=coalesce(excluded.name, waitlist.name), business_name=coalesce(excluded.business_name, waitlist.business_name)""",
                     w.email.strip().lower(), w.name, w.business_name, w.business_type, w.city, w.locale)
    pos = await db.fetchval("select count(*) from waitlist")
    ar = w.locale == "ar"
    body = (f"<p>{'أهلين' if ar else 'Hi'} {html.escape(w.name or '')}،</p><p>"
            + ("انضممت لقائمة الانتظار. رح نبعثلك أول ما نفتح لمحلّك." if ar else "You're on the Idrak waitlist. We'll write as soon as your spot opens.") + "</p>")
    await email.send(w.email, "أهلاً بك في إدراك" if ar else "You're on the Idrak waitlist", email.layout("قائمة الانتظار" if ar else "Waitlist", body, w.locale or "ar"))
    return {"ok": True, "position": pos}


class Contact(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=5, max_length=200)
    phone: str | None = None
    message: str = Field(min_length=2, max_length=5000)
    locale: str | None = "ar"


@router.post("/contact")
async def contact(c: Contact):
    await db.execute("insert into contact_messages(name,email,phone,message,locale) values($1,$2,$3,$4,$5)", c.name, c.email, c.phone, c.message, c.locale)
    body = f"<p><b>{html.escape(c.name)}</b> &lt;{html.escape(c.email)}&gt; {html.escape(c.phone or '')}</p><p>{html.escape(c.message)}</p>"
    delivery = await email.send(
        "team@idrak.example.com",
        f"New contact message from {c.name}",
        email.layout("Contact form", body, "en"),
        reply_to=c.email,
    )
    if not delivery.get("ok"):
        raise HTTPException(503, "Message saved, but email delivery is temporarily unavailable")
    return {"ok": True}


@router.post("/health-check")
async def health_check(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 5MB)")
    try:
        headers, rows, _ = read_table(file.filename or "file.csv", data)
    except Exception as e:
        raise HTTPException(422, f"Could not read this file: {e}") from e
    if not headers or not rows:
        raise HTTPException(422, "The file looks empty")
    rows = rows[:5000]
    mapping = {h: m["field"] for h, m in auto_map(headers).items()}
    res = engine.run(headers, rows, mapping)
    await db.execute("insert into health_checks(file_name,row_count,score) values($1,$2,$3)", file.filename, len(rows), res["score_before"]["score"])
    return {
        "file_name": file.filename, "rows": res["rows_before"], "columns": len(headers), "entity": res["entity"],
        "score": res["score_before"]["score"], "projected_score": res["score_after"]["score"],
        "dimensions": res["score_before"]["dimensions"], "dimensions_after": res["score_after"]["dimensions"],
        "issues": [{k: i[k] for k in ("key", "kind", "title_en", "title_ar", "count", "category", "examples")} for i in res["issues"][:12]],
        "fixes_total": len(res["changes"]),
    }
