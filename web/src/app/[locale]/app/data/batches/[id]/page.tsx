"use client";
import { useParams } from "next/navigation";
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Link2 } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { PageHeader, Section } from "@/components/app/kit";
import { Badge, Button, Skeleton } from "@/components/ui";

type Contract = { currency: string };
type Upload = { id: string; file_name: string; entity: string; row_count: number; status: string };
type Report = {
  rows: number; relationships: { sales_products: number; catalog_products: number; exact_product_matches: number; unmatched_products: number; sales_customer_phones: number; customer_phone_matches: number };
  recommended_order: string[];
  warnings: { code: string; count: number }[];
};
type Batch = { id: string; status: string; contract: Contract; link_report: Report; uploads: Upload[]; created_at: string };

const ENTITY: Record<string, [string, string]> = {
  sales: ["Sales", "مبيعات"], products: ["Products & inventory", "أصناف ومخزون"], customers: ["Customers", "زبائن"],
  supplier_prices: ["Supplier prices", "أسعار موردين"], purchases: ["Purchases", "مشتريات"], unknown: ["Needs mapping", "بحاجة لربط الأعمدة"],
};

export default function BatchPage() {
  const { id } = useParams<{ id: string }>();
  const tx = useTx();
  const locale = useLocale();
  const batch = useApiQuery<Batch>(`/data/batches/${id}`);
  const b = batch.data;
  const arrow = locale === "ar" ? <ArrowLeft size={15} /> : <ArrowRight size={15} />;
  if (batch.error) return <p className="text-danger">{batch.error.message}</p>;

  return (
    <div>
      <PageHeader eyebrow={tx("Import batch", "دفعة استيراد")} title={tx("Review linked files", "مراجعة الملفات المرتبطة")}
        subtitle={b ? tx(`${b.uploads.length} files · ${b.link_report.rows.toLocaleString()} rows`, `${b.uploads.length} ملفات · ${b.link_report.rows.toLocaleString()} صف`) : undefined} />

      <Section title={tx("Files", "الملفات")} bodyClass="p-0">
        {!b ? <div className="p-5"><Skeleton className="h-48" /></div> : (
          <div className="divide-y divide-line">
            {[...b.uploads].sort((a, z) => b.link_report.recommended_order.indexOf(a.id) - b.link_report.recommended_order.indexOf(z.id)).map((upload, index) => {
              const label = ENTITY[upload.entity] || ENTITY.unknown;
              return (
                <div key={upload.id} className="flex items-center gap-3 px-5 py-4">
                  <span className="num grid size-9 shrink-0 place-items-center rounded-md bg-sand text-ink-3">{index + 1}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-ink">{upload.file_name}</p>
                    <p className="mt-0.5 text-[12.5px] text-ink-3"><span className="num">{upload.row_count.toLocaleString()}</span> {tx("rows", "صف")}</p>
                  </div>
                  <Badge tone={upload.entity === "unknown" ? "saffron" : "sky"}>{tx(label[0], label[1])}</Badge>
                  <Button size="sm" variant="secondary" href={`/${locale}/app/data/uploads/${upload.id}`}>{tx("Review", "راجع")}{arrow}</Button>
                </div>
              );
            })}
          </div>
        )}
      </Section>

      <Section className="mt-5" title={<span className="inline-flex items-center gap-2"><Link2 size={16} />{tx("Cross-file reconciliation", "مطابقة الملفات")}</span>}>
        {!b ? <Skeleton className="h-32" /> : <Reconciliation report={b.link_report} />}
      </Section>
    </div>
  );
}

function Reconciliation({ report }: { report: Report }) {
  const tx = useTx();
  const stats = [
    [report.relationships.exact_product_matches, tx("products linked exactly", "منتج مرتبط بدقة")],
    [report.relationships.unmatched_products, tx("products need review", "منتج بحاجة لمراجعة")],
    [report.relationships.customer_phone_matches, tx("customers linked by phone", "زبون مرتبط بالهاتف")],
  ] as const;
  return (
    <div>
      <div className="grid gap-3 sm:grid-cols-3">{stats.map(([n, label]) => <div key={label} className="border-s-2 border-terra ps-3"><p className="num text-2xl text-ink">{n.toLocaleString()}</p><p className="text-[12.5px] text-ink-3">{label}</p></div>)}</div>
      <div className="mt-5 space-y-2">
        {report.warnings.length === 0 ? <p className="flex items-center gap-2 text-sm text-olive"><CheckCircle2 size={16} />{tx("No blocking relationship issues", "ما في مشاكل ربط مانعة")}</p> : report.warnings.map((warning) => (
          <p key={warning.code} className="flex items-center gap-2 text-sm text-[#8a5d0e]"><AlertTriangle size={15} /><b className="num">{warning.count}</b> {tx(({ unmatched_products: "unmatched products", barcode_conflicts: "conflicting barcodes", low_customer_matches: "sales customers not found in the customer file", unknown_files: "unclassified files", missing_product_catalog: "sales products without a catalog" } as Record<string, string>)[warning.code] || warning.code, ({ unmatched_products: "منتجات غير مرتبطة", barcode_conflicts: "باركودات متعارضة", low_customer_matches: "عملاء مبيعات غير موجودين في ملف العملاء", unknown_files: "ملفات غير مصنفة", missing_product_catalog: "منتجات مبيعات بدون كتالوج" } as Record<string, string>)[warning.code] || warning.code)}</p>
        ))}
      </div>
    </div>
  );
}
