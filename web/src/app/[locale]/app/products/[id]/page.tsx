"use client";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import type { EChartsCoreOption } from "echarts/core";
import { useLocale, useTx } from "@/i18n";
import { useApiMutation, useApiQuery } from "@/lib/useApi";
import { date, num } from "@/lib/format";
import Chart, { axisStyle, PALETTE } from "@/components/app/Chart";
import { AskIdrak, ErrorBox, LinkCell, Money, N, PageHeader, Section, Stat, useName } from "@/components/app/kit";
import { useSession } from "@/components/app/session";
import { Badge, Button, Empty, Input, Label, ProgressBar } from "@/components/ui";
import { toast } from "@/components/ui/toast";
import { BackLink, DetailSkeleton, RoleNote, useHref } from "@/components/workspace/common";
import { daysUntil } from "@/components/workspace/products";

type Product = {
  id: string; sku: string | null; barcode: string | null; name: string; name_ar: string | null; brand: string | null; unit: string | null; size: string | null;
  cost: number; price: number; tax_rate: number; reorder_level: number; is_perishable: boolean; shelf_life_days: number | null; is_active: boolean;
  category: string | null; category_ar: string | null; supplier: string | null; supplier_id: string | null;
  stock: { branch: string; branch_ar: string | null; quantity: number }[];
  batches: { branch: string; quantity: number; expiry_date: string }[];
  weekly: { w: string; q: number; rev: number; cost: number; price: number }[];
  aliases: { alias: string; source: string }[];
  forecast: {
    actual: { d: string; q: number }[];
    forecast: { d: string; q: number; low: number; high: number; ramadan: boolean }[];
    avg_daily: number; next30_qty: number; next30_revenue: number; uplift_ramadan: number | null; ramadan_in_days: number | null;
  } | null;
};

export default function ProductDetail() {
  const { id } = useParams<{ id: string }>();
  const tx = useTx();
  const locale = useLocale();
  const name = useName();
  const href = useHref();
  const { can } = useSession();
  const editable = can("manager");
  const { data: p, error, refetch } = useApiQuery<Product>(`/ws/products/${id}`);

  const [price, setPrice] = useState("");
  const [cost, setCost] = useState("");
  const [reorder, setReorder] = useState("");
  useEffect(() => {
    if (!p) return;
    setPrice(String(p.price));
    setCost(String(p.cost));
    setReorder(String(p.reorder_level));
  }, [p]);

  const save = useApiMutation<{ price?: number; cost?: number; reorder_level?: number }>("PATCH", `/ws/products/${id}`, {
    invalidate: ["/ws/products"],
    errorTitle: tx("Couldn't save", "ما قدرنا نحفظ"),
    onSuccess: () => toast(tx("Product saved", "انحفظ الصنف"), tx("New numbers apply from now on.", "الأرقام الجديدة بتتطبّق من هلّق.")),
  });

  const pNum = Number(price), cNum = Number(cost), rNum = Number(reorder);
  const valid = price !== "" && cost !== "" && reorder !== "" && pNum >= 0 && cNum >= 0 && Number.isInteger(rNum) && rNum >= 0;
  const dirty = !!p && (pNum !== p.price || cNum !== p.cost || rNum !== p.reorder_level);
  const newMargin = pNum > 0 ? ((pNum - cNum) / pNum) * 100 : null;
  const oldMargin = p && p.price > 0 ? ((p.price - p.cost) / p.price) * 100 : null;

  const totalStock = p?.stock.reduce((a, s) => a + s.quantity, 0) ?? 0;
  const sold30 = useMemo(() => (p?.forecast?.actual || []).slice(-30).reduce((a, x) => a + x.q, 0), [p]);
  const daysCover = p?.forecast?.avg_daily ? totalStock / p.forecast.avg_daily : null;

  const weeklyOpt = useMemo<EChartsCoreOption | null>(() => {
    if (!p?.weekly.length) return null;
    const x = p.weekly.map((w) => date(w.w, locale, { day: "numeric", month: "short" }));
    return {
      legend: { top: 0, data: [tx("Revenue", "الإيراد"), tx("Unit price", "سعر الوحدة"), tx("Unit cost", "كلفة الوحدة")] },
      grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
      xAxis: { type: "category", data: x, ...axisStyle },
      yAxis: [
        { type: "value", ...axisStyle, name: tx("JD / week", "د.أ / أسبوع"), nameTextStyle: { color: "#8A786A", fontSize: 11 } },
        { type: "value", ...axisStyle, splitLine: { show: false }, name: tx("JD / unit", "د.أ / وحدة"), nameTextStyle: { color: "#8A786A", fontSize: 11 } },
      ],
      series: [
        { name: tx("Revenue", "الإيراد"), type: "bar", data: p.weekly.map((w) => +w.rev.toFixed(2)), itemStyle: { color: "#E4D8C5", borderRadius: [3, 3, 0, 0] }, barMaxWidth: 14 },
        { name: tx("Unit price", "سعر الوحدة"), type: "line", yAxisIndex: 1, step: "end", symbol: "none", data: p.weekly.map((w) => +w.price.toFixed(3)), lineStyle: { width: 2, color: PALETTE[1] }, itemStyle: { color: PALETTE[1] } },
        { name: tx("Unit cost", "كلفة الوحدة"), type: "line", yAxisIndex: 1, step: "end", symbol: "none", data: p.weekly.map((w) => +w.cost.toFixed(3)), lineStyle: { width: 2, color: PALETTE[0] }, itemStyle: { color: PALETTE[0] } },
      ],
    };
  }, [p, locale, tx]);

  const forecastOpt = useMemo<EChartsCoreOption | null>(() => {
    const f = p?.forecast;
    if (!f || !f.forecast.length) return null;
    const actual = f.actual.slice(-60);
    const days = [...actual.map((a) => a.d), ...f.forecast.map((x) => x.d)];
    const pad = (n: number) => Array<null>(n).fill(null);
    const ramadan = f.forecast.filter((x) => x.ramadan);
    return {
      legend: { top: 0, data: [tx("Actual", "الفعلي"), tx("Forecast", "المتوقّع")] },
      grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        formatter: (ps: { seriesName: string; value: number | null; marker: string; axisValueLabel: string; dataIndex: number }[]) => {
          const rows = ps.filter((x) => x.seriesName !== "low" && x.seriesName !== "band" && x.value !== null && x.value !== undefined);
          const fi = ps[0] ? ps[0].dataIndex - actual.length : -1;
          const range = fi >= 0 && f.forecast[fi] ? `<br/><span style="color:#8A786A">${tx("Likely range", "المدى المتوقّع")}: ${f.forecast[fi].low.toFixed(1)} – ${f.forecast[fi].high.toFixed(1)}</span>` : "";
          return `${ps[0]?.axisValueLabel ?? ""}<br/>${rows.map((x) => `${x.marker}${x.seriesName}: <b>${Number(x.value).toFixed(1)}</b>`).join("<br/>")}${range}`;
        },
      },
      xAxis: { type: "category", data: days.map((d) => date(d, locale, { day: "numeric", month: "short" })), boundaryGap: false, ...axisStyle },
      yAxis: { type: "value", ...axisStyle, name: tx("units / day", "وحدة / يوم"), nameTextStyle: { color: "#8A786A", fontSize: 11 } },
      series: [
        { name: "low", type: "line", stack: "band", symbol: "none", lineStyle: { opacity: 0 }, data: [...pad(actual.length), ...f.forecast.map((x) => +x.low.toFixed(2))] },
        { name: "band", type: "line", stack: "band", symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { color: "rgba(217,154,43,.18)" }, data: [...pad(actual.length), ...f.forecast.map((x) => +(x.high - x.low).toFixed(2))] },
        { name: tx("Actual", "الفعلي"), type: "line", symbol: "none", data: [...actual.map((a) => a.q), ...pad(f.forecast.length)], lineStyle: { width: 1.6, color: PALETTE[3] }, itemStyle: { color: PALETTE[3] } },
        {
          name: tx("Forecast", "المتوقّع"), type: "line", symbol: "none", data: [...pad(actual.length), ...f.forecast.map((x) => +x.q.toFixed(2))], lineStyle: { width: 2, type: "dashed", color: PALETTE[2] }, itemStyle: { color: PALETTE[2] },
          markArea: ramadan.length ? {
            silent: true, itemStyle: { color: "rgba(107,122,58,.08)" }, label: { color: "#6B7A3A", fontSize: 11 },
            data: [[{ name: tx("Ramadan", "رمضان"), xAxis: date(ramadan[0].d, locale, { day: "numeric", month: "short" }) }, { xAxis: date(ramadan[ramadan.length - 1].d, locale, { day: "numeric", month: "short" }) }]],
          } : undefined,
        },
      ],
    };
  }, [p, locale, tx]);

  if (error) return <ErrorBox error={error} retry={refetch} />;
  if (!p) return <DetailSkeleton />;

  const maxStock = Math.max(1, ...p.stock.map((s) => s.quantity));

  return (
    <div>
      <BackLink href={href("/app/products")}>{tx("All products", "كل الأصناف")}</BackLink>
      <PageHeader
        eyebrow={<>{name(p.category, p.category_ar)}{p.sku && <span className="num ms-2 normal-case tracking-normal text-ink-3">{p.sku}</span>}</>}
        title={name(p.name, p.name_ar)}
        subtitle={<>
          {[p.brand, p.size].filter(Boolean).join(" · ")}
          {p.supplier && <> · {tx("Supplier", "المورد")}: {p.supplier_id ? <LinkCell href={href(`/app/suppliers/${p.supplier_id}`)}>{p.supplier}</LinkCell> : p.supplier}</>}
          {p.is_perishable && <Badge tone="saffron" className="ms-2">{tx("Perishable", "بيخرب")}</Badge>}
          {!p.is_active && <Badge className="ms-2">{tx("Inactive", "موقوف")}</Badge>}
        </>}
        actions={<AskIdrak q={tx(`Is the price of ${p.name} right? What would happen if I changed it?`, `هل سعر ${p.name_ar || p.name} مزبوط؟ شو بصير لو غيّرته؟`)} />}
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={tx("In stock (all branches)", "المخزون (كل الفروع)")} value={<N v={totalStock} />} hint={daysCover !== null ? tx(`≈ ${num(daysCover)} days of sales`, `بيكفي تقريباً ${num(daysCover)} يوم`) : undefined} tone={totalStock <= p.reorder_level ? "terra" : undefined} />
        <Stat label={tx("Sold, last 30 days", "انباع آخر 30 يوم")} value={<N v={sold30} />} hint={p.forecast ? tx(`${num(p.forecast.avg_daily, 1)} a day on average`, `معدّل ${num(p.forecast.avg_daily, 1)} باليوم`) : undefined} />
        <Stat label={tx("Expected next 30 days", "المتوقّع لـ 30 يوم الجاية")} value={<N v={p.forecast?.next30_qty} />} hint={p.forecast ? <Money v={p.forecast.next30_revenue} /> : undefined} tone="olive" />
        <Stat label={tx("Margin", "الهامش")} value={oldMargin === null ? "—" : <span className="num">{oldMargin.toFixed(1)}%</span>} hint={<><Money v={p.price - p.cost} /> {tx("per unit", "بالحبة")}</>} tone={oldMargin !== null && oldMargin < 0 ? "terra" : undefined} />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Section title={tx("Price & stock rules", "السعر وقواعد المخزون")} subtitle={tx("Changes apply to new sales and reorder suggestions.", "التغيير بيأثّر عالمبيعات الجاية واقتراحات الطلب.")}>
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (valid && dirty && editable) save.mutate({ price: pNum, cost: cNum, reorder_level: rNum }); }}>
            <div data-basira="price-field">
              <Label>{tx("Selling price (JD, incl. tax)", "سعر البيع (د.أ، شامل الضريبة)")}</Label>
              <Input type="number" inputMode="decimal" step="0.005" min="0" value={price} onChange={(e) => setPrice(e.target.value)} disabled={!editable} className="num" />
            </div>
            <div data-basira="cost-field">
              <Label>{tx("Unit cost (JD)", "كلفة الحبة (د.أ)")}</Label>
              <Input type="number" inputMode="decimal" step="0.005" min="0" value={cost} onChange={(e) => setCost(e.target.value)} disabled={!editable} className="num" />
            </div>
            <div data-basira="reorder-level-field">
              <Label>{tx("Reorder when stock falls to", "اطلب لما ينزل المخزون لـ")}</Label>
              <Input type="number" inputMode="numeric" step="1" min="0" value={reorder} onChange={(e) => setReorder(e.target.value)} disabled={!editable} className="num" />
            </div>
            <div className="rounded-xl bg-paper-2 px-4 py-3 text-[13px]">
              <div className="flex items-baseline justify-between">
                <span className="text-ink-3">{tx("Margin preview", "معاينة الهامش")}</span>
                <span className={`num font-serif text-[20px] ${newMargin !== null && newMargin < 0 ? "text-danger" : "text-ink"}`}>{newMargin === null ? "—" : `${newMargin.toFixed(1)}%`}</span>
              </div>
              {dirty && oldMargin !== null && newMargin !== null && (
                <p className="mt-1 text-[12px] text-ink-3">
                  {tx("was", "كان")} <span className="num">{oldMargin.toFixed(1)}%</span> · {tx("profit per unit", "الربح بالحبة")} <Money v={pNum - cNum} className={pNum - cNum < 0 ? "text-danger" : "text-olive"} />
                </p>
              )}
              {newMargin !== null && newMargin < 0 && <p className="mt-1 text-[12px] text-danger">{tx("This price is below cost — you'd lose money on every unit.", "هالسعر تحت الكلفة — رح تخسر بكل حبة.")}</p>}
            </div>
            {editable ? (
              <div className="flex items-center gap-2">
                <Button type="submit" data-basira="save-product" loading={save.isPending} disabled={!valid || !dirty}>{tx("Save changes", "احفظ التغييرات")}</Button>
                {dirty && <Button type="button" variant="ghost" size="sm" onClick={() => { setPrice(String(p.price)); setCost(String(p.cost)); setReorder(String(p.reorder_level)); }}>{tx("Reset", "رجّع")}</Button>}
              </div>
            ) : (
              <div className="space-y-2">
                <Button type="button" data-basira="save-product" disabled>{tx("Save changes", "احفظ التغييرات")}</Button>
                <RoleNote>{tx("Only managers and owners can change prices and stock rules.", "بس المدير أو المالك بيقدر يغيّر الأسعار وقواعد المخزون.")}</RoleNote>
              </div>
            )}
          </form>
        </Section>

        <Section id="sales-history" className="lg:col-span-2" title={tx("Weekly sales", "المبيعات الأسبوعية")} subtitle={tx("Revenue per week, with the unit price and unit cost you actually sold at.", "الإيراد كل أسبوع، مع سعر البيع والكلفة الفعلية للحبة.")}>
          {weeklyOpt ? <Chart option={weeklyOpt} height={290} /> : <Empty title={tx("No sales recorded yet", "لسا ما في مبيعات مسجّلة")} />}
        </Section>

        <Section id="stock-by-branch" title={tx("Stock by branch", "المخزون حسب الفرع")}>
          {p.stock.length ? (
            <ul className="space-y-3">
              {p.stock.map((s) => (
                <li key={s.branch}>
                  <div className="mb-1 flex justify-between text-[13.5px]"><span className="text-ink">{name(s.branch, s.branch_ar)}</span><N v={s.quantity} /></div>
                  <ProgressBar value={(s.quantity / maxStock) * 100} tone={s.quantity <= p.reorder_level / Math.max(1, p.stock.length) ? "saffron" : "olive"} />
                </li>
              ))}
            </ul>
          ) : <Empty title={tx("No stock recorded", "ما في مخزون مسجّل")} />}
        </Section>

        <Section id="product-forecast" className="lg:col-span-2" title={tx("Demand forecast — next 60 days", "توقّع الطلب — 60 يوم الجاية")}
          subtitle={p.forecast?.ramadan_in_days !== null && p.forecast?.ramadan_in_days !== undefined && p.forecast.ramadan_in_days <= 120
            ? tx(`Ramadan starts in ${p.forecast.ramadan_in_days} days${p.forecast.uplift_ramadan ? ` · usually ×${p.forecast.uplift_ramadan.toFixed(2)} demand` : ""}`,
              `رمضان بعد ${p.forecast.ramadan_in_days} يوم${p.forecast.uplift_ramadan ? ` · الطلب عادة ×${p.forecast.uplift_ramadan.toFixed(2)}` : ""}`)
            : tx("Shaded band = likely range.", "المنطقة المظلّلة = المدى المتوقّع.")}>
          {forecastOpt ? <Chart option={forecastOpt} height={270} /> : <Empty title={tx("Not enough history to forecast", "التاريخ مش كافي للتوقّع")} body={tx("We need a few weeks of sales for this product.", "بدنا كم أسبوع مبيعات لهالصنف.")} />}
        </Section>

        <Section id="expiry-batches" title={tx("Expiry batches", "دفعات الصلاحية")} bodyClass="p-0">
          {p.batches.length ? (
            <ul className="divide-y divide-line/60">
              {p.batches.map((b, i) => {
                const d = daysUntil(b.expiry_date);
                return (
                  <li key={i} className="flex items-center justify-between gap-3 px-5 py-2.5 text-[13.5px]">
                    <div><span className="num text-ink">{date(b.expiry_date, locale)}</span><span className="block text-[12px] text-ink-3">{b.branch} · <N v={b.quantity} /> {tx("units", "حبة")}</span></div>
                    {d !== null && <Badge tone={d < 0 ? "danger" : d <= 14 ? "saffron" : "neutral"}>{d < 0 ? tx("Expired", "منتهي") : tx(`${d} days`, `${d} يوم`)}</Badge>}
                  </li>
                );
              })}
            </ul>
          ) : <p className="px-5 py-6 text-center text-[13px] text-ink-3">{p.is_perishable ? tx("No batches with stock left.", "ما في دفعات فيها مخزون.") : tx("This product doesn't expire.", "هالصنف ما إله تاريخ انتهاء.")}</p>}
        </Section>

        <Section className="lg:col-span-2" title={tx("Names Idrak has learned", "الأسماء اللي تعلّمها إدراك")} subtitle={tx("Spellings from your files that map to this product — used when cleaning new uploads.", "طرق كتابة من ملفاتك بتنربط بهالصنف — بنستعملها لما ننظّف الملفات الجديدة.")}>
          {p.aliases.length ? (
            <div className="flex flex-wrap gap-2">
              {p.aliases.map((a) => (
                <span key={a.alias} className="inline-flex items-center gap-1.5 rounded-full border border-line bg-paper px-3 py-1 text-[13px] text-ink">
                  {a.alias}<span className="text-[11px] text-ink-3">· {a.source === "catalog" ? tx("catalog", "الكتالوج") : a.source === "learned" || a.source === "cleaning" ? tx("learned", "متعلّم") : a.source}</span>
                </span>
              ))}
            </div>
          ) : <p className="text-[13px] text-ink-3">{tx("No other names yet.", "لسا ما في أسماء ثانية.")}</p>}
        </Section>
      </div>
    </div>
  );
}
