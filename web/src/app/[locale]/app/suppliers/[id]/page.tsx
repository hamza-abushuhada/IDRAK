"use client";
import { useMemo } from "react";
import { useParams } from "next/navigation";
import { useRouter } from "@/lib/router";
import type { EChartsCoreOption } from "echarts/core";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { date } from "@/lib/format";
import Chart, { axisStyle, PALETTE } from "@/components/app/Chart";
import { AskIdrak, ErrorBox, Money, N, PageHeader, Section, Stat, Table, useName, type Col } from "@/components/app/kit";
import { Badge, Empty } from "@/components/ui";
import { BackLink, DetailSkeleton, KV, useHref } from "@/components/workspace/common";

type Purchase = { id: string; po_number: string; ordered_at: string; received_at: string | null; status: string; total: number; branch: string | null; emailed_at: string | null };
type Supplier = {
  id: string; name: string; name_ar: string | null; contact_name: string | null; phone: string | null; email: string | null; payment_terms_days: number | null; category: string | null;
  purchases: Purchase[];
  products: { id: string; name: string; name_ar: string | null; cost: number; price: number }[];
  cost_trend: { m: string; avg_cost: number | null }[];
};

const PO_STATUS = {
  draft: { en: "Draft", ar: "مسودة", tone: "neutral" },
  sent: { en: "Sent", ar: "انبعتت", tone: "saffron" },
  received: { en: "Received", ar: "استلمناها", tone: "olive" },
  cancelled: { en: "Cancelled", ar: "ملغاة", tone: "danger" },
} as const;

export default function SupplierDetail() {
  const { id } = useParams<{ id: string }>();
  const tx = useTx();
  const locale = useLocale();
  const name = useName();
  const href = useHref();
  const router = useRouter();
  const { data: s, error, refetch } = useApiQuery<Supplier>(`/ws/suppliers/${id}`);

  const trend = useMemo(() => (s?.cost_trend || []).filter((c) => c.avg_cost !== null) as { m: string; avg_cost: number }[], [s]);
  const change = trend.length >= 2 ? ((trend[trend.length - 1].avg_cost - trend[0].avg_cost) / trend[0].avg_cost) * 100 : null;

  const trendOpt = useMemo<EChartsCoreOption | null>(() => {
    if (trend.length < 2) return null;
    return {
      legend: { show: false },
      grid: { left: 8, right: 12, top: 20, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", valueFormatter: (v: unknown) => (typeof v === "number" ? `${v.toFixed(3)}` : "—") },
      xAxis: { type: "category", data: trend.map((t) => date(t.m, locale, { month: "short", year: "2-digit" })), boundaryGap: false, ...axisStyle },
      yAxis: { type: "value", scale: true, ...axisStyle, name: tx("avg JD / unit", "معدّل د.أ / وحدة"), nameTextStyle: { color: "#8A786A", fontSize: 11 } },
      series: [{
        name: tx("Average unit cost", "معدّل كلفة الوحدة"), type: "line", data: trend.map((t) => +t.avg_cost.toFixed(3)), smooth: 0.25, symbolSize: 6,
        lineStyle: { width: 2.2, color: PALETTE[0] }, itemStyle: { color: PALETTE[0] }, areaStyle: { color: "rgba(194,89,58,.08)" },
      }],
    };
  }, [trend, locale, tx]);

  if (error) return <ErrorBox error={error} retry={refetch} />;
  if (!s) return <DetailSkeleton />;

  const total = s.purchases.reduce((a, p) => a + (p.status === "cancelled" ? 0 : p.total), 0);
  const open = s.purchases.filter((p) => p.status === "sent" || p.status === "draft").length;
  const leadDays = s.purchases.filter((p) => p.received_at).map((p) => (new Date(p.received_at!).getTime() - new Date(p.ordered_at).getTime()) / 86400000);
  const avgLead = leadDays.length ? leadDays.reduce((a, b) => a + b, 0) / leadDays.length : null;

  const poCols: Col<Purchase>[] = [
    { key: "po_number", label: tx("PO", "رقم الطلبية"), render: (p) => <span className="num font-medium">{p.po_number}</span> },
    { key: "ordered_at", label: tx("Ordered", "تاريخ الطلب"), render: (p) => <span className="num whitespace-nowrap">{date(p.ordered_at, locale)}</span> },
    { key: "received_at", label: tx("Received", "تاريخ الاستلام"), render: (p) => <span className="num whitespace-nowrap text-ink-2">{date(p.received_at, locale)}</span> },
    { key: "branch", label: tx("Branch", "الفرع"), render: (p) => p.branch || "—" },
    { key: "status", label: tx("Status", "الحالة"), render: (p) => { const m = PO_STATUS[p.status as keyof typeof PO_STATUS]; return <Badge tone={m?.tone}>{m ? tx(m.en, m.ar) : p.status}</Badge>; } },
    { key: "total", label: tx("Total", "المجموع"), align: "end", render: (p) => <Money v={p.total} /> },
  ];
  type Prod = Supplier["products"][number];
  const prodCols: Col<Prod>[] = [
    { key: "name", label: tx("Product", "الصنف"), render: (p) => <span className="text-ink">{name(p.name, p.name_ar)}</span> },
    { key: "cost", label: tx("Cost", "الكلفة"), align: "end", render: (p) => <Money v={p.cost} /> },
    { key: "price", label: tx("Price", "السعر"), align: "end", render: (p) => <Money v={p.price} /> },
    { key: "margin", label: tx("Margin", "الهامش"), align: "end", render: (p) => { const m = p.price ? ((p.price - p.cost) / p.price) * 100 : null; return <span className={`num ${m !== null && m < 0 ? "text-danger" : "text-ink-2"}`}>{m === null ? "—" : `${m.toFixed(1)}%`}</span>; } },
  ];

  return (
    <div>
      <BackLink href={href("/app/suppliers")}>{tx("All suppliers", "كل الموردين")}</BackLink>
      <PageHeader
        eyebrow={s.category || tx("Supplier", "مورد")}
        title={name(s.name, s.name_ar)}
        subtitle={s.contact_name ? tx(`Contact: ${s.contact_name}`, `جهة الاتصال: ${s.contact_name}`) : undefined}
        actions={<AskIdrak q={tx(`Have ${s.name}'s prices gone up, and should I negotiate or switch?`, `هل أسعار ${s.name_ar || s.name} زادت، وهل لازم أفاوض أو أغيّر المورد؟`)} />}
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={tx("Purchases (last 40 orders)", "المشتريات (آخر 40 طلبية)")} value={<Money v={total} compact />} tone="terra" />
        <Stat label={tx("Open orders", "طلبيات مفتوحة")} value={<N v={open} />} />
        <Stat label={tx("Average delivery time", "معدّل وقت التوصيل")} value={avgLead === null ? "—" : tx(`${avgLead.toFixed(1)} days`, `${avgLead.toFixed(1)} يوم`)} />
        <Stat label={tx("Unit cost change", "تغيّر كلفة الوحدة")} value={change === null ? "—" : <span className={`num ${change > 0 ? "text-danger" : "text-olive"}`}>{change > 0 ? "+" : ""}{change.toFixed(1)}%</span>} hint={tx("since the first recorded month", "من أول شهر مسجّل")} />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Section title={tx("Contact & terms", "التواصل والشروط")}>
          <KV k={tx("Contact", "الشخص")} v={s.contact_name || "—"} />
          <KV k={tx("Phone", "الهاتف")} v={s.phone ? <a href={`tel:${s.phone}`} className="num hover:text-terra" dir="ltr">{s.phone}</a> : "—"} />
          <KV k={tx("Email", "الإيميل")} v={s.email ? <a href={`mailto:${s.email}`} className="break-all hover:text-terra">{s.email}</a> : "—"} />
          <KV k={tx("Payment terms", "شروط الدفع")} v={s.payment_terms_days ? tx(`${s.payment_terms_days} days`, `${s.payment_terms_days} يوم`) : tx("Cash", "كاش")} />
          <KV k={tx("Products supplied", "الأصناف")} v={<N v={s.products.length} />} />
        </Section>

        <Section id="supplier-cost-trend" className="lg:col-span-2" title={tx("Cost trend", "تطوّر الكلفة")} subtitle={tx("Average unit cost on your purchase orders, per month.", "معدّل كلفة الوحدة بطلبياتك، كل شهر.")}>
          {trendOpt ? <Chart option={trendOpt} height={250} /> : <Empty title={tx("Not enough orders yet", "الطلبيات لسا قليلة")} body={tx("We need at least two months of purchases.", "بدنا شهرين مشتريات على الأقل.")} />}
        </Section>

        <Section id="supplier-orders" className="lg:col-span-2" title={tx("Purchase orders", "طلبيات الشراء")} bodyClass="p-0">
          <Table rows={s.purchases} cols={poCols} dense empty={tx("No purchase orders yet", "لسا ما في طلبيات")} />
        </Section>

        <Section title={tx("Products", "الأصناف")} bodyClass="p-0 max-h-[460px] overflow-y-auto">
          <Table rows={s.products} cols={prodCols} dense onRow={(p) => router.push(href(`/app/products/${p.id}`))} empty={tx("No products linked", "ما في أصناف مربوطة")} />
        </Section>
      </div>
    </div>
  );
}
