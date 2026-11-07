"use client";
import { Suspense, useMemo } from "react";
import Link from "next/link";
import clsx from "clsx";
import type { EChartsCoreOption } from "echarts/core";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { date, jd, num, pct } from "@/lib/format";
import { AskIdrak, Delta, ErrorBox, LinkCell, Money, N, PageHeader, Section, Stat, StatSkeleton, Table, useName } from "@/components/app/kit";
import Chart, { axisStyle } from "@/components/app/Chart";
import { useSession } from "@/components/app/session";
import { Badge, Empty, Select, Skeleton, Tabs } from "@/components/ui";
import { ChartSkeleton, DOW, JO_WEEK_ORDER, PageSkeleton, ShareBar, isWeekend, oneOf, paymentLabel, useOrgDetail, useParamState } from "@/components/insights/common";
import SalesTrendChart from "@/components/insights/SalesTrendChart";
import type { Dashboard } from "@/components/insights/types";

const RANGES = ["7", "30", "90", "365"] as const;

export default function DashboardPage() {
  return <Suspense fallback={<PageSkeleton stats={5} />}><DashboardScreen /></Suspense>;
}

function DashboardScreen() {
  const tx = useTx();
  const locale = useLocale();
  const nm = useName();
  const { org } = useSession();
  const [daysRaw, setDays] = useParamState("days", "30");
  const days = oneOf(daysRaw, RANGES, "30");
  const [branch, setBranch] = useParamState("branch_id", "");
  const orgQ = useOrgDetail();
  const q = useApiQuery<Dashboard>(`/insights/dashboard?days=${days}${branch ? `&branch_id=${branch}` : ""}`);
  const d = q.data;
  const k = d?.kpis;
  const vsLabel = tx(`vs previous ${days} days`, `مقارنة بالـ ${days} يوم اللي قبل`);

  const rangeLabel = d ? `${date(d.range.start, locale, { day: "numeric", month: "short" })} – ${date(d.range.end, locale)}` : "";
  const branchName = branch ? nm(orgQ.data?.branches.find((b) => b.id === branch)?.name, orgQ.data?.branches.find((b) => b.id === branch)?.name_ar) : null;

  return (
    <div>
      <PageHeader
        eyebrow={tx("Business report", "تقرير الشغل")}
        title={org ? tx(`How ${org.name} is doing`, `كيف ماشي الشغل في ${org.name_ar || org.name}`) : tx("How the business is doing", "كيف ماشي الشغل")}
        subtitle={<>
          {tx("Sales, profit and where to look next — so you know what to fix this week.", "المبيعات والربح ووين لازم تركّز — عشان تعرف شو تصلّح هالأسبوع.")}
          {rangeLabel && <span className="ms-1 text-ink-3">· <span className="num">{rangeLabel}</span>{branchName && ` · ${branchName}`}</span>}
        </>}
        actions={<>
          <div data-basira="range-picker">
            <Tabs value={days} onChange={(v) => setDays(v)} items={[
              { value: "7", label: tx("7 days", "7 أيام") }, { value: "30", label: tx("30 days", "30 يوم") },
              { value: "90", label: tx("90 days", "90 يوم") }, { value: "365", label: tx("Year", "سنة") },
            ]} />
          </div>
          <Select data-basira="branch-picker" value={branch} onChange={(e) => setBranch(e.target.value)} className="h-10 min-w-[150px]" aria-label={tx("Branch", "الفرع")}>
            <option value="">{tx("All branches", "كل الفروع")}</option>
            {(orgQ.data?.branches || []).map((b) => <option key={b.id} value={b.id}>{nm(b.name, b.name_ar)}</option>)}
          </Select>
          <AskIdrak q={tx(`Summarise my last ${days} days: what went well, what went badly, and the one thing I should do this week.`,
            `لخّصلي آخر ${days} يوم: شو ماشي منيح، شو مش ماشي، وشو أهم إشي لازم أعمله هالأسبوع؟`)} />
        </>}
      />

      {q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-5">
            {!k ? Array.from({ length: 5 }).map((_, i) => <StatSkeleton key={i} />) : (<>
              <Stat id="kpi-revenue" tone="terra" label={tx("Revenue", "المبيعات")} value={<Money v={k.revenue} compact />} delta={d.deltas.revenue} hint={vsLabel} />
              <Stat id="kpi-profit" tone="olive" label={tx("Gross profit", "الربح الإجمالي")} value={<Money v={k.profit} compact />} delta={d.deltas.profit} hint={vsLabel} />
              <Stat id="kpi-basket" label={tx("Average basket", "متوسط السلة")} value={<Money v={k.basket} decimals={3} />} delta={d.deltas.basket}
                hint={tx(`${num(k.units_per_tx, 1)} items per receipt`, `${num(k.units_per_tx, 1)} قطعة بالفاتورة`)} />
              <Stat id="kpi-margin" label={tx("Gross margin", "هامش الربح")} value={<span className="num">{pct(k.margin)}</span>} delta={d.deltas.margin}
                hint={tx(`Discounts ${jd(k.discounts, locale)}`, `خصومات ${jd(k.discounts, locale)}`)} />
              <Stat id="kpi-transactions" label={tx("Receipts", "عدد الفواتير")} value={<N v={k.tx} />} delta={d.deltas.tx}
                hint={tx(`${num(k.customers)} known customers · ${num(k.voids)} voids`, `${num(k.customers)} زبون معروف · ${num(k.voids)} ملغية`)} />
            </>)}
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-3">
            <Section id="chart-sales" className="lg:col-span-2" title={tx("Sales trend", "حركة المبيعات")}
              subtitle={tx("Daily revenue (bars) and gross profit (line)", "المبيعات اليومية (أعمدة) والربح الإجمالي (خط)")}>
              {d ? (d.series.length ? <SalesTrendChart series={d.series} /> : <Empty title={tx("No sales in this period", "ما في مبيعات بهالفترة")} />) : <ChartSkeleton height={280} />}
            </Section>
            <Goals d={d} />
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-5">
            <Section id="top-products" className="lg:col-span-3" title={tx("Best sellers", "الأكثر مبيعاً")} subtitle={tx("Top 10 by revenue", "أعلى 10 أصناف بالمبيعات")} bodyClass="p-0"
              action={<Link href={`/${locale}/app/products`} className="text-[12.5px] text-terra hover:underline">{tx("All products", "كل الأصناف")}</Link>}>
              <Table dense rows={d?.top_products} rowKey={(r) => r.id} empty={tx("No sales yet", "ما في مبيعات لسّا")} cols={[
                { key: "rank", label: "#", render: (_r, i) => <span className="num text-ink-3">{i + 1}</span>, className: "w-8" },
                { key: "name", label: tx("Product", "الصنف"), render: (r) => <LinkCell href={`/${locale}/app/products/${r.id}`}>{nm(r.name, r.name_ar)}</LinkCell> },
                { key: "qty", label: tx("Units", "الكمية"), align: "end", render: (r) => <N v={r.qty} /> },
                { key: "revenue", label: tx("Revenue", "المبيعات"), align: "end", render: (r) => <Money v={r.revenue} /> },
                { key: "margin", label: tx("Margin", "الهامش"), align: "end", className: "hidden sm:table-cell",
                  render: (r) => <span className="num text-ink-2">{pct(r.revenue ? (100 * r.profit) / r.revenue : 0)}</span> },
              ]} />
            </Section>
            <Branches d={d} />
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-5">
            <Section id="heatmap" className="lg:col-span-3" title={tx("Busy hours", "أوقات الذروة")}
              subtitle={tx("Receipts by day and hour — staff the shifts where the colour is darkest", "عدد الفواتير حسب اليوم والساعة — زيد الموظفين وين اللون أغمق")}>
              {d ? (d.heatmap.length ? <Heatmap d={d} /> : <Empty title={tx("No data yet", "ما في بيانات لسّا")} />) : <ChartSkeleton height={260} />}
            </Section>
            <Section className="lg:col-span-2" title={tx("How customers pay", "كيف بيدفعوا الزبائن")} subtitle={tx("Share of revenue", "حصة كل طريقة من المبيعات")}>
              <Payments d={d} />
            </Section>
          </div>

          <Section id="category-mix" className="mt-5" title={tx("Category mix", "توزيع الأقسام")}
            subtitle={tx("Where revenue comes from, and how much each category keeps as profit", "من وين بتيجي المبيعات، وقدّيش كل قسم بيربّح")}>
            <Categories d={d} />
          </Section>
        </>
      )}
    </div>
  );
}

function Goals({ d }: { d?: Dashboard }) {
  const tx = useTx();
  const locale = useLocale();
  const nm = useName();
  return (
    <Section id="goal-progress" title={tx("This month's goals", "أهداف هالشهر")} subtitle={tx("Revenue so far and where you'll land at this pace", "المبيعات لهلأ ووين رح توصل على هالوتيرة")}
      action={<Link href={`/${locale}/app/goals`} className="text-[12.5px] text-terra hover:underline">{tx("Edit", "تعديل")}</Link>}>
      {!d ? <div className="space-y-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10 w-full" />)}</div> : !d.goals.length ? (
        <Empty title={tx("No goals set for this month", "ما في أهداف لهالشهر")} body={tx("Set a monthly revenue target per branch to track pace.", "حط هدف مبيعات شهري لكل فرع عشان تتابع الوتيرة.")}
          action={<Link href={`/${locale}/app/goals`} className="text-sm text-terra underline">{tx("Set goals", "حط أهداف")}</Link>} />
      ) : (
        <ul className="space-y-5">
          {d.goals.map((g) => {
            const done = g.target ? (100 * g.actual) / g.target : 0;
            const paceP = g.target ? (100 * g.pace) / g.target : 0;
            const ok = g.pace >= g.target;
            return (
              <li key={g.branch_id}>
                <div className="flex items-baseline justify-between gap-2 text-[13.5px]">
                  <span className="font-medium text-ink">{nm(g.name, g.name_ar)}</span>
                  <span className="text-ink-3"><Money v={g.actual} className="text-ink" /> / <Money v={g.target} /></span>
                </div>
                <div className="relative mt-2 h-2.5 w-full overflow-hidden rounded-full bg-sand">
                  <div className={clsx("absolute inset-y-0 start-0 rounded-full opacity-30", ok ? "bg-olive" : "bg-saffron")} style={{ width: `${Math.min(100, paceP)}%` }} />
                  <div className={clsx("absolute inset-y-0 start-0 rounded-full", ok ? "bg-olive" : "bg-saffron")} style={{ width: `${Math.min(100, done)}%` }} />
                </div>
                <p className={clsx("mt-1.5 text-[12px]", ok ? "text-olive" : "text-[#8a5d0e]")}>
                  {ok ? tx(`On pace for ${jd(g.pace, locale)} (${num(paceP)}% of target)`, `على هالوتيرة رح توصل ${jd(g.pace, locale)} (${num(paceP)}% من الهدف)`)
                    : tx(`Pace: ${jd(g.pace, locale)} — ${jd(g.target - g.pace, locale)} short`, `الوتيرة: ${jd(g.pace, locale)} — ناقص ${jd(g.target - g.pace, locale)}`)}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}

function Branches({ d }: { d?: Dashboard }) {
  const tx = useTx();
  const locale = useLocale();
  const nm = useName();
  const max = Math.max(1, ...(d?.branches || []).map((b) => b.revenue));
  return (
    <Section id="branch-compare" className="lg:col-span-2" title={tx("Branches", "الفروع")} subtitle={tx("Revenue and growth vs the previous period", "المبيعات والنمو مقارنة بالفترة اللي قبل")}
      action={<Link href={`/${locale}/app/branches`} className="text-[12.5px] text-terra hover:underline">{tx("Compare", "قارن")}</Link>}>
      {!d ? <div className="space-y-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12 w-full" />)}</div> : !d.branches.length ? <Empty title={tx("No branches", "ما في فروع")} /> : (
        <ul className="space-y-4">
          {d.branches.map((b, i) => (
            <li key={b.id}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="flex items-center gap-2 text-[13.5px] font-medium text-ink">
                  {i === 0 && d.branches.length > 1 && <Badge tone="olive">{tx("Top", "الأول")}</Badge>}
                  {nm(b.name, b.name_ar)}
                </span>
                <span className="flex items-baseline gap-2"><Money v={b.revenue} className="text-[14px] text-ink" /><Delta v={b.growth} /></span>
              </div>
              <ShareBar className="mt-2" value={(100 * b.revenue) / max} tone={i === 0 ? "terra" : "ink"} />
              <p className="mt-1 text-[12px] text-ink-3">
                <span className="num">{num(b.tx)}</span> {tx("receipts", "فاتورة")} · {tx("basket", "السلة")} <Money v={b.basket} decimals={3} />
              </p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function Heatmap({ d }: { d: Dashboard }) {
  const tx = useTx();
  const locale = useLocale();
  const option = useMemo<EChartsCoreOption>(() => {
    const hours = d.heatmap.map((c) => c.h);
    const h0 = Math.min(...hours), h1 = Math.max(...hours);
    const hrs = Array.from({ length: h1 - h0 + 1 }, (_, i) => h0 + i);
    const names = locale === "ar" ? DOW.ar : DOW.en;
    const rows = JO_WEEK_ORDER;
    const max = Math.max(1, ...d.heatmap.map((c) => c.n));
    const data = d.heatmap.map((c) => [hrs.indexOf(c.h), rows.indexOf(c.dow), c.n]);
    return {
      tooltip: {
        trigger: "item",
        formatter: (p: { value: [number, number, number] }) =>
          `${names[rows[p.value[1]]]} · ${String(hrs[p.value[0]]).padStart(2, "0")}:00<br/><b>${num(p.value[2])}</b> ${tx("receipts", "فاتورة")}`,
      },
      grid: { left: 8, right: 8, top: 8, bottom: 4, containLabel: true },
      xAxis: { type: "category", data: hrs.map((h) => String(h).padStart(2, "0")), ...axisStyle, splitArea: { show: false }, splitLine: { show: false } },
      yAxis: {
        type: "category", inverse: true, data: rows.map((r) => names[r]), ...axisStyle, splitLine: { show: false },
        axisLabel: { ...axisStyle.axisLabel, formatter: (v: string) => (rows.some((r) => names[r] === v && isWeekend(r)) ? `{w|${v}}` : v), rich: { w: { color: "#C2593A", fontWeight: 600, fontSize: 11 } } },
      },
      visualMap: { show: false, min: 0, max, inRange: { color: ["#F4EDE2", "#F6E6C6", "#E3B866", "#D99A2B", "#C2593A"] } },
      series: [{ type: "heatmap", data, itemStyle: { borderColor: "#FFFCF7", borderWidth: 2, borderRadius: 3 }, emphasis: { itemStyle: { borderColor: "#2B211B", borderWidth: 1 } } }],
    };
  }, [d, tx, locale]);
  return (
    <>
      <Chart option={option} height={260} />
      <p className="mt-2 text-[12px] text-ink-3"><span className="font-medium text-terra">{tx("Fri & Sat", "الجمعة والسبت")}</span> {tx("are the weekend in Jordan.", "عطلة نهاية الأسبوع بالأردن.")}</p>
    </>
  );
}

function Payments({ d }: { d?: Dashboard }) {
  const tx = useTx();
  if (!d) return <div className="space-y-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)}</div>;
  if (!d.payments.length) return <Empty title={tx("No payments yet", "ما في دفعات لسّا")} />;
  const total = d.payments.reduce((a, p) => a + p.revenue, 0) || 1;
  const tones = ["terra", "olive", "saffron", "sky"] as const;
  return (
    <ul className="space-y-4">
      {d.payments.map((p, i) => {
        const share = (100 * p.revenue) / total;
        return (
          <li key={p.m}>
            <div className="flex items-baseline justify-between gap-2 text-[13.5px]">
              <span className="text-ink">{paymentLabel(p.m, tx.isAr)}</span>
              <span className="num font-medium text-ink">{pct(share, 0)}</span>
            </div>
            <ShareBar className="mt-1.5" value={share} tone={tones[i % tones.length]} />
            <p className="mt-1 text-[12px] text-ink-3"><Money v={p.revenue} /> · <span className="num">{num(p.n)}</span> {tx("receipts", "فاتورة")}</p>
          </li>
        );
      })}
    </ul>
  );
}

function Categories({ d }: { d?: Dashboard }) {
  const tx = useTx();
  const nm = useName();
  if (!d) return <div className="grid gap-4 sm:grid-cols-2">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>;
  if (!d.categories.length) return <Empty title={tx("No categories yet", "ما في أقسام لسّا")} />;
  const total = d.categories.reduce((a, c) => a + c.revenue, 0) || 1;
  const max = Math.max(...d.categories.map((c) => c.revenue));
  return (
    <ul className="grid gap-x-10 gap-y-4 sm:grid-cols-2">
      {d.categories.slice(0, 12).map((c) => {
        const m = c.revenue ? (100 * c.profit) / c.revenue : 0;
        return (
          <li key={c.name}>
            <div className="flex items-baseline justify-between gap-2 text-[13.5px]">
              <span className="min-w-0 truncate text-ink">{nm(c.name, c.name_ar)}</span>
              <span className="flex shrink-0 items-baseline gap-3">
                <Money v={c.revenue} className="text-ink" />
                <span className="num w-12 text-end text-[12px] text-ink-3">{pct((100 * c.revenue) / total, 0)}</span>
              </span>
            </div>
            <ShareBar className="mt-1.5" value={(100 * c.revenue) / max} tone="saffron" />
            <p className={clsx("mt-1 text-[12px]", m < 15 ? "text-danger" : "text-ink-3")}>
              {tx("margin", "الهامش")} <span className="num">{pct(m)}</span>
              {m < 15 && <> · {tx("thin margin", "هامش ضعيف")}</>}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
