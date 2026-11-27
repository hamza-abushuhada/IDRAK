"use client";

import { useState } from "react";
import clsx from "clsx";
import { ArrowLeft, ArrowRight, CheckCircle2, ExternalLink, FlaskConical, Globe, Loader2, LogIn, ShieldCheck, ShoppingBag, Sparkles, Undo2, XCircle } from "lucide-react";
import { useTx } from "@/i18n";
import { api, ApiError, getOrgId } from "@/lib/api";
import { LAB_LOGIN_URL } from "@/lib/labUrl";
import { useSession } from "@/components/app/session";
import { Badge, Button, Input } from "@/components/ui";
import { Drawer } from "@/components/workspace/common";
import LabPairing, { type Paired } from "@/components/app/LabPairing";
import { friendlyError, type Provider } from "./model";
import { savePending } from "./pending";

type SystemType = "pos" | "store";
type Choice = "lab" | "demo";
type Step = "type" | "provider" | "instructions" | "authorize" | "name" | "test" | "done";
type Check = { name: string; ok: boolean };
type TestResult = { ok: boolean; checks: Check[] };
const STEPS: Step[] = ["type", "provider", "instructions", "authorize", "name", "test", "done"];
// Lab: after "Continue to your POS" the owner signs in and approves there, then returns to IDRAK.
const LAB_STEPS: Step[] = ["type", "provider", "instructions", "done"];
// The manual pairing-code method stays as an admin fallback, reachable only with ?pairing=manual.
const manualPairing = () => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("pairing") === "manual";

/** Coming-soon connector categories by system type. Generic categories only: no real vendor is claimed as supported. */
const SOON_FOR: Record<SystemType, string[]> = { pos: ["cloud_api", "local_agent", "file_export"], store: ["cloud_api"] };

export default function ConnectWizard({ open, onOpenChange, providers, initialChoice, onConnected }: {
  open: boolean; onOpenChange: (o: boolean) => void; providers: Provider[] | undefined;
  initialChoice?: Choice | null; onConnected: () => void;
}) {
  const tx = useTx();
  const { session } = useSession();
  const [step, setStep] = useState<Step>(initialChoice ? "instructions" : "type");
  const [type, setType] = useState<SystemType>("pos");
  const [choice, setChoice] = useState<Choice | null>(initialChoice ?? null);
  const [connIds, setConnIds] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [test, setTest] = useState<{ id: string; channel: string; result: TestResult | null; error?: string }[]>([]);

  const has = (code: string) => !!providers?.some((p) => p.code === code && p.is_implemented);
  const labAvailable = has("lab_pos") && has("lab_web");
  const demoAvailable = has("demo");
  const soon = (providers || []).filter((p) => p.status === "coming_soon" && SOON_FOR[type].includes(p.code));

  function reset(o: boolean) {
    if (!o) {
      setStep(initialChoice ? "instructions" : "type"); setChoice(initialChoice ?? null); setConnIds([]); setName("");
      setError(""); setTest([]); setBusy(false);
    }
    onOpenChange(o);
  }
  const go = (s: Step) => { setError(""); setStep(s); };
  const flow = choice === "lab" && STEPS.indexOf(step) <= 2 ? LAB_STEPS : STEPS;
  const index = flow.indexOf(step);

  async function continueToPos() {
    setBusy(true); setError("");
    try {
      const org = getOrgId(), user = session?.user.id;
      if (!org || !user) throw new ApiError(401, "no session");
      const r = await api<{ authorize_url: string; intent: string; state: string; expires_at: number }>(
        "/integrations/lab/authorize", { method: "POST", json: { locale: tx.isAr ? "ar" : "en" } });
      // Only ever leave for the configured Lab's consent page.
      const target = new URL(r.authorize_url);
      if (!LAB_LOGIN_URL || target.origin !== new URL(LAB_LOGIN_URL).origin || target.pathname !== "/connect" || target.search) throw new ApiError(503, "lab origin");
      savePending({ intent: r.intent, state: r.state, org, user, expires_at: r.expires_at });
      window.location.assign(r.authorize_url);
    } catch (e) {
      setError(friendlyError(e instanceof ApiError ? e.status : undefined, tx.isAr));
      setBusy(false);
    }
  }
  const Back = tx.isAr ? ArrowRight : ArrowLeft;

  async function connectDemo() {
    setBusy(true); setError("");
    try {
      const r = await api<{ connection: { id: string } }>("/integrations/connections", { method: "POST", json: { provider_code: "demo" } });
      setConnIds([r.connection.id]); onConnected(); go("name");
    } catch (e) { setError(friendlyError(e instanceof ApiError ? e.status : undefined, tx.isAr)); }
    finally { setBusy(false); }
  }

  function paired(result: Paired) {
    setConnIds(result.connections.map((c) => c.id)); onConnected(); go("name");
  }

  async function saveName() {
    const value = name.trim();
    if (!value) { go("test"); void runTest(); return; }
    setBusy(true); setError("");
    try {
      for (const id of connIds) await api(`/integrations/connections/${id}`, { method: "PATCH", json: { display_name: value } });
      onConnected(); go("test"); void runTest();
    } catch (e) { setError(friendlyError(e instanceof ApiError ? e.status : undefined, tx.isAr)); }
    finally { setBusy(false); }
  }

  async function runTest() {
    const rows = connIds.map((id, i) => ({ id, channel: choice === "demo" ? "pos" : i === 0 ? "first" : "second", result: null as TestResult | null }));
    setTest(rows);
    const out = [];
    for (const row of rows) {
      try { out.push({ ...row, result: await api<TestResult>(`/integrations/connections/${row.id}/test`, { method: "POST" }) }); }
      catch (e) { out.push({ ...row, error: friendlyError(e instanceof ApiError ? e.status : undefined, tx.isAr) }); }
      setTest([...out, ...rows.slice(out.length)]);
    }
  }
  const testDone = test.length > 0 && test.every((t) => t.result || t.error);
  const testOk = testDone && test.every((t) => t.result?.ok);

  const title = tx("Connect a new system", "ربط نظام جديد");
  const stepLabel = step === "done" ? "" : tx(`Step ${index + 1} of ${flow.length - 1}`, `الخطوة ${index + 1} من ${flow.length - 1}`);

  return (
    <Drawer open={open} onOpenChange={reset} title={title} subtitle={stepLabel}>
      <ol className="mb-5 flex gap-1" aria-hidden>
        {flow.slice(0, -1).map((s, i) => <li key={s} className={clsx("h-1.5 flex-1 rounded-full", i <= index ? "bg-terra" : "bg-sand")} />)}
      </ol>
      {error && <p role="alert" className="mb-4 rounded-lg bg-danger/10 p-3 text-[13px] text-danger">{error}</p>}

      {step === "type" && (
        <section aria-labelledby="w-type">
          <h3 id="w-type" className="font-serif text-[17px] text-ink">{tx("What do you want to connect?", "ما نوع النظام الذي تريد ربطه؟")}</h3>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {([["pos", ShoppingBag, tx("Point of sale (POS)", "نظام كاشير (POS)"), tx("Sales at your shop counter.", "مبيعات المحل من الكاشير.")],
               ["store", Globe, tx("Online store", "متجر إلكتروني"), tx("Orders from your website or online store.", "طلبات موقعك أو متجرك الإلكتروني.")]] as const)
              .map(([value, Icon, label, hint]) => (
                <button key={value} type="button" onClick={() => { setType(value); go("provider"); }}
                  className="flex items-start gap-3 rounded-xl border border-line bg-paper p-4 text-start transition hover:border-terra hover:bg-terra-soft/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-terra">
                  <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-terra-soft text-terra-2"><Icon size={19} /></span>
                  <span><span className="block font-medium text-ink">{label}</span><span className="mt-0.5 block text-[12.5px] text-ink-3">{hint}</span></span>
                </button>
              ))}
          </div>
        </section>
      )}

      {step === "provider" && (
        <section aria-labelledby="w-provider">
          <h3 id="w-provider" className="font-serif text-[17px] text-ink">{tx("Choose your system", "اختر نظامك")}</h3>
          <p className="mt-1 text-[13px] text-ink-3">{tx("Only systems with a working, secure integration can be connected.", "يمكن ربط الأنظمة التي لديها تكامل آمن وفعّال فقط.")}</p>
          <div className="mt-4 space-y-3">
            <ProviderOption disabled={!labAvailable} onClick={() => { setChoice("lab"); go("instructions"); }}
              title="IDRAK Connect Lab" badge={<Badge tone="saffron"><FlaskConical size={11} />{tx("Test system", "نظام اختبار")}</Badge>}
              body={type === "pos"
                ? tx("A standalone test POS for trying the integration. Links its cashier and its online store together.", "نظام كاشير اختباري مستقل لتجربة الربط. يربط الكاشير والمتجر الإلكتروني التابعين للمحل معًا.")
                : tx("The test online store of an IDRAK Connect Lab shop. Links together with that shop's cashier.", "المتجر الإلكتروني الاختباري لمحل في IDRAK Connect Lab. يُربط مع كاشير المحل نفسه.")}
              method={tx("Sign in to your POS and approve", "تسجيل الدخول إلى نظام الكاشير والموافقة")} />
            {type === "pos" && (
              <ProviderOption disabled={!demoAvailable} onClick={() => { setChoice("demo"); go("instructions"); }}
                title={tx("Demo POS", "كاشير تجريبي")} badge={<Badge tone="neutral"><Sparkles size={11} />{tx("Sample data", "بيانات وهمية")}</Badge>}
                body={tx("Adds generated sample sales so you can explore reports. Not a real system.", "يضيف مبيعات وهمية مولّدة لاستكشاف التقارير. ليس نظامًا حقيقيًا.")}
                method={tx("No authorization needed", "لا يحتاج تفويضًا")} />
            )}
            {soon.map((p) => (
              <ProviderOption key={p.code} disabled title={tx(p.name, p.name_ar || p.name)} badge={<Badge tone="neutral">{tx("Coming soon", "قريبًا")}</Badge>}
                body={tx(p.description || "", p.description_ar || p.description || "")} method={tx("Not available yet", "غير متاح بعد")} />
            ))}
          </div>
          <div className="mt-5"><Button variant="ghost" size="sm" onClick={() => go("type")}><Back size={14} />{tx("Back", "رجوع")}</Button></div>
        </section>
      )}

      {step === "instructions" && choice && (
        <section aria-labelledby="w-instr">
          <h3 id="w-instr" className="font-serif text-[17px] text-ink">{choice === "lab" ? tx("Link your shop", "ربط محلك") : tx("Before you start", "قبل أن تبدأ")}</h3>
          {choice === "lab" ? (
            <ol className="mt-4 space-y-3 text-[13.5px] text-ink-2">
              {([[LogIn, tx("Sign in to your POS", "سجّل الدخول إلى نظام الكاشير"), tx("With your POS email and password, not your IDRAK account.", "ببريدك وكلمة مرورك في نظام الكاشير، وليس حساب إدراك.")],
                 [ShieldCheck, tx("Choose your shop and approve", "اختر محلك ووافق"), tx("Only the shop owner can approve. You'll see exactly what IDRAK can read.", "الموافقة لمالك المحل فقط، وسترى بوضوح ما يستطيع إدراك قراءته.")],
                 [Undo2, tx("You'll come back here automatically", "ستعود إلى هنا تلقائيًا"), tx("Your shop then appears under your connected systems.", "ويظهر محلك ضمن أنظمتك المرتبطة.")]] as const)
                .map(([Icon, head, hint], i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-terra-soft text-terra-2"><Icon size={16} /></span>
                    <span><span className="block font-medium text-ink">{head}</span><span className="block text-[12.5px] text-ink-3">{hint}</span></span>
                  </li>
                ))}
            </ol>
          ) : (
            <p className="mt-3 text-[13.5px] text-ink-2">{tx("The demo POS creates sample sales in this business so you can see how syncing and reports work. You can disconnect it at any time; imported sample data stays.", "الكاشير التجريبي ينشئ مبيعات وهمية في هذه المؤسسة لتجربة المزامنة والتقارير. يمكنك قطع الاتصال في أي وقت مع بقاء البيانات المستوردة.")}</p>
          )}
          <p className="mt-4 rounded-lg bg-sand/60 p-3 text-[12.5px] text-ink-3">{tx("IDRAK only reads the sales data you authorize. It never asks for your POS passwords.", "إدراك يقرأ فقط بيانات المبيعات التي تأذن بها، ولا يطلب كلمات مرور نظام الكاشير.")}</p>
          <div className="mt-5 flex gap-2">
            {!initialChoice && <Button variant="ghost" size="sm" onClick={() => go("provider")} disabled={busy}><Back size={14} />{tx("Back", "رجوع")}</Button>}
            {choice === "lab"
              ? <Button onClick={continueToPos} loading={busy} disabled={busy}>{tx("Continue to your POS", "متابعة إلى نظام الكاشير")}<ExternalLink size={14} /></Button>
              : <Button onClick={() => go("authorize")}>{tx("Continue", "متابعة")}</Button>}
          </div>
          {choice === "lab" && manualPairing() && (
            <button type="button" onClick={() => go("authorize")} className="mt-4 text-[12px] text-ink-3 underline">
              {tx("Admin fallback: link with a pairing code", "بديل إداري: الربط برمز اقتران")}
            </button>
          )}
        </section>
      )}

      {step === "authorize" && choice && (
        <section aria-labelledby="w-auth">
          <h3 id="w-auth" className="font-serif text-[17px] text-ink">{choice === "lab" ? tx("Authorize with a pairing code", "التفويض برمز الاقتران") : tx("Create the demo connection", "إنشاء الاتصال التجريبي")}</h3>
          <div className="mt-4">
            {choice === "lab" ? <LabPairing onPaired={paired} /> : (
              <Button onClick={connectDemo} loading={busy} disabled={busy}>{tx("Connect demo POS", "ربط الكاشير التجريبي")}</Button>
            )}
          </div>
          {!busy && <div className="mt-5"><Button variant="ghost" size="sm" onClick={() => go("instructions")}><Back size={14} />{tx("Back", "رجوع")}</Button></div>}
        </section>
      )}

      {step === "name" && (
        <section aria-labelledby="w-name">
          <h3 id="w-name" className="flex items-center gap-2 font-serif text-[17px] text-ink"><CheckCircle2 size={18} className="text-olive" />{tx("Linked! Name this shop", "تم الربط! سمِّ هذا المحل")}</h3>
          <p className="mt-1 text-[13px] text-ink-3">{choice === "lab"
            ? tx("Your Lab shop's cashier and online store are now linked. Give the shop or branch a name you'll recognize.", "تم ربط كاشير محلك ومتجره الإلكتروني. اختر اسمًا للمحل أو الفرع تعرفه بسهولة.")
            : tx("Give this system a name you'll recognize.", "اختر اسمًا لهذا النظام تعرفه بسهولة.")}</p>
          <label htmlFor="w-name-input" className="mt-4 block text-[13px] font-medium text-ink-2">{tx("Shop or branch name", "اسم المحل أو الفرع")}</label>
          <Input id="w-name-input" className="mt-1" value={name} onChange={(e) => setName(e.target.value)} maxLength={60}
            placeholder={tx("e.g. Downtown branch", "مثال: فرع وسط البلد")} />
          <div className="mt-5 flex gap-2">
            <Button onClick={saveName} loading={busy} disabled={busy}>{tx("Save and test connection", "حفظ واختبار الاتصال")}</Button>
            <Button variant="ghost" onClick={() => { setName(""); go("test"); void runTest(); }} disabled={busy}>{tx("Skip", "تخطٍّ")}</Button>
          </div>
        </section>
      )}

      {step === "test" && (
        <section aria-labelledby="w-test">
          <h3 id="w-test" className="font-serif text-[17px] text-ink">{tx("Testing the connection", "اختبار الاتصال")}</h3>
          <ul className="mt-4 space-y-2">
            {test.map((t) => (
              <li key={t.id} className="flex items-start gap-2 rounded-lg border border-line bg-paper p-3 text-[13.5px]">
                {!t.result && !t.error ? <Loader2 size={16} className="mt-0.5 animate-spin text-terra" />
                  : t.result?.ok ? <CheckCircle2 size={16} className="mt-0.5 text-olive" /> : <XCircle size={16} className="mt-0.5 text-danger" />}
                <span>
                  <span className="font-medium text-ink">{choice === "demo" ? tx("Demo POS", "الكاشير التجريبي") : t.channel === "first" ? tx("Cashier (POS)", "الكاشير") : tx("Online store", "المتجر الإلكتروني")}</span>
                  <span className="block text-[12.5px] text-ink-3">{!t.result && !t.error ? tx("Checking…", "جارٍ الفحص…")
                    : t.result?.ok ? tx("Reachable, authorized and data reads correctly.", "متاح ومفوَّض والبيانات تُقرأ بشكل صحيح.")
                    : t.error || tx("Linked, but the check didn't pass. You can retry or sync later.", "تم الربط لكن الفحص لم ينجح. يمكنك إعادة المحاولة أو المزامنة لاحقًا.")}</span>
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-5 flex gap-2">
            <Button onClick={() => go("done")} disabled={!testDone}>{testOk ? tx("Finish", "إنهاء") : tx("Continue anyway", "متابعة على أي حال")}</Button>
            {testDone && !testOk && <Button variant="secondary" onClick={() => void runTest()}>{tx("Retry test", "إعادة الاختبار")}</Button>}
          </div>
        </section>
      )}

      {step === "done" && (
        <section aria-labelledby="w-done" className="text-center">
          <span className="mx-auto grid size-14 place-items-center rounded-full bg-olive-soft text-olive"><CheckCircle2 size={28} /></span>
          <h3 id="w-done" className="mt-4 font-serif text-[20px] text-ink">{tx("Your system is connected", "تم ربط نظامك بنجاح")}</h3>
          <p className="mx-auto mt-2 max-w-sm text-[13.5px] text-ink-3">{tx("It now appears under “Your connected systems”. Use “Sync now” to bring in the latest sales.", "يظهر الآن ضمن «أنظمتك المرتبطة». استخدم «مزامنة الآن» لجلب أحدث المبيعات.")}</p>
          <Button className="mt-5" onClick={() => reset(false)}>{tx("View my systems", "عرض أنظمتي")}</Button>
        </section>
      )}
    </Drawer>
  );
}

function ProviderOption({ title, badge, body, method, disabled, onClick }: {
  title: string; badge: React.ReactNode; body: string; method: string; disabled?: boolean; onClick?: () => void;
}) {
  const tx = useTx();
  return (
    <button type="button" disabled={disabled} onClick={onClick} aria-disabled={disabled}
      className={clsx("w-full rounded-xl border p-4 text-start transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-terra",
        disabled ? "cursor-not-allowed border-dashed border-line bg-paper-2/40 opacity-75" : "border-line bg-paper hover:border-terra hover:bg-terra-soft/40")}>
      <span className="flex flex-wrap items-center gap-2"><span className="font-medium text-ink">{title}</span>{badge}</span>
      {body && <span className="mt-1 block text-[12.5px] leading-relaxed text-ink-3">{body}</span>}
      <span className="mt-2 block text-[11.5px] text-ink-3">{tx("Connection method:", "طريقة الربط:")} {method}</span>
    </button>
  );
}
