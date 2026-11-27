"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Copy, ExternalLink, KeyRound } from "lucide-react";
import { useTx } from "@/i18n";
import { API_URL, ApiError, getOrgId } from "@/lib/api";
import { useSession } from "@/components/app/session";
import { Button, Input, Textarea } from "@/components/ui";
import { LAB_LOGIN_URL } from "@/lib/labUrl";

type Intent = { intent: string; expires_at: number };
export type Paired = { shop_id: string; connections: { id: string; provider_code: string }[] };

// Pairing step of the IDRAK Connect wizard. Security properties:
// - request/code live only in component memory (no query cache, storage or URL);
// - every call is pinned to the user + business that started it, and aborts if
//   either changes; the server binds the request to them and makes codes single-use.
export default function LabPairing({ onPaired }: { onPaired: (result: Paired) => void }) {
  const tx = useTx();
  const { org, session } = useSession();
  const [intent, setIntent] = useState<Intent | null>(null);
  const [code, setCode] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (!intent) return;
    const timer = setInterval(() => {
      const remaining = Math.max(0, Math.ceil(intent.expires_at - Date.now() / 1000));
      setSeconds(remaining);
      if (!remaining) {
        setIntent(null); setCode("");
        setError(tx("The request expired. Create a new one.", "انتهت صلاحية الطلب. أنشئ طلبًا جديدًا."));
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [intent, tx]);

  function message(err: unknown) {
    const status = err instanceof ApiError ? err.status : 0;
    if (status === 401) return tx("Sign in again, then create a new request.", "سجّل الدخول مجددًا، ثم أنشئ طلبًا جديدًا.");
    if (status === 403) return tx("You need permission to manage connections in this business.", "تحتاج صلاحية إدارة الاتصالات في هذه المؤسسة.");
    if (status === 400 || status === 409) return tx(
      "This code is invalid, expired, already used, or belongs to another request. A shop already linked to another business can't be moved. Create a new request and code.",
      "الرمز غير صالح أو منتهٍ أو مستخدم أو تابع لطلب آخر. لا يمكن نقل محل مرتبط بمؤسسة أخرى. أنشئ طلبًا ورمزًا جديدين.");
    if (status === 503) return tx("Linking isn't available right now. Try again later.", "الربط غير متاح الآن. حاول لاحقًا.");
    return tx("We couldn't confirm the link. Check your connections, then try again.", "تعذّر تأكيد الربط. تحقق من الاتصالات ثم حاول مجددًا.");
  }

  async function post<T>(path: string, body?: unknown): Promise<T> {
    if (!org || !session || getOrgId() !== org.id) throw new ApiError(400, "context changed");
    controller.current?.abort();
    const pending = new AbortController();
    controller.current = pending;
    const response = await fetch(API_URL + path, {
      method: "POST", signal: pending.signal, cache: "no-store",
      headers: { Authorization: `Bearer ${session.access_token}`, "X-Org-Id": org.id, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) throw new ApiError(response.status, "pairing failed");
    const result = await response.json() as T;
    if (pending.signal.aborted || getOrgId() !== org.id) throw new DOMException("Cancelled", "AbortError");
    return result;
  }

  async function start() {
    setBusy(true); setError(""); setNotice(""); setCode(""); setIntent(null);
    try {
      const value = await post<Intent>("/integrations/lab/pairing-intents");
      setIntent(value); setSeconds(Math.max(0, Math.ceil(value.expires_at - Date.now() / 1000)));
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) setError(message(err));
    } finally { setBusy(false); }
  }

  async function redeem(event: React.FormEvent) {
    event.preventDefault();
    if (!intent || intent.expires_at <= Date.now() / 1000 || busy) return;
    setBusy(true); setError(""); setNotice("");
    const value = code.trim();
    setCode("");
    try {
      const result = await post<Paired>("/integrations/lab/pair", { code: value, intent: intent.intent });
      setIntent(null);
      onPaired(result);
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) setError(message(err));
    } finally { setBusy(false); }
  }

  async function copy() {
    if (!intent) return;
    try { await navigator.clipboard.writeText(intent.intent); setNotice(tx("Copied. Paste it in your Lab shop.", "تم النسخ. الصقه في محلك داخل المحاكي.")); }
    catch { setNotice(tx("Select the request below and copy it manually.", "حدّد الطلب أدناه وانسخه يدويًا.")); }
  }

  return (
    <div className="space-y-4">
      {error && <p role="alert" className="rounded-lg bg-danger/10 p-3 text-[13px] text-danger">{error}</p>}
      {notice && <p role="status" className="flex items-center gap-1.5 text-[13px] text-olive"><CheckCircle2 size={14} />{notice}</p>}
      {!intent ? (
        <div className="rounded-xl border border-line bg-paper-2/50 p-4">
          <p className="text-[13.5px] text-ink-2">{tx("Step 1: create a one-time link request for this business.", "الخطوة ١: أنشئ طلب ربط لمرة واحدة لهذه المؤسسة.")}</p>
          <Button className="mt-3" onClick={start} loading={busy} disabled={busy}><KeyRound size={15} />{error ? tx("Create a new request", "إنشاء طلب جديد") : tx("Create link request", "إنشاء طلب الربط")}</Button>
        </div>
      ) : (
        <>
          <div className="rounded-xl border border-line bg-paper-2/50 p-4">
            <p className="text-[13.5px] text-ink-2">{tx("Step 2: copy the request, then in your Lab shop choose “Connect to IDRAK” and paste it.", "الخطوة ٢: انسخ الطلب، ثم داخل محلك في المحاكي اختر «ربط مع IDRAK» والصقه.")}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button type="button" variant="secondary" size="sm" onClick={copy}><Copy size={14} />{tx("Copy request", "نسخ الطلب")}</Button>
              {LAB_LOGIN_URL && <a href={LAB_LOGIN_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[13px] text-terra underline"><ExternalLink size={13} />{tx("Open IDRAK Connect Lab", "فتح IDRAK Connect Lab")}</a>}
              <span className="ms-auto text-[12.5px] text-ink-3" role="timer">{tx("Expires in", "ينتهي خلال")} <span dir="ltr">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}</span></span>
            </div>
            <details className="mt-2"><summary className="cursor-pointer text-[12px] text-ink-3">{tx("Show request to copy manually", "عرض الطلب للنسخ اليدوي")}</summary>
              <label htmlFor="lab-intent" className="sr-only">{tx("Link request", "طلب الربط")}</label>
              <Textarea id="lab-intent" readOnly value={intent.intent} dir="ltr" rows={3} autoComplete="off" spellCheck={false} className="mt-2 break-all font-mono text-xs" />
            </details>
          </div>
          <form onSubmit={redeem} className="rounded-xl border border-line bg-paper-2/50 p-4">
            <label htmlFor="lab-code" className="text-[13.5px] text-ink-2">{tx("Step 3: enter the pairing code shown in your Lab shop.", "الخطوة ٣: أدخل رمز الاقتران الظاهر في محلك.")}</label>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row">
              <Input id="lab-code" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" spellCheck={false} dir="ltr" maxLength={128} minLength={20} required disabled={busy} className="font-mono" />
              <Button type="submit" loading={busy} disabled={busy || code.trim().length < 20 || !seconds}>{tx("Confirm link", "تأكيد الربط")}</Button>
            </div>
            <p className="mt-2 text-[12px] text-ink-3">{tx("Codes work once and expire within minutes. No passwords or secrets are shared with IDRAK.", "الرمز يعمل مرة واحدة وينتهي خلال دقائق. لا تتم مشاركة أي كلمة مرور أو أسرار مع إدراك.")}</p>
          </form>
        </>
      )}
    </div>
  );
}
