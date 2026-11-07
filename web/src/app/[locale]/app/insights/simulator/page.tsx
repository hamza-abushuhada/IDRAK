"use client";
import { Suspense, useMemo, useState } from "react";
import clsx from "clsx";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { api, getOrgId } from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { jd, num, pct } from "@/lib/format";
import { AskIdrak, ErrorBox, Money, PageHeader, Section, useName } from "@/components/app/kit";
import { Button, Card, Field, Select, Skeleton, Spinner, Tabs } from "@/components/ui";
import { PageSkeleton, useDebounced } from "@/components/insights/common";
import type { Forecast, SimResult, SimSide } from "@/components/insights/types";

type Scope = "all" | "category" | "product";

export default function SimulatorPage() {
  return <Suspense fallback={<PageSkeleton />}><SimulatorScreen /></Suspense>;
}

function SimulatorScreen() {
  const tx = useTx();
  const locale = useLocale();
  const nm = useName();
  const [scope, setScope] = useState<Scope>("all");
  const [categoryId, setCategoryId] = useState("");
  const [productId, setProductId] = useState("");
  const [price, setPrice] = useState(0);
  const [cost, setCost] = useState(0);
  const [discount, setDiscount] = useState(0);
  const [elasticity, setElasticity] = useState(-1.3);

  const lists = useApiQuery<Forecast>("/insights/forecast?horizon=14", { staleTime: 10 * 60_000 });
  const cats = lists.data?.categories || [];
  const prods = lists.data?.products || [];
  const cat = scope === "category" ? categoryId || cats[0]?.id || "" : "";
  const prod = scope === "product" ? productId || prods[0]?.id || "" : "";

  const bodyKey = useDebounced(JSON.stringify({
    price_pct: price, cost_pct: cost, discount_pct: discount, elasticity,
    ...(scope === "category" && cat ? { category_id: cat } : {}), ...(scope === "product" && prod ? { product_ids: [prod] } : {}),
  }), 350);
  const body = useMemo(() => JSON.parse(bodyKey) as { category_id?: string; product_ids?: string[] }, [bodyKey]);
  const ready = scope === "all" ? !body.category_id && !body.product_ids : scope === "category" ? !!body.category_id : !!body.product_ids;
  const sim = useQuery<SimResult>({
    queryKey: [getOrgId(), "/insights/simulate", body],
    queryFn: () => api<SimResult>("/insights/simulate", { method: "POST", json: body }),
    enabled: ready,
    placeholderData: keepPreviousData,
  });
  const r = sim.data;
  const reset = () => { setPrice(0); setCost(0); setDiscount(0); setElasticity(-1.3); };
  const scopeName = scope === "product" ? nm(prods.find((p) => p.id === prod)?.name, prods.find((p) => p.id === prod)?.name_ar)
    : scope === "category" ? nm(cats.find((c) => c.id === cat)?.name, cats.find((c) => c.id === cat)?.name_ar) : tx("the whole shop", "المحل كامل");

  return (
    <div>
      <PageHeader
        eyebrow={tx("What-if simulator", "محاكي «شو لو»")}
        title={tx("Try a price change before you make it", "جرّب تغيير السعر قبل ما تعمله")}
        subtitle={tx("See what a price rise, a supplier cost change or a discount would do to a month of sales and profit — based on your last 30 days.",
          "شوف شو بيصير بمبيعات وربح شهر لو رفعت السعر، أو تغيّرت التكلفة، أو عملت خصم — على أساس آخر 30 يوم.")}
        actions={<AskIdrak q={tx(`If I raise prices on ${scopeName} by ${price}%, what happens to my profit and is it a good idea?`, `لو رفعت أسعار ${scopeName} ${price}%، شو بيصير بالربح وهل هي فكرة منيحة؟`)} />}
      />

      <div className="grid gap-5 lg:grid-cols-5">
        <Section className="lg:col-span-2" title={tx("Your scenario", "السيناريو تبعك")}
          action={<Button size="sm" variant="ghost" onClick={reset}><RotateCcw size={13} />{tx("Reset", "رجّع")}</Button>}>
          <div className="space-y-6">
            <div data-basira="sim-scope" className="space-y-3">
              <Tabs value={scope} onChange={setScope} items={[
                { value: "all", label: tx("Whole shop", "المحل كامل") }, { value: "category", label: tx("Category", "قسم") }, { value: "product", label: tx("Product", "صنف") },
              ]} />
              {scope === "category" && (
                lists.isLoading ? <Skeleton className="h-10 w-full" /> :
                  <Select value={cat} onChange={(e) => setCategoryId(e.target.value)} className="w-full" aria-label={tx("Category", "القسم")}>
                    {cats.map((c) => <option key={c.id} value={c.id}>{nm(c.name, c.name_ar)}</option>)}
                  </Select>
              )}
              {scope === "product" && (
                lists.isLoading ? <Skeleton className="h-10 w-full" /> :
                  <Select value={prod} onChange={(e) => setProductId(e.target.value)} className="w-full" aria-label={tx("Product", "الصنف")}>
                    {prods.map((p) => <option key={p.id} value={p.id}>{nm(p.name, p.name_ar)}</option>)}
                  </Select>
              )}
            </div>
            <Slider id="sim-price" label={tx("Change selling price", "غيّر سعر البيع")} value={price} onChange={setPrice} min={-30} max={30} step={1} signed />
            <Slider id="sim-cost" label={tx("Supplier cost changes by", "تكلفة المورد بتتغير")} value={cost} onChange={setCost} min={-20} max={30} step={1} signed
              hint={tx("e.g. the supplier announced +8%", "مثلاً المورد أعلن زيادة 8%")} />
            <Slider id="sim-discount" label={tx("Promotion discount", "خصم العرض")} value={discount} onChange={setDiscount} min={0} max={50} step={1} />
            <Field label={tx("How price-sensitive are your customers?", "قدّيش زباينك بيتأثروا بالسعر؟")}
              hint={tx("Essentials (bread, milk) barely change; snacks and treats react more.", "الأساسيات (خبز، حليب) ما بتتأثر كثير؛ السناكات والكماليات بتتأثر أكثر.")}>
              <Select value={String(elasticity)} onChange={(e) => setElasticity(Number(e.target.value))} className="w-full">
                <option value="-0.6">{tx("Hardly — essentials (−0.6)", "قليل — أساسيات (−0.6)")}</option>
                <option value="-1.3">{tx("Typical mini-market (−1.3)", "سوبرماركت عادي (−1.3)")}</option>
                <option value="-2">{tx("Very — treats & brands (−2.0)", "كثير — كماليات وماركات (−2.0)")}</option>
              </Select>
            </Field>
          </div>
        </Section>

        <Section id="sim-result" className="lg:col-span-3" title={tx(`Result for one month — ${scopeName}`, `النتيجة لشهر — ${scopeName}`)}
          action={sim.isFetching ? <Spinner size={16} /> : undefined}>
          {sim.error ? <ErrorBox error={sim.error} retry={() => sim.refetch()} /> : !r ? (
            <div className="space-y-3"><Skeleton className="h-16 w-full" /><Skeleton className="h-40 w-full" /></div>
          ) : !r.baseline.qty ? (
            <p className="text-sm text-ink-3">{tx("No sales in the last 30 days for this selection.", "ما في مبيعات آخر 30 يوم لهالاختيار.")}</p>
          ) : <Result r={r} locale={locale} />}
        </Section>
      </div>
    </div>
  );
}

function Slider({ id, label, value, onChange, min, max, step, signed, hint }: {
  id: string; label: string; value: number; onChange: (v: number) => void; min: number; max: number; step: number; signed?: boolean; hint?: string;
}) {
  return (
    <div data-basira={id}>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-[13px] font-medium text-ink-2">{label}</label>
        <span className={clsx("num rounded-full px-2 py-0.5 text-[13px] font-medium", value === 0 ? "bg-sand text-ink-2" : value > 0 ? "bg-terra-soft text-terra-2" : "bg-olive-soft text-olive")}>
          {signed && value > 0 ? "+" : ""}{value}%
        </span>
      </div>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[#C2593A]" dir="ltr" />
      <div className="num mt-1 flex justify-between text-[11px] text-ink-3" dir="ltr"><span>{min}%</span><span>0</span><span>{signed ? "+" : ""}{max}%</span></div>
      {hint && <p className="mt-1 text-xs text-ink-3">{hint}</p>}
    </div>
  );
}

function Result({ r, locale }: { r: SimResult; locale: "ar" | "en" }) {
  const tx = useTx();
  const b = r.baseline, s = r.scenario;
  const dp = s.profit - b.profit;
  const dq = b.qty ? (100 * (s.qty - b.qty)) / b.qty : 0;
  const dpPct = b.profit ? (100 * dp) / Math.abs(b.profit) : 0;
  const same = Math.abs(dp) < 0.5 && Math.abs(dq) < 0.05;
  const rows: { k: keyof SimSide; en: string; ar: string; money?: boolean; pctv?: boolean }[] = [
    { k: "revenue", en: "Revenue", ar: "المبيعات", money: true },
    { k: "profit", en: "Gross profit", ar: "الربح الإجمالي", money: true },
    { k: "qty", en: "Units sold", ar: "الكمية المباعة" },
    { k: "margin", en: "Margin", ar: "الهامش", pctv: true },
  ];
  return (
    <div>
      <div className={clsx("rounded-xl px-5 py-4", same ? "bg-paper-2" : dp >= 0 ? "bg-olive-soft/70" : "bg-[#f6d9d3]/70")}>
        <p className="text-[13px] text-ink-2">{tx("Monthly profit would", "الربح الشهري رح")}</p>
        <p className={clsx("mt-1 font-serif text-[30px] leading-tight", same ? "text-ink" : dp >= 0 ? "text-olive" : "text-danger")}>
          {same ? tx("stay the same", "يضل نفسه") : <>{dp >= 0 ? tx("rise by ", "يزيد ") : tx("fall by ", "ينقص ")}<Money v={Math.abs(dp)} decimals={0} />
            <span className="num ms-2 text-[16px]">({dpPct >= 0 ? "+" : "−"}{num(Math.abs(dpPct), 1)}%)</span></>}
        </p>
        {!same && (
          <p className="mt-1.5 text-[13px] text-ink-2">
            {dq < -0.5 ? tx(`…even though you'd sell ${num(Math.abs(dq), 1)}% fewer units.`, `…حتى لو بعت ${num(Math.abs(dq), 1)}% أقل بالكمية.`)
              : dq > 0.5 ? tx(`…and you'd sell ${num(dq, 1)}% more units.`, `…وبتبيع ${num(dq, 1)}% أكثر بالكمية.`) : tx("…with about the same units sold.", "…بنفس الكمية تقريباً.")}
          </p>
        )}
      </div>
      <div className="mt-5 overflow-x-auto">
        <table className="w-full border-collapse text-[13.5px]">
          <thead>
            <tr className="border-b border-line text-[12px] text-ink-3">
              <th className="py-2 text-start font-medium" />
              <th className="px-3 py-2 text-end font-medium">{tx("Today", "هلأ")}</th>
              <th className="px-3 py-2 text-end font-medium">{tx("Scenario", "السيناريو")}</th>
              <th className="py-2 text-end font-medium">{tx("Change", "الفرق")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const a = b[row.k], c = s[row.k], diff = c - a;
              const fmt = (v: number) => (row.money ? jd(v, locale, { decimals: 0 }) : row.pctv ? pct(v) : num(v));
              const good = diff >= 0;
              return (
                <tr key={row.k} className="border-b border-line/60 last:border-0">
                  <td className="py-2.5 text-ink-2">{tx(row.en, row.ar)}</td>
                  <td className="num px-3 py-2.5 text-end text-ink-2">{fmt(a)}</td>
                  <td className="num px-3 py-2.5 text-end font-medium text-ink">{fmt(c)}</td>
                  <td className={clsx("num py-2.5 text-end", Math.abs(diff) < 0.05 ? "text-ink-3" : good ? "text-olive" : "text-danger")}>
                    {Math.abs(diff) < 0.05 ? "—" : `${diff > 0 ? "+" : "−"}${row.money ? jd(Math.abs(diff), locale, { decimals: 0 }) : row.pctv ? `${num(Math.abs(diff), 1)} ${tx("pt", "نقطة")}` : num(Math.abs(diff))}`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Card className="mt-5 bg-paper-2/50 px-4 py-3 text-[12px] leading-relaxed text-ink-3 shadow-none">
        {tx(`Estimate based on the last ${r.period_days} days and a price sensitivity of ${r.elasticity}. Real customers may react differently — test on a few items first.`,
          `تقدير على أساس آخر ${r.period_days} يوم وحساسية سعر ${r.elasticity}. الزباين ممكن يتصرفوا غير هيك — جرّب على كم صنف أول.`)}
      </Card>
    </div>
  );
}
