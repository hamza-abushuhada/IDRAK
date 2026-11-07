"use client";
import { Suspense, useMemo, useState } from "react";
import clsx from "clsx";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import type { EChartsCoreOption } from "echarts/core";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { date, jd, num } from "@/lib/format";
import { AskIdrak, ErrorBox, Money, PageHeader, Section, Stat, StatSkeleton, Table } from "@/components/app/kit";
import Chart, { INK, PALETTE, axisStyle } from "@/components/app/Chart";
import { useSession } from "@/components/app/session";
import { Card, Field, Input, Skeleton, Tabs } from "@/components/ui";
import { ChartSkeleton, PageSkeleton, RoleNotice, oneOf, useDebounced, useParamState } from "@/components/insights/common";
import type { Cashflow } from "@/components/insights/types";

const WEEKS = ["8", "12", "16"] as const;

export default function CashflowPage() {
  return <Suspense fallback={<PageSkeleton />}><CashflowGate /></Suspense>;
}

function CashflowGate() {
  const { can, loading, org } = useSession();
  if (loading || !org) return <PageSkeleton />;
  if (!can("accountant")) return <RoleNotice min="accountant" />;
  return <CashflowScreen />;
}

function CashflowScreen() {
  const tx = useTx();
  const locale = useLocale();
  const [wRaw, setWeeks] = useParamState("weeks", "8");
  const weeks = oneOf(wRaw, WEEKS, "8");
  const [openingParam] = useParamState("opening", "");
  const [opening, setOpening] = useState<string>(openingParam);
  const op = useDebounced(opening, 500);
  const valid = op === "" || Number.isFinite(Number(op));
  const q = useApiQuery<Cashflow>(`/insights/cashflow?weeks=${weeks}${op !== "" && valid ? `&opening=${Number(op)}` : ""}`, { placeholderData: (p) => p });
  const d = q.data;
  const low = d?.lowest;
  const tight = low ? low.balance < (d?.payroll || 0) : false;
  const negative = low ? low.balance < 0 : false;
  const totalIn = d?.weeks.reduce((a, w) => a + w.inflow, 0) || 0;
  const totalOut = d?.weeks.reduce((a, w) => a + w.outflow, 0) || 0;

  return (
    <div>
      <PageHeader
        eyebrow={tx("Cash-flow projection", "توقّع السيولة")}
        title={tx("Will you have enough cash?", "رح يكفيك الكاش؟")}
        subtitle={tx("Week-by-week money in and out — supplier dues, salaries and rent — so you see the tight week before it arrives.",
          "الداخل والطالع أسبوع بأسبوع — مستحقات الموردين والرواتب والإيجار — عشان تشوف الأسبوع الصعب قبل ما ييجي.")}
        actions={<AskIdrak q={tx("When is my cash tightest in the next weeks and what can I do now to avoid a shortfall?", "إمتى رح يكون الكاش أقل إشي بالأسابيع الجاية، وشو بقدر أعمل هلأ عشان ما أتعثّر؟")} />}
      />

      <div className="mb-5 flex flex-wrap items-end gap-4">
        <div data-basira="cash-opening" className="w-full max-w-[240px]">
          <Field label={tx("Cash you have today (JD)", "الكاش اللي معك اليوم (د.أ)")}>
            <Input type="number" inputMode="decimal" min={0} step={100} value={opening} placeholder={d ? String(d.opening) : "15000"}
              onChange={(e) => setOpening(e.target.value)} className="num" />
          </Field>
        </div>
        <Tabs value={weeks} onChange={(v) => setWeeks(v)} items={WEEKS.map((w) => ({ value: w, label: tx(`${w} weeks`, `${w} أسبوع`) }))} />
        {q.isFetching && d && <span className="pb-2.5 text-[12px] text-ink-3">{tx("Recalculating…", "عم نعيد الحساب…")}</span>}
      </div>

      {q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            {!d ? [0, 1, 2, 3].map((i) => <StatSkeleton key={i} />) : (<>
              <Card data-basira="cash-lowest" className={clsx("relative col-span-2 overflow-hidden px-5 py-4", negative ? "border-danger/40" : tight ? "border-saffron/60" : "")}>
                <span className={clsx("absolute inset-y-0 start-0 w-1", negative ? "bg-danger" : tight ? "bg-saffron" : "bg-olive")} />
                <p className="flex items-center gap-1.5 text-[12.5px] text-ink-3">
                  {negative || tight ? <AlertTriangle size={13} className={negative ? "text-danger" : "text-saffron"} /> : <CheckCircle2 size={13} className="text-olive" />}
                  {tx("Lowest point", "أقل نقطة")}
                </p>
                {low ? (<>
                  <p className={clsx("mt-1.5 font-serif text-[28px] leading-none", negative ? "text-danger" : "text-ink")}><Money v={low.balance} decimals={0} /></p>
                  <p className="mt-1.5 text-[12.5px] text-ink-2">
                    {tx(`Week of ${date(low.week_start, locale, { day: "numeric", month: "long" })}`, `أسبوع ${date(low.week_start, locale, { day: "numeric", month: "long" })}`)}
                    {low.salaries > 0 && tx(" — salaries and rent are due", " — وقت الرواتب والإيجار")}
                  </p>
                  <p className="mt-1 text-[12px] text-ink-3">
                    {negative ? tx("You'd run out of cash. Delay a supplier payment or arrange a short credit line now.", "رح يخلص الكاش. أجّل دفعة مورد أو رتّب تسهيلات قصيرة من هلأ.")
                      : tight ? tx("Less than one month of payroll left at that point — keep big orders for after.", "باقي أقل من راتب شهر وقتها — خلّي الطلبيات الكبيرة لبعدها.")
                        : tx("Comfortable — you stay above one month of payroll.", "مريح — بتضل فوق راتب شهر.")}
                  </p>
                </>) : <Skeleton className="mt-2 h-7 w-32" />}
              </Card>
              <Stat label={tx("Money in", "الداخل")} tone="olive" value={<Money v={totalIn} compact />} hint={tx(`${d.weeks.length} weeks of expected sales`, `مبيعات متوقعة لـ ${d.weeks.length} أسبوع`)} />
              <Stat label={tx("Money out", "الطالع")} tone="terra" value={<Money v={totalOut} compact />} hint={tx(`incl. payroll ${jd(d.payroll, locale, { decimals: 0 })}/month`, `منها رواتب ${jd(d.payroll, locale, { decimals: 0 })} بالشهر`)} />
            </>)}
          </div>

          <Section id="cash-chart" className="mt-5" title={tx("Cash balance by week", "رصيد الكاش أسبوع بأسبوع")} subtitle={tx("Bars: money in and out · line: cash at the end of each week", "الأعمدة: الداخل والطالع · الخط: الكاش آخر كل أسبوع")}>
            {d ? <CashChart d={d} /> : <ChartSkeleton height={300} />}
          </Section>

          <Section id="cash-table" className="mt-5" bodyClass="p-0" title={tx("Week by week", "أسبوع بأسبوع")}>
            <Table dense rows={d?.weeks} rowKey={(r) => r.week_start} highlightRow={(r) => r.week_start === low?.week_start} cols={[
              { key: "week", label: tx("Week of", "أسبوع"), render: (r) => <span className="num whitespace-nowrap text-ink">{date(r.week_start, locale, { day: "numeric", month: "short" })}</span> },
              { key: "inflow", label: tx("Sales in", "المبيعات"), align: "end", render: (r) => <Money v={r.inflow} decimals={0} className="text-olive" /> },
              { key: "sup", label: tx("Suppliers", "الموردين"), align: "end", render: (r) => <Money v={-r.supplier_payments} decimals={0} /> },
              { key: "sal", label: tx("Salaries", "الرواتب"), align: "end", render: (r) => (r.salaries ? <Money v={-r.salaries} decimals={0} /> : <span className="text-ink-3">—</span>) },
              { key: "rent", label: tx("Rent", "الإيجار"), align: "end", render: (r) => (r.rent ? <Money v={-r.rent} decimals={0} /> : <span className="text-ink-3">—</span>) },
              { key: "net", label: tx("Net", "الصافي"), align: "end", render: (r) => <Money v={r.net} decimals={0} className={r.net < 0 ? "text-danger" : "text-ink"} /> },
              { key: "balance", label: tx("Cash at end", "الكاش آخر الأسبوع"), align: "end", render: (r) => <Money v={r.balance} decimals={0} className={clsx("font-medium", r.balance < 0 ? "text-danger" : "text-ink")} /> },
            ]} />
          </Section>
          <p className="mt-4 text-[12px] text-ink-3">
            {tx("Projection uses your average weekly sales (+12% in Ramadan weeks), supplier payment terms on received orders, active staff salaries and branch rent on the 1st of each month.",
              "التوقع مبني على متوسط مبيعاتك الأسبوعي (+12% بأسابيع رمضان)، وشروط الدفع للموردين على الطلبيات المستلمة، ورواتب الموظفين، وإيجار الفروع أول كل شهر.")}
          </p>
        </>
      )}
    </div>
  );
}

function CashChart({ d }: { d: Cashflow }) {
  const tx = useTx();
  const locale = useLocale();
  const option = useMemo<EChartsCoreOption>(() => ({
    legend: { top: 0, data: [tx("Money in", "الداخل"), tx("Money out", "الطالع"), tx("Cash balance", "رصيد الكاش")] },
    tooltip: { trigger: "axis", valueFormatter: (v: number) => jd(v, locale, { decimals: 0 }) },
    xAxis: { type: "category", data: d.weeks.map((w) => date(w.week_start, locale, { day: "numeric", month: "short" })), ...axisStyle, splitLine: { show: false } },
    yAxis: { type: "value", ...axisStyle, axisLabel: { ...axisStyle.axisLabel, formatter: (v: number) => (Math.abs(v) >= 1000 ? `${num(v / 1000, 0)}k` : num(v)) } },
    series: [
      { name: tx("Money in", "الداخل"), type: "bar", data: d.weeks.map((w) => w.inflow), barMaxWidth: 22, itemStyle: { color: PALETTE[1], borderRadius: [3, 3, 0, 0] } },
      { name: tx("Money out", "الطالع"), type: "bar", data: d.weeks.map((w) => -w.outflow), barMaxWidth: 22, itemStyle: { color: PALETTE[0], borderRadius: [0, 0, 3, 3] } },
      { name: tx("Cash balance", "رصيد الكاش"), type: "line", data: d.weeks.map((w) => w.balance), smooth: true, symbolSize: 6, lineStyle: { width: 2.4, color: INK }, itemStyle: { color: INK },
        markLine: { silent: true, symbol: "none", data: [{ yAxis: 0 }], lineStyle: { color: "#B3412E", type: "dashed" }, label: { show: false } } },
    ],
  }), [d, tx, locale]);
  return <Chart option={option} height={300} />;
}
