"use client";
import { useEffect, useRef, useState } from "react";
import { Loader2, XCircle, CheckCircle2 } from "lucide-react";
import { useTx } from "@/i18n";
import { api, ApiError, getOrgId } from "@/lib/api";
import { useRouter } from "@/lib/router";
import { useSession } from "@/components/app/session";
import { Button, Card } from "@/components/ui";
import { friendlyError } from "@/components/app/connect/model";
import { readOAuthReturn, setFlash, takePending, type OAuthDiag, type Pending } from "@/components/app/connect/pending";

type View = { kind: "working" } | { kind: "denied" } | { kind: "error"; message: string; diag?: OAuthDiag };

// Loyverse sends the owner back here (registered redirect URI) with ?code&state.
// The code is single-use and only exchanged server-side with the app secret;
// the request is re-verified against this user, business and the state this tab issued.
export default function LoyverseCallbackPage() {
  const tx = useTx();
  const router = useRouter();
  const { session, loading } = useSession();
  const [view, setView] = useState<View>({ kind: "working" });
  const captured = useRef<{ code: string; state: string; denied: boolean; diag: OAuthDiag; pending: Pending | null } | null>(null);
  const started = useRef(false);
  const home = `/${tx.locale}/app/integrations`;

  useEffect(() => {
    if (captured.current) return;
    const ret = readOAuthReturn(window.location.search, window.location.hash);
    window.history.replaceState(null, "", window.location.pathname);  // drop the code from the address bar/history
    captured.current = { ...ret, pending: takePending("loyverse") };
  }, []);

  useEffect(() => {
    if (loading || !session || started.current || !captured.current) return;
    started.current = true;
    const { code, state, denied, diag, pending } = captured.current;
    const restart = tx("Start again from “Connect a new system”.", "ابدأ من جديد من «ربط نظام جديد».");
    if (!pending || !state || pending.state !== state) {
      setView({ kind: "error", message: tx("This return doesn't match a request started in this window, or it expired. ", "هذه العودة لا تطابق طلبًا بدأ من هذه النافذة، أو انتهت صلاحيته. ") + restart });
      return;
    }
    if (pending.org !== getOrgId() || pending.user !== session.user.id) {
      setView({ kind: "error", message: tx("You switched business or account while connecting. ", "تم تغيير المؤسسة أو الحساب أثناء الربط. ") + restart });
      return;
    }
    if (denied) { setView({ kind: "denied" }); return; }
    if (!code) { setView({ kind: "error", message: tx("Loyverse didn't return an approval. ", "لم يُرجع Loyverse موافقة صالحة. ") + restart, diag }); return; }
    void (async () => {
      try {
        const r = await api<{ name: string; automatic_updates: boolean }>("/integrations/loyverse/connect",
          { method: "POST", json: { code, intent: pending.intent, state: pending.state } });
        setFlash({ name: r.name, ok: r.automatic_updates });
        router.replace(home);
      } catch (e) {
        const status = e instanceof ApiError ? e.status : undefined;
        setView({ kind: "error", message: status === 409
          ? tx("This Loyverse account can't be linked here (already linked to another business, different currency, or the approval expired). ", "لا يمكن ربط حساب Loyverse هذا هنا (مرتبط بمؤسسة أخرى، أو بعملة مختلفة، أو انتهت صلاحية الموافقة). ") + restart
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
            <h1 className="mt-4 font-serif text-[20px] text-ink">{tx("Connecting Loyverse…", "جارٍ ربط Loyverse…")}</h1>
          </div>
        )}
        {view.kind === "denied" && (
          <div role="alert">
            <CheckCircle2 size={30} className="mx-auto text-ink-3" />
            <h1 className="mt-4 font-serif text-[20px] text-ink">{tx("Connection cancelled", "تم إلغاء الربط")}</h1>
            <p className="mt-2 text-[13.5px] text-ink-3">{tx("Nothing was connected and no data was shared.", "لم يتم أي ربط ولم تُشارك أي بيانات.")}</p>
            <Button className="mt-5" onClick={() => router.replace(home)}>{tx("Back to IDRAK Connect", "العودة إلى IDRAK Connect")}</Button>
          </div>
        )}
        {view.kind === "error" && (
          <div role="alert">
            <XCircle size={30} className="mx-auto text-danger" />
            <h1 className="mt-4 font-serif text-[20px] text-ink">{tx("We couldn't connect Loyverse", "تعذّر ربط Loyverse")}</h1>
            <p className="mt-2 text-[13.5px] text-ink-3">{view.message}</p>
            {view.diag && (
              <details className="mt-4 rounded-lg bg-paper-2/60 p-3 text-start text-[12px] text-ink-3">
                <summary className="cursor-pointer">{tx("Technical details for support (no codes or secrets)", "تفاصيل تقنية للدعم (بدون رموز أو أسرار)")}</summary>
                <p className="mt-2" dir="ltr">query: {view.diag.query.join(", ") || "—"} · fragment: {view.diag.fragment.join(", ") || "—"}</p>
                <p dir="ltr">code: {view.diag.code.present ? `present, ${view.diag.code.length} chars, contains: ${view.diag.code.classes.join(" ") || "—"}` : "absent"}</p>
              </details>
            )}
            <Button className="mt-5" onClick={() => router.replace(home)}>{tx("Back to IDRAK Connect", "العودة إلى IDRAK Connect")}</Button>
          </div>
        )}
      </Card>
    </div>
  );
}
