"use client";
import { Suspense, useState } from "react";
import clsx from "clsx";
import { CheckCircle2, ChevronDown, Info, XCircle } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { num } from "@/lib/format";
import { AskIdrak, ErrorBox, Money, N, PageHeader, Section, Table, type Col } from "@/components/app/kit";
import { useSession } from "@/components/app/session";
import { Button, Card, Empty, Skeleton, Tabs } from "@/components/ui";
import { PageSkeleton, RoleNotice, SeverityBadge, oneOf, useParamState } from "@/components/insights/common";
import type { Compliance, ComplianceIssue } from "@/components/insights/types";

const WINDOWS = ["30", "90", "180"] as const;

const FIX: Record<string, { en: string; ar: string }> = {
  no_tax_number: { en: "Add your sales-tax number in Settings so it prints on every invoice.", ar: "ضيف الرقم الضريبي من الإعدادات عشان ينطبع على كل فاتورة." },
  tax_mismatch: { en: "Check the tax rate on these items in the POS (most goods are 16%, some basics are reduced or exempt) and re-issue the invoices.", ar: "راجع نسبة الضريبة على هالأصناف بنظام الكاشير (أغلب السلع 16%، وبعض الأساسيات مخفّضة أو معفاة) وأعد إصدار الفواتير." },
  duplicate_numbers: { en: "Each invoice number must be used once. Fix the POS counter so two tills can't issue the same number.", ar: "كل رقم فاتورة لازم ينستعمل مرة وحدة. ظبّط عدّاد الكاشير عشان ما يطلع نفس الرقم من جهازين." },
  sequence_gaps: { en: "Numbers should run without gaps. Document why numbers were skipped or jumped (e.g. a till reset) and keep the note.", ar: "الأرقام لازم تمشي بدون فجوات. وثّق ليش انقفزت أرقام (مثلاً إعادة ضبط الجهاز) واحتفظ بالملاحظة." },
  voids: { en: "Record a reason and approver for every voided invoice.", ar: "سجّل سبب ومين وافق على كل فاتورة ملغية." },
};

export default function CompliancePage() {
  return <Suspense fallback={<PageSkeleton />}><Gate /></Suspense>;
}

function Gate() {
  const { can, loading, org } = useSession();
  if (loading || !org) return <PageSkeleton />;
  if (!can("accountant")) return <RoleNotice min="accountant" />;
  return <ComplianceScreen />;
}

function ComplianceScreen() {
  const tx = useTx();
  const locale = useLocale();
  const [dRaw, setDays] = useParamState("days", "90");
  const days = oneOf(dRaw, WINDOWS, "90");
  const q = useApiQuery<Compliance>(`/compliance?days=${days}`);
  const d = q.data;
  const tone = !d ? "ink" : d.score >= 85 ? "olive" : d.score >= 60 ? "saffron" : "danger";

  return (
    <div>
      <PageHeader
        eyebrow={tx("E-invoice readiness", "جاهزية الفوترة الإلكترونية")}
        title={tx("Are your invoices ready for JoFotara?", "فواتيرك جاهزة للفوترة الوطنية؟")}
        subtitle={tx("We scan your sales invoices for the problems that usually block e-invoicing: missing tax number, wrong tax, duplicate or skipped numbers.",
          "بنفحص فواتير المبيعات عن المشاكل اللي عادةً بتعطّل الفوترة الإلكترونية: رقم ضريبي ناقص، ضريبة غلط، أرقام مكررة أو مقفوزة.")}
        actions={<>
          <Tabs value={days} onChange={(v) => setDays(v)} items={WINDOWS.map((w) => ({ value: w, label: tx(`${w} days`, `${w} يوم`) }))} />
          <AskIdrak q={tx("What do I need to fix first to be ready for Jordan's national e-invoicing system?", "شو لازم أصلّح أول عشان أكون جاهز لنظام الفوترة الوطني بالأردن؟")} />
        </>}
      />

      <Card className="mb-5 flex gap-3 border-sky/30 bg-[#dce8eb]/40 px-4 py-3 text-[12.5px] leading-relaxed text-ink-2 shadow-none">
        <Info size={16} className="mt-0.5 shrink-0 text-sky" />
        <p>{tx("This is a readiness aid based on public guidance about Jordan's national e-invoicing system. It is not an official validation by the Income and Sales Tax Department (ISTD) — confirm with your accountant or ISTD before relying on it.",
          "هاد فحص مساعد للجاهزية مبني على الإرشادات المنشورة عن نظام الفوترة الوطني بالأردن. مش تحقق رسمي من دائرة ضريبة الدخل والمبيعات — تأكد مع محاسبك أو مع الدائرة قبل ما تعتمد عليه.")}</p>
      </Card>

      {q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : (
        <>
          <div className="grid gap-5 lg:grid-cols-3">
            <Card data-basira="compliance-score" className="p-6">
              <p className="text-[13px] text-ink-3">{tx("Readiness score", "علامة الجاهزية")}</p>
              {!d ? <Skeleton className="mt-3 h-14 w-32" /> : (<>
                <p className={clsx("mt-2 font-serif text-[56px] leading-none", tone === "olive" ? "text-olive" : tone === "saffron" ? "text-[#8a5d0e]" : "text-danger")}>
                  <span className="num">{num(d.score)}</span><span className="text-[22px] text-ink-3">/100</span>
                </p>
                <div className="mt-4 h-2.5 w-full overflow-hidden rounded-full bg-sand">
                  <div className={clsx("h-full rounded-full", tone === "olive" ? "bg-olive" : tone === "saffron" ? "bg-saffron" : "bg-danger")} style={{ width: `${d.score}%` }} />
                </div>
                <p className="mt-3 text-[13px] text-ink-2">
                  {d.score >= 85 ? tx("Looking good — fix the remaining items and you're set.", "ماشي منيح — صلّح اللي باقي وبتكون جاهز.")
                    : d.score >= 60 ? tx("A few problems to fix before going live.", "في كم مشكلة لازم تتصلّح قبل التشغيل.") : tx("Several blocking problems — start with the red ones.", "في مشاكل كثيرة بتعطّل — ابدأ بالأحمر.")}
                </p>
                <dl className="mt-4 space-y-1.5 border-t border-line/70 pt-3 text-[12.5px]">
                  <div className="flex justify-between"><dt className="text-ink-3">{tx("Invoices checked", "فواتير انفحصت")}</dt><dd><N v={d.invoices_checked} /></dd></div>
                  <div className="flex justify-between"><dt className="text-ink-3">{tx("Period", "الفترة")}</dt><dd>{tx(`last ${d.days} days`, `آخر ${d.days} يوم`)}</dd></div>
                  <div className="flex justify-between"><dt className="text-ink-3">{tx("Tax number", "الرقم الضريبي")}</dt>
                    <dd className={clsx("num", !d.tax_number && "text-danger")}>{d.tax_number || tx("missing", "ناقص")}</dd></div>
                </dl>
              </>)}
            </Card>

            <Section id="compliance-checklist" className="lg:col-span-2" title={tx("Checklist", "قائمة التحقق")} subtitle={tx("What e-invoicing generally expects from every seller", "شو بيتطلب نظام الفوترة عادةً من كل بائع")}>
              {!d ? <div className="space-y-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-6 w-full" />)}</div> : (
                <ul className="divide-y divide-line/60">
                  {d.checklist.map((c) => (
                    <li key={c.en} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
                      {c.ok ? <CheckCircle2 size={18} className="shrink-0 text-olive" /> : <XCircle size={18} className="shrink-0 text-danger" />}
                      <span className={clsx("text-[14px]", c.ok ? "text-ink-2" : "font-medium text-ink")}>{tx(c.en, c.ar)}</span>
                      <span className={clsx("ms-auto text-[12px]", c.ok ? "text-olive" : "text-danger")}>{c.ok ? tx("Done", "تمام") : tx("Needs work", "بده شغل")}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>

          <div data-basira="compliance-issues" className="mt-5 space-y-4">
            <h2 className="font-serif text-[20px] text-ink">{tx("Problems found", "المشاكل اللي لقيناها")}</h2>
            {!d ? <Card className="p-5"><Skeleton className="h-5 w-64" /><Skeleton className="mt-3 h-4 w-full" /></Card> :
              !d.issues.length ? <Card><Empty icon={<CheckCircle2 size={22} className="text-olive" />} title={tx("No problems found", "ما لقينا مشاكل")} body={tx(`All ${num(d.invoices_checked)} invoices passed the checks.`, `كل الـ ${num(d.invoices_checked)} فاتورة نجحت بالفحص.`)} /></Card> :
                d.issues.map((i) => <IssueCard key={i.key} i={i} locale={locale} />)}
          </div>
        </>
      )}
    </div>
  );
}

function IssueCard({ i, locale }: { i: ComplianceIssue; locale: "ar" | "en" }) {
  const tx = useTx();
  const [open, setOpen] = useState(false);
  const fix = FIX[i.key];
  const items = (i.items || []) as Record<string, unknown>[];
  const s = (v: unknown) => (v === null || v === undefined ? "—" : String(v));
  const n = (v: unknown) => (typeof v === "number" ? v : null);
  let cols: Col<Record<string, unknown>>[] = [];
  if (i.key === "tax_mismatch") cols = [
    { key: "invoice", label: tx("Invoice", "الفاتورة"), render: (r) => <span className="num text-ink" dir="ltr">{s(r.invoice)}</span> },
    { key: "branch", label: tx("Branch", "الفرع"), render: (r) => <span className="text-ink-2">{s(r.branch)}</span> },
    { key: "total", label: tx("Total", "المجموع"), align: "end", render: (r) => <Money v={n(r.total)} /> },
    { key: "tax", label: tx("Tax charged", "الضريبة المحسوبة"), align: "end", render: (r) => <Money v={n(r.tax)} className="text-danger" /> },
    { key: "expected", label: tx("Expected", "المفروض"), align: "end", render: (r) => <Money v={n(r.expected)} /> },
  ];
  else if (i.key === "duplicate_numbers") cols = [
    { key: "invoice", label: tx("Invoice number", "رقم الفاتورة"), render: (r) => <span className="num text-ink" dir="ltr">{s(r.invoice)}</span> },
    { key: "branch", label: tx("Branch", "الفرع"), render: (r) => <span className="text-ink-2">{s(r.branch)}</span> },
    { key: "times", label: tx("Used", "انستعمل"), align: "end", render: (r) => <span className="num">{s(r.times)}×</span> },
  ];
  else if (i.key === "sequence_gaps") cols = [
    { key: "branch", label: tx("Branch", "الفرع"), render: (r) => <span className="text-ink">{s(r.branch)}</span> },
    { key: "prefix", label: tx("Series", "السلسلة"), render: (r) => <span className="num text-ink-2" dir="ltr">{s(r.prefix)}</span> },
    { key: "kind", label: tx("Problem", "المشكلة"), render: (r) => (n(r.out_of_sequence)
      ? <span>{tx(`${s(r.out_of_sequence)} numbers jump far out of sequence`, `${s(r.out_of_sequence)} أرقام قافزة بعيد عن التسلسل`)}</span>
      : <span>{tx(`${s(r.missing)} numbers missing`, `${s(r.missing)} أرقام ناقصة`)}</span>) },
    { key: "examples", label: tx("Examples", "أمثلة"), render: (r) => <span className="num text-[12px] text-ink-3" dir="ltr">{Array.isArray(r.examples) ? r.examples.join(", ") : "—"}</span> },
  ];
  else if (items.length) cols = Object.keys(items[0]).map((k) => ({ key: k, label: k, render: (r: Record<string, unknown>) => <span className="num">{s(r[k])}</span> }));

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-3 p-5 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><SeverityBadge s={i.severity} /></div>
          <h3 className="mt-1.5 font-serif text-[17.5px] text-ink">{tx(i.en, i.ar)}</h3>
          {fix && <p className="mt-1.5 text-[13px] text-ink-2"><span className="font-medium text-olive">{tx("How to fix: ", "كيف تصلّحها: ")}</span>{tx(fix.en, fix.ar)}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-3 sm:flex-col sm:items-end">
          <p className="sm:text-end"><span className="num font-serif text-[26px] leading-none text-ink">{num(i.count)}</span>
            <span className="ms-1 text-[12px] text-ink-3">{i.key === "no_tax_number" ? "" : tx("cases", "حالة")}</span></p>
          {i.link && <Button size="sm" variant="secondary" href={`/${locale}${i.link}`}>{tx("Fix it", "صلّحها")}</Button>}
        </div>
      </div>
      {!!items.length && (
        <div className="border-t border-line/70">
          <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-center justify-between px-5 py-2.5 text-[13px] text-ink-2 hover:bg-paper-2">
            <span>{open ? tx("Hide invoices", "خبّي الفواتير") : tx(`Show ${items.length} examples`, `اعرض ${items.length} أمثلة`)}</span>
            <ChevronDown size={15} className={clsx("transition-transform", open && "rotate-180")} />
          </button>
          {open && <div className="border-t border-line/60"><Table dense rows={items} cols={cols} rowKey={(_r, k) => String(k)} /></div>}
        </div>
      )}
    </Card>
  );
}
