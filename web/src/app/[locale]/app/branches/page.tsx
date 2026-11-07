"use client";
import { Suspense, useEffect, useMemo } from "react";
import clsx from "clsx";
import { MapPin } from "lucide-react";
import type { EChartsCoreOption } from "echarts/core";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { date } from "@/lib/format";
import Chart, { axisStyle, PALETTE } from "@/components/app/Chart";
import { AskIdrak, Delta, ErrorBox, Money, N, PageHeader, Section, useName } from "@/components/app/kit";
import { Card, Empty, Skeleton } from "@/components/ui";
import { useQueryParams } from "@/components/workspace/common";

type Branch = {
  id: string; name: string; name_ar: string | null; city: string | null; area: string | null; revenue30: number; tx30: number; prev30: number; disc30: number;
  staff: number; stock_value: number; basket: number; growth: number | null; margin: number | null;
};
type Resp = { items: Branch[]; trend: { name: string; w: string; rev: number }[] };

export default function BranchesPage() {
  return <Suspense><Branches /></Suspense>;
}

function Branches() {
  const tx = useTx();
  const locale = useLocale();
  const name = useName();
  const { get } = useQueryParams();
  const highlight = get("highlight");
  const { data, error, refetch } = useApiQuery<Resp>("/ws/branches");

  useEffect(() => {
    if (!highlight || !data) return;
    const t = setTimeout(() => document.getElementById(`branch-${highlight}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 150);
    return () => clearTimeout(t);
  }, [highlight, data]);

  const total = data?.items.reduce((a, b) => a + b.revenue30, 0) ?? 0;

  const trendOpt = useMemo<EChartsCoreOption | null>(() => {
    if (!data?.trend.length) return null;
    const weeks = Array.from(new Set(data.trend.map((t) => t.w))).sort();
    const names = data.items.map((b) => b.name);
    const label = (n: string) => { const b = data.items.find((x) => x.name === n); return b ? name(b.name, b.name_ar) : n; };
    const map = new Map(data.trend.map((t) => [`${t.name}|${t.w}`, t.rev]));
    return {
      legend: { top: 0, data: names.map(label) },
      grid: { left: 8, right: 12, top: 36, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", valueFormatter: (v: unknown) => (typeof v === "number" ? `${Math.round(v).toLocaleString("en-US")}` : "—") },
      xAxis: { type: "category", boundaryGap: false, data: weeks.map((w) => date(w, locale, { day: "numeric", month: "short" })), ...axisStyle },
      yAxis: { type: "value", ...axisStyle, name: tx("JD / week", "د.أ / أسبوع"), nameTextStyle: { color: "#8A786A", fontSize: 11 } },
      series: names.map((n, i) => {
        const hl = !!highlight && data.items[i]?.id === highlight;
        return {
          name: label(n), type: "line", symbol: "circle", symbolSize: 5, smooth: 0.2,
          data: weeks.map((w) => { const v = map.get(`${n}|${w}`); return v === undefined ? null : +v.toFixed(1); }),
          lineStyle: { width: hl ? 3.2 : 2, color: PALETTE[i % PALETTE.length], opacity: highlight && !hl ? 0.45 : 1 },
          itemStyle: { color: PALETTE[i % PALETTE.length] },
        };
      }),
    };
  }, [data, locale, tx, name, highlight]);

  return (
    <div>
      <PageHeader
        eyebrow={tx("Business · Branches", "الشغل · الفروع")}
        title={tx("Branches", "الفروع")}
        subtitle={tx("Side by side: how each branch sells, earns and grows over the last 30 days.", "جنب بعض: كيف كل فرع عم يبيع ويربح ويكبر بآخر 30 يوم.")}
        actions={<AskIdrak q={tx("Which branch is underperforming and why?", "أي فرع أداؤه أضعف وليش؟")} />}
      />

      {error ? <ErrorBox error={error} retry={refetch} /> : (
        <>
          <div data-basira="branch-cards" className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {!data ? Array.from({ length: 3 }).map((_, i) => <Card key={i} className="p-5"><Skeleton className="h-5 w-32" /><Skeleton className="mt-4 h-8 w-40" /><Skeleton className="mt-5 h-16 w-full" /></Card>)
              : !data.items.length ? <Card className="md:col-span-2 xl:col-span-3"><Empty title={tx("No branches yet", "لسا ما في فروع")} body={tx("Add one from Settings.", "أضف فرع من الإعدادات.")} /></Card>
                : data.items.map((b) => {
                  const share = total ? (b.revenue30 / total) * 100 : 0;
                  return (
                    <Card key={b.id} id={`branch-${b.id}`} className={clsx("p-5 transition", b.id === highlight && "ring-2 ring-saffron ring-offset-2 ring-offset-paper")}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="font-serif text-[19px] text-ink">{name(b.name, b.name_ar)}</h3>
                          <p className="mt-0.5 flex items-center gap-1 text-[12px] text-ink-3"><MapPin size={12} />{[b.area, b.city].filter(Boolean).join("، ") || "—"}</p>
                        </div>
                        <span className="num rounded-full bg-sand px-2 py-0.5 text-[11.5px] text-ink-2">{share.toFixed(0)}%</span>
                      </div>
                      <div className="mt-4 flex items-baseline gap-2">
                        <Money v={b.revenue30} className="font-serif text-[28px] leading-none text-ink" />
                        <Delta v={b.growth} />
                      </div>
                      <p className="mt-1 text-[12px] text-ink-3">{tx("revenue, last 30 days · vs previous 30", "مبيعات آخر 30 يوم · مقارنة بالـ 30 اللي قبل")}</p>
                      <dl className="mt-4 grid grid-cols-3 gap-x-3 gap-y-3 border-t border-line/70 pt-4 text-[12px]">
                        <Metric k={tx("Transactions", "العمليات")} v={<N v={b.tx30} />} />
                        <Metric k={tx("Avg basket", "معدّل السلة")} v={<Money v={b.basket} />} />
                        <Metric k={tx("Margin", "الهامش")} v={b.margin === null ? "—" : <span className={clsx("num", b.margin < 15 && "text-terra")}>{b.margin}%</span>} />
                        <Metric k={tx("Staff", "الموظفين")} v={<N v={b.staff} />} />
                        <Metric k={tx("Stock value", "قيمة المخزون")} v={<Money v={b.stock_value} compact />} />
                        <Metric k={tx("Discounts", "الخصومات")} v={<Money v={b.disc30} />} />
                      </dl>
                    </Card>
                  );
                })}
          </div>

          <Section id="branch-trend" title={tx("Weekly revenue by branch", "المبيعات الأسبوعية لكل فرع")} subtitle={tx("Last ~4 months. The latest week may be partial.", "آخر 4 شهور تقريباً. آخر أسبوع ممكن يكون مش كامل.")}>
            {!data ? <Skeleton className="h-[300px] w-full" /> : trendOpt ? <Chart option={trendOpt} height={320} /> : <Empty title={tx("No sales in this period", "ما في مبيعات بهالفترة")} />}
          </Section>
        </>
      )}
    </div>
  );
}

function Metric({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-ink-3">{k}</dt>
      <dd className="mt-0.5 text-[14px] text-ink">{v}</dd>
    </div>
  );
}
