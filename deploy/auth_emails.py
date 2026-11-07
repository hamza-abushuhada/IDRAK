import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from app.services.email_design import bilingual, button, link_fallback, note, page

URL = "{{ .ConfirmationURL }}"

TEMPLATES = {
    "confirmation": (
        "أكّد حسابك في إدراك · Confirm your Idrak account",
        "خطوة وحدة وبتبدأ تشوف وين عم تخسر · One step to start seeing your numbers clearly",
        "أهلاً فيك بإدراك 👋".replace(" 👋", ""), "Welcome to Idrak",
        "<p style='margin:0'>شكراً لتسجيلك! اضغط الزر تحت لتأكيد إيميلك، وبعدها بتقدر ترفع أول ملف وتشوف <b>مؤشر صحة بياناتك</b> خلال دقيقة.</p>",
        "<p style='margin:0'>Thanks for signing up! Confirm your email below, then upload your first file and see your <b>Data Health Score</b> in a minute.</p>",
        "تأكيد الحساب · Confirm my account",
        "الرابط صالح لمدة 24 ساعة. إذا ما سجّلت إنت، تجاهل هالرسالة.", "This link is valid for 24 hours. If you didn’t sign up, you can ignore this email.",
    ),
    "magic_link": (
        "رابط الدخول إلى إدراك · Your Idrak sign-in link",
        "اضغط للدخول بدون كلمة مرور · Tap to sign in, no password needed",
        "رابط دخول سريع", "Your sign-in link",
        "<p style='margin:0'>طلبت تدخل لإدراك بدون كلمة مرور. اضغط الزر وبتكون جوّا.</p>",
        "<p style='margin:0'>You asked to sign in to Idrak without a password. Tap the button and you’re in.</p>",
        "الدخول إلى إدراك · Sign in to Idrak",
        "الرابط بيشتغل مرة وحدة وصالح لساعة. إذا ما طلبته إنت، تجاهل الرسالة.", "The link works once and expires in 1 hour. If you didn’t request it, ignore this email.",
    ),
    "recovery": (
        "إعادة تعيين كلمة المرور · Reset your Idrak password",
        "اختار كلمة مرور جديدة لحسابك · Choose a new password for your account",
        "إعادة تعيين كلمة المرور", "Reset your password",
        "<p style='margin:0'>وصلنا طلب لتغيير كلمة المرور لحسابك. اضغط الزر واختار كلمة مرور جديدة.</p>",
        "<p style='margin:0'>We received a request to reset your password. Tap the button to choose a new one.</p>",
        "اختيار كلمة مرور جديدة · Choose a new password",
        "إذا ما طلبت هالتغيير، تجاهل الرسالة — كلمة مرورك الحالية رح تضل زي ما هي.", "If you didn’t ask for this, ignore this email — your current password stays the same.",
    ),
    "invite": (
        "انعزمت على إدراك · You’re invited to Idrak",
        "فريقك بستناك على إدراك · Your team is waiting for you on Idrak",
        "انعزمت تنضم لإدراك", "You’re invited",
        "<p style='margin:0'>حدا من فريقك عزمك تنضم لمساحة شغلهم على إدراك — المكان اللي بيشوفوا فيه المبيعات والمخزون ووين عم يخسروا.</p>",
        "<p style='margin:0'>Someone on your team invited you to their Idrak workspace — where they see sales, stock and where money is leaking.</p>",
        "قبول الدعوة · Accept invitation",
        "إذا ما بتعرف مين بعتلك الدعوة، تجاهل الرسالة.", "If you weren’t expecting this, you can ignore this email.",
    ),
    "email_change": (
        "تأكيد الإيميل الجديد · Confirm your new email",
        "أكّد تغيير الإيميل لحسابك على إدراك · Confirm the email change on your Idrak account",
        "تأكيد الإيميل الجديد", "Confirm your new email",
        "<p style='margin:0'>طلبت تغيّر إيميل حسابك من <b dir='ltr'>{{ .Email }}</b> إلى <b dir='ltr'>{{ .NewEmail }}</b>. اضغط الزر للتأكيد.</p>",
        "<p style='margin:0'>You asked to change your account email from <b>{{ .Email }}</b> to <b>{{ .NewEmail }}</b>. Tap the button to confirm.</p>",
        "تأكيد التغيير · Confirm change",
        "إذا ما طلبت هالتغيير، تواصل معنا فوراً.", "If you didn’t request this, contact us right away.",
    ),
}


def build(key: str) -> tuple[str, str]:
    subject, pre, tar, ten, ar, en, label, nar, nen = TEMPLATES[key]
    body = bilingual(ar, en) + button(label, URL) + link_fallback(URL) + note(nar, True) + note(nen, False)
    return subject, page(preheader=pre, title_ar=tar, title_en=ten, body=body)


def build_reauth() -> tuple[str, str]:
    code = ('<div style="margin:24px auto 6px;text-align:center"><span style="display:inline-block;font-family:Consolas,Menlo,monospace;font-size:30px;'
            'letter-spacing:8px;color:#2B211B;background:#EFE6D8;border-radius:12px;padding:14px 22px">{{ .Token }}</span></div>')
    body = bilingual("<p style='margin:0'>استعمل هالرمز لتأكيد هويتك:</p>", "<p style='margin:0'>Use this code to confirm it’s you:</p>") + code \
        + note("الرمز صالح لدقائق قليلة. لا تشاركه مع حدا.", True) + note("The code expires in a few minutes. Never share it with anyone.", False)
    return "رمز التحقق · Your Idrak verification code", page(preheader="رمز التحقق الخاص فيك · Your verification code",
                                                          title_ar="رمز التحقق", title_en="Verification code", body=body)


def main():
    out = ROOT / "deploy" / "emails"
    out.mkdir(exist_ok=True)
    built = {k: build(k) for k in TEMPLATES}
    built["reauthentication"] = build_reauth()
    for k, (subj, html_doc) in built.items():
        (out / f"{k}.html").write_text(html_doc, encoding="utf-8")
    (out / "subjects.txt").write_text("\n".join(f"{k}: {s}" for k, (s, _) in built.items()), encoding="utf-8")
    print(f"wrote {len(built)} templates to {out}")
    if "--no-push" in sys.argv:
        return
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    body = {}
    for k, (subj, html_doc) in built.items():
        body[f"mailer_subjects_{k}"] = subj
        body[f"mailer_templates_{k}_content"] = html_doc
    r = httpx.patch(f"https://api.supabase.com/v1/projects/{env['SUPABASE_PROJECT_REF']}/config/auth",
                    headers={"Authorization": f"Bearer {env['SUPABASE_ACCESS_TOKEN']}"}, json=body, timeout=60)
    print("supabase templates:", r.status_code, "installed" if r.status_code < 300 else r.text[:300])


if __name__ == "__main__":
    main()
