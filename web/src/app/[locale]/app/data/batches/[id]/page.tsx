"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Link2, Save } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { api } from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { PageHeader, Section } from "@/components/app/kit";
import { Badge, Button, Field, Input, Select, Skeleton } from "@/components/ui";
import { toast } from "@/components/ui/toast";

type Contract = {
  currency: string; price_unit: "jd" | "fils"; tax_mode: "none" | "from_file" | "included" | "excluded";
  tax_rate: number | null; date_order: "auto" | "dmy" | "mdy" | "ymd"; unknown_values: "block" | "review";
};
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

      <div className="grid gap-5 xl:grid-cols-[1.25fr_.75fr]">
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

        {b ? <ContractEditor batch={b} onSaved={() => batch.refetch()} /> : <Skeleton className="h-96" />}
      </div>

      <Section className="mt-5" title={<span className="inline-flex items-center gap-2"><Link2 size={16} />{tx("Cross-file reconciliation", "مطابقة الملفات")}</span>}>
        {!b ? <Skeleton className="h-32" /> : <Reconciliation report={b.link_report} />}
      </Section>
    </div>
  );
}

function ContractEditor({ batch, onSaved }: { batch: Batch; onSaved: () => void }) {
  const tx = useTx();
  const [value, setValue] = useState(batch.contract);
  const [busy, setBusy] = useState(false);
  useEffect(() => setValue(batch.contract), [batch.contract]);
  const save = async () => {
    setBusy(true);
    try {
      await api(`/data/batches/${batch.id}/contract`, { method: "PUT", json: value });
      toast(tx("Import settings saved", "انحفظت إعدادات الاستيراد"));
      onSaved();
    } catch (e) { toast(tx("Couldn't save settings", "ما قدرنا نحفظ الإعدادات"), (e as Error).message, "error"); }
    finally { setBusy(false); }
  };
  return (
    <Section title={tx("Import settings", "إعدادات الاستيراد")}>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
        <Field label={tx("Price unit", "وحدة السعر")}><Select className="w-full" value={value.price_unit} onChange={(e) => setValue({ ...value, price_unit: e.target.value as Contract["price_unit"] })}><option value="jd">{tx("Jordanian dinar", "دينار أردني")}</option><option value="fils">{tx("Fils", "فلس")}</option></Select></Field>
        <Field label={tx("Tax", "الضريبة")}><Select className="w-full" value={value.tax_mode} onChange={(e) => setValue({ ...value, tax_mode: e.target.value as Contract["tax_mode"] })}><option value="from_file">{tx("Read from file", "من الملف")}</option><option value="none">{tx("No tax", "بدون ضريبة")}</option><option value="included">{tx("Included in prices", "مشمولة بالأسعار")}</option><option value="excluded">{tx("Added to prices", "تضاف للأسعار")}</option></Select></Field>
        {(value.tax_mode === "included" || value.tax_mode === "excluded") && <Field label={tx("Tax rate %", "نسبة الضريبة %")}><Input type="number" min="0" max="100" step="0.01" value={value.tax_rate ?? ""} onChange={(e) => setValue({ ...value, tax_rate: e.target.value === "" ? null : Number(e.target.value) })} /></Field>}
        <Field label={tx("Date order", "ترتيب التاريخ")}><Select className="w-full" value={value.date_order} onChange={(e) => setValue({ ...value, date_order: e.target.value as Contract["date_order"] })}><option value="auto">{tx("Detect, then review", "اكتشاف ثم مراجعة")}</option><option value="dmy">DD/MM/YYYY</option><option value="mdy">MM/DD/YYYY</option><option value="ymd">YYYY/MM/DD</option></Select></Field>
        <Field label={tx("Unknown values", "القيم غير المعروفة")}><Select className="w-full" value={value.unknown_values} onChange={(e) => setValue({ ...value, unknown_values: e.target.value as Contract["unknown_values"] })}><option value="block">{tx("Block import", "إيقاف الاستيراد")}</option><option value="review">{tx("Require review", "مراجعة إلزامية")}</option></Select></Field>
      </div>
      <Button className="mt-5 w-full" onClick={save} loading={busy}><Save size={15} />{tx("Save settings", "حفظ الإعدادات")}</Button>
    </Section>
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
