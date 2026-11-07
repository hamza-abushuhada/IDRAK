"use client";
import { Suspense, useState } from "react";
import { ChevronLeft, ChevronRight, RotateCcw } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { dateTime, num } from "@/lib/format";
import { AskIdrak, ErrorBox, Money, N, PageHeader, Section, Table, useName, type Col } from "@/components/app/kit";
import { Badge, Button, Input, Select, Skeleton } from "@/components/ui";
import { Drawer, KV, PAYMENTS, qs, SALE_STATUSES, SearchBox, useDebounced, useQueryParams } from "@/components/workspace/common";

type SaleRow = {
  id: string; invoice_number: string; sold_at: string; total: number; discount: number; tax: number; payment_method: string; status: string;
  branch: string | null; branch_ar: string | null; cashier: string | null; cashier_ar: string | null; customer: string | null; customer_ar: string | null; items: number;
};
type SaleLine = { id: string; name: string | null; name_ar: string | null; quantity: number; unit_price: number; unit_cost: number; discount: number; line_total: number };
type SaleDetail = SaleRow & { subtotal: number; customer_phone: string | null; buyer_tax_number: string | null; lines: SaleLine[] };
type OrgBranches = { branches: { id: string; name: string; name_ar: string | null }[] };

const LIMIT = 50;

export default function SalesPage() {
  return <Suspense><Sales /></Suspense>;
}

function Sales() {
  const tx = useTx();
  const locale = useLocale();
  const name = useName();
  const { get, set } = useQueryParams();
  const [search, setSearch] = useState("");
  const q = useDebounced(search, 350);
  const branch = get("branch_id"), status = get("status"), payment = get("payment"), start = get("start"), end = get("end");
  const [offset, setOffset] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const [openRow, setOpenRow] = useState<SaleRow | null>(null);

  const org = useApiQuery<OrgBranches>("/org");
  const path = `/ws/sales${qs({ q, branch_id: branch, status, payment, start, end, offset, limit: LIMIT })}`;
  const { data, error, refetch, isFetching } = useApiQuery<{ total: number; items: SaleRow[] }>(path, { placeholderData: (p) => p });
  const detail = useApiQuery<SaleDetail>(openId ? `/ws/sales/${openId}` : null);

  const setFilter = (patch: Record<string, string>) => { setOffset(0); set(patch); };
  const hasFilters = !!(branch || status || payment || start || end || q);
  const statusMeta = (s: string) => SALE_STATUSES.find((x) => x.v === s);
  const payLabel = (p: string) => { const x = PAYMENTS.find((i) => i.v === p); return x ? tx(x.en, x.ar) : p; };

  const cols: Col<SaleRow>[] = [
    { key: "invoice_number", label: tx("Invoice", "الفاتورة"), render: (r) => <span className="num font-medium text-ink">{r.invoice_number}</span> },
    { key: "sold_at", label: tx("Time", "الوقت"), render: (r) => <span className="num whitespace-nowrap text-ink-2">{dateTime(r.sold_at, locale)}</span> },
    { key: "branch", label: tx("Branch", "الفرع"), render: (r) => name(r.branch, r.branch_ar) },
    { key: "cashier", label: tx("Cashier", "الكاشير"), render: (r) => <span className="whitespace-nowrap">{name(r.cashier, r.cashier_ar)}</span> },
    { key: "customer", label: tx("Customer", "الزبون"), render: (r) => r.customer ? <span className="whitespace-nowrap">{name(r.customer, r.customer_ar)}</span> : <span className="text-ink-3">{tx("Walk-in", "زبون عابر")}</span> },
    { key: "items", label: tx("Items", "الأصناف"), align: "end", render: (r) => <N v={r.items} /> },
    { key: "payment_method", label: tx("Payment", "الدفع"), render: (r) => <Badge>{payLabel(r.payment_method)}</Badge> },
    { key: "discount", label: tx("Discount", "الخصم"), align: "end", render: (r) => r.discount ? <Money v={r.discount} className="text-terra" /> : <span className="text-ink-3">—</span> },
    { key: "total", label: tx("Total", "المجموع"), align: "end", render: (r) => <Money v={r.total} className="font-medium" /> },
    { key: "status", label: tx("Status", "الحالة"), render: (r) => { const m = statusMeta(r.status); return <Badge tone={m?.tone}>{m ? tx(m.en, m.ar) : r.status}</Badge>; } },
  ];

  const total = data?.total ?? 0;
  const from = total ? offset + 1 : 0, to = Math.min(offset + LIMIT, total);

  return (
    <div>
      <PageHeader
        eyebrow={tx("Business · Sales", "الشغل · المبيعات")}
        title={tx("Sales", "المبيعات")}
        subtitle={tx("Every invoice across your branches. Filter, search, and open one to see its lines.", "كل فاتورة بكل فروعك. فلتر، دوّر، وافتح أي فاتورة لتشوف تفاصيلها.")}
        actions={<AskIdrak q={tx("Which branch and cashier gave the most discounts this month, and is it normal?", "مين الفرع والكاشير اللي عطوا أكثر خصومات هالشهر، وهل هاد طبيعي؟")} />}
      />

      <div data-basira="sales-filters" className="mb-4 flex flex-wrap items-end gap-2.5 rounded-[var(--radius-card)] border border-line bg-paper-2/60 p-3">
        <SearchBox id="sales-search" value={search} onChange={(v) => { setSearch(v); setOffset(0); }} placeholder={tx("Invoice, customer or cashier…", "رقم فاتورة، زبون أو كاشير…")} />
        <Select value={branch} onChange={(e) => setFilter({ branch_id: e.target.value })} aria-label={tx("Branch", "الفرع")}>
          <option value="">{tx("All branches", "كل الفروع")}</option>
          {org.data?.branches.map((b) => <option key={b.id} value={b.id}>{name(b.name, b.name_ar)}</option>)}
        </Select>
        <Select value={status} onChange={(e) => setFilter({ status: e.target.value })} aria-label={tx("Status", "الحالة")}>
          <option value="">{tx("Any status", "أي حالة")}</option>
          {SALE_STATUSES.map((s) => <option key={s.v} value={s.v}>{tx(s.en, s.ar)}</option>)}
        </Select>
        <Select value={payment} onChange={(e) => setFilter({ payment: e.target.value })} aria-label={tx("Payment", "الدفع")}>
          <option value="">{tx("Any payment", "أي طريقة دفع")}</option>
          {PAYMENTS.map((p) => <option key={p.v} value={p.v}>{tx(p.en, p.ar)}</option>)}
        </Select>
        <label className="flex items-center gap-1.5 text-[12.5px] text-ink-3">
          {tx("From", "من")}
          <Input type="date" value={start} max={end || undefined} onChange={(e) => setFilter({ start: e.target.value })} className="w-[150px]" />
        </label>
        <label className="flex items-center gap-1.5 text-[12.5px] text-ink-3">
          {tx("To", "لـ")}
          <Input type="date" value={end} min={start || undefined} onChange={(e) => setFilter({ end: e.target.value })} className="w-[150px]" />
        </label>
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={() => { setSearch(""); setOffset(0); set({ branch_id: null, status: null, payment: null, start: null, end: null }); }}>
            <RotateCcw size={13} />{tx("Clear", "مسح")}
          </Button>
        )}
      </div>

      {error ? <ErrorBox error={error} retry={refetch} /> : (
        <Section
          title={tx("Invoices", "الفواتير")}
          subtitle={data ? tx(`${num(total)} invoices${hasFilters ? " match your filters" : ""}`, `${num(total)} فاتورة${hasFilters ? " حسب الفلترة" : ""}`) : " "}
          bodyClass="p-0"
          action={isFetching && data ? <span className="text-[12px] text-ink-3">{tx("Updating…", "عم نحدّث…")}</span> : undefined}
        >
          <Table<SaleRow>
            id="sales-table"
            rows={data?.items}
            cols={cols}
            onRow={(r) => { setOpenId(r.id); setOpenRow(r); }}
            empty={hasFilters ? tx("No invoices match these filters. Try widening the dates.", "ما في فواتير بهالفلترة. جرّب توسّع التاريخ.") : tx("No sales yet — upload a sales file from the Data hub.", "لسا ما في مبيعات — ارفع ملف مبيعات من صفحة البيانات.")}
          />
          {!!total && (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 text-[13px] text-ink-3">
              <span className="num">{tx(`${num(from)}–${num(to)} of ${num(total)}`, `${num(from)}–${num(to)} من ${num(total)}`)}</span>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>
                  <ChevronLeft size={14} className="rtl:rotate-180" />{tx("Previous", "السابق")}
                </Button>
                <Button variant="secondary" size="sm" disabled={to >= total} onClick={() => setOffset(offset + LIMIT)}>
                  {tx("Next", "التالي")}<ChevronRight size={14} className="rtl:rotate-180" />
                </Button>
              </div>
            </div>
          )}
        </Section>
      )}

      <Drawer
        open={!!openId}
        onOpenChange={(o) => { if (!o) { setOpenId(null); setOpenRow(null); } }}
        title={<span className="num">{openRow?.invoice_number || tx("Invoice", "فاتورة")}</span>}
        subtitle={openRow && <span className="num">{dateTime(openRow.sold_at, locale)} · {name(openRow.branch, openRow.branch_ar)}</span>}
      >
        {detail.error ? <ErrorBox error={detail.error} retry={detail.refetch} /> : !detail.data ? (
          <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
        ) : (
          <SaleDetailBody s={detail.data} row={openRow} payLabel={payLabel} />
        )}
      </Drawer>
    </div>
  );
}

function SaleDetailBody({ s, row, payLabel }: { s: SaleDetail; row: SaleRow | null; payLabel: (p: string) => string }) {
  const tx = useTx();
  const locale = useLocale();
  const name = useName();
  const m = SALE_STATUSES.find((x) => x.v === s.status);
  const profit = s.lines.reduce((a, l) => a + (l.line_total - l.unit_cost * l.quantity), 0);
  return (
    <div className="space-y-6">
      <div>
        <KV k={tx("Status", "الحالة")} v={<Badge tone={m?.tone}>{m ? tx(m.en, m.ar) : s.status}</Badge>} />
        <KV k={tx("Date", "التاريخ")} v={<span className="num">{dateTime(s.sold_at, locale)}</span>} />
        <KV k={tx("Cashier", "الكاشير")} v={row ? name(row.cashier, row.cashier_ar) : s.cashier || "—"} />
        <KV k={tx("Customer", "الزبون")} v={row?.customer ? <span>{name(row.customer, row.customer_ar)}{s.customer_phone && <span className="num ms-2 text-ink-3" dir="ltr">{s.customer_phone}</span>}</span> : tx("Walk-in", "زبون عابر")} />
        <KV k={tx("Payment", "الدفع")} v={payLabel(s.payment_method)} />
        {s.buyer_tax_number && <KV k={tx("Buyer tax no.", "الرقم الضريبي للمشتري")} v={<span className="num">{s.buyer_tax_number}</span>} />}
      </div>

      <div>
        <h4 className="mb-2 font-serif text-[15.5px] text-ink">{tx("Lines", "البنود")} <span className="num text-[13px] text-ink-3">({s.lines.length})</span></h4>
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-line bg-paper-2 text-[12px] text-ink-3">
                <th className="px-3 py-2 text-start font-medium">{tx("Product", "الصنف")}</th>
                <th className="px-3 py-2 text-end font-medium">{tx("Qty", "الكمية")}</th>
                <th className="px-3 py-2 text-end font-medium">{tx("Price", "السعر")}</th>
                <th className="px-3 py-2 text-end font-medium">{tx("Total", "المجموع")}</th>
              </tr>
            </thead>
            <tbody>
              {s.lines.map((l) => {
                const belowCost = l.unit_price < l.unit_cost;
                return (
                  <tr key={l.id} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2">
                      <span className="text-ink">{name(l.name, l.name_ar)}</span>
                      {belowCost && <Badge tone="danger" className="ms-2">{tx("Below cost", "تحت الكلفة")}</Badge>}
                      {l.discount > 0 && <span className="block text-[11.5px] text-terra">{tx("Discount", "خصم")} <Money v={l.discount} /></span>}
                    </td>
                    <td className="px-3 py-2 text-end"><N v={l.quantity} d={2} /></td>
                    <td className="px-3 py-2 text-end"><Money v={l.unit_price} /></td>
                    <td className="px-3 py-2 text-end font-medium"><Money v={l.line_total} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-xl bg-paper-2 px-4 py-3">
        <KV k={tx("Subtotal", "المجموع الفرعي")} v={<Money v={s.subtotal} />} />
        <KV k={tx("Discount", "الخصم")} v={<Money v={s.discount} className={s.discount ? "text-terra" : ""} />} />
        <KV k={tx("Tax (incl.)", "الضريبة (ضمن السعر)")} v={<Money v={s.tax} />} />
        <KV k={<span className="font-medium text-ink">{tx("Total", "المجموع")}</span>} v={<Money v={s.total} className="font-serif text-[18px]" />} />
        <KV k={tx("Gross profit on this invoice", "الربح الإجمالي بهالفاتورة")} v={<Money v={profit} className={profit < 0 ? "text-danger" : "text-olive"} />} />
      </div>
    </div>
  );
}
