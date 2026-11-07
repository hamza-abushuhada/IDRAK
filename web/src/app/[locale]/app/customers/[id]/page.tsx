"use client";
import { useMemo } from "react";
import { useParams } from "next/navigation";
import type { EChartsCoreOption } from "echarts/core";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { date, dateTime, num } from "@/lib/format";
import Chart, { axisStyle, PALETTE } from "@/components/app/Chart";
import { AskIdrak, ErrorBox, Money, N, PageHeader, Section, Stat, Table, useName, type Col } from "@/components/app/kit";
import { Badge, Empty } from "@/components/ui";
import { BackLink, DetailSkeleton, KV, SEGMENT_TONE, useHref } from "@/components/workspace/common";

type Customer = {
  id: string; full_name: string; full_name_ar: string | null; phone: string | null; email: string | null; gender: string | null; city: string | null; area: string | null;
  loyalty_card: string | null; loyalty_points: number | null; first_seen: string | null;
  sales: { id: string; invoice_number: string; sold_at: string; total: number; branch: string | null }[];
  favorites: { name: string; name_ar: string | null; q: number; rev: number }[];
  monthly: { m: string; rev: number; n: number }[];
};
type RfmList = {
  segments: { key: string; en: string; ar: string }[];
  items: { id: string; segment: string; recency_days: number; freq: number; monetary: number; lifetime: number; lifetime_tx: number }[];
};

export default function CustomerDetail() {
  const { id } = useParams<{ id: string }>();
  const tx = useTx();
  const locale = useLocale();
  const name = useName();
  const href = useHref();
  const { data: c, error, refetch } = useApiQuery<Customer>(`/ws/customers/${id}`);
  const rfm = useApiQuery<RfmList>("/ws/customers");
  const r = rfm.data?.items.find((x) => x.id === id);
  const seg = r && rfm.data?.segments.find((s) => s.key === r.segment);

  const monthlyOpt = useMemo<EChartsCoreOption | null>(() => {
    if (!c?.monthly.length) return null;
    const months = c.monthly.map((m) => date(`${m.m}-01`, locale, { month: "short", year: "2-digit" }));
    return {
      legend: { top: 0, data: [tx("Spend", "الصرف"), tx("Visits", "الزيارات")] },
      grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
      xAxis: { type: "category", data: months, ...axisStyle },
      yAxis: [{ type: "value", ...axisStyle }, { type: "value", ...axisStyle, splitLine: { show: false } }],
      series: [
        { name: tx("Spend", "الصرف"), type: "bar", data: c.monthly.map((m) => +m.rev.toFixed(2)), itemStyle: { color: PALETTE[0], borderRadius: [4, 4, 0, 0] }, barMaxWidth: 26 },
        { name: tx("Visits", "الزيارات"), type: "line", yAxisIndex: 1, data: c.monthly.map((m) => m.n), symbolSize: 5, lineStyle: { color: PALETTE[3], width: 2 }, itemStyle: { color: PALETTE[3] } },
      ],
    };
  }, [c, locale, tx]);

  if (error) return <ErrorBox error={error} retry={refetch} />;
  if (!c) return <DetailSkeleton />;

  const lifetime = c.monthly.reduce((a, m) => a + m.rev, 0);
  const visits = c.monthly.reduce((a, m) => a + m.n, 0);
  const maxFav = Math.max(1, ...c.favorites.map((f) => f.q));
  const saleCols: Col<Customer["sales"][number]>[] = [
    { key: "invoice_number", label: tx("Invoice", "الفاتورة"), render: (s) => <span className="num font-medium">{s.invoice_number}</span> },
    { key: "sold_at", label: tx("Time", "الوقت"), render: (s) => <span className="num whitespace-nowrap text-ink-2">{dateTime(s.sold_at, locale)}</span> },
    { key: "branch", label: tx("Branch", "الفرع"), render: (s) => s.branch || "—" },
    { key: "total", label: tx("Total", "المجموع"), align: "end", render: (s) => <Money v={s.total} /> },
  ];

  return (
    <div>
      <BackLink href={href("/app/customers")}>{tx("All customers", "كل الزبائن")}</BackLink>
      <PageHeader
        eyebrow={tx("Customer", "زبون")}
        title={<span className="inline-flex flex-wrap items-center gap-3">{name(c.full_name, c.full_name_ar)}{seg && <Badge tone={SEGMENT_TONE[seg.key] || "neutral"}>{tx(seg.en, seg.ar)}</Badge>}</span>}
        subtitle={[c.area, c.city].filter(Boolean).join("، ") || undefined}
        actions={<AskIdrak q={tx(`What does ${c.full_name} usually buy, and what could I offer them next?`, `شو عادةً بيشتري ${c.full_name_ar || c.full_name}، وشو ممكن أعرض عليه؟`)} />}
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={tx("Lifetime spend", "مجموع الصرف")} value={<Money v={r?.lifetime ?? lifetime} />} tone="terra" />
        <Stat label={tx("Visits", "عدد الزيارات")} value={<N v={r?.lifetime_tx ?? visits} />} hint={r ? tx(`${num(r.freq)} in the last 6 months`, `${num(r.freq)} بآخر 6 شهور`) : undefined} />
        <Stat label={tx("Average basket", "معدّل السلة")} value={<Money v={visits ? lifetime / visits : null} />} />
        <Stat label={tx("Last visit", "آخر زيارة")} value={r ? (r.recency_days === 0 ? tx("Today", "اليوم") : tx(`${r.recency_days} days ago`, `قبل ${r.recency_days} يوم`)) : (c.sales[0] ? date(c.sales[0].sold_at, locale) : "—")}
          tone={r && r.recency_days > 30 ? "saffron" : "olive"} />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Section id="customer-profile" title={tx("Profile", "الملف")}>
          <KV k={tx("Phone", "الهاتف")} v={c.phone ? <a href={`tel:${c.phone}`} className="num hover:text-terra" dir="ltr">{c.phone}</a> : "—"} />
          <KV k={tx("Email", "الإيميل")} v={c.email ? <span className="break-all">{c.email}</span> : "—"} />
          <KV k={tx("Area", "المنطقة")} v={[c.area, c.city].filter(Boolean).join("، ") || "—"} />
          <KV k={tx("Loyalty card", "بطاقة الولاء")} v={<span className="num">{c.loyalty_card || "—"}</span>} />
          <KV k={tx("Points", "النقاط")} v={<N v={c.loyalty_points} />} />
          <KV k={tx("Customer since", "زبون من")} v={<span className="num">{date(c.first_seen, locale)}</span>} />
        </Section>

        <Section className="lg:col-span-2" title={tx("Monthly spend", "الصرف الشهري")} subtitle={tx("What they spent and how often they came, month by month.", "قديش صرف وقديش إجا، شهر بشهر.")}>
          {monthlyOpt ? <Chart option={monthlyOpt} height={260} /> : <Empty title={tx("No purchases yet", "لسا ما في مشتريات")} />}
        </Section>

        <Section id="customer-favorites" title={tx("Favourite products", "الأصناف المفضّلة")}>
          {c.favorites.length ? (
            <ul className="space-y-3">
              {c.favorites.map((f) => (
                <li key={f.name}>
                  <div className="mb-1 flex items-baseline justify-between gap-3 text-[13.5px]">
                    <span className="min-w-0 truncate text-ink">{name(f.name, f.name_ar)}</span>
                    <span className="shrink-0 text-[12px] text-ink-3"><N v={f.q} /> × · <Money v={f.rev} /></span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-sand"><div className="h-full rounded-full bg-olive" style={{ width: `${(f.q / maxFav) * 100}%` }} /></div>
                </li>
              ))}
            </ul>
          ) : <p className="text-[13px] text-ink-3">{tx("Nothing yet.", "لسا ما في إشي.")}</p>}
        </Section>

        <Section id="customer-history" className="lg:col-span-2" title={tx("Recent invoices", "آخر الفواتير")} subtitle={tx("Last 50 completed purchases", "آخر 50 عملية شراء")} bodyClass="p-0">
          <Table rows={c.sales} cols={saleCols} dense empty={tx("No invoices yet", "لسا ما في فواتير")} />
        </Section>
      </div>
    </div>
  );
}
