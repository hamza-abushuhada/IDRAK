import html
import os

import httpx

from ..config import settings

TEST_RECIPIENT = os.getenv("RESEND_TEST_RECIPIENT", "").strip()


def layout(title: str, body_html: str, locale: str = "ar", cta: tuple[str, str] | None = None, preheader: str | None = None) -> str:
    from .email_design import button, page, section
    rtl = locale == "ar"
    body = section(body_html, rtl) + (button(html.escape(cta[0]), html.escape(cta[1])) if cta else "")
    return page(preheader=preheader or title, title_ar=title if rtl else None, title_en=None if rtl else title, body=body)


async def send(to: str | list[str], subject: str, html_body: str, reply_to: str | None = None) -> dict:
    if not settings.resend_api_key:
        return {"ok": False, "error": "RESEND_API_KEY not configured"}
    to_list = [to] if isinstance(to, str) else to
    real = to_list
    if TEST_RECIPIENT:
        subject = f"{subject}  [→ {', '.join(to_list)}]"
        real = [TEST_RECIPIENT]
    payload = {"from": f"Idrak <{settings.resend_from}>", "to": real, "subject": subject, "html": html_body}
    if reply_to:
        payload["reply_to"] = reply_to
    try:
        async with httpx.AsyncClient(timeout=20) as cx:
            r = await cx.post("https://api.resend.com/emails", json=payload, headers={"Authorization": f"Bearer {settings.resend_api_key}"})
        if r.status_code >= 300:
            return {"ok": False, "error": r.json().get("message", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text,
                    "delivered_to": real}
        return {"ok": True, "id": r.json().get("id"), "delivered_to": real}
    except httpx.HTTPError as e:
        return {"ok": False, "error": str(e)}
