"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Copy, ExternalLink, Link2 } from "lucide-react";
import { useTx } from "@/i18n";
import { API_URL, ApiError, getOrgId } from "@/lib/api";
import { useSession } from "@/components/app/session";
import { Button, Card, Input, Textarea } from "@/components/ui";
import { LAB_LOGIN_URL } from "@/lib/labUrl";

type Intent = { intent: string; expires_at: number };
type Paired = { shop_id: string; connections: { id: string; provider_code: string }[] };

// Pairing values stay in component memory, outside query/mutation caches.
export default function LabPairing({ onPaired }: { onPaired: () => void }) {
  const tx = useTx();
  const { org, session } = useSession();
  const [intent, setIntent] = useState<Intent | null>(null);
  const [code, setCode] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [paired, setPaired] = useState<Paired | null>(null);
  const controller = useRef<AbortController | null>(null);
  const codeInput = useRef<HTMLInputElement>(null);

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (!intent) return;
    const timer = setInterval(() => {
      const remaining = Math.max(0, Math.ceil(intent.expires_at - Date.now() / 1000));
      setSeconds(remaining);
      if (!remaining) {
        setIntent(null); setCode("");
        setError(tx("The request expired. Create a new request and code.", "انتهت صلاحية الطلب. أنشئ طلبًا ورمزًا جديدين."));
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [intent, tx]);

  function message(error: unknown) {
    const status = error instanceof ApiError ? error.status : 0;
    if (status === 401) return tx("Sign in again, then create a new request.", "سجّل الدخول مجددًا، ثم أنشئ طلبًا جديدًا.");
    if (status === 403) return tx("You need permission to manage integrations in this business.", "تحتاج صلاحية إدارة الربط على هذه المؤسسة.");
    if (status === 400 || status === 409) return tx(
      "This code may have expired, been used, or belong to another request or business. A shop already linked elsewhere cannot be transferred. Check the shop and create a new request and code.",
      "قد يكون الرمز منتهيًا أو مستخدمًا أو تابعًا لطلب أو مؤسسة أخرى. لا يمكن نقل محل مرتبط بمؤسسة أخرى. تحقق من المحل وأنشئ طلبًا ورمزًا جديدين.");
    if (status === 503) return tx("Pairing is not ready on the server. Ask your administrator to finish setup.", "الربط غير جاهز على الخادم. اطلب من المسؤول إكمال الإعداد.");
    return tx("Could not confirm the connection. Check your connections first, then create a new request if needed.", "تعذّر تأكيد الربط. تحقق من الاتصالات الحالية أولًا، ثم أنشئ طلبًا جديدًا عند الحاجة.");
  }

  async function post<T>(path: string, body?: unknown): Promise<T> {
    if (!org || !session || getOrgId() !== org.id) throw new ApiError(400, "context changed");
    controller.current?.abort();
    const pending = new AbortController();
    controller.current = pending;
    // Capture the original user/org explicitly; the shared API helper reads a
    // mutable current-org value after awaiting auth and is unsuitable here.
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
    setBusy(true); setError(""); setNotice(""); setCode(""); setIntent(null); setPaired(null);
    try {
      const value = await post<Intent>("/integrations/lab/pairing-intents");
      setIntent(value); setSeconds(Math.max(0, Math.ceil(value.expires_at - Date.now() / 1000)));
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) setError(message(error));
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
      setPaired(result); setIntent(null); setError(""); onPaired();
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) setError(message(error));
    } finally { setBusy(false); }
  }

  async function copy() {
    if (!intent) return;
    try { await navigator.clipboard.writeText(intent.intent); setNotice(tx("Request copied. Paste it in your Lab shop.", "نُسخ الطلب. الصقه داخل محلك في المحاكي.")); }
    catch { setNotice(tx("Select the request below and copy it manually.", "حدد الطلب أدناه وانسخه يدويًا.")); }
  }

  return <Card id="lab-pairing" className="mb-6 scroll-mt-6 p-5 sm:p-6">
    <div className="mb-4 flex items-start gap-3">
      <Link2 className="mt-1 shrink-0 text-terra" size={22} />
      <div><h2 className="font-serif text-xl">{tx("Connect the demo cashier", "ربط الكاشير التجريبي")}</h2>
        <p className="mt-1 text-sm text-ink-3">{tx("Connect your Lab shop's POS and online store to", "اربط كاشير محلك ومتجره الإلكتروني مع")} <strong className="text-ink">{org?.name_ar && tx.isAr ? org.name_ar : org?.name}</strong>.</p>
      </div>
    </div>
    <ol className="mb-4 grid gap-3 text-sm sm:grid-cols-3">
      <li className="rounded-lg bg-sand/50 p-3">{tx("1. Create and copy your connection request here.", "١. أنشئ طلب الربط هنا وانسخه.")}</li>
      <li className="rounded-lg bg-sand/50 p-3">{tx('2. In your Lab shop, choose “Connect to IDRAK”, paste the request and copy the code.', '٢. داخل محلك في المحاكي، اختر «ربط مع IDRAK»، والصق الطلب ثم انسخ الرمز.')}</li>
      <li className="rounded-lg bg-sand/50 p-3">{tx("3. Return here and enter the code. Keep this page open.", "٣. عُد إلى هنا وأدخل الرمز. أبقِ هذه الصفحة مفتوحة.")}</li>
    </ol>
    {error && <p role="alert" className="mb-3 rounded-lg bg-danger/10 p-3 text-sm text-danger">{error}</p>}
    {notice && <p role="status" className="mb-3 text-sm text-olive">{notice}</p>}
    {paired ? <div role="status" className="rounded-xl border border-olive/30 bg-olive/10 p-4">
      <p className="flex items-center gap-2 font-medium"><CheckCircle2 size={18} />{tx("Shop connected", "تم ربط المحل")}</p>
      <p className="mt-1 font-mono text-sm" dir="ltr">{paired.shop_id}</p>
      <p className="mt-2 text-sm">{tx("POS and online store connections are ready. Their current status and Sync now buttons appear below.", "اتصالا الكاشير والمتجر الإلكتروني جاهزان. ستجد حالتهما الحالية وأزرار «زامن الآن» أدناه.")}</p>
      <a className="mt-2 inline-block text-sm underline" href="#pos-connections">{tx("View connections and sync", "عرض الاتصالات والمزامنة")}</a>
    </div> : intent ? <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="secondary" onClick={copy}><Copy size={15} />{tx("Copy request", "نسخ طلب الربط")}</Button>
        {LAB_LOGIN_URL && <a href={LAB_LOGIN_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-terra underline"><ExternalLink size={14} />{tx("Open the Lab", "فتح المحاكي")}</a>}
        <span className="text-sm text-ink-3" role="timer">{tx("Expires in", "ينتهي خلال")} {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}</span>
      </div>
      <details><summary className="cursor-pointer text-sm text-ink-3">{tx("Show request for manual copying", "عرض الطلب للنسخ اليدوي")}</summary>
        <label htmlFor="lab-intent" className="sr-only">{tx("Connection request", "طلب الربط")}</label>
        <Textarea id="lab-intent" readOnly value={intent.intent} dir="ltr" rows={3} autoComplete="off" spellCheck={false} className="mt-2 break-all font-mono text-xs" />
      </details>
      <form onSubmit={redeem} className="flex max-w-xl flex-col gap-2">
        <label htmlFor="lab-code" className="text-sm font-medium">{tx("Pairing code from your Lab shop", "رمز الاقتران من محلك في المحاكي")}</label>
        <Input ref={codeInput} id="lab-code" value={code} onChange={e => setCode(e.target.value)} autoComplete="off" spellCheck={false} dir="ltr" maxLength={128} minLength={20} required disabled={busy} />
        <Button type="submit" loading={busy} disabled={busy || code.trim().length < 20 || !seconds}>{tx("Confirm connection", "تأكيد الربط")}</Button>
      </form>
    </div> : null}
    {!paired && <Button className="mt-4" type="button" variant={intent ? "ghost" : "primary"} onClick={start} loading={busy} disabled={busy}>
      {intent || error ? tx("Create a new request", "إنشاء طلب جديد") : tx("Start connection", "بدء الربط")}
    </Button>}
    <p className="mt-3 text-xs text-ink-3">{tx("Requests are tied to your current user and business. Switching business or reloading clears this step. No API secrets are shared.", "الطلب خاص بمستخدمك ومؤسستك الحالية. تغيير المؤسسة أو تحديث الصفحة يمسح هذه الخطوة. لا تتم مشاركة أسرار API.")}</p>
  </Card>;
}
