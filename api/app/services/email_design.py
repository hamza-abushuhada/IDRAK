import html

PAPER, CARD, LINE, INK, INK2, INK3, TERRA, SAND, OLIVE = "#F4EDE2", "#FFFCF7", "#E2D6C3", "#2B211B", "#5A4A3F", "#8A786A", "#C2593A", "#EFE6D8", "#6B7A3A"
AR_FONT = "'IBM Plex Sans Arabic','Segoe UI',Tahoma,Arial,sans-serif"
EN_FONT = "'IBM Plex Sans','Segoe UI',Helvetica,Arial,sans-serif"
SERIF = "Georgia,'Times New Roman',serif"


def _logo() -> str:
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto"><tr>'
        f'<td style="vertical-align:middle;padding:0 8px 0 0">'
        f'<div style="width:22px;height:22px;border:3px solid {INK};border-radius:50%;position:relative;line-height:0;text-align:center">'
        f'<div style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{TERRA};margin-top:7px"></div></div></td>'
        f'<td style="vertical-align:middle;font-family:{SERIF};font-size:24px;font-weight:700;color:{INK};letter-spacing:-.5px">idrak</td>'
        f'<td style="vertical-align:middle;padding:0 10px;color:{LINE};font-size:22px">|</td>'
        f'<td style="vertical-align:middle;font-family:{AR_FONT};font-size:22px;font-weight:700;color:{INK}" dir="rtl">إدراك</td>'
        f'</tr></table>'
    )


def button(label: str, url: str) -> str:
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:26px auto 6px"><tr>'
        f'<td style="background:{TERRA};border-radius:999px;text-align:center">'
        f'<a href="{url}" style="display:inline-block;padding:14px 30px;font-family:{AR_FONT};font-size:15px;font-weight:700;'
        f'color:#FAF6EF;text-decoration:none;border-radius:999px">{label}</a></td></tr></table>'
    )


def section(text_html: str, rtl: bool) -> str:
    return (f'<div dir="{"rtl" if rtl else "ltr"}" style="font-family:{AR_FONT if rtl else EN_FONT};font-size:15px;line-height:1.85;'
            f'color:{INK2};text-align:{"right" if rtl else "left"}">{text_html}</div>')


def note(text_html: str, rtl: bool) -> str:
    return (f'<div dir="{"rtl" if rtl else "ltr"}" style="margin-top:18px;background:{SAND};border-radius:12px;padding:12px 16px;'
            f'font-family:{AR_FONT if rtl else EN_FONT};font-size:13px;line-height:1.7;color:{INK2};text-align:{"right" if rtl else "left"}">{text_html}</div>')


def page(*, preheader: str, title_ar: str | None, title_en: str | None, body: str, footer_note: str = "") -> str:
    titles = ""
    if title_ar:
        titles += f'<h1 dir="rtl" style="margin:0 0 6px;font-family:{AR_FONT};font-size:24px;line-height:1.5;color:{INK};text-align:center;font-weight:700">{html.escape(title_ar)}</h1>'
    if title_en:
        titles += f'<p style="margin:0;font-family:{SERIF};font-size:19px;color:{INK3};text-align:center;font-style:italic">{html.escape(title_en)}</p>'
    return f"""<!doctype html>
<html lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light only">
<title>{html.escape(title_en or title_ar or "Idrak")}</title></head>
<body style="margin:0;padding:0;background:{PAPER}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{html.escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER}"><tr><td align="center" style="padding:36px 14px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:580px">
    <tr><td style="padding:0 0 20px">{_logo()}</td></tr>
    <tr><td style="background:{CARD};border:1px solid {LINE};border-radius:18px;overflow:hidden">
      <div style="height:5px;background:{TERRA};border-radius:18px 18px 0 0;line-height:5px;font-size:0">&nbsp;</div>
      <div style="padding:34px 34px 30px">
        {titles}
        <div style="height:1px;background:{LINE};margin:24px 0"></div>
        {body}
      </div>
    </td></tr>
    <tr><td style="padding:22px 10px 0;text-align:center;font-family:{AR_FONT};font-size:12px;line-height:1.8;color:{INK3}">
      {footer_note}
      <div dir="rtl">إدراك — بيساعد المحلات تشوف شو أرقامها عم تحكي · عمّان، الأردن</div>
      <div>Idrak — helping shops see what their numbers are saying · Amman, Jordan</div>
    </td></tr>
  </table>
</td></tr></table></body></html>"""


def bilingual(ar_html: str, en_html: str) -> str:
    return section(ar_html, True) + f'<div style="height:1px;background:{LINE};margin:22px 0;opacity:.7"></div>' + section(en_html, False)


def link_fallback(url: str) -> str:
    return (f'<p style="margin:18px 0 0;font-family:{EN_FONT};font-size:12px;line-height:1.6;color:{INK3};text-align:center;word-break:break-all">'
            f'إذا الزر ما اشتغل، انسخ هالرابط · If the button doesn’t work, copy this link:<br>'
            f'<a href="{url}" style="color:{TERRA}">{url}</a></p>')
