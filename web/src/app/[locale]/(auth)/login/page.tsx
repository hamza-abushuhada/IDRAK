"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useRouter } from "@/lib/router";
import { Suspense, useState } from "react";
import { useLocale, useTx } from "@/i18n";
import { supabase } from "@/lib/supabase";
import { Button, Field, Input } from "@/components/ui";
import { toast } from "@/components/ui/toast";
import GoogleButton, { OrDivider } from "@/components/GoogleButton";

// الدخول التجريبي بنقرة واحدة. كلمة المرور تصل إلى المتصفّح بحكم التصميم،
// فهذه الحسابات يجب أن تفتح مستأجرين تجريبيين ببيانات اصطناعية فقط —
// ولا يجوز أن يحمل أيٌّ منها صلاحية is_super_admin.
// حساب المؤسس أُزيل من هذه القائمة: كان يمنح وصولاً إلى /admin/overview
// (كل المستأجرين + قائمة الانتظار + رسائل التواصل) بنقرة من أي زائر.
// اضبط NEXT_PUBLIC_ENABLE_DEMO_LOGIN=0 لإخفاء الكتلة كلياً في الإنتاج.
const DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_PASSWORD || "Idrak@Demo2026";
const DEMO_ENABLED = process.env.NEXT_PUBLIC_ENABLE_DEMO_LOGIN !== "0";
const DEMOS = [
  { email: "owner@nashama.example.com", en: "Mini-market owner", ar: "مالك ميني ماركت", who: "Khaled · Al-Nashama Market" },
  { email: "manager@nashama.example.com", en: "Store manager", ar: "مديرة المحل", who: "Rania · Al-Nashama Market" },
  { email: "cashier@nashama.example.com", en: "Cashier (limited)", ar: "كاشير (صلاحيات محدودة)", who: "Yazan · Al-Nashama Market" },
  { email: "owner@alshifa.example.com", en: "Pharmacy owner", ar: "مالكة صيدلية", who: "Dr. Lina · Al-Shifa Pharmacy" },
];

function LoginInner() {
  const locale = useLocale();
  const tx = useTx();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || `/${locale}/app`;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [magicSent, setMagicSent] = useState(false);

  async function login(e?: React.FormEvent, em = email, pw = password) {
    e?.preventDefault();
    setLoading(true);
    const { error } = await supabase().auth.signInWithPassword({ email: em, password: pw });
    setLoading(false);
    if (error) return toast(tx("Couldn't sign in", "ما زبط تسجيل الدخول"), error.message, "error");
    router.replace(next.startsWith("/") ? next : `/${locale}/app`);
  }

  async function magic() {
    if (!email) return toast(tx("Enter your email first", "اكتب إيميلك أول"), undefined, "info");
    setLoading(true);
    const { error } = await supabase().auth.signInWithOtp({ email, options: { emailRedirectTo: `${window.location.origin}/${locale}/app`, shouldCreateUser: false } });
    setLoading(false);
    if (error) return toast(tx("Couldn't send the link", "ما قدرنا نبعث الرابط"), error.message, "error");
    setMagicSent(true);
  }

  return (
    <div>
      <h1 className="font-serif text-[34px] leading-tight text-ink">{tx("Welcome back", "أهلاً من جديد")}</h1>
      <p className="mt-2 text-ink-2">{tx("Sign in to see what your numbers are telling you.", "سجّل دخولك وشوف شو أرقامك عم تحكيلك.")}</p>
      <div className="mt-8"><GoogleButton next={next} /></div>
      <OrDivider />
      <form onSubmit={login} className="space-y-4">
        <Field label={tx("Email", "الإيميل")}><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required dir="ltr" autoComplete="email" /></Field>
        <Field label={tx("Password", "كلمة المرور")}><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required dir="ltr" autoComplete="current-password" /></Field>
        <div className="flex items-center justify-between text-sm">
          <Link href={`/${locale}/forgot-password`} className="text-ink-2 hover:text-terra">{tx("Forgot password?", "نسيت كلمة المرور؟")}</Link>
          <button type="button" onClick={magic} className="text-ink-2 hover:text-terra">{tx("Email me a sign-in link", "ابعتلي رابط دخول")}</button>
        </div>
        {magicSent && <p className="rounded-lg bg-olive-soft px-3 py-2 text-sm text-olive">{tx("Check your inbox for the sign-in link.", "شيّك إيميلك، بعتنالك رابط الدخول.")}</p>}
        <Button type="submit" size="lg" className="w-full" loading={loading}>{tx("Sign in", "تسجيل الدخول")}</Button>
      </form>
      <p className="mt-6 text-center text-sm text-ink-2">{tx("New to Idrak?", "جديد على إدراك؟")} <Link href={`/${locale}/signup`} className="font-medium text-terra">{tx("Create an account", "أنشئ حساب")}</Link></p>

      {DEMO_ENABLED && (
      <div className="mt-10 rounded-2xl border border-dashed border-sand-2 p-4">
        <p className="text-[12px] font-medium uppercase tracking-[.12em] text-ink-3">{tx("Try the live demo", "جرّب العرض الحي")}</p>
        <div className="mt-3 grid gap-1.5">
          {DEMOS.map((d) => (
            <button key={d.email} disabled={loading} onClick={() => login(undefined, d.email, DEMO_PASSWORD)}
              className="flex items-center justify-between rounded-lg px-3 py-2 text-start hover:bg-sand">
              <span><span className="block text-[13.5px] text-ink">{tx(d.en, d.ar)}</span><span className="block text-[12px] text-ink-3">{d.who}</span></span>
              <span className="text-terra rtl:rotate-180">→</span>
            </button>
          ))}
        </div>
      </div>
      )}
    </div>
  );
}

export default function LoginPage() {
  return <Suspense><LoginInner /></Suspense>;
}
