"use client";
import { useParams } from "next/navigation";
import { useRouter } from "@/lib/router";
import { useMemo, useState } from "react";
import clsx from "clsx";
import { AlertTriangle, Brain, Check, CheckCheck, Download, Loader2, Printer, RotateCcw, Undo2, X } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { api, downloadFile } from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { useQueryClient } from "@tanstack/react-query";
import { AskIdrak, ErrorBox, PageHeader, Section } from "@/components/app/kit";
import { Badge, Button, Card, Input, Skeleton, Tabs } from "@/components/ui";
import { toast } from "@/components/ui/toast";
import HealthGauge from "@/components/data/HealthGauge";
import { useSession } from "@/components/app/session";

type Score = { score: number; dimensions: Record<string, number> };
type Issue = { key: string; kind: "fix" | "flag"; title_en: string; title_ar: string; category: string; count: number; examples: { before: string; after: string; column: string }[] };
type Cluster = { column: string; field: string; canonical: string; variants: { value: string; count: number }[]; rows: number };
type Run = {
  id: string; upload_id: string; file_name: string; status: string; entity: string; score_before: Score; score_after: Score; columns: string[];
  stats: { rows_before: number; rows_after: number; issues: Issue[]; clusters: Cluster[]; flag_count: number; memory_hits: number; import?: Record<string, number | string[]>; learned_rules?: number;
    skipped?: { count: number; items: { row: number | null; reason: string; reason_ar: string; data: Record<string, string> }[] };
    branches_created?: string[];
    returns?: { lines: number; invoices: number; value: number; imported?: boolean } };
  rule_status: Record<string, { proposed: number; approved: number; rejected: number }>; totals: { proposed: number; approved: number; rejected: number };
  imported_at: string | null; reverted_at: string | null;
};
type Cell = { v: string; change: { id: string; new_value: string; rule: string; status: string; confidence: number } | null; flag: string | null };
type Grid = { columns: string[]; total: number; rows: { i: number; cells: Cell[]; row_change: { rule: string; new_value: string; status: string } | null }[] };

const DIMS: [string, string, string][] = [["completeness", "Completeness", "الاكتمال"], ["validity", "Validity", "الصلاحية"], ["consistency", "Consistency", "الاتساق"], ["uniqueness", "Uniqueness", "عدم التكرار"], ["timeliness", "Timeliness", "حداثة التواريخ"]];

// What an import wrote (api/app/routers/data.py: apply_run stats), in words.
const IMPORT_LABELS: Record<string, [string, string]> = {
  sales: ["sales", "فاتورة مبيعات"], lines: ["sale lines", "سطر مبيعات"],
  customers: ["customers", "زبون"], customers_updated: ["customers completed", "زبون اكتملت بياناته"],
  products_created: ["new products", "صنف جديد"], products_updated: ["products updated", "صنف انحدّث"],
  products_no_cost: ["products with no cost yet", "صنف لسا بدون كلفة"],
  purchases: ["purchase invoices", "فاتورة شراء"], purchase_lines: ["purchase lines", "سطر شراء"],
  suppliers_created: ["new suppliers", "مورد جديد"], stock_levels: ["stock levels", "رصيد مخزون"],
  payment_other: ["sales with no payment method", "بيعة بدون طريقة دفع"],
};

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const tx = useTx();
  const locale = useLocale();
  const router = useRouter();
  const qc = useQueryClient();
  const { can } = useSession();
  const run = useApiQuery<Run>(`/data/runs/${id}`);
  const [tab, setTab] = useState<"fixes" | "merges" | "grid" | "review">("fixes");
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<{ imported: Record<string, number | string[]>; learned_rules: number; skipped?: { count: number; sample: { row: number | null; reason: string; reason_ar: string; data: Record<string, string> }[] }; branches_created?: string[]; returns?: { lines: number; invoices: number; value: number; imported?: boolean } } | null>(null);
  const r = run.data;
  const refresh = () => qc.invalidateQueries({ predicate: (q) => String(q.queryKey[1] || "").includes(`/data/runs/${id}`) });

  const [deciding, setDeciding] = useState<string | null>(null);
  async function decide(body: Record<string, unknown>) {
    const key = String(body.rule ?? body.group ?? "all") + ":" + String(body.status);
    setDeciding(key);
    try {
      await api(`/data/runs/${id}/decide`, { method: "POST", json: body });
      await qc.invalidateQueries({ predicate: (q) => String(q.queryKey[1] || "").includes(`/data/runs/${id}`) });
    } catch (e) {
      toast(tx("Couldn't save your choice", "ما قدرنا نحفظ اختيارك"), (e as Error).message, "error");
    } finally {
      setDeciding(null);
    }
  }
  async function apply() {
    setBusy("apply");
    try {
      const res = await api<{ imported: Record<string, number | string[]>; learned_rules: number; skipped?: { count: number; sample: { row: number | null; reason: string; reason_ar: string; data: Record<string, string> }[] } }>(`/data/runs/${id}/apply`, { method: "POST" });
      setResult(res);
      refresh();
      qc.invalidateQueries();
      const sk = res.skipped?.count || 0;
      toast(tx("Clean data imported", "تم استيراد البيانات النظيفة"),
        sk ? tx(`${sk} rows were skipped — download the list to fix and re-upload`,
                `انتخطّى ${sk} صفّ — نزّل القائمة وصلحها وارفعها مرة ثانية`)
           : tx(`Idrak learned ${res.learned_rules} new rules`, `إدراك تعلّم ${res.learned_rules} قاعدة جديدة`));
    } catch (e) {
      toast(tx("Import failed", "فشل الاستيراد"), (e as Error).message, "error");
    } finally { setBusy(null); }
  }
  async function undo() {
    setBusy("undo");
    try {
      const res = await api<{ sales_removed: number; customers_removed: number }>(`/data/runs/${id}/undo`, { method: "POST" });
      setResult(null);
      refresh();
      qc.invalidateQueries();
      toast(tx("Import undone", "تم التراجع عن الاستيراد"), tx(`${res.sales_removed} sales and ${res.customers_removed} customers removed`, `انحذفت ${res.sales_removed} عملية بيع و ${res.customers_removed} زبون`), "info");
    } catch (e) {
      toast(tx("Undo failed", "فشل التراجع"), (e as Error).message, "error");
    } finally { setBusy(null); }
  }

  if (run.error) return <ErrorBox error={run.error} retry={() => run.refetch()} />;
  const fixes = r?.stats.issues.filter((i) => i.kind === "fix") || [];
  const flags = r?.stats.issues.filter((i) => i.kind === "flag") || [];
  const imported = !!r?.imported_at && !r?.reverted_at;
  const totalFixes = r ? r.totals.proposed + r.totals.approved + r.totals.rejected : 0;

  return (
    <div>
      <PageHeader eyebrow={tx("Step 2 of 2 · Review & apply", "خطوة 2 من 2 · راجع وطبّق")} title={r?.file_name || <Skeleton className="h-8 w-64" />}
        subtitle={tx("Nothing is saved until you apply. Every change is explained and reversible.", "ما في إشي بينحفظ قبل ما تطبّق. كل تعديل مشروح وبتقدر تتراجع عنه.")}
        actions={r && (
          <>
            <Button variant="ghost" onClick={() => window.print()} className="no-print"><Printer size={15} />{tx("Report", "تقرير")}</Button>
            {imported
              ? <Button variant="secondary" onClick={undo} loading={busy === "undo"} data-basira="undo-button" disabled={!can("manager")}><Undo2 size={15} />{tx("Undo import", "تراجع عن الاستيراد")}</Button>
              : <Button size="lg" onClick={apply} loading={busy === "apply"} data-basira="apply-button" disabled={!can("manager")}><CheckCheck size={16} />{tx("Apply & import", "طبّق واستورد")}</Button>}
          </>
        )} />

      <Card data-basira="health-score" className="grain overflow-hidden">
        <div className="grid gap-6 p-6 lg:grid-cols-[auto_1fr_auto] lg:items-center">
          <div className="flex flex-col items-center">
            {r ? <HealthGauge from={r.score_before.score} to={r.score_after.score} label={tx("Data Health Score", "مؤشر صحة البيانات")} /> : <Skeleton className="h-40 w-64" />}
            {r && <p className="num mt-2 text-sm text-ink-3"><span className="text-danger">{r.score_before.score.toFixed(1)}</span> → <span className="text-olive">{r.score_after.score.toFixed(1)}</span></p>}
          </div>
          <div className="space-y-3">
            {DIMS.map(([k, en, ar]) => (
              <div key={k}>
                <div className="mb-1 flex justify-between text-[12.5px]"><span className="text-ink-2">{tx(en, ar)}</span>
                  <span className="num text-ink-3">{r ? `${r.score_before.dimensions[k]?.toFixed(0)} → ${r.score_after.dimensions[k]?.toFixed(0)}` : ""}</span></div>
                <div className="relative h-2 overflow-hidden rounded-full bg-sand">
                  <div className="absolute inset-y-0 start-0 rounded-full bg-terra/35" style={{ width: `${r?.score_after.dimensions[k] ?? 0}%` }} />
                  <div className="absolute inset-y-0 start-0 rounded-full bg-terra" style={{ width: `${r?.score_before.dimensions[k] ?? 0}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-4 lg:grid-cols-1">
            <Fig n={totalFixes} l={tx("fixes proposed", "تعديل مقترح")} />
            <Fig n={r ? r.stats.rows_before - r.stats.rows_after : 0} l={tx("duplicate / empty rows", "صف مكرر أو فاضي")} />
            <Fig n={r?.stats.clusters.length || 0} l={tx("value groups merged", "مجموعة قيم مدموجة")} />
            <Fig n={r?.stats.memory_hits || 0} l={tx("fixed from memory", "تصحيح من الذاكرة")} icon={<Brain size={14} className="text-terra" />} />
          </div>
        </div>
        {(result || (imported && r?.stats.import)) && (
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line bg-olive-soft/60 px-6 py-3 text-[13.5px] text-olive">
            <span className="font-medium"><Check size={15} className="me-1 inline" />{tx("Imported into your workspace", "انضافت لمساحة شغلك")}</span>
            {Object.entries(result?.imported || r?.stats.import || {}).map(([k, v]) => {
              // Counts only; lists (suppliers_created) show as a count.
              const n = Array.isArray(v) ? v.length : typeof v === "number" ? v : 0;
              if (!n) return null;
              const l = IMPORT_LABELS[k];
              return <span key={k}><b className="num">{n.toLocaleString()}</b> {l ? tx(l[0], l[1]) : k.replace(/_/g, " ")}</span>;
            })}
            <span>{tx("Rules learned", "قواعد متعلّمة")}: <b className="num">{result?.learned_rules ?? r?.stats.learned_rules ?? 0}</b></span>
            <button onClick={() => router.push(`/${locale}/app`)} className="ms-auto underline">{tx("See it on the dashboard →", "شوفها على لوحة التحكم ←")}</button>
          </div>
        )}
        {(() => {
          const ret = result?.returns ?? r?.stats.returns;
          if (!ret || !ret.invoices) return null;
          return (
            <div className="border-t border-saffron/40 bg-saffron/10 px-6 py-3 text-[13.5px] text-ink">
              <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
                <AlertTriangle size={15} className="mt-0.5 text-saffron" />
                <div className="min-w-0">
                  {ret.imported ? (
                    <>
                      <p className="font-medium">
                        {tx(`${ret.invoices} return invoices imported as returns (${ret.value.toFixed(3)} JD)`,
                            `${ret.invoices} فاتورة مرتجع انستوردت كمرتجعات (${ret.value.toFixed(3)} د.أ)`)}
                      </p>
                      <p className="mt-0.5 text-ink-3">
                        {tx("Rows with a negative quantity are returns. They're kept apart from sales so revenue stays clean, and shown on the dashboard and in the sales list as \"Returned\".",
                            "الأسطر اللي كميتها سالبة هي مرتجعات. انحفظت لحالها بعيد عن المبيعات عشان الإيراد يضل نظيف، وبتطلع على لوحة التحكم وبقائمة المبيعات كـ\"مرتجعة\".")}
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="font-medium">
                        {tx(`${ret.invoices} return invoices were not imported (${ret.value.toFixed(0)} JD)`,
                            `${ret.invoices} فاتورة مرتجع ما انستوردت (${ret.value.toFixed(0)} د.أ)`)}
                      </p>
                      <p className="mt-0.5 text-ink-3">
                        {tx("Their quantity is negative and would flip revenue and profit. Everything else was imported normally — but because returns are outside the numbers, sales and profit read slightly higher than reality.",
                            "كمياتها سالبة وبتقلب الإيراد والربح، فتركناهم برّا. باقي الملف انستورد عادي — بس لأن المرتجعات مش محسوبة، المبيعات والربح بيطلعوا أعلى من الواقع شوي.")}
                      </p>
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })()}
        {(() => {
          const created = result?.branches_created ?? r?.stats.branches_created ?? [];
          if (!created.length) return null;
          return (
            <div className="border-t border-sky/30 bg-sky/10 px-6 py-3 text-[13.5px] text-ink">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <Check size={15} className="text-sky" />
                <span className="font-medium">{tx(`${created.length} new branches were added to your workspace`, `انضاف ${created.length} فرع جديد لمساحة شغلك`)}</span>
                <span className="text-ink-3">{tx("They were not defined before; each sale in the file created one. Rename them in Settings → Branches if the spelling isn't how you'd write it.",
                                                    "ما كانوا معرَّفين قبل، وكل فرع ظهر بالملف انفتح تلقائياً. غيّر اسمائهم من الإعدادات → الفروع إذا الإملاء مش زي ما بتحبّه.")}</span>
                <button onClick={() => router.push(`/${locale}/app/settings/branches`)} className="ms-auto underline">{tx("Manage branches →", "إدارة الفروع ←")}</button>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {created.map((b, i) => <Badge key={i}>{b}</Badge>)}
              </div>
            </div>
          );
        })()}
        {(() => {
          const sk = result?.skipped?.count ?? r?.stats.skipped?.count ?? 0;
          if (!sk) return null;
          const sample = result?.skipped?.sample ?? r?.stats.skipped?.items ?? [];
          return (
            <div className="border-t border-saffron/40 bg-saffron/10 px-6 py-3 text-[13.5px] text-ink">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <AlertTriangle size={15} className="text-saffron" />
                <span className="font-medium">{tx(`${sk} rows were skipped`, `انتخطّى ${sk} صفّ`)}</span>
                <span className="text-ink-3">{tx("The clean rows were imported. Download the list below, fix the issues, and re-upload just the fixed rows.",
                                                "الصفوف السليمة انستوردت. نزّل القائمة تحت، صلّح الأخطاء، وارفع بس الصفوف المصلّحة.")}</span>
                <button onClick={async () => {
                  try { await downloadFile(`/data/runs/${id}/skipped.csv`, `skipped_${id.slice(0, 8)}.csv`); }
                  catch (e) { toast(tx("Couldn't download", "ما قدرنا ننزّل"), (e as Error).message, "error"); }
                }} className="ms-auto inline-flex items-center gap-1 rounded-md border border-saffron/50 bg-sand px-3 py-1 text-saffron hover:bg-saffron/15">
                  <Download size={14} />{tx("Download skipped rows (CSV)", "نزّل الصفوف المتخطّاة (CSV)")}
                </button>
              </div>
              {sample.length > 0 && (
                <ul className="mt-2 list-disc ps-5 text-[12.5px] text-ink-2">
                  {sample.slice(0, 5).map((it, i) => (
                    <li key={i}><span className="num">#{(it.row ?? 0) + 1}</span> — {tx(it.reason, it.reason_ar)}</li>
                  ))}
                  {sk > 5 && <li className="text-ink-3">{tx(`… and ${sk - 5} more`, `… و${sk - 5} غيرها`)}</li>}
                </ul>
              )}
            </div>
          );
        })()}
      </Card>

      <div className="no-print mt-6 flex flex-wrap items-center justify-between gap-3">
        <Tabs value={tab} onChange={setTab} items={[
          { value: "fixes", label: `${tx("Fixes", "التعديلات")} (${fixes.length})` },
          { value: "merges", label: `${tx("Merged values", "القيم المدموجة")} (${r?.stats.clusters.length ?? 0})` },
          { value: "grid", label: tx("Before / after", "قبل / بعد") },
          { value: "review", label: `${tx("Needs your eye", "بدها نظرة منك")} (${r?.stats.flag_count ?? 0})` },
        ]} />
        <AskIdrak q={tx("Explain the main problems Idrak found in this file and which ones I should check myself.", "اشرحلي أهم المشاكل اللي لقاها إدراك بهالملف وأي وحدة لازم أراجعها بنفسي.")} />
      </div>

      <div className="mt-4">
        {tab === "fixes" && (
          <div data-basira="issues-list" className="grid gap-3 md:grid-cols-2">
            {!r && Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-36" />)}
            {fixes.map((i) => {
              const st = r!.rule_status[i.key] || { proposed: 0, approved: 0, rejected: 0 };
              const rejected = st.rejected > 0 && st.rejected >= st.proposed + st.approved;
              return (
                <Card key={i.key} className={clsx("p-4 transition", rejected && "opacity-55")}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-ink">{tx(i.title_en, i.title_ar)}</p>
                      <p className="mt-0.5 text-[12.5px] text-ink-3"><span className="num">{i.count.toLocaleString()}</span> {tx("cells", "خلية")} · <Badge tone={i.category === "merge" ? "terra" : i.category === "fix" ? "saffron" : i.category === "dedupe" ? "sky" : i.category === "memory" ? "olive" : "neutral"}>{i.category}</Badge></p>
                    </div>
                    {!imported && can("manager") && (
                      <div className="flex shrink-0 gap-1">
                        <button title={tx("Keep", "اعتمد")} disabled={!!deciding} onClick={() => decide({ rule: i.key, status: "approved" })} className={clsx("grid size-8 disabled:opacity-60 place-items-center rounded-full border", st.approved ? "border-olive bg-olive text-paper" : "border-line text-ink-3 hover:border-olive hover:text-olive")}>{deciding === `${i.key}:approved` ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}</button>
                        <button title={tx("Skip", "تجاهل")} disabled={!!deciding} onClick={() => decide({ rule: i.key, status: rejected ? "proposed" : "rejected" })} className={clsx("grid size-8 place-items-center rounded-full border disabled:opacity-60", rejected ? "border-danger bg-danger text-paper" : "border-line text-ink-3 hover:border-danger hover:text-danger")}>{deciding?.startsWith(`${i.key}:`) && !deciding.endsWith("approved") ? <Loader2 size={15} className="animate-spin" /> : rejected ? <RotateCcw size={14} /> : <X size={15} />}</button>
                      </div>
                    )}
                  </div>
                  <div className="mt-3 space-y-1.5">
                    {i.examples.map((e, k) => (
                      <div key={k} className="flex flex-wrap items-center gap-2 font-mono text-[12px]">
                        <span className="max-w-[46%] truncate rounded bg-[#f6d9d3]/60 px-1.5 py-0.5 text-danger line-through decoration-danger/40">{e.before || "∅"}</span>
                        <span className="text-ink-3 rtl:rotate-180">→</span>
                        <span className="max-w-[46%] truncate rounded bg-olive-soft px-1.5 py-0.5 text-olive">{e.after || "∅"}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              );
            })}
          </div>
        )}

        {tab === "merges" && r && <Merges clusters={r.stats.clusters} onDecide={decide} disabled={imported || !can("manager")} />}
        {tab === "grid" && <DiffGrid runId={id} editable={!imported && can("manager")} onChanged={refresh} />}
        {tab === "review" && (
          <div className="grid gap-3 md:grid-cols-2">
            {flags.length === 0 && <Card className="p-8 text-center text-ink-3">{tx("Nothing needs manual review.", "ما في إشي بحاجة مراجعة يدوية.")}</Card>}
            {flags.map((f) => (
              <Card key={f.key} className="p-4">
                <p className="flex items-center gap-2 font-medium text-ink"><AlertTriangle size={16} className="text-saffron" />{tx(f.title_en, f.title_ar)} <span className="num text-ink-3">· {f.count}</span></p>
                <p className="mt-1 text-[12.5px] text-ink-3">{tx("Idrak won't guess these. Fix them in the before/after grid or at the source.", "إدراك ما بيخمّن هدول. صلّحهم من جدول قبل/بعد أو من المصدر.")}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">{f.examples.map((e, k) => <span key={k} className="rounded bg-saffron-soft px-1.5 py-0.5 font-mono text-[12px] text-[#8a5d0e]">{e.column}: {e.before || "∅"}</span>)}</div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Fig({ n, l, icon }: { n: number; l: string; icon?: React.ReactNode }) {
  return <div><p className="num flex items-center gap-1.5 text-[24px] leading-none text-ink">{icon}{n.toLocaleString()}</p><p className="mt-1 text-[12px] text-ink-3">{l}</p></div>;
}

function Merges({ clusters, onDecide, disabled }: { clusters: Cluster[]; onDecide: (b: Record<string, unknown>) => void; disabled: boolean }) {
  const tx = useTx();
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {clusters.map((c) => {
        const key = `${c.column}::${c.canonical}`;
        const off = skipped.has(key);
        return (
          <Card key={key} className={clsx("p-4", off && "opacity-50")}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-[11.5px] uppercase tracking-wider text-ink-3">{c.column}</p>
                <p className="mt-0.5 truncate font-medium text-ink">{c.canonical}</p>
              </div>
              <span className="num shrink-0 text-[12px] text-ink-3">{c.rows} {tx("rows", "صف")}</span>
            </div>
            <ul className="mt-3 space-y-1">
              {c.variants.slice(0, 7).map((v) => (
                <li key={v.value} className="flex items-center justify-between gap-2 text-[12.5px]">
                  <span className={clsx("truncate font-mono", v.value === c.canonical ? "text-olive" : "text-ink-2")}>{v.value}</span>
                  <span className="num text-ink-3">{v.count}</span>
                </li>
              ))}
              {c.variants.length > 7 && <li className="text-[12px] text-ink-3">+{c.variants.length - 7} {tx("more", "كمان")}</li>}
            </ul>
            {!disabled && (
              <button onClick={() => { const n = new Set(skipped); if (off) { n.delete(key); onDecide({ group: key, status: "proposed" }); } else { n.add(key); onDecide({ group: key, status: "rejected" }); } setSkipped(n); }}
                className="mt-3 text-[12.5px] text-ink-3 underline-offset-4 hover:text-terra hover:underline">{off ? tx("Merge again", "ادمج مرة ثانية") : tx("Don't merge these", "لا تدمج هدول")}</button>
            )}
          </Card>
        );
      })}
    </div>
  );
}

function DiffGrid({ runId, editable, onChanged }: { runId: string; editable: boolean; onChanged: () => void }) {
  const tx = useTx();
  const [offset, setOffset] = useState(0);
  const [onlyChanged, setOnlyChanged] = useState(true);
  const [edit, setEdit] = useState<{ row: number; col: string; value: string } | null>(null);
  const grid = useApiQuery<Grid>(`/data/runs/${runId}/grid?offset=${offset}&limit=60&only_changed=${onlyChanged}`);
  const g = grid.data;
  const save = async () => {
    if (!edit) return;
    const res = await api<{ learned: boolean }>(`/data/runs/${runId}/edit`, { method: "POST", json: { row: edit.row, column: edit.col, value: edit.value, remember: true } });
    toast(tx("Saved", "انحفظ"), res.learned ? tx("Idrak will remember this correction", "إدراك رح يتذكر هالتصحيح") : undefined);
    setEdit(null);
    grid.refetch();
    onChanged();
  };
  const legend = useMemo(() => (
    <div className="flex flex-wrap items-center gap-3 text-[12px] text-ink-3">
      <span className="flex items-center gap-1.5"><span className="size-3 rounded bg-olive-soft" />{tx("changed", "متغيّر")}</span>
      <span className="flex items-center gap-1.5"><span className="size-3 rounded bg-saffron-soft" />{tx("needs review", "بدها مراجعة")}</span>
      <span className="flex items-center gap-1.5"><span className="size-3 rounded bg-[#f6d9d3]" />{tx("row removed", "صف محذوف")}</span>
    </div>
  ), [tx]);
  return (
    <Section id="diff-grid" title={tx("Before / after", "قبل / بعد")} subtitle={editable ? tx("Click any cell to correct it — Idrak learns from your edits.", "اضغط على أي خلية لتصحيحها — إدراك بيتعلم من تعديلاتك.") : undefined}
      action={<label className="flex items-center gap-2 text-[13px] text-ink-2"><input type="checkbox" checked={onlyChanged} onChange={(e) => { setOffset(0); setOnlyChanged(e.target.checked); }} />{tx("Only changed rows", "الصفوف المتغيرة بس")}</label>} bodyClass="p-0">
      <div className="px-5 py-3">{legend}</div>
      <div className="max-h-[560px] overflow-auto border-t border-line">
        {!g ? <div className="p-5"><Skeleton className="h-64" /></div> : (
          <table className="w-full text-[12.5px]">
            <thead className="sticky top-0 z-10 bg-paper-2"><tr>
              <th className="px-3 py-2 text-start font-medium text-ink-3">#</th>
              {g.columns.map((c) => <th key={c} className="whitespace-nowrap px-3 py-2 text-start font-medium text-ink-3">{c}</th>)}
            </tr></thead>
            <tbody>
              {g.rows.map((row) => {
                const removed = row.row_change && row.row_change.status !== "rejected";
                return (
                  <tr key={row.i} className={clsx("border-b border-line/50 align-top", removed && "bg-[#f6d9d3]/40")}>
                    <td className="num px-3 py-1.5 text-ink-3">{row.i + 2}{removed && <span className="block text-[10.5px] text-danger">{row.row_change!.rule === "duplicate_row" ? tx("duplicate", "مكرر") : tx("empty", "فاضي")}</span>}</td>
                    {row.cells.map((c, ci) => {
                      const ch = c.change && c.change.status !== "rejected" ? c.change : null;
                      const col = g.columns[ci];
                      const isEdit = edit && edit.row === row.i && edit.col === col;
                      return (
                        <td key={ci} onClick={() => editable && !isEdit && setEdit({ row: row.i, col, value: ch ? ch.new_value : c.v })}
                          className={clsx("max-w-[220px] px-3 py-1.5 font-mono", ch && "bg-olive-soft/70", c.flag && !ch && "bg-saffron-soft/70", editable && "cursor-text hover:outline hover:outline-1 hover:outline-terra/40")}>
                          {isEdit ? (
                            <div className="flex items-center gap-1">
                              <Input autoFocus value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })} onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setEdit(null); }} className="h-7 text-[12px]" />
                              <button onClick={(e) => { e.stopPropagation(); save(); }} className="text-olive"><Check size={14} /></button>
                            </div>
                          ) : ch ? (
                            <>
                              <span className="block truncate text-[11px] text-ink-3 line-through">{c.v || "∅"}</span>
                              <span className="block truncate text-olive" title={ch.rule}>{ch.new_value || "∅"}</span>
                            </>
                          ) : (
                            <span className="block truncate text-ink-2" title={c.flag || undefined}>{c.v}{c.flag && <AlertTriangle size={11} className="ms-1 inline text-saffron" />}</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      {g && (
        <div className="flex items-center justify-between border-t border-line px-5 py-3 text-[13px] text-ink-3">
          <span className="num">{offset + 1}–{Math.min(offset + 60, g.total)} / {g.total}</span>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 60))}>{tx("Previous", "السابق")}</Button>
            <Button size="sm" variant="secondary" disabled={offset + 60 >= g.total} onClick={() => setOffset(offset + 60)}>{tx("Next", "التالي")}</Button>
          </div>
        </div>
      )}
    </Section>
  );
}

