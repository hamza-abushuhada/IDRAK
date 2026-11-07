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

function SignupInner() {
  const locale = useLocale();
  const tx = useTx();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next");
  const [form, setForm] = useState({ name: "", email: params.get("email") || "", password: "" });
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (form.password.length < 8) return toast(tx("Password must be at least 8 characters", "كلمة المرور لازم تكون 8 أحرف أو أكثر"), undefined, "error");
    setLoading(true);
    const { data, error } = await supabase().auth.signUp({
      email: form.email, password: form.password,
      options: { data: { full_name: form.name, locale }, emailRedirectTo: `${window.location.origin}/${locale}/onboarding` },
    });
    setLoading(false);
    if (error) return toast(tx("Couldn't create the account", "ما قدرنا ننشئ الحساب"), error.message, "error");
    if (data.session) router.replace(next || `/${locale}/onboarding`);
    else setSent(true);
  }

  if (sent) {
    return (
      <div>
        <h1 className="font-serif text-[32px] text-ink">{tx("Check your email", "شيّك إيميلك")}</h1>
        <p className="mt-3 text-ink-2">{tx(`We sent a confirmation link to ${form.email}. Open it to start your 14-day trial.`, `بعتنا رابط تأكيد على ${form.email}. افتحه وابدأ تجربتك المجانية لمدة 14 يوم.`)}</p>
        <p className="mt-6 text-sm text-ink-3">{tx("Just exploring? Use one of the demo accounts on the sign-in page.", "بس حابب تتفرج؟ استعمل حساب من الحسابات التجريبية بصفحة الدخول.")}</p>
        <Button href={`/${locale}/login`} variant="secondary" className="mt-6">{tx("Back to sign in", "رجوع لتسجيل الدخول")}</Button>
      </div>
    );
  }

  return (
    <div>
      <h1 className="font-serif text-[34px] leading-tight text-ink">{tx("Start your free trial", "ابدأ تجربتك المجانية")}</h1>
      <p className="mt-2 text-ink-2">{tx("14 days, no card. Upload a file and see your Health Score in a minute.", "14 يوم بدون بطاقة. ارفع ملف وشوف صحة بياناتك خلال دقيقة.")}</p>
      <div className="mt-8"><GoogleButton next={next || undefined} /></div>
      <OrDivider />
      <form onSubmit={submit} className="space-y-4">
        <Field label={tx("Your name", "اسمك")}><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required autoComplete="name" /></Field>
        <Field label={tx("Work email", "إيميل الشغل")}><Input type="email" dir="ltr" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required autoComplete="email" /></Field>
        <Field label={tx("Password", "كلمة المرور")} hint={tx("At least 8 characters", "8 أحرف على الأقل")}><Input type="password" dir="ltr" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required autoComplete="new-password" /></Field>
        <Button type="submit" size="lg" className="w-full" loading={loading}>{tx("Create account", "إنشاء الحساب")}</Button>
        <p className="text-xs text-ink-3">{tx("By continuing you agree to our Terms and Privacy Policy.", "بالمتابعة إنت موافق على الشروط وسياسة الخصوصية.")}</p>
      </form>
      <p className="mt-6 text-center text-sm text-ink-2">{tx("Already have an account?", "عندك حساب؟")} <Link href={`/${locale}/login`} className="font-medium text-terra">{tx("Sign in", "سجّل دخول")}</Link></p>
    </div>
  );
}

export default function SignupPage() {
  return <Suspense><SignupInner /></Suspense>;
}
