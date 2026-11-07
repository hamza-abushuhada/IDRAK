"use client";
import { useParams } from "next/navigation";
import { useRouter } from "@/lib/router";
import { useEffect, useState } from "react";
import { useLocale, useTx } from "@/i18n";
import { supabase } from "@/lib/supabase";
import { api, publicApi, setOrgId } from "@/lib/api";
import { Logo } from "@/components/Logo";
import { Button, Card, Spinner } from "@/components/ui";
import { toast } from "@/components/ui/toast";

type Inv = { email: string; role: string; status: string; name: string; name_ar: string | null };

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const locale = useLocale();
  const tx = useTx();
  const router = useRouter();
  const [inv, setInv] = useState<Inv | null | undefined>(undefined);
  const [signedIn, setSignedIn] = useState(false);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    publicApi<Inv>(`/invitations/${token}`).then(setInv).catch(() => setInv(null));
    supabase().auth.getSession().then(({ data }) => setSignedIn(!!data.session));
  }, [token]);
  async function accept() {
    setLoading(true);
    try {
      const r = await api<{ org_id: string }>(`/invitations/${token}/accept`, { method: "POST" });
      setOrgId(r.org_id);
      router.replace(`/${locale}/app`);
    } catch (e) {
      toast(tx("Couldn't accept", "ما زبط القبول"), (e as Error).message, "error");
      setLoading(false);
    }
  }
  const roles: Record<string, [string, string]> = { owner: ["Owner", "مالك"], manager: ["Manager", "مدير"], accountant: ["Accountant", "محاسب"], cashier: ["Cashier", "كاشير"] };
  const next = encodeURIComponent(`/${locale}/invite/${token}`);
  return (
    <div className="grain grid min-h-dvh place-items-center bg-paper px-5">
      <Card className="w-full max-w-md p-8 text-center">
        <div className="flex justify-center"><Logo locale={locale} /></div>
        {inv === undefined && <div className="mt-8 flex justify-center"><Spinner /></div>}
        {inv === null && <p className="mt-8 text-ink-2">{tx("This invitation is invalid or has expired.", "الدعوة مش صالحة أو انتهت.")}</p>}
        {inv && (
          <>
            <h1 className="mt-8 font-serif text-[26px] text-ink">{tx(`Join ${inv.name}`, `انضم لـ ${inv.name_ar || inv.name}`)}</h1>
            <p className="mt-2 text-ink-2">{tx("You've been invited as", "انعزمت كـ")} <b>{tx(...(roles[inv.role] || [inv.role, inv.role]))}</b> · <span dir="ltr">{inv.email}</span></p>
            {inv.status !== "pending" ? <p className="mt-6 text-sm text-ink-3">{tx("This invitation was already used.", "الدعوة مستخدمة.")}</p> : signedIn ? (
              <Button className="mt-8 w-full" size="lg" loading={loading} onClick={accept}>{tx("Accept invitation", "قبول الدعوة")}</Button>
            ) : (
              <div className="mt-8 grid gap-2">
                <Button href={`/${locale}/signup?email=${encodeURIComponent(inv.email)}&next=${next}`} size="lg">{tx("Create account to join", "أنشئ حساب وانضم")}</Button>
                <Button href={`/${locale}/login?next=${next}`} variant="secondary">{tx("I already have an account", "عندي حساب")}</Button>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
