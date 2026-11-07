"use client";
import { useRouter } from "@/lib/router";
import { useState } from "react";
import { useLocale, useTx } from "@/i18n";
import { supabase } from "@/lib/supabase";
import { Button, Field, Input } from "@/components/ui";
import { toast } from "@/components/ui/toast";

export default function ResetPage() {
  const locale = useLocale();
  const tx = useTx();
  const router = useRouter();
  const [pw, setPw] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (pw.length < 8) return toast(tx("At least 8 characters", "8 أحرف على الأقل"), undefined, "error");
    setLoading(true);
    const { error } = await supabase().auth.updateUser({ password: pw });
    setLoading(false);
    if (error) return toast(tx("Couldn't update password", "ما قدرنا نغيّر كلمة المرور"), error.message, "error");
    toast(tx("Password updated", "تم تغيير كلمة المرور"));
    router.replace(`/${locale}/app`);
  }
  return (
    <div>
      <h1 className="font-serif text-[32px] text-ink">{tx("Choose a new password", "اختار كلمة مرور جديدة")}</h1>
      <form onSubmit={submit} className="mt-8 space-y-4">
        <Field label={tx("New password", "كلمة المرور الجديدة")}><Input type="password" dir="ltr" value={pw} onChange={(e) => setPw(e.target.value)} required /></Field>
        <Button type="submit" size="lg" className="w-full" loading={loading}>{tx("Save password", "حفظ")}</Button>
      </form>
    </div>
  );
}
