"use client";
import { Suspense, useState } from "react";
import { useRouter } from "@/lib/router";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { date, num } from "@/lib/format";
import { AskIdrak, Chip, ErrorBox, Money, N, PageHeader, Section, Table, useName, type Col } from "@/components/app/kit";
import { Badge } from "@/components/ui";
import { qs, SearchBox, SEGMENT_TONE, useDebounced, useHref, useQueryParams } from "@/components/workspace/common";

type Segment = { key: string; en: string; ar: string; count: number; revenue: number };
type CustomerRow = {
  id: string; full_name: string; full_name_ar: string | null; phone: string | null; area: string | null; loyalty_points: number | null; last_visit: string;
  freq: number; monetary: number; lifetime_tx: number; lifetime: number; recency_days: number; segment: string;
};
type Resp = { segments: Segment[]; items: CustomerRow[]; total: number };

export default function CustomersPage() {
  return <Suspense><Customers /></Suspense>;
}

function Customers() {
  const tx = useTx();
  const locale = useLocale();
  const name = useName();
  const href = useHref();
  const router = useRouter();
  const { get, set } = useQueryParams();
  const segment = get("segment");
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim(), 300);

  const { data, error, refetch, isFetching } = useApiQuery<Resp>(`/ws/customers${qs({ q, segment })}`, { placeholderData: (p) => p });
  const segs = data?.segments || [];
  const segName = (k: string) => { const s = segs.find((x) => x.key === k); return s ? tx(s.en, s.ar) : k; };
  const allCount = segs.reduce((a, s) => a + s.count, 0);

  const cols: Col<CustomerRow>[] = [
    { key: "full_name", label: tx("Customer", "الزبون"), render: (c) => <span className="whitespace-nowrap font-medium text-ink">{name(c.full_name, c.full_name_ar)}</span> },
    { key: "phone", label: tx("Phone", "الهاتف"), render: (c) => c.phone ? <span className="num whitespace-nowrap text-ink-2" dir="ltr">{c.phone}</span> : "—" },
    { key: "area", label: tx("Area", "المنطقة"), render: (c) => <span className="whitespace-nowrap text-ink-2">{c.area || "—"}</span> },
    { key: "segment", label: tx("Segment", "الفئة"), render: (c) => <Badge tone={SEGMENT_TONE[c.segment] || "neutral"}>{segName(c.segment)}</Badge> },
    {
      key: "recency_days", label: tx("Last visit", "آخر زيارة"), align: "end", render: (c) => (
        <span className="whitespace-nowrap">
          <span className={`num ${c.recency_days > 30 ? "text-terra" : "text-ink"}`}>{c.recency_days === 0 ? tx("today", "اليوم") : tx(`${c.recency_days}d ago`, `قبل ${c.recency_days} يوم`)}</span>
          <span className="num block text-[11px] text-ink-3">{date(c.last_visit, locale)}</span>
        </span>
      ),
    },
    { key: "freq", label: tx("Visits (6 mo)", "زيارات (6 شهور)"), align: "end", render: (c) => <N v={c.freq} /> },
    { key: "monetary", label: tx("Spend (6 mo)", "صرف (6 شهور)"), align: "end", render: (c) => <Money v={c.monetary} /> },
    { key: "loyalty_points", label: tx("Points", "النقاط"), align: "end", render: (c) => <N v={c.loyalty_points} /> },
  ];

  const ask = segment === "at_risk"
    ? tx("Which at-risk customers are worth winning back first, and what offer should I send them?", "مين من الزبائن المعرّضين للخسارة لازم نرجّعهم أول، وشو العرض المناسب إلهم؟")
    : tx("Who are my best customers and how do I keep them coming back?", "مين أحسن زبائني وكيف أخليهم يضلّوا يرجعوا؟");

  return (
    <div>
      <PageHeader
        eyebrow={tx("Business · Customers", "الشغل · الزبائن")}
        title={tx("Customers", "الزبائن")}
        subtitle={tx("Grouped by how recently, how often and how much they buy — so you know who to thank and who to call.", "مقسّمين حسب آخر زيارة وقديش بيجوا وقديش بيصرفوا — عشان تعرف مين تشكر ومين تتصل فيه.")}
        actions={<AskIdrak q={ask} />}
      />

      <div data-basira="customer-segments" className="mb-4 flex flex-wrap gap-2">
        <Chip active={!segment} onClick={() => set({ segment: null })} count={data ? allCount : undefined}>{tx("Everyone", "الكل")}</Chip>
        {segs.map((s) => (
          <Chip key={s.key} active={segment === s.key} onClick={() => set({ segment: segment === s.key ? null : s.key })} count={s.count}>{tx(s.en, s.ar)}</Chip>
        ))}
      </div>
      {segs.length > 0 && (
        <div className="mb-5 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
          {segs.map((s) => (
            <button key={s.key} onClick={() => set({ segment: segment === s.key ? null : s.key })}
              className={`rounded-xl border px-3.5 py-2.5 text-start transition ${segment === s.key ? "border-ink bg-paper" : "border-line bg-paper-2/60 hover:bg-paper"}`}>
              <span className="block text-[12px] text-ink-3">{tx(s.en, s.ar)}</span>
              <Money v={s.revenue} compact className="font-serif text-[17px] text-ink" />
              <span className="block text-[11px] text-ink-3">{tx("spend, last 6 months", "صرف آخر 6 شهور")}</span>
            </button>
          ))}
        </div>
      )}

      <div className="mb-4">
        <SearchBox id="customer-search" value={search} onChange={setSearch} placeholder={tx("Name or phone…", "الاسم أو رقم الهاتف…")} />
      </div>

      {error ? <ErrorBox error={error} retry={refetch} /> : (
        <Section
          title={segment ? segName(segment) : tx("All customers", "كل الزبائن")}
          subtitle={data ? (data.total > data.items.length
            ? tx(`Showing top ${num(data.items.length)} of ${num(data.total)} by spend`, `عرض أعلى ${num(data.items.length)} من ${num(data.total)} حسب الصرف`)
            : tx(`${num(data.total)} customers · sorted by spend`, `${num(data.total)} زبون · مرتّبين حسب الصرف`)) : " "}
          action={isFetching && data ? <span className="text-[12px] text-ink-3">{tx("Updating…", "عم نحدّث…")}</span> : undefined}
          bodyClass="p-0"
        >
          <Table<CustomerRow>
            id="customers-table"
            rows={data?.items}
            cols={cols}
            onRow={(c) => router.push(href(`/app/customers/${c.id}`))}
            empty={q || segment ? tx("No customers match.", "ما في زبائن بهالبحث.") : tx("No customers with purchases yet. Customers appear once sales are linked to a name or phone.", "لسا ما في زبائن عندهم مشتريات. بيظهروا لما تنربط المبيعات باسم أو رقم.")}
          />
        </Section>
      )}
    </div>
  );
}
