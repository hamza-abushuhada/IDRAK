"use client";
import { useParams } from "next/navigation";
import { useRouter } from "@/lib/router";
import { useEffect, useState } from "react";
import { Sparkles, Wand2 } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { api } from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { ErrorBox, PageHeader, Section } from "@/components/app/kit";
import { Badge, Button, Select, Skeleton } from "@/components/ui";
import { toast } from "@/components/ui/toast";

type Upload = {
  id: string; file_name: string; entity: string; row_count: number; column_count: number; columns: string[];
  mapping: Record<string, { field: string | null; confidence: number; source: string | null; reason?: string }>;
  preview: unknown[][]; fields: { key: string; kind: string; en: string; ar: string }[]; entity_label: [string, string]; last_run_id: string | null;
};

export default function MappingPage() {
  const { id } = useParams<{ id: string }>();
  const tx = useTx();
  const locale = useLocale();
  const router = useRouter();
  const q = useApiQuery<Upload>(`/data/uploads/${id}`);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [cleaning, setCleaning] = useState(false);
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    if (q.data) setMapping(Object.fromEntries(q.data.columns.map((c) => [c, q.data!.mapping[c]?.field ?? null])));
  }, [q.data]);
  useEffect(() => {
    if (!cleaning) return;
    const t = setInterval(() => setPhase((p) => Math.min(p + 1, 5)), 700);
    return () => clearInterval(t);
  }, [cleaning]);

  if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;
  const u = q.data;
  const label = (k: string) => { const f = u?.fields.find((x) => x.key === k); return f ? tx(f.en, f.ar) : k; };

  async function clean() {
    setCleaning(true);
    try {
      await api(`/data/uploads/${id}/mapping`, { method: "PUT", json: { mapping } });
      const run = await api<{ id: string }>(`/data/uploads/${id}/clean`, { method: "POST" });
      router.push(`/${locale}/app/data/runs/${run.id}`);
    } catch (e) {
      toast(tx("Cleaning failed", "فشل التنظيف"), (e as Error).message, "error");
      setCleaning(false);
    }
  }

  const phases = [tx("Normalizing Arabic spelling & digits", "توحيد التهجئة العربية والأرقام"), tx("Reading 7 date formats incl. Hijri & Excel", "قراءة 7 صيغ تواريخ منها الهجري وإكسل"),
    tx("Fixing prices typed in fils", "تصحيح الأسعار المكتوبة بالفلس"), tx("Matching products to your catalog (عربي ⇄ English)", "مطابقة الأصناف مع قائمتك (عربي ⇄ إنجليزي)"),
    tx("Standardizing phones to +962", "توحيد الهواتف بصيغة 962+"), tx("Scoring data health", "حساب صحة البيانات")];

  return (
    <div>
      <PageHeader eyebrow={tx("Step 1 of 2 · Map columns", "خطوة 1 من 2 · ربط الأعمدة")} title={u ? u.file_name : <Skeleton className="h-8 w-64" />}
        subtitle={u ? tx(`${u.row_count.toLocaleString()} rows · ${u.column_count} columns · detected: ${u.entity_label[0]}`, `${u.row_count.toLocaleString()} صف · ${u.column_count} عمود · نوع الملف: ${u.entity_label[1]}`) : undefined}
        actions={<Button size="lg" onClick={clean} loading={cleaning} disabled={!u} data-basira="clean-button"><Wand2 size={16} />{tx("Clean with Idrak", "نظّف بإدراك")}</Button>} />

      {cleaning && (
        <div className="mb-6 rounded-[var(--radius-card)] border border-line bg-cocoa px-6 py-5 font-mono text-[13px] text-[#EDE3D4]">
          {phases.slice(0, phase + 1).map((p, i) => (
            <p key={p} className="flex gap-2"><span className={i < phase ? "text-olive" : "animate-pulse text-saffron"}>●</span>{p}{i < phase && <span className="text-[#8f7f70]"> ✓</span>}</p>
          ))}
        </div>
      )}

      <Section title={tx("How Idrak read your columns", "كيف إدراك فهم أعمدتك")} subtitle={tx("Check the mapping. AI suggestions are marked — change anything that's wrong.", "راجع الربط. اقتراحات الذكاء الاصطناعي معلّمة — غيّر أي إشي مش مزبوط.")} bodyClass="p-0">
        {!u ? <div className="space-y-2 p-5">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10" />)}</div> : (
          <div className="divide-y divide-line/70">
            {u.columns.map((c, ci) => {
              const m = u.mapping[c];
              const samples = u.preview.map((r) => r[ci]).filter((v) => v !== null && v !== "").slice(0, 4);
              return (
                <div key={c} className="grid items-center gap-3 px-5 py-3 md:grid-cols-[1.1fr_1.6fr_1fr]">
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{c}</p>
                    <p className="mt-0.5 flex items-center gap-1.5 text-[12px] text-ink-3">
                      {m?.source === "ai" ? <Badge tone="terra"><Sparkles size={11} />AI · {Math.round((m.confidence || 0) * 100)}%</Badge> : m?.field ? <Badge tone="olive">{tx("Recognized", "معروف")}</Badge> : <Badge>{tx("Not used", "غير مستخدم")}</Badge>}
                      {m?.reason && <span className="truncate">{m.reason}</span>}
                    </p>
                  </div>
                  <div className="flex min-w-0 flex-wrap gap-1.5">
                    {samples.map((s, i) => <span key={i} className="max-w-[180px] truncate rounded-md bg-paper-2 px-2 py-0.5 font-mono text-[12px] text-ink-2">{String(s)}</span>)}
                  </div>
                  <Select value={mapping[c] ?? ""} onChange={(e) => setMapping({ ...mapping, [c]: e.target.value || null })} className="w-full">
                    <option value="">{tx("— don't use —", "— لا تستخدم —")}</option>
                    {u.fields.map((f) => <option key={f.key} value={f.key}>{label(f.key)}</option>)}
                  </Select>
                </div>
              );
            })}
          </div>
        )}
      </Section>

      {u && (
        <Section className="mt-6" title={tx("Raw preview (as uploaded)", "معاينة الملف كما هو")} bodyClass="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead><tr className="border-b border-line text-ink-3">{u.columns.map((c) => <th key={c} className="whitespace-nowrap px-3 py-2 text-start font-medium">{c}</th>)}</tr></thead>
              <tbody>{u.preview.slice(0, 12).map((r, i) => <tr key={i} className="border-b border-line/50">{u.columns.map((_, j) => <td key={j} className="whitespace-nowrap px-3 py-1.5 font-mono text-ink-2">{r[j] === null ? "" : String(r[j])}</td>)}</tr>)}</tbody>
            </table>
          </div>
        </Section>
      )}
    </div>
  );
}
