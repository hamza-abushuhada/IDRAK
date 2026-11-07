"use client";
import { Suspense, useMemo, useState } from "react";
import { useRouter } from "@/lib/router";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { date, num } from "@/lib/format";
import { AskIdrak, Chip, ErrorBox, Money, N, PageHeader, Section, Table, useName, type Col } from "@/components/app/kit";
import { Badge, Select } from "@/components/ui";
import { qs, SearchBox, useDebounced, useHref, useQueryParams } from "@/components/workspace/common";
import { productFlags, type ProductRow } from "@/components/workspace/products";

type Resp = { items: ProductRow[]; categories: { id: string; name: string; name_ar: string | null }[] };

const FILTERS = [
  { v: "below_cost", en: "Selling below cost", ar: "عم ينباع تحت الكلفة", id: "filter-below-cost" },
  { v: "low_stock", en: "Low stock", ar: "المخزون قليل", id: "filter-low-stock" },
  { v: "dead", en: "Dead stock", ar: "بضاعة واقفة", id: "filter-dead" },
  { v: "expiring", en: "Expiring in 14 days", ar: "بتنتهي خلال 14 يوم", id: "filter-expiring" },
] as const;

export default function ProductsPage() {
  return <Suspense><Products /></Suspense>;
}

function Products() {
  const tx = useTx();
  const locale = useLocale();
  const name = useName();
  const href = useHref();
  const router = useRouter();
  const { get, set } = useQueryParams();
  const filter = get("filter");
  const category = get("category");
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim(), 300);

  const { data, error, refetch, isFetching } = useApiQuery<Resp>(`/ws/products${qs({ q, category_id: category, filter })}`, { placeholderData: (p) => p });
  const all = useApiQuery<Resp>("/ws/products");
  const counts = useMemo(() => {
    const c = { below_cost: 0, low_stock: 0, dead: 0 } as Record<string, number>;
    for (const p of all.data?.items || []) {
      const f = productFlags(p);
      if (f.belowCost) c.below_cost++;
      if (f.lowStock) c.low_stock++;
      if (f.dead) c.dead++;
    }
    return c;
  }, [all.data]);
  const cats = data?.categories || all.data?.categories || [];

  const cols: Col<ProductRow>[] = [
    {
      key: "name", label: tx("Product", "الصنف"), render: (p) => (
        <div className="min-w-[220px]">
          <span className="font-medium text-ink">{name(p.name, p.name_ar)}</span>
          <span className="num block text-[11.5px] text-ink-3">{[p.sku, p.brand, p.size].filter(Boolean).join(" · ")}</span>
        </div>
      ),
    },
    { key: "category", label: tx("Category", "الفئة"), render: (p) => <span className="whitespace-nowrap text-ink-2">{name(p.category, p.category_ar)}</span> },
    {
      key: "stock", label: tx("Stock", "المخزون"), align: "end", render: (p) => (
        <span className={productFlags(p).lowStock ? "font-medium text-danger" : ""}><N v={p.stock} /><span className="num block text-[11px] text-ink-3">{tx("reorder at", "اطلب عند")} {num(p.reorder_level)}</span></span>
      ),
    },
    { key: "sold30", label: tx("Sold 30d", "مبيع 30 يوم"), align: "end", render: (p) => <N v={p.sold30} /> },
    { key: "revenue30", label: tx("Revenue 30d", "إيراد 30 يوم"), align: "end", render: (p) => <Money v={p.revenue30} /> },
    { key: "price", label: tx("Price / cost", "السعر / الكلفة"), align: "end", render: (p) => <span className="whitespace-nowrap"><Money v={p.price} /><span className="block text-[11.5px] text-ink-3"><Money v={p.cost} /></span></span> },
    {
      key: "margin", label: tx("Margin", "الهامش"), align: "end", render: (p) => (
        <span className={`num ${p.margin === null ? "text-ink-3" : p.margin < 0 ? "font-medium text-danger" : p.margin < 10 ? "text-[#8a5d0e]" : "text-olive"}`}>{p.margin === null ? "—" : `${p.margin}%`}</span>
      ),
    },
    { key: "next_expiry", label: tx("Next expiry", "أقرب انتهاء"), render: (p) => p.next_expiry ? <span className="num whitespace-nowrap">{date(p.next_expiry, locale)}</span> : <span className="text-ink-3">—</span> },
    {
      key: "flags", label: "", render: (p) => {
        const f = productFlags(p);
        return (
          <div className="flex flex-wrap gap-1">
            {f.belowCost && <Badge tone="danger">{tx("Below cost", "تحت الكلفة")}</Badge>}
            {f.lowStock && <Badge tone="terra">{tx("Low", "قليل")}</Badge>}
            {f.dead && <Badge tone="neutral">{tx("Not moving", "واقف")}</Badge>}
            {f.expiring && <Badge tone="saffron">{f.expDays !== null && f.expDays < 0 ? tx("Expired", "منتهي") : tx(`${f.expDays}d left`, `باقي ${f.expDays} يوم`)}</Badge>}
          </div>
        );
      },
    },
  ];

  const active = FILTERS.find((f) => f.v === filter);
  const ask = active?.v === "below_cost"
    ? tx("Which products am I selling below cost, and what price should each be?", "شو الأصناف اللي عم أبيعها تحت الكلفة، وقديش لازم يكون سعر كل واحد؟")
    : active?.v === "dead"
      ? tx("How much cash is stuck in dead stock and what should I do with it?", "قديش مصاري واقفة ببضاعة ما بتتحرك، وشو أعمل فيها؟")
      : active?.v === "expiring"
        ? tx("Which items expire soon and how can I sell them before they do?", "شو الأصناف اللي قرّبت تنتهي، وكيف أبيعها قبل ما تخرب؟")
        : tx("Which products should I reorder this week?", "شو الأصناف اللي لازم أطلبها هالأسبوع؟");

  return (
    <div>
      <PageHeader
        eyebrow={tx("Business · Products & stock", "الشغل · الأصناف والمخزون")}
        title={tx("Products & stock", "الأصناف والمخزون")}
        subtitle={tx("What you sell, what's on the shelf, and what needs attention.", "شو بتبيع، شو عالرف، وشو بدّه انتباه.")}
        actions={<AskIdrak q={ask} />}
      />

      <div className="mb-4 flex flex-wrap items-center gap-2.5">
        <SearchBox id="product-search" value={search} onChange={setSearch} placeholder={tx("Name, SKU or barcode…", "الاسم، الرمز أو الباركود…")} />
        <Select value={category} onChange={(e) => set({ category: e.target.value })} aria-label={tx("Category", "الفئة")}>
          <option value="">{tx("All categories", "كل الفئات")}</option>
          {cats.map((c) => <option key={c.id} value={c.id}>{name(c.name, c.name_ar)}</option>)}
        </Select>
      </div>
      <div className="mb-5 flex flex-wrap gap-2">
        <Chip active={!filter} onClick={() => set({ filter: null })}>{tx("All products", "كل الأصناف")}</Chip>
        {FILTERS.map((f) => (
          <Chip key={f.v} id={f.id} active={filter === f.v} onClick={() => set({ filter: filter === f.v ? null : f.v })}
            count={f.v === "expiring" ? (filter === f.v ? data?.items.length : undefined) : all.data ? counts[f.v] : undefined}>
            {tx(f.en, f.ar)}
          </Chip>
        ))}
      </div>

      {error ? <ErrorBox error={error} retry={refetch} /> : (
        <Section
          title={active ? tx(active.en, active.ar) : tx("All products", "كل الأصناف")}
          subtitle={data ? tx(`${num(data.items.length)} products · sorted by revenue in the last 30 days`, `${num(data.items.length)} صنف · مرتّبة حسب إيراد آخر 30 يوم`) : " "}
          action={isFetching && data ? <span className="text-[12px] text-ink-3">{tx("Updating…", "عم نحدّث…")}</span> : undefined}
          bodyClass="p-0"
        >
          <Table<ProductRow>
            id="products-table"
            rows={data?.items}
            cols={cols}
            onRow={(p) => router.push(href(`/app/products/${p.id}`))}
            empty={filter || q || category
              ? tx("Nothing here — that's good news, or try another filter.", "ما في إشي هون — يا إما خبر حلو، يا جرّب فلتر ثاني.")
              : tx("No products yet. Upload your product list from the Data hub.", "لسا ما في أصناف. ارفع قائمة الأصناف من صفحة البيانات.")}
          />
        </Section>
      )}
    </div>
  );
}
