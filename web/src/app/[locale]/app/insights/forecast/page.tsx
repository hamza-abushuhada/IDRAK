"use client";
import { Suspense, useMemo } from "react";
import { Moon } from "lucide-react";
import type { EChartsCoreOption } from "echarts/core";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { date, num } from "@/lib/format";
import { AskIdrak, ErrorBox, Money, N, PageHeader, Section, Stat, StatSkeleton, Table, useName } from "@/components/app/kit";
import Chart, { INK, PALETTE, axisStyle } from "@/components/app/Chart";
import { Badge, Card, Empty, Select, Skeleton, Tabs } from "@/components/ui";
import { ChartSkeleton, PageSkeleton, oneOf, useParamState, useSetParams } from "@/components/insights/common";
import type { Forecast } from "@/components/insights/types";

const HORIZONS = ["30", "90", "180"] as const;

export default function ForecastPage() {
  return <Suspense fallback={<PageSkeleton />}><ForecastScreen /></Suspense>;
}

function ForecastScreen() {
  const tx = useTx();
  const locale = useLocale();
  const nm = useName();
  const [productId] = useParamState("product_id", "");
  const [categoryId] = useParamState("category_id", "");
  const setParams = useSetParams();
  const [hRaw, setHorizon] = useParamState("horizon", "90");
  const horizon = oneOf(hRaw, HORIZONS, "90");
  const qs = new URLSearchParams({ horizon });
  if (productId) qs.set("product_id", productId);
  else if (categoryId) qs.set("category_id", categoryId);
  const q = useApiQuery<Forecast>(`/insights/forecast?${qs.toString()}`, { placeholderData: (prev) => prev });
  const d = q.data;

  const scopeValue = productId ? `p:${productId}` : categoryId ? `c:${categoryId}` : "all";
  const onScope = (v: string) => setParams({
    product_id: v.startsWith("p:") ? v.slice(2) : "",
    category_id: v.startsWith("c:") ? v.slice(2) : "",
  });
  const scopeName = productId ? nm(d?.products.find((p) => p.id === productId)?.name, d?.products.find((p) => p.id === productId)?.name_ar)
    : categoryId ? nm(d?.categories.find((c) => c.id === categoryId)?.name, d?.categories.find((c) => c.id === categoryId)?.name_ar) : tx("the whole shop", "المحل كامل");

  return (
    <div>
      <PageHeader
        eyebrow={tx("Demand forecast", "توقّع الطلب")}
        title={tx("How much will you sell?", "قدّيش رح تبيع؟")}
        subtitle={tx("Daily units for the coming weeks, with Ramadan, Eid and holidays built in — so you buy the right amount, not too much.",
          "الكميات اليومية للأسابيع الجاية، محسوب فيها رمضان والعيد والعطل — عشان تشتري الكمية الصح، مش زيادة.")}
        actions={<AskIdrak q={tx(`What should I stock up on before Ramadan, and how much more of ${scopeName} will I need?`, `شو لازم أخزّن قبل رمضان، وقدّيش رح أحتاج زيادة من ${scopeName}؟`)} />}
      />

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Select data-basira="forecast-product-picker" value={scopeValue} onChange={(e) => onScope(e.target.value)} className="min-w-0 max-w-full flex-1 sm:max-w-sm" aria-label={tx("What to forecast", "شو بدك تتوقع")}>
          <option value="all">{tx("Whole shop (all products)", "المحل كامل (كل الأصناف)")}</option>
          {!!d?.categories.length && (
            <optgroup label={tx("Categories", "الأقسام")}>
              {d.categories.map((c) => <option key={c.id} value={`c:${c.id}`}>{nm(c.name, c.name_ar)}</option>)}
            </optgroup>
          )}
          {!!d?.products.length && (
            <optgroup label={tx("Products", "الأصناف")}>
              {d.products.map((p) => <option key={p.id} value={`p:${p.id}`}>{nm(p.name, p.name_ar)}</option>)}
            </optgroup>
          )}
        </Select>
        <div data-basira="forecast-horizon">
          <Tabs value={horizon} onChange={(v) => setHorizon(v)} items={[
            { value: "30", label: tx("30 days", "30 يوم") }, { value: "90", label: tx("90 days", "90 يوم") }, { value: "180", label: tx("6 months", "6 شهور") },
          ]} />
        </div>
        {q.isFetching && d && <span className="text-[12px] text-ink-3">{tx("Updating…", "عم نحدّث…")}</span>}
      </div>

      {q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            {!d ? [0, 1, 2, 3].map((i) => <StatSkeleton key={i} />) : (<>
              <RamadanCard d={d} />
              <Stat label={tx("Expected next 30 days", "المتوقع بالـ 30 يوم الجاية")} value={<N v={d.next30_qty} />} hint={tx("units", "قطعة")} tone="terra" />
              <Stat label={tx("Revenue next 30 days", "مبيعات الـ 30 يوم الجاية")} value={<Money v={d.next30_revenue} compact />} hint={tx(`at ~${num(d.unit_price, 3)} JD / unit`, `على متوسط ${num(d.unit_price, 3)} د.أ للقطعة`)} />
              <Stat label={tx("Normal day today", "اليوم العادي هلأ")} value={<N v={d.avg_daily} d={1} />} hint={tx("units / day (last 4 weeks)", "قطعة باليوم (آخر 4 أسابيع)")} />
            </>)}
          </div>

          <Section id="forecast-chart" className="mt-5" title={tx(`Daily units — ${scopeName}`, `الكمية اليومية — ${scopeName}`)}
            subtitle={tx("Solid: what you sold · dashed: forecast · band: likely range · shaded: Ramadan", "الخط المتصل: اللي انباع · المتقطع: المتوقع · الظل: المدى المحتمل · المظلل: رمضان")}>
            {d ? (d.actual.length ? <ForecastChart d={d} /> : <Empty title={tx("Not enough sales history yet", "ما في تاريخ مبيعات كافي لسّا")} body={tx("We need a few weeks of sales to forecast this.", "بنحتاج كم أسبوع مبيعات عشان نتوقع.")} />) : <ChartSkeleton height={320} />}
          </Section>

          <div className="mt-5 grid gap-5 lg:grid-cols-5">
            <Section id="ramadan-movers" className="lg:col-span-3" bodyClass="p-0" title={tx("What jumps in Ramadan", "شو بيطلع برمضان")}
              subtitle={tx("Products whose daily sales rose the most last Ramadan — order these early", "الأصناف اللي زاد بيعها أكثر إشي برمضان الماضي — اطلبها بكير")}>
              <Table dense rows={d?.ramadan_movers} rowKey={(r) => r.id} empty={tx("No Ramadan history yet", "ما في بيانات رمضان لسّا")} onRow={(r) => onScope(`p:${r.id}`)} cols={[
                { key: "name", label: tx("Product", "الصنف"), render: (r) => <span className="font-medium text-ink">{nm(r.name, r.name_ar)}</span> },
                { key: "base", label: tx("Normal / day", "يوم عادي"), align: "end", render: (r) => <N v={r.base_daily} d={1} /> },
                { key: "ram", label: tx("Ramadan / day", "يوم برمضان"), align: "end", render: (r) => <N v={r.ram_daily} d={1} /> },
                { key: "uplift", label: tx("Jump", "الزيادة"), align: "end", render: (r) => <Badge tone={r.uplift >= 3 ? "terra" : "saffron"}><span className="num">×{num(r.uplift, 1)}</span></Badge> },
              ]} />
              {!!d?.ramadan_movers.length && <p className="border-t border-line/60 px-5 py-2.5 text-[12px] text-ink-3">{tx("Tap a product to see its forecast.", "اضغط على أي صنف لتشوف توقعه.")}</p>}
            </Section>
            <Section id="forecast-events" className="lg:col-span-2" title={tx("Coming up", "شو جاي")} subtitle={tx("Seasons and holidays inside this forecast", "مواسم وعطل ضمن فترة التوقع")}>
              {!d ? <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10 w-full" />)}</div> : !d.events.length ? (
                <p className="text-sm text-ink-3">{tx("No special dates in this window. Try 6 months.", "ما في مناسبات بهالفترة. جرّب 6 شهور.")}</p>
              ) : (
                <ol className="space-y-3">
                  {d.events.map((e) => (
                    <li key={e.d} className="flex items-center gap-3">
                      <span className="grid w-14 shrink-0 place-items-center rounded-lg border border-line bg-paper py-1.5 text-center">
                        <span className="num block font-serif text-[18px] leading-none text-ink">{e.in_days}</span>
                        <span className="block text-[10.5px] text-ink-3">{tx("days", "يوم")}</span>
                      </span>
                      <span className="min-w-0">
                        <span className="block text-[13.5px] text-ink">{tx(e.en, e.ar)}</span>
                        <span className="num block text-[12px] text-ink-3">{date(e.d, locale, { weekday: "long", day: "numeric", month: "long" })}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </Section>
          </div>
        </>
      )}
    </div>
  );
}

function RamadanCard({ d }: { d: Forecast }) {
  const tx = useTx();
  const n = d.ramadan_in_days;
  const up = Math.round((d.uplift_ramadan - 1) * 100);
  return (
    <Card className="relative overflow-hidden px-5 py-4">
      <span className="absolute inset-y-0 start-0 w-1 bg-saffron" />
      <p className="flex items-center gap-1.5 text-[12.5px] text-ink-3"><Moon size={13} className="text-saffron" />{tx("Ramadan", "رمضان")}</p>
      <p className="mt-1.5 font-serif text-[26px] leading-none text-ink">
        {n === null ? "—" : n <= 0 ? tx("Now", "هلأ") : <>{tx("in ", "بعد ")}<span className="num">{n}</span>{tx(" days", " يوم")}</>}
      </p>
      <p className="mt-1.5 text-[12px] text-ink-3">
        {up > 0 ? tx(`Demand ${up}% higher last Ramadan`, `الطلب زاد ${up}% برمضان الماضي`) : up < 0 ? tx(`Demand ${-up}% lower last Ramadan`, `الطلب قلّ ${-up}% برمضان الماضي`) : tx("No Ramadan effect seen", "ما في تأثير واضح لرمضان")}
      </p>
    </Card>
  );
}

function ForecastChart({ d }: { d: Forecast }) {
  const tx = useTx();
  const locale = useLocale();
  const option = useMemo<EChartsCoreOption>(() => {
    const days = [...d.actual.map((a) => a.d), ...d.forecast.map((f) => f.d)];
    const na = d.actual.length;
    const last = d.actual[na - 1];
    const actual = [...d.actual.map((a) => a.q), ...d.forecast.map(() => null)];
    const fc = [...d.actual.map((_, i) => (i === na - 1 ? last.q : null)), ...d.forecast.map((f) => f.q)];
    const low = [...d.actual.map(() => null), ...d.forecast.map((f) => f.low)];
    const band = [...d.actual.map(() => null), ...d.forecast.map((f) => Math.max(0, f.high - f.low))];
    const flags = [...d.actual.map((a) => a.ramadan), ...d.forecast.map((f) => f.ramadan)];
    const areas: [{ xAxis: string; name: string }, { xAxis: string }][] = [];
    let s = -1;
    flags.forEach((r, i) => {
      if (r && s < 0) s = i;
      if ((!r || i === flags.length - 1) && s >= 0) {
        areas.push([{ xAxis: days[s], name: tx("Ramadan", "رمضان") }, { xAxis: days[r ? i : i - 1] }]);
        s = -1;
      }
    });
    const eventLines = d.events.filter((e) => days.includes(e.d)).map((e) => ({ xAxis: e.d, label: { formatter: tx(e.en, e.ar) } }));
    const fmt = (v: string) => date(v, locale, { day: "numeric", month: "short" });
    return {
      legend: { top: 0, data: [tx("Sold", "المباع"), tx("Forecast", "المتوقع"), tx("Likely range", "المدى المحتمل")] },
      grid: { left: 8, right: 16, top: 34, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        formatter: (ps: { axisValue: string; seriesName: string; value: number | null; marker: string }[]) => {
          const rows = ps.filter((p) => p.value !== null && p.value !== undefined && p.seriesName !== "low");
          const i = days.indexOf(ps[0]?.axisValue);
          const f = i >= na ? d.forecast[i - na] : null;
          const head = `<b>${date(ps[0]?.axisValue, locale, { weekday: "short", day: "numeric", month: "short" })}</b>${flags[i] ? ` · ${tx("Ramadan", "رمضان")}` : ""}`;
          const body = rows.filter((p) => p.seriesName !== tx("Likely range", "المدى المحتمل")).map((p) => `${p.marker}${p.seriesName}: <b>${num(p.value, 1)}</b>`).join("<br/>");
          const range = f ? `<br/><span style="color:#8A786A">${tx("Range", "المدى")}: ${num(f.low, 0)} – ${num(f.high, 0)}</span>` : "";
          return `${head}<br/>${body}${range}`;
        },
      },
      xAxis: { type: "category", data: days, boundaryGap: false, ...axisStyle, splitLine: { show: false }, axisLabel: { ...axisStyle.axisLabel, formatter: fmt } },
      yAxis: { type: "value", ...axisStyle, axisLabel: { ...axisStyle.axisLabel, formatter: (v: number) => (v >= 1000 ? `${num(v / 1000, 1)}k` : num(v)) } },
      series: [
        { name: "low", type: "line", data: low, stack: "band", symbol: "none", lineStyle: { opacity: 0 }, silent: true, tooltip: { show: false } },
        { name: tx("Likely range", "المدى المحتمل"), type: "line", data: band, stack: "band", symbol: "none", lineStyle: { opacity: 0 },
          areaStyle: { color: "rgba(217,154,43,.18)" }, itemStyle: { color: "#E3B866" }, silent: true },
        { name: tx("Sold", "المباع"), type: "line", data: actual, symbol: "none", lineStyle: { width: 1.6, color: INK }, itemStyle: { color: INK },
          markArea: areas.length ? { silent: true, itemStyle: { color: "rgba(122,75,92,.08)" }, label: { color: "#7A4B5C", fontSize: 11, position: "insideTop" }, data: areas } : undefined },
        { name: tx("Forecast", "المتوقع"), type: "line", data: fc, symbol: "none", lineStyle: { width: 2.2, type: "dashed", color: PALETTE[0] }, itemStyle: { color: PALETTE[0] },
          markLine: eventLines.length ? {
            silent: true, symbol: "none", lineStyle: { color: "#4F7C8A", type: "dotted", width: 1.2 },
            label: { color: "#4F7C8A", fontSize: 10.5, position: "insideEndTop" }, data: eventLines,
          } : undefined },
      ],
    };
  }, [d, tx, locale]);
  return <Chart option={option} height={320} />;
}
