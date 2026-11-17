"use client";
import { useRouter } from "@/lib/router";
import { useRef, useState } from "react";
import clsx from "clsx";
import { FileSpreadsheet, Link2, Trash2, Brain, Download, Files } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { api } from "@/lib/api";
import { useApiMutation, useApiQuery } from "@/lib/useApi";
import { date, timeAgo } from "@/lib/format";
import { AskIdrak, PageHeader, Section, Table } from "@/components/app/kit";
import { Badge, Button, Input, Spinner } from "@/components/ui";
import { toast } from "@/components/ui/toast";
import { useSession } from "@/components/app/session";

type Upload = { id: string; batch_id: string | null; file_name: string; source: string; entity: string; row_count: number; status: string; health_before: number | null; health_after: number | null; imported_rows: number | null; created_at: string; uploaded_by_name: string | null; last_run_id: string | null; has_data: boolean };
type Rule = { id: string; column_kind: string; match_value: string; replace_value: string; times_applied: number; created_by_name: string | null; created_at: string };

const SAMPLES = [
  { file: "pos_export_messy.xlsx", en: "Messy POS export (Khalda, 660 rows)", ar: "تصدير كاشير فوضوي (خلدا، 660 صف)" },
  { file: "customers_from_whatsapp.csv", en: "Customers copied from WhatsApp", ar: "زبائن منسوخين من الواتساب" },
  { file: "supplier_prices.csv", en: "Supplier price list (Arabic headers)", ar: "قائمة أسعار مورد (عناوين عربية)" },
];

export default function DataHub() {
  const tx = useTx();
  const locale = useLocale();
  const router = useRouter();
  const { can } = useSession();
  const fileRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [sheet, setSheet] = useState("");
  const uploads = useApiQuery<Upload[]>("/data/uploads");
  const rules = useApiQuery<Rule[]>("/data/rules");
  const delRule = useApiMutation<string>("DELETE", (id) => `/data/rules/${id}`, { invalidate: ["/data/rules"] });

  async function uploadFile(f: File) {
    if (!can("manager")) return toast(tx("Managers and owners can upload data", "رفع البيانات للمدير والمالك بس"), undefined, "info");
    setBusy(f.name);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const u = await api<{ id: string }>("/data/uploads", { method: "POST", body: fd });
      router.push(`/${locale}/app/data/uploads/${u.id}`);
    } catch (e) {
      toast(tx("Upload failed", "فشل الرفع"), (e as Error).message, "error");
      setBusy(null);
    }
  }
  async function uploadBatch(selected: File[]) {
    if (!can("manager")) return toast(tx("Managers and owners can upload data", "رفع البيانات للمدير والمالك بس"), undefined, "info");
    if (selected.length > 8) return toast(tx("Choose up to 8 files", "اختار لحد 8 ملفات"), undefined, "error");
    if (selected.some((file) => file.size > 4 * 1024 * 1024)) return toast(tx("Each file must be 4 MB or smaller", "كل ملف لازم يكون 4 ميغا أو أقل"), undefined, "error");
    setBusy(`0/${selected.length}`);
    try {
      const batch = await api<{ id: string }>("/data/batches", { method: "POST" });
      for (let i = 0; i < selected.length; i += 1) {
        setBusy(`${i + 1}/${selected.length} · ${selected[i].name}`);
        const fd = new FormData();
        fd.append("file", selected[i]);
        await api(`/data/batches/${batch.id}/files`, { method: "POST", body: fd });
      }
      await api(`/data/batches/${batch.id}/finalize`, { method: "POST" });
      router.push(`/${locale}/app/data/batches/${batch.id}`);
    } catch (e) {
      toast(tx("Batch upload failed", "فشل رفع الدفعة"), (e as Error).message, "error");
      setBusy(null);
    }
  }
  function chooseFiles(list: FileList | null) {
    const selected = Array.from(list || []);
    if (selected.length === 1) uploadFile(selected[0]);
    else if (selected.length > 1) uploadBatch(selected);
  }
  async function trySample(file: string) {
    const r = await fetch(`/samples/${file}`);
    const b = await r.blob();
    uploadFile(new File([b], file));
  }
  async function importSheet() {
    setBusy("sheet");
    try {
      const u = await api<{ id: string }>("/data/import-url", { method: "POST", json: { url: sheet } });
      router.push(`/${locale}/app/data/uploads/${u.id}`);
    } catch (e) {
      toast(tx("Couldn't import the sheet", "ما قدرنا نستورد الشيت"), (e as Error).message, "error");
      setBusy(null);
    }
  }

  const status = (s: string) => ({ mapped: [tx("Mapped", "تم الربط"), "sky"], cleaned: [tx("Cleaned · review", "منظّف · للمراجعة"), "saffron"], imported: [tx("Imported", "تم الاستيراد"), "olive"], uploaded: [tx("Uploaded", "مرفوع"), "neutral"] } as Record<string, [string, "sky" | "saffron" | "olive" | "neutral"]>)[s] || [s, "neutral"];

  return (
    <div>
      <PageHeader eyebrow={tx("Data hub", "مركز البيانات")} title={tx("Bring your data. Idrak cleans it.", "جيب بياناتك. إدراك بينظّفها.")}
        subtitle={tx("Upload any export from your POS, Excel or WhatsApp lists — Arabic, English or both. You review every change before anything is saved.", "ارفع أي ملف من الكاشير أو الإكسل أو قوائم الواتساب — عربي أو إنجليزي أو الثنين. بتراجع كل تعديل قبل ما ينحفظ إشي.")}
        actions={<AskIdrak q={tx("How does Idrak clean my data and what does the Health Score mean?", "كيف إدراك بينظّف بياناتي وشو معنى مؤشر صحة البيانات؟")} />} />

      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div data-basira="upload-dropzone"
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); chooseFiles(e.dataTransfer.files); }}
          onClick={() => !busy && fileRef.current?.click()}
          className={clsx("grain flex cursor-pointer flex-col items-center justify-center rounded-[var(--radius-card)] border-2 border-dashed px-6 py-14 text-center transition",
            drag ? "border-terra bg-terra-soft/40" : "border-sand-2 bg-[#FFFCF7] hover:border-terra/50")}>
          <input ref={fileRef} type="file" multiple accept=".xlsx,.xlsm,.csv,.txt" className="hidden" onChange={(e) => chooseFiles(e.target.files)} />
          {busy && busy !== "sheet" ? (
            <><Spinner size={28} /><p className="mt-4 font-serif text-lg text-ink">{tx("Reading", "عم نقرأ")} {busy}…</p><p className="mt-1 text-sm text-ink-3">{tx("Detecting columns (Arabic & English) and mapping them with AI", "عم نكتشف الأعمدة (عربي وإنجليزي) ونربطها بالذكاء الاصطناعي")}</p></>
          ) : (
            <>
              <span className="grid size-14 place-items-center rounded-full bg-terra-soft text-terra"><Files size={26} /></span>
              <p className="mt-4 font-serif text-[22px] text-ink">{tx("Drop one file or a related batch", "اسحب ملف واحد أو مجموعة ملفات مرتبطة")}</p>
              <p className="mt-1 text-sm text-ink-3">{tx("Choose up to 8 files · 4 MB each · Idrak links shared data before import", "اختار لحد 8 ملفات · 4 ميغا للملف · إدراك بيربط البيانات المشتركة قبل الاستيراد")}</p>
            </>
          )}
        </div>
        <div className="space-y-5">
          <Section id="google-sheet-import" title={<span className="inline-flex items-center gap-2"><Link2 size={16} className="text-ink-3" />{tx("Import from Google Sheets", "استيراد من Google Sheets")}</span>}
            subtitle={tx("Share the sheet as “Anyone with the link can view”", "شارك الشيت كـ «أي حدا معه الرابط بيقدر يشوف»")}>
            <div className="flex gap-2">
              <Input dir="ltr" placeholder="https://docs.google.com/spreadsheets/d/…" value={sheet} onChange={(e) => setSheet(e.target.value)} />
              <Button variant="secondary" loading={busy === "sheet"} disabled={!sheet} onClick={importSheet}>{tx("Import", "استيراد")}</Button>
            </div>
          </Section>
          <Section id="sample-files" title={<span className="inline-flex items-center gap-2"><FileSpreadsheet size={16} className="text-ink-3" />{tx("Try a real-world messy file", "جرّب ملف فوضوي من الواقع")}</span>} bodyClass="p-2">
            {SAMPLES.map((s) => (
              <div key={s.file} className="flex items-center justify-between gap-2 rounded-lg px-3 py-2 hover:bg-paper-2">
                <span className="text-[13.5px] text-ink">{tx(s.en, s.ar)}</span>
                <span className="flex shrink-0 items-center gap-1">
                  <a href={`/samples/${s.file}`} download className="rounded p-1.5 text-ink-3 hover:bg-sand hover:text-ink" title={tx("Download", "تنزيل")}><Download size={15} /></a>
                  <Button size="sm" variant="secondary" disabled={!!busy} onClick={() => trySample(s.file)}>{tx("Clean it", "نظّفه")}</Button>
                </span>
              </div>
            ))}
          </Section>
        </div>
      </div>

      <Section id="upload-history" className="mt-6" title={tx("Upload history", "سجل الملفات")} bodyClass="p-0">
        <Table rows={uploads.data} empty={tx("No uploads yet — drop your first file above.", "ما في ملفات لسا — ارفع أول ملف فوق.")}
          onRow={(u) => u.batch_id ? router.push(`/${locale}/app/data/batches/${u.batch_id}`) : (u.last_run_id ? router.push(`/${locale}/app/data/runs/${u.last_run_id}`) : u.has_data && router.push(`/${locale}/app/data/uploads/${u.id}`))}
          cols={[
            { key: "file", label: tx("File", "الملف"), render: (u) => <span className="font-medium text-ink">{u.file_name}</span> },
            { key: "entity", label: tx("Type", "النوع"), render: (u) => <span className="text-ink-2">{({ sales: tx("Sales", "مبيعات"), customers: tx("Customers", "زبائن"), products: tx("Products", "أصناف"), supplier_prices: tx("Supplier prices", "أسعار مورد") } as Record<string, string>)[u.entity] || u.entity}</span> },
            { key: "rows", label: tx("Rows", "الصفوف"), align: "end", render: (u) => <span className="num">{u.row_count.toLocaleString()}</span> },
            { key: "health", label: tx("Health", "الصحة"), render: (u) => u.health_before != null ? <span className="num"><span className="text-danger">{u.health_before.toFixed(0)}</span> <span className="text-ink-3">→</span> <span className="text-olive">{u.health_after?.toFixed(0)}</span></span> : "—" },
            { key: "status", label: tx("Status", "الحالة"), render: (u) => { const [l, t] = status(u.status); return <Badge tone={t}>{l}</Badge>; } },
            { key: "by", label: tx("By", "بواسطة"), render: (u) => <span className="text-ink-3">{u.uploaded_by_name || "—"}</span> },
            { key: "when", label: tx("When", "متى"), render: (u) => <span className="text-ink-3" title={date(u.created_at, locale)}>{timeAgo(u.created_at, locale)}</span> },
          ]} />
      </Section>

      <Section id="cleaning-memory" className="mt-6" title={<span className="inline-flex items-center gap-2"><Brain size={16} className="text-terra" />{tx("Cleaning memory", "ذاكرة التنظيف")}</span>}
        subtitle={tx("Rules Idrak learned from your corrections. They're applied automatically to every new upload.", "قواعد تعلّمها إدراك من تصحيحاتك. بتنطبق تلقائياً على كل ملف جديد.")} bodyClass="p-0">
        <Table rows={rules.data} dense empty={tx("No rules yet. Approve merges or edit a cell during review and Idrak will remember.", "ما في قواعد لسا. وافق على الدمج أو عدّل خلية وقت المراجعة وإدراك رح يتذكر.")}
          cols={[
            { key: "kind", label: tx("Column", "العمود"), render: (r) => <Badge>{r.column_kind}</Badge> },
            { key: "from", label: tx("When we see", "لما نشوف"), render: (r) => <span className="font-mono text-[12.5px] text-danger/90">{r.match_value}</span> },
            { key: "to", label: tx("We write", "منكتب"), render: (r) => <span className="font-mono text-[12.5px] text-olive">{r.replace_value}</span> },
            { key: "n", label: tx("Applied", "انطبقت"), align: "end", render: (r) => <span className="num">{r.times_applied}×</span> },
            { key: "x", label: "", align: "end", render: (r) => can("manager") ? <button onClick={(e) => { e.stopPropagation(); delRule.mutate(r.id); }} className="text-ink-3 hover:text-danger"><Trash2 size={15} /></button> : null },
          ]} />
      </Section>
    </div>
  );
}
