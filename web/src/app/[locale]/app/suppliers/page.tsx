"use client";
import { Suspense } from "react";
import { useRouter } from "@/lib/router";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { date } from "@/lib/format";
import { AskIdrak, ErrorBox, Money, N, PageHeader, Section, Stat, StatSkeleton, Table, useName, type Col } from "@/components/app/kit";
import { Badge } from "@/components/ui";
import { useHref, useQueryParams, useScrollToHighlighted } from "@/components/workspace/common";

type SupplierRow = {
  id: string; name: string; name_ar: string | null; contact_name: string | null; phone: string | null; email: string | null; payment_terms_days: number | null; category: string | null;
  products: number; spend90: number; last_order: string | null; open_orders: number;
};

export default function SuppliersPage() {
  return <Suspense><Suppliers /></Suspense>;
}

function Suppliers() {
  const tx = useTx();
  const locale = useLocale();
  const name = useName();
  const href = useHref();
  const router = useRouter();
  const { get } = useQueryParams();
  const highlight = get("highlight");
  const { data, error, refetch } = useApiQuery<SupplierRow[]>("/ws/suppliers");
  useScrollToHighlighted("suppliers-table", highlight, !!data);

  const spend = data?.reduce((a, s) => a + s.spend90, 0) ?? 0;
  const open = data?.reduce((a, s) => a + s.open_orders, 0) ?? 0;
  const top = data?.[0];

  const cols: Col<SupplierRow>[] = [
    {
      key: "name", label: tx("Supplier", "المورد"), render: (s) => (
        <div className="min-w-[200px]">
          <span className="font-medium text-ink">{name(s.name, s.name_ar)}</span>
          <span className="block text-[11.5px] text-ink-3">{[s.category, s.contact_name].filter(Boolean).join(" · ")}</span>
        </div>
      ),
    },
    { key: "spend90", label: tx("Spend 90d", "مشتريات 90 يوم"), align: "end", render: (s) => <Money v={s.spend90} className="font-medium" /> },
    { key: "products", label: tx("Products", "الأصناف"), align: "end", render: (s) => <N v={s.products} /> },
    { key: "open_orders", label: tx("Open orders", "طلبيات مفتوحة"), align: "end", render: (s) => s.open_orders ? <Badge tone="saffron">{s.open_orders}</Badge> : <span className="text-ink-3">0</span> },
    { key: "last_order", label: tx("Last order", "آخر طلبية"), render: (s) => <span className="num whitespace-nowrap text-ink-2">{date(s.last_order, locale)}</span> },
    { key: "payment_terms_days", label: tx("Payment terms", "شروط الدفع"), render: (s) => s.payment_terms_days ? <span className="whitespace-nowrap">{tx(`${s.payment_terms_days} days`, `${s.payment_terms_days} يوم`)}</span> : <span className="text-ink-3">{tx("Cash", "كاش")}</span> },
    { key: "phone", label: tx("Phone", "الهاتف"), render: (s) => s.phone ? <span className="num whitespace-nowrap text-ink-2" dir="ltr">{s.phone}</span> : "—" },
  ];

  return (
    <div>
      <PageHeader
        eyebrow={tx("Business · Suppliers", "الشغل · الموردين")}
        title={tx("Suppliers", "الموردين")}
        subtitle={tx("Who you buy from, how much, and on what terms.", "من وين بتشتري، قديش، وبأي شروط.")}
        actions={<AskIdrak q={tx("Which supplier raised their prices the most recently?", "مين المورد اللي رفع أسعاره أكثر إشي مؤخراً؟")} />}
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        {data ? (
          <>
            <Stat label={tx("Purchases, last 90 days", "المشتريات آخر 90 يوم")} value={<Money v={spend} compact />} tone="terra" />
            <Stat label={tx("Open purchase orders", "طلبيات مفتوحة")} value={<N v={open} />} />
            <Stat label={tx("Biggest supplier", "أكبر مورد")} value={<span className="text-[19px]">{top ? name(top.name, top.name_ar) : "—"}</span>} hint={top && spend ? tx(`${Math.round((top.spend90 / spend) * 100)}% of purchases`, `${Math.round((top.spend90 / spend) * 100)}% من المشتريات`) : undefined} />
          </>
        ) : Array.from({ length: 3 }).map((_, i) => <StatSkeleton key={i} />)}
      </div>

      {error ? <ErrorBox error={error} retry={refetch} /> : (
        <Section title={tx("All suppliers", "كل الموردين")} subtitle={tx("Sorted by spend in the last 90 days", "مرتّبين حسب المشتريات آخر 90 يوم")} bodyClass="p-0">
          <Table<SupplierRow>
            id="suppliers-table"
            rows={data}
            cols={cols}
            highlightRow={(s) => s.id === highlight}
            onRow={(s) => router.push(href(`/app/suppliers/${s.id}`))}
            empty={tx("No suppliers yet. They're created when you upload products or purchase files.", "لسا ما في موردين. بينضافوا لما ترفع ملف أصناف أو مشتريات.")}
          />
        </Section>
      )}
    </div>
  );
}
