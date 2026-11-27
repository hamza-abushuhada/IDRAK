"use client";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useTx } from "@/i18n";
import { api, ApiError, getOrgId } from "@/lib/api";
import { useRouter } from "@/lib/router";
import { useSession } from "@/components/app/session";
import { Button, Card } from "@/components/ui";
import { friendlyError } from "@/components/app/connect/model";
import { readReturn, setFlash, takePending, type Pending } from "@/components/app/connect/pending";

type View = { kind: "working" } | { kind: "denied" } | { kind: "error"; message: string };
type Paired = { shop_id: string; name?: string; connections: { id: string; provider_code: string }[] };

// Where the POS sends the owner back after they approve (or deny) in the Lab.
// Everything here is re-checked by the server: the code is single-use and the
// request is bound to this user + business and to the state this tab issued.
export default function ConnectCallbackPage() {
  const tx = useTx();
  const router = useRouter();
  const { session, loading } = useSession();
  const [view, setView] = useState<View>({ kind: "working" });
  const captured = useRef<{ ret: ReturnType<typeof readReturn>; pending: Pending | null } | null>(null);
  const started = useRef(false);
  const home = `/${tx.locale}/app/integrations`;

  useEffect(() => {
    if (captured.current) return;
    const ret = readReturn(window.location.hash);
    // Drop the code from the address bar and history straight away.
    window.history.replaceState(null, "", window.location.pathname);
    captured.current = { ret, pending: takePending() };
  }, []);

  useEffect(() => {
    if (loading || !session || started.current || !captured.current) return;
    started.current = true;
    const { ret, pending } = captured.current;
    const restart = tx("Start again from “Connect a new system”.", "ابدأ من جديد من «ربط نظام جديد».");
    if (!pending || !ret.state || pending.state !== ret.state) {
      setView({ kind: "error", message: tx("This return doesn't match a link request started in this window, or the request expired. ", "هذه العودة لا تطابق طلب ربط بدأ من هذه النافذة، أو انتهت صلاحية الطلب. ") + restart });
      return;
    }
    if (pending.org !== getOrgId() || pending.user !== session.user.id) {
      setView({ kind: "error", message: tx("You switched business or account while linking. ", "تم تغيير المؤسسة أو الحساب أثناء الربط. ") + restart });
      return;
    }
    if (ret.denied) { setView({ kind: "denied" }); return; }
    if (!ret.code) { setView({ kind: "error", message: tx("The POS didn't return an approval. ", "لم يُرجع نظام الكاشير موافقة صالحة. ") + restart }); return; }
    void (async () => {
      try {
        const result = await api<Paired>("/integrations/lab/pair", { method: "POST", json: { code: ret.code, intent: pending.intent, state: pending.state } });
        // Confirm the link works before announcing success; a failed check still leaves it linked.
        const checks = await Promise.all(result.connections.map((c) =>
          api<{ ok: boolean }>(`/integrations/connections/${c.id}/test`, { method: "POST" }).then((r) => r.ok, () => false)));
        setFlash({ name: result.name || "", ok: checks.every(Boolean) });
        router.replace(home);
      } catch (e) {
        const status = e instanceof ApiError ? e.status : undefined;
        setView({ kind: "error", message: status === 409 || status === 400
          ? tx("The approval expired or was already used, or this shop is linked to another business. ", "انتهت صلاحية الموافقة أو استُخدمت مسبقًا، أو أن المحل مرتبط بمؤسسة أخرى. ") + restart
          : friendlyError(status, tx.isAr) });
      }
    })();
  }, [loading, session, tx, router, home]);

  return (
    <div className="mx-auto max-w-lg py-10">
      <Card className="p-6 text-center">
        {view.kind === "working" && (
          <div role="status">
            <Loader2 size={30} className="mx-auto animate-spin text-terra" />
            <h1 className="mt-4 font-serif text-[20px] text-ink">{tx("Finishing the link…", "جارٍ إكمال الربط…")}</h1>
            <p className="mt-2 text-[13.5px] text-ink-3">{tx("Confirming the approval with your POS and testing the connection.", "نؤكد الموافقة مع نظام الكاشير ونختبر الاتصال.")}</p>
          </div>
        )}
        {view.kind === "denied" && (
          <div role="alert">
            <CheckCircle2 size={30} className="mx-auto text-ink-3" />
            <h1 className="mt-4 font-serif text-[20px] text-ink">{tx("Linking was cancelled", "تم إلغاء الربط")}</h1>
            <p className="mt-2 text-[13.5px] text-ink-3">{tx("You declined the request in your POS. Nothing was linked and no data was shared.", "رفضت الطلب في نظام الكاشير. لم يتم أي ربط ولم تُشارك أي بيانات.")}</p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              <Button onClick={() => router.replace(`${home}?connect=lab`)}>{tx("Try again", "حاول مرة أخرى")}</Button>
              <Button variant="secondary" onClick={() => router.replace(home)}>{tx("Back to IDRAK Connect", "العودة إلى IDRAK Connect")}</Button>
            </div>
          </div>
        )}
        {view.kind === "error" && (
          <div role="alert">
            <XCircle size={30} className="mx-auto text-danger" />
            <h1 className="mt-4 font-serif text-[20px] text-ink">{tx("We couldn't finish linking", "تعذّر إكمال الربط")}</h1>
            <p className="mt-2 text-[13.5px] text-ink-3">{view.message}</p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              <Button onClick={() => router.replace(`${home}?connect=lab`)}>{tx("Try again", "حاول مرة أخرى")}</Button>
              <Button variant="secondary" onClick={() => router.replace(home)}>{tx("Back to IDRAK Connect", "العودة إلى IDRAK Connect")}</Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
