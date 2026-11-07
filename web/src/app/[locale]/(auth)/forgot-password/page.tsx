"use client";
import Link from "next/link";
import { useState } from "react";
import { useLocale, useTx } from "@/i18n";
import { supabase } from "@/lib/supabase";
import { Button, Field, Input } from "@/components/ui";
import { toast } from "@/components/ui/toast";

export default function ForgotPage() {
  const locale = useLocale();
  const tx = useTx();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    const { error } = await supabase().auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/${locale}/reset-password` });
    setLoading(false);
    if (error) return toast(tx("Couldn't send the email", "ما قدرنا نبعث الإيميل"), error.message, "error");
    setSent(true);
  }
  return (
    <div>
      <h1 className="font-serif text-[32px] text-ink">{tx("Reset your password", "إعادة تعيين كلمة المرور")}</h1>
      <p className="mt-2 text-ink-2">{tx("We'll email you a link to choose a new one.", "رح نبعتلك رابط تختار فيه كلمة مرور جديدة.")}</p>
      {sent ? (
        <p className="mt-8 rounded-lg bg-olive-soft px-4 py-3 text-olive">{tx("If an account exists for that email, a reset link is on its way.", "إذا في حساب على هالإيميل، رابط إعادة التعيين بالطريق.")}</p>
      ) : (
        <form onSubmit={submit} className="mt-8 space-y-4">
          <Field label={tx("Email", "الإيميل")}><Input type="email" dir="ltr" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
          <Button type="submit" size="lg" className="w-full" loading={loading}>{tx("Send reset link", "ابعت الرابط")}</Button>
        </form>
      )}
      <p className="mt-6 text-sm"><Link href={`/${locale}/login`} className="text-terra">{tx("← Back to sign in", "→ رجوع لتسجيل الدخول")}</Link></p>
    </div>
  );
}
