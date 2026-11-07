"use client";
import { Suspense } from "react";
import clsx from "clsx";
import { Mail, Printer } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { useApiMutation, useApiQuery } from "@/lib/useApi";
import { date, jd, num, pct } from "@/lib/format";
import { toast } from "@/components/ui/toast";
import { AskIdrak, Delta, ErrorBox, Money, PageHeader, useName } from "@/components/app/kit";
import { useSession } from "@/components/app/session";
import { Button, Card, Skeleton, Tabs } from "@/components/ui";
import { PageSkeleton, oneOf, useParamState } from "@/components/insights/common";
import SalesTrendChart from "@/components/insights/SalesTrendChart";
import type { EmailResult, Summary } from "@/components/insights/types";

const PERIODS = ["7", "30"] as const;
const PRINT_CSS = `@page { size: A4; margin: 12mm; }
@media print {
  html, body { background: #fff !important; }
  main { padding: 0 !important; }
  .report-sheet { border: 0 !important; box-shadow: none !important; padding: 0 !important; }
  .report-block { break-inside: avoid; page-break-inside: avoid; }
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}`;

export default function ReportsPage() {
  return <Suspense fallback={<PageSkeleton />}><ReportsScreen /></Suspense>;
}

function ReportsScreen() {
  const tx = useTx();
  const locale = useLocale();
  const { me } = useSession();
  const [pRaw, setPeriod] = useParamState("days", "7");
  const days = oneOf(pRaw, PERIODS, "7");
  const q = useApiQuery<Summary>(`/reports/summary?days=${days}`);
  const digest = useApiMutation<undefined, { ok: boolean; email: EmailResult }>("POST", `/reports/digest?locale=${locale}`, {
    errorTitle: tx("Couldn't send the digest", "ما قدرنا نبعث الملخص"),
    onSuccess: (r) => {
      if (r.ok) toast(tx("Weekly digest sent", "انبعت الملخص الأسبوعي"), tx(`Delivered to ${r.email?.delivered_to?.join(", ") || me?.email || ""}`, `وصل على ${r.email?.delivered_to?.join(", ") || me?.email || ""}`));
      else toast(tx("Digest prepared, but the email didn't go out", "الملخص جاهز، بس الإيميل ما انبعت"), r.email?.error || "", "info");
    },
  });

  return (
    <div>
      <style>{PRINT_CSS}</style>
      <div className="no-print">
        <PageHeader
          eyebrow={tx("Reports", "التقارير")}
          title={tx("Your business on one page", "شغلك بصفحة وحدة")}
          subtitle={tx("A printable summary for partners, your accountant or the bank — and a weekly digest straight to your inbox.",
            "ملخص جاهز للطباعة للشركاء أو المحاسب أو البنك — وملخص أسبوعي بيوصلك عالإيميل.")}
          actions={<>
            <div data-basira="report-period">
              <Tabs value={days} onChange={(v) => setPeriod(v)} items={[{ value: "7", label: tx("Last 7 days", "آخر 7 أيام") }, { value: "30", label: tx("Last 30 days", "آخر 30 يوم") }]} />
            </div>
            <Button data-basira="print-button" variant="secondary" onClick={() => window.print()} disabled={!q.data}><Printer size={15} />{tx("Print / PDF", "اطبع / PDF")}</Button>
            <Button data-basira="digest-button" loading={digest.isPending} onClick={() => digest.mutate(undefined)}
              title={tx(`Sends this week's digest to ${me?.email || "your email"}`, `بيبعت ملخص الأسبوع على ${me?.email || "إيميلك"}`)}>
              <Mail size={15} />{tx("Email me the weekly digest", "ابعتلي الملخص الأسبوعي")}
            </Button>
            <AskIdrak q={tx("Write a short paragraph summarising this week for my business partner.", "اكتبلي فقرة قصيرة بتلخص هالأسبوع لشريكي بالشغل.")} />
          </>}
        />
      </div>
      {q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : !q.data ? (
        <Card className="p-8"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-24 w-full" /><Skeleton className="mt-6 h-64 w-full" /></Card>
      ) : <Sheet s={q.data} />}
    </div>
  );
}

function Sheet({ s }: { s: Summary }) {
  const tx = useTx();
  const locale = useLocale();
  const nm = useName();
  const d = s.dashboard;
  const k = d.kpis;
  const orgName = nm(s.org.name, s.org.name_ar);
  const best = d.branches[0];
  const monthlyLeak = s.leaks.filter((l) => !["dead_stock", "expiring"].includes(l.kind)).reduce((a, l) => a + (l.amount_jod || 0), 0);
  const kpis: { label: string; v: React.ReactNode; dl?: number | null }[] = [
    { label: tx("Revenue", "المبيعات"), v: <Money v={k.revenue} decimals={0} />, dl: d.deltas.revenue },
    { label: tx("Gross profit", "الربح الإجمالي"), v: <Money v={k.profit} decimals={0} />, dl: d.deltas.profit },
    { label: tx("Margin", "الهامش"), v: <span className="num">{pct(k.margin)}</span>, dl: d.deltas.margin },
    { label: tx("Avg basket", "متوسط السلة"), v: <Money v={k.basket} decimals={3} />, dl: d.deltas.basket },
    { label: tx("Receipts", "الفواتير"), v: <span className="num">{num(k.tx)}</span>, dl: d.deltas.tx },
  ];

  return (
    <article className="report-sheet rounded-[var(--radius-card)] border border-line bg-[#FFFCF7] p-6 shadow-[var(--shadow-paper)] sm:p-10">
      <header className="report-block flex flex-wrap items-end justify-between gap-4 border-b-2 border-ink pb-5">
        <div>
          <p className="text-[12px] font-medium uppercase tracking-[.14em] text-terra">{s.period_days === 7 ? tx("Weekly business report", "التقرير الأسبوعي") : tx("Monthly business report", "التقرير الشهري")}</p>
          <h2 className="mt-1 font-serif text-[30px] leading-tight text-ink">{orgName}</h2>
          <p className="mt-1 text-[13px] text-ink-2">
            <span className="num">{date(d.range.start, locale)} – {date(d.range.end, locale)}</span>
            {s.org.city && <> · {s.org.city}</>}
            {s.org.tax_number && <> · {tx("Tax no.", "الرقم الضريبي")} <span className="num">{s.org.tax_number}</span></>}
          </p>
        </div>
        <p className="text-[12px] text-ink-3">{tx("Prepared by Idrak on", "أعدّه إدراك بتاريخ")} <span className="num">{date(new Date(), locale)}</span></p>
      </header>

      <section className="report-block mt-6">
        <p className="max-w-3xl text-[15px] leading-relaxed text-ink">
          {tx(`Revenue was ${jd(k.revenue, locale, { decimals: 0 })}`, `المبيعات كانت ${jd(k.revenue, locale, { decimals: 0 })}`)}
          {d.deltas.revenue !== null && d.deltas.revenue !== undefined && tx(` (${d.deltas.revenue >= 0 ? "up" : "down"} ${num(Math.abs(d.deltas.revenue), 1)}% on the previous ${s.period_days} days)`,
            ` (${d.deltas.revenue >= 0 ? "أعلى" : "أقل"} بـ ${num(Math.abs(d.deltas.revenue), 1)}% من الـ ${s.period_days} يوم اللي قبل)`)}
          {tx(` with a gross profit of ${jd(k.profit, locale, { decimals: 0 })}.`, ` بربح إجمالي ${jd(k.profit, locale, { decimals: 0 })}.`)}
          {best && tx(` ${best.name} was the strongest branch.`, ` أقوى فرع كان ${nm(best.name, best.name_ar)}.`)}
          {monthlyLeak > 0 && tx(` We estimate about ${jd(monthlyLeak, locale, { decimals: 0 })} a month is leaking — details below.`, ` منقدّر إنه في حوالي ${jd(monthlyLeak, locale, { decimals: 0 })} بالشهر عم تتسرّب — التفاصيل تحت.`)}
        </p>
      </section>

      <section className="report-block mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-5">
        {kpis.map((x) => (
          <div key={x.label} className="bg-[#FFFCF7] px-4 py-3">
            <p className="text-[11.5px] text-ink-3">{x.label}</p>
            <p className="mt-1 font-serif text-[21px] leading-none text-ink">{x.v}</p>
            <div className="mt-1"><Delta v={x.dl} /></div>
          </div>
        ))}
      </section>

      <section className="report-block mt-8">
        <H>{tx("Daily sales and profit", "المبيعات والربح اليومي")}</H>
        {d.series.length ? <SalesTrendChart series={d.series} height={220} animation={false} /> : <p className="text-sm text-ink-3">—</p>}
      </section>

      <div className="mt-8 grid gap-8 md:grid-cols-2">
        <section className="report-block">
          <H>{tx("Best sellers", "الأكثر مبيعاً")}</H>
          <SimpleTable head={[tx("Product", "الصنف"), tx("Units", "الكمية"), tx("Revenue", "المبيعات")]}
            rows={d.top_products.slice(0, 8).map((p) => [nm(p.name, p.name_ar), <span key="q" className="num">{num(p.qty)}</span>, <Money key="r" v={p.revenue} decimals={0} />])} />
        </section>
        <section className="report-block">
          <H>{tx("Branches", "الفروع")}</H>
          <SimpleTable head={[tx("Branch", "الفرع"), tx("Revenue", "المبيعات"), tx("Growth", "النمو"), tx("Basket", "السلة")]}
            rows={d.branches.map((b) => [nm(b.name, b.name_ar), <Money key="r" v={b.revenue} decimals={0} />, <Delta key="g" v={b.growth} />, <Money key="b" v={b.basket} decimals={3} />])} />
          {!!d.goals.length && (
            <div className="mt-4 space-y-2.5">
              <p className="text-[12px] font-medium text-ink-3">{tx("Monthly goals — projected at current pace", "أهداف الشهر — المتوقع على الوتيرة الحالية")}</p>
              {d.goals.map((g) => {
                const p = g.target ? (100 * g.pace) / g.target : 0;
                return (
                  <div key={g.branch_id} className="text-[12.5px]">
                    <div className="flex justify-between"><span className="text-ink">{nm(g.name, g.name_ar)}</span><span className={clsx("num", p >= 100 ? "text-olive" : "text-[#8a5d0e]")}>{num(p)}%</span></div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-sand"><div className={clsx("h-full rounded-full", p >= 100 ? "bg-olive" : "bg-saffron")} style={{ width: `${Math.min(100, p)}%` }} /></div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      <section className="report-block mt-8">
        <H>{tx("Where money is leaking", "وين عم تتسرّب المصاري")}</H>
        {s.leaks.length ? (
          <ol className="divide-y divide-line/70 border-y border-line/70">
            {s.leaks.map((l, i) => (
              <li key={i} className="flex items-start gap-4 py-3">
                <span className="num w-5 shrink-0 font-serif text-[16px] text-terra">{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13.5px] font-medium text-ink">{tx(l.title, l.title_ar)}</span>
                  <span className="mt-0.5 block text-[12.5px] text-ink-2">{tx(l.body, l.body_ar)}</span>
                </span>
                <span className="shrink-0 text-end">
                  <Money v={l.amount_jod} decimals={0} className="text-[14px] font-medium text-ink" />
                  <span className="block text-[11px] text-ink-3">{["dead_stock", "expiring"].includes(l.kind) ? tx("tied up", "عالقة") : tx("/ month", "بالشهر")}</span>
                </span>
              </li>
            ))}
          </ol>
        ) : <p className="text-sm text-ink-3">{tx("No leaks found.", "ما في تسريب.")}</p>}
      </section>

      <div className="mt-8 grid gap-8 md:grid-cols-2">
        <section className="report-block">
          <H>{tx("To order", "للطلب")}</H>
          <p className="mb-3 text-[13px] text-ink-2">
            {tx(`${s.reorder.lines} items (${s.reorder.critical} critical) worth ${jd(s.reorder.total, locale, { decimals: 0 })} at cost.`,
              `${s.reorder.lines} صنف (${s.reorder.critical} عاجل) بقيمة ${jd(s.reorder.total, locale, { decimals: 0 })} بسعر التكلفة.`)}
          </p>
          <SimpleTable head={[tx("Supplier", "المورد"), tx("Items", "الأصناف"), tx("Amount", "المبلغ")]}
            rows={s.reorder.suppliers.map((x) => [nm(x.supplier, x.supplier_ar), <span key="l" className="num">{x.lines}</span>, <Money key="t" v={x.total} decimals={0} />])} />
        </section>
        <section className="report-block">
          <H>{tx("E-invoice readiness", "جاهزية الفوترة الإلكترونية")}</H>
          <p className="flex items-baseline gap-2"><span className={clsx("num font-serif text-[34px] leading-none", s.compliance.score >= 85 ? "text-olive" : s.compliance.score >= 60 ? "text-[#8a5d0e]" : "text-danger")}>{num(s.compliance.score)}</span>
            <span className="text-[13px] text-ink-3">/100</span></p>
          {s.compliance.issues.length ? (
            <ul className="mt-3 space-y-1.5 text-[13px]">
              {s.compliance.issues.map((i) => <li key={i.en} className="flex justify-between gap-3"><span className="text-ink-2">{tx(i.en, i.ar)}</span><span className="num text-ink">{num(i.count)}</span></li>)}
            </ul>
          ) : <p className="mt-3 text-[13px] text-olive">{tx("No issues found.", "ما في مشاكل.")}</p>}
          <p className="mt-3 text-[11px] text-ink-3">{tx("Readiness aid only — not an official ISTD validation.", "فحص مساعد فقط — مش تحقق رسمي من دائرة الضريبة.")}</p>
        </section>
      </div>

      <footer className="mt-10 border-t border-line pt-4 text-[11.5px] text-ink-3">
        {tx("Figures in Jordanian dinars. Profit is gross (sales minus cost of goods). Leak amounts are estimates.", "الأرقام بالدينار الأردني. الربح إجمالي (المبيعات ناقص تكلفة البضاعة). أرقام التسريب تقديرية.")}
        <span className="float-end">Idrak · إدراك</span>
      </footer>
    </article>
  );
}

function H({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-3 font-serif text-[17px] text-ink">{children}</h3>;
}

function SimpleTable({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) {
  if (!rows.length) return <p className="text-sm text-ink-3">—</p>;
  return (
    <table className="w-full border-collapse text-[13px]">
      <thead><tr className="border-b border-ink/70 text-[11.5px] text-ink-3">{head.map((h, i) => <th key={h} className={clsx("py-1.5 font-medium", i ? "text-end" : "text-start")}>{h}</th>)}</tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-b border-line/70 last:border-0">
            {r.map((c, j) => <td key={j} className={clsx("py-1.5", j ? "text-end" : "text-start text-ink")}>{c}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
