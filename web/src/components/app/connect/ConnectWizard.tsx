"use client";

import { useState } from "react";
import clsx from "clsx";
import {
  ArrowLeft, ArrowRight, CheckCircle2, ExternalLink, FlaskConical, Globe, HelpCircle, Loader2, LogIn, ShieldCheck,
  ShoppingBag, Sparkles, Undo2, XCircle,
} from "lucide-react";
import { useTx } from "@/i18n";
import { api, ApiError, getOrgId } from "@/lib/api";
import { LAB_LOGIN_URL } from "@/lib/labUrl";
import { useSession } from "@/components/app/session";
import { Badge, Button, Input } from "@/components/ui";
import { Drawer } from "@/components/workspace/common";
import LabPairing, { type Paired } from "@/components/app/LabPairing";
import { friendlyError, PHASES, phaseOf, type Provider, type WizardStep } from "./model";
import { savePending } from "./pending";

type SystemType = "pos" | "store";
type Choice = "lab" | "demo";
type Check = { name: string; ok: boolean };
type TestResult = { ok: boolean; checks: Check[] };

// The manual pairing-code method stays as an admin fallback, reachable only with ?pairing=manual.
const manualPairing = () => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("pairing") === "manual";

export default function ConnectWizard({ open, onOpenChange, providers, labLinking, initialChoice, onConnected }: {
  open: boolean; onOpenChange: (o: boolean) => void; providers: Provider[] | undefined;
  /** The server can really link a Lab shop here (true on Staging). Demo POS never depends on it. */
  labLinking: boolean;
  initialChoice?: Choice | null; onConnected: () => void;
}) {
  const tx = useTx();
  const { session } = useSession();
  const [step, setStep] = useState<WizardStep>(initialChoice ? "connect" : "type");
  const [type, setType] = useState<SystemType>("pos");
  const [choice, setChoice] = useState<Choice | null>(initialChoice ?? null);
  const [connIds, setConnIds] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [test, setTest] = useState<{ id: string; channel: string; result: TestResult | null; error?: string }[]>([]);

  // Only systems that can really be linked here are offered. Nothing "coming soon" is selectable.
  const has = (code: string) => !!providers?.some((p) => p.code === code && p.is_implemented);
  const labAvailable = labLinking && has("lab_pos") && has("lab_web") && !!LAB_LOGIN_URL;
  const demoAvailable = has("demo");
  const options = { lab: labAvailable, demo: type === "pos" && demoAvailable };

  function reset(o: boolean) {
    if (!o) {
      setStep(initialChoice ? "connect" : "type"); setChoice(initialChoice ?? null); setConnIds([]); setName("");
      setError(""); setTest([]); setBusy(false);
    }
    onOpenChange(o);
  }
  const go = (s: WizardStep) => { setError(""); setStep(s); };
  const phase = phaseOf(step);
  const Back = tx.isAr ? ArrowRight : ArrowLeft;
  const fail = (e: unknown) => setError(friendlyError(e instanceof ApiError ? e.status : undefined, tx.isAr));

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
      window.location.assign(r.authorize_url); // busy stays on while the browser leaves
    } catch (e) { fail(e); setBusy(false); }
  }

  async function connectDemo() {
    setBusy(true); setError("");
    try {
      const r = await api<{ connection: { id: string } }>("/integrations/connections", { method: "POST", json: { provider_code: "demo" } });
      setConnIds([r.connection.id]); onConnected(); go("name");
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  function paired(result: Paired) {
    setConnIds(result.connections.map((c) => c.id)); onConnected(); go("name");
  }

  async function saveName() {
    const value = name.trim();
    setBusy(true); setError("");
    try {
      if (value) for (const id of connIds) await api(`/integrations/connections/${id}`, { method: "PATCH", json: { display_name: value } });
      onConnected(); go("test"); void runTest();
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function runTest() {
    const rows = connIds.map((id, i) => ({ id, channel: choice === "demo" || i === 0 ? "pos" : "web", result: null as TestResult | null }));
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

  const phaseNames = [tx("Type", "النوع"), tx("System", "النظام"), tx("Authorize", "التفويض"), tx("Done", "الانتهاء")];
  const stepLabel = tx(`Step ${phase + 1} of ${PHASES}: ${phaseNames[phase]}`, `الخطوة ${phase + 1} من ${PHASES}: ${phaseNames[phase]}`);

  return (
    <Drawer open={open} onOpenChange={reset} title={tx("Connect a new system", "ربط نظام جديد")} subtitle={stepLabel}>
      <ol className="mb-5 grid grid-cols-4 gap-1.5" aria-label={stepLabel}>
        {phaseNames.map((label, i) => (
          <li key={label} className="min-w-0" aria-current={i === phase ? "step" : undefined}>
            <span className={clsx("block h-1.5 rounded-full", i <= phase ? "bg-terra" : "bg-sand")} />
            <span className={clsx("mt-1 block truncate text-[11px]", i === phase ? "font-medium text-ink-2" : "text-ink-3")}>{label}</span>
          </li>
        ))}
      </ol>
      {error && <p role="alert" className="mb-4 rounded-lg bg-danger/10 p-3 text-[13px] text-danger">{error}</p>}

      {step === "type" && (
        <section aria-labelledby="w-type">
          <h3 id="w-type" className="font-serif text-[17px] text-ink">{tx("What do you want to connect?", "ما الذي تريد ربطه؟")}</h3>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {([["pos", ShoppingBag, tx("Cashier system (POS)", "نظام كاشير (POS)"), tx("Sales from your shop counter.", "مبيعات المحل من الكاشير.")],
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
          <div className="mt-4 space-y-3">
            {options.lab && (
              <ProviderOption onClick={() => { setChoice("lab"); go("connect"); }}
                title="IDRAK Connect Lab" badge={<Badge tone="saffron"><FlaskConical size={11} />{tx("Test system", "نظام اختبار")}</Badge>}
                body={tx("A practice cashier and online store for trying the connection. Not a real sales system.", "كاشير ومتجر إلكتروني للتجربة فقط، لاختبار الربط. ليس نظام مبيعات حقيقيًا.")}
                method={tx("Sign in to the test system and approve", "تسجيل الدخول إلى نظام الاختبار والموافقة")} />
            )}
            {options.demo && (
              <ProviderOption onClick={() => { setChoice("demo"); go("connect"); }}
                title={tx("Demo POS", "كاشير تجريبي")} badge={<Badge tone="neutral"><Sparkles size={11} />{tx("Sample data", "بيانات وهمية")}</Badge>}
                body={tx("Fills IDRAK with sample sales so you can explore the reports. No real system or shop is connected.", "يضيف مبيعات وهمية لتجربة التقارير في إدراك. لا يرتبط بأي نظام أو محل حقيقي.")}
                method={tx("One click, nothing to set up", "بضغطة واحدة، دون أي إعداد")} />
            )}
            {!options.lab && !options.demo && (
              <p className="rounded-xl border border-dashed border-line bg-paper-2/40 p-4 text-[13px] text-ink-2">
                {type === "store"
                  ? tx("Online stores can't be connected directly yet.", "لا يمكن ربط المتاجر الإلكترونية مباشرة بعد.")
                  : tx("No cashier system can be connected here yet.", "لا يوجد نظام كاشير يمكن ربطه هنا بعد.")}
              </p>
            )}
          </div>
          <NotListed />
          <div className="mt-5"><Button variant="ghost" size="sm" onClick={() => go("type")}><Back size={14} />{tx("Back", "رجوع")}</Button></div>
        </section>
      )}

      {step === "connect" && choice === "lab" && (
        <section aria-labelledby="w-lab">
          <h3 id="w-lab" className="font-serif text-[17px] text-ink">{tx("Link your shop", "ربط محلك")}</h3>
          <p className="mt-1 text-[13px] text-ink-3">{tx("You'll finish this step in your cashier system:", "ستكمل هذه الخطوة في نظام الكاشير:")}</p>
          <ol className="mt-4 space-y-3 text-[13.5px] text-ink-2">
            {([[LogIn, tx("Sign in to your cashier system", "سجّل الدخول إلى نظام الكاشير"), tx("Use your cashier system email and password, not your IDRAK account.", "ببريدك وكلمة مرورك في نظام الكاشير، وليس حساب إدراك.")],
               [ShieldCheck, tx("Choose your shop and approve", "اختر محلك ووافق"), tx("Only the shop owner can approve. You'll see what IDRAK can read.", "الموافقة لمالك المحل فقط، وسترى ما يستطيع إدراك قراءته.")],
               [Undo2, tx("You'll come back here automatically", "ستعود إلى هنا تلقائيًا"), tx("Your shop then appears in your systems.", "ثم يظهر محلك ضمن أنظمتك.")]] as const)
              .map(([Icon, head, hint], i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-terra-soft text-terra-2"><Icon size={16} /></span>
                  <span><span className="block font-medium text-ink">{head}</span><span className="block text-[12.5px] text-ink-3">{hint}</span></span>
                </li>
              ))}
          </ol>
          <p className="mt-4 rounded-lg bg-sand/60 p-3 text-[12.5px] text-ink-3">{tx("IDRAK only reads the sales you allow. It never sees your cashier system password.", "إدراك يقرأ فقط المبيعات التي تسمح بها، ولا يرى كلمة مرور نظام الكاشير.")}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            {!initialChoice && <Button variant="ghost" size="sm" onClick={() => go("provider")} disabled={busy}><Back size={14} />{tx("Back", "رجوع")}</Button>}
            <Button onClick={continueToPos} loading={busy} disabled={busy}>{busy ? tx("Opening your cashier system…", "جارٍ فتح نظام الكاشير…") : tx("Continue to your cashier system", "متابعة إلى نظام الكاشير")}{!busy && <ExternalLink size={14} />}</Button>
          </div>
          {manualPairing() && (
            <button type="button" onClick={() => go("authorize")} className="mt-4 text-[12px] text-ink-3 underline">
              {tx("Admin fallback: link with a pairing code", "بديل إداري: الربط برمز اقتران")}
            </button>
          )}
        </section>
      )}

      {step === "connect" && choice === "demo" && (
        <section aria-labelledby="w-demo">
          <h3 id="w-demo" className="font-serif text-[17px] text-ink">{tx("Add the demo POS", "إضافة الكاشير التجريبي")}</h3>
          <p className="mt-3 text-[13.5px] text-ink-2">{tx("IDRAK will add sample sales to this business so you can see how syncing and reports work. You can disconnect it at any time; the sample sales stay.", "سيضيف إدراك مبيعات وهمية إلى هذه المؤسسة لترى كيف تعمل المزامنة والتقارير. يمكنك قطع الاتصال في أي وقت، وتبقى المبيعات الوهمية.")}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            {!initialChoice && <Button variant="ghost" size="sm" onClick={() => go("provider")} disabled={busy}><Back size={14} />{tx("Back", "رجوع")}</Button>}
            <Button onClick={connectDemo} loading={busy} disabled={busy}>{tx("Add demo POS", "إضافة الكاشير التجريبي")}</Button>
          </div>
        </section>
      )}

      {step === "authorize" && (
        <section aria-labelledby="w-auth">
          <h3 id="w-auth" className="font-serif text-[17px] text-ink">{tx("Link with a pairing code (admin)", "الربط برمز اقتران (للمسؤول)")}</h3>
          <div className="mt-4"><LabPairing onPaired={paired} /></div>
          <div className="mt-5"><Button variant="ghost" size="sm" onClick={() => go("connect")}><Back size={14} />{tx("Back", "رجوع")}</Button></div>
        </section>
      )}

      {step === "name" && (
        <section aria-labelledby="w-name">
          <h3 id="w-name" className="flex items-center gap-2 font-serif text-[17px] text-ink"><CheckCircle2 size={18} className="text-olive" />{tx("Connected! Give it a name", "تم الربط! اختر اسمًا")}</h3>
          <p className="mt-1 text-[13px] text-ink-3">{tx("A name you'll recognize in your systems list. You can change it later.", "اسم تعرفه بسهولة في قائمة أنظمتك. يمكنك تغييره لاحقًا.")}</p>
          <label htmlFor="w-name-input" className="mt-4 block text-[13px] font-medium text-ink-2">{tx("Name", "الاسم")}</label>
          <Input id="w-name-input" className="mt-1" value={name} onChange={(e) => setName(e.target.value)} maxLength={60}
            placeholder={choice === "demo" ? tx("e.g. Demo POS", "مثال: الكاشير التجريبي") : tx("e.g. Downtown branch", "مثال: فرع وسط البلد")} />
          <div className="mt-5 flex flex-wrap gap-2">
            <Button onClick={saveName} loading={busy} disabled={busy}>{name.trim() ? tx("Save and check connection", "حفظ وفحص الاتصال") : tx("Skip and check connection", "تخطٍّ وفحص الاتصال")}</Button>
          </div>
        </section>
      )}

      {step === "test" && (
        <section aria-labelledby="w-test">
          <h3 id="w-test" className="font-serif text-[17px] text-ink">{tx("Checking the connection", "فحص الاتصال")}</h3>
          <ul className="mt-4 space-y-2">
            {test.map((t) => (
              <li key={t.id} className="flex items-start gap-2 rounded-lg border border-line bg-paper p-3 text-[13.5px]">
                {!t.result && !t.error ? <Loader2 size={16} className="mt-0.5 animate-spin text-terra" />
                  : t.result?.ok ? <CheckCircle2 size={16} className="mt-0.5 text-olive" /> : <XCircle size={16} className="mt-0.5 text-danger" />}
                <span>
                  <span className="font-medium text-ink">{choice === "demo" ? tx("Demo POS", "الكاشير التجريبي") : t.channel === "pos" ? tx("Cashier", "الكاشير") : tx("Online store", "المتجر الإلكتروني")}</span>
                  <span className="block text-[12.5px] text-ink-3">{!t.result && !t.error ? tx("Checking…", "جارٍ الفحص…")
                    : t.result?.ok ? tx("Working: sales can be read.", "يعمل: يمكن قراءة المبيعات.")
                    : t.error || tx("Connected, but the check didn't pass. Try again in a moment.", "تم الربط لكن الفحص لم ينجح. أعد المحاولة بعد قليل.")}</span>
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button onClick={() => go("done")} disabled={!testDone}>{testOk ? tx("Finish", "إنهاء") : tx("Finish anyway", "إنهاء على أي حال")}</Button>
            {testDone && !testOk && <Button variant="secondary" onClick={() => void runTest()}>{tx("Check again", "إعادة الفحص")}</Button>}
          </div>
        </section>
      )}

      {step === "done" && (
        <section aria-labelledby="w-done" className="text-center">
          <span className="mx-auto grid size-14 place-items-center rounded-full bg-olive-soft text-olive"><CheckCircle2 size={28} /></span>
          <h3 id="w-done" className="mt-4 font-serif text-[20px] text-ink">{tx("Connected", "تم الربط بنجاح")}</h3>
          <p className="mx-auto mt-2 max-w-sm text-[13.5px] text-ink-3">{tx("It now appears in your systems. Press “Sync now” to bring in the latest sales.", "يظهر الآن ضمن أنظمتك. اضغط «مزامنة الآن» لجلب أحدث المبيعات.")}</p>
          <Button className="mt-5" onClick={() => reset(false)}>{tx("View my systems", "عرض أنظمتي")}</Button>
        </section>
      )}
    </Drawer>
  );
}

/** Honest answer for systems we can't connect yet: no fake form, no fake connector. */
function NotListed() {
  const tx = useTx();
  return (
    <details className="mt-5 rounded-xl border border-line bg-paper-2/40 p-3">
      <summary className="flex cursor-pointer items-center gap-2 text-[13px] font-medium text-ink-2"><HelpCircle size={15} />{tx("Your system isn't listed?", "نظامك غير موجود؟")}</summary>
      <div className="mt-2 space-y-2 text-[12.5px] leading-relaxed text-ink-3">
        <p>{tx("We add systems one at a time, and only list a system once its connection is ready and tested.", "نضيف الأنظمة تدريجيًا، ولا نعرض أي نظام قبل أن يكون ربطه جاهزًا ومختبرًا.")}</p>
        <p>{tx("Tell us which system you use, and meanwhile upload your sales as an Excel or CSV file.", "أخبرنا باسم النظام الذي تستخدمه، وإلى ذلك الحين يمكنك رفع مبيعاتك بملف Excel أو CSV.")}</p>
        <div className="flex flex-wrap gap-2 pt-1">
          <Button href={`/${tx.locale}/contact`} variant="secondary" size="sm">{tx("Contact us", "تواصل معنا")}</Button>
          <Button href={`/${tx.locale}/app/data`} variant="ghost" size="sm">{tx("Upload a sales file", "رفع ملف المبيعات")}</Button>
        </div>
      </div>
    </details>
  );
}

function ProviderOption({ title, badge, body, method, onClick }: {
  title: string; badge: React.ReactNode; body: string; method: string; onClick: () => void;
}) {
  const tx = useTx();
  return (
    <button type="button" onClick={onClick}
      className="w-full rounded-xl border border-line bg-paper p-4 text-start transition hover:border-terra hover:bg-terra-soft/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-terra">
      <span className="flex flex-wrap items-center gap-2"><span className="font-medium text-ink">{title}</span>{badge}</span>
      <span className="mt-1 block text-[12.5px] leading-relaxed text-ink-3">{body}</span>
      <span className="mt-2 block text-[11.5px] text-ink-3">{tx("How it connects:", "طريقة الربط:")} {method}</span>
    </button>
  );
}
