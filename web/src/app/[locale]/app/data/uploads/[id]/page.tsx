"use client";
import { useParams } from "next/navigation";
import { useRouter } from "@/lib/router";
import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { AlertTriangle, Check, ScanSearch, Sparkles, Wand2 } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { api } from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { ErrorBox, PageHeader, Section } from "@/components/app/kit";
import { Badge, Button, Skeleton } from "@/components/ui";
import { toast } from "@/components/ui/toast";

// ما يقوله شكل القيم عن العمود (api/app/cleaning/profile.py).
type Evidence = { type: "mismatch" | "discovered"; kind: string; share: number };
type Upload = {
  id: string; file_name: string; entity: string; row_count: number; column_count: number; columns: string[];
  mapping: Record<string, {
    field: string | null; confidence: number; source: string | null; reason?: string;
    review?: boolean; evidence?: Evidence | null;
  }>;
  preview: unknown[][]; fields: { key: string; kind: string; en: string; ar: string }[]; entity_label: [string, string]; last_run_id: string | null;
};

// أنواع القيم كما تظهر للمستخدم، بمفاتيح profile.py.
const KINDS: Record<string, [string, string]> = {
  phone: ["phone numbers", "أرقام هواتف"], email: ["emails", "إيميلات"], time: ["times", "أوقات"],
  date: ["dates", "تواريخ"], payment: ["payment methods", "طرق دفع"], city: ["city names", "أسماء مدن"],
  barcode: ["barcodes", "باركودات"], gender: ["gender values", "قيم جنس"], money: ["amounts", "مبالغ"],
  quantity: ["numbers", "أرقام"], person: ["names", "أسماء"], product: ["item names", "أسماء أصناف"],
  branch: ["branch names", "أسماء فروع"], category: ["categories", "فئات"], company: ["company names", "أسماء شركات"],
  area: ["area names", "أسماء مناطق"],
};

function FieldPicker({ value, options, labelOf, onChange }: {
  value: string; options: { key: string }[]; labelOf: (k: string) => string; onChange: (v: string | null) => void;
}) {
  const tx = useTx();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const current = value ? labelOf(value) : tx("— don't use —", "— لا تستخدم —");
  // التصفية تعمل على الاسم العربي والإنجليزي ومفتاح الحقل معاً، فيكفي
  // يكتب "خصم" أو "discount" ويلاقيه فوراً.
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return options;
    return options.filter((f) => `${labelOf(f.key)} ${f.key}`.toLowerCase().includes(s));
  }, [q, options, labelOf]);
  return (
    <div className="relative">
      <input
        value={open ? q : current}
        placeholder={tx("Type to search…", "اكتب للبحث…")}
        onFocus={() => { setQ(""); setOpen(true); }}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
          if (e.key === "Enter" && filtered.length) { onChange(filtered[0].key); setOpen(false); }
        }}
        className="h-9 w-full rounded-lg border border-line bg-paper px-3 text-[13px] text-ink outline-none placeholder:text-ink-3 focus:border-terra/60 focus:ring-2 focus:ring-terra/15"
      />
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute z-50 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-line bg-paper shadow-[var(--shadow-lift)]">
            <button type="button" onClick={() => { onChange(null); setOpen(false); }}
              className="block w-full px-3 py-1.5 text-start text-[12.5px] text-ink-3 hover:bg-sand">
              {tx("— don't use —", "— لا تستخدم —")}
            </button>
            {filtered.map((f) => (
              <button key={f.key} type="button" onClick={() => { onChange(f.key); setOpen(false); }}
                className={clsx("block w-full px-3 py-1.5 text-start text-[12.5px] hover:bg-sand",
                  f.key === value ? "font-medium text-ink" : "text-ink-2")}>
                {labelOf(f.key)}
              </button>
            ))}
            {!filtered.length && (
              <p className="px-3 py-2 text-[12px] text-ink-3">
                {tx("No field matches that name — leave the column out or rename it in the file.",
                    "ما في حقل بهذا الاسم — خلّي العمود برّا أو غيّر اسمه بالملف.")}
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function MappingPage() {
  const { id } = useParams<{ id: string }>();
  const tx = useTx();
  const locale = useLocale();
  const router = useRouter();
  const q = useApiQuery<Upload>(`/data/uploads/${id}`);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
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
  // أعمدة إدراك مش متأكد منها ولسا ما انراجعت. إذا المستخدم أكّدها أو غيّر
  // حقلها تعتبر مراجَعة. التنظيف ينتظر حتى تخلص، لأن ربطاً غلطاً يمرّ بصمت
  // (مورد مقروء كزبون) يخرّب الأرقام بعد الاستيراد.
  const pending = u ? u.columns.filter((c) => u.mapping[c]?.review && !confirmed[c]
    && (mapping[c] ?? null) === (u.mapping[c]?.field ?? null)) : [];
  const why = (e: Evidence) => {
    const [en, ar] = KINDS[e.kind] ?? [e.kind, e.kind];
    const pct = Math.round(e.share * 100);
    return e.type === "discovered"
      ? tx(`${pct}% of the values look like ${en}`, `${pct}% من القيم تشبه ${ar}`)
      : tx(`Only ${pct}% of the values look like ${en}`, `${pct}% بس من القيم تشبه ${ar}`);
  };
  const columnsAr = (n: number) => (n === 1 ? "عمود واحد" : n === 2 ? "عمودين" : n <= 10 ? `${n} أعمدة` : `${n} عمود`);

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
        actions={<Button size="lg" onClick={clean} loading={cleaning} disabled={!u || pending.length > 0} data-basira="clean-button"
          title={pending.length ? tx("Check the yellow columns first", "راجع الأعمدة الصفراء أولاً") : undefined}>
          <Wand2 size={16} />{tx("Clean with Idrak", "نظّف بإدراك")}</Button>} />

      {u && pending.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-card)] border border-saffron/40 bg-saffron-soft px-5 py-3.5">
          <p className="flex items-center gap-2 text-[13.5px] text-[#8a5d0e]">
            <AlertTriangle size={16} className="shrink-0" />
            {tx(`Idrak isn't sure about ${pending.length} column${pending.length === 1 ? "" : "s"} (marked in yellow). Check them before cleaning.`,
                `إدراك مش متأكد من ${columnsAr(pending.length)} (معلّمة بالأصفر). راجعها قبل التنظيف.`)}
          </p>
          <Button size="sm" variant="secondary" onClick={() => setConfirmed({ ...confirmed, ...Object.fromEntries(pending.map((c) => [c, true])) })}>
            <Check size={14} />{tx("They all look right", "كلها صحيحة")}
          </Button>
        </div>
      )}

      {cleaning && (
        <div className="mb-6 rounded-[var(--radius-card)] border border-line bg-cocoa px-6 py-5 font-mono text-[13px] text-[#EDE3D4]">
          {phases.slice(0, phase + 1).map((p, i) => (
            <p key={p} className="flex gap-2"><span className={i < phase ? "text-olive" : "animate-pulse text-saffron"}>●</span>{p}{i < phase && <span className="text-[#8f7f70]"> ✓</span>}</p>
          ))}
        </div>
      )}

      <Section title={tx("How Idrak read your columns", "كيف إدراك فهم أعمدتك")} subtitle={tx("Idrak reads each column's name and its values. Columns it isn't sure about are in yellow — change anything that's wrong.", "إدراك بيقرأ اسم كل عمود وقيمه. الأعمدة اللي مش متأكد منها بالأصفر — غيّر أي إشي مش مزبوط.")} bodyClass="p-0">
        {!u ? <div className="space-y-2 p-5">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10" />)}</div> : (
          <div className="divide-y divide-line/70">
            {u.columns.map((c, ci) => {
              const m = u.mapping[c];
              const samples = u.preview.map((r) => r[ci]).filter((v) => v !== null && v !== "").slice(0, 4);
              const chosen = mapping[c] ?? "";
              // حقول أخرى استُخدمت بأعمدة تانية — نخفيها من القائمة.
              // القائمة كانت ٣٠ خياراً بلا سياق، والشخص يختار واحداً
              // ويطلع الحقل محجوزاً أصلاً.
              const takenBy = (field: string) => Object.entries(mapping).find(([col, f]) => col !== c && f === field)?.[0];
              const options = u.fields.filter((f) => f.key === chosen || !takenBy(f.key));
              const remembered = m?.source === "memory";
              const unusedWithData = !chosen && samples.length > 0;
              const isPending = pending.includes(c);
              const reason = m?.evidence ? why(m.evidence)
                : m?.reason || (isPending ? tx("Not sure about this match", "إدراك مش متأكد من هالربط") : null);
              return (
                <div key={c} className={clsx("grid items-center gap-3 px-5 py-3 md:grid-cols-[1.1fr_1.6fr_1fr]", isPending && "bg-saffron-soft/50")}>
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{c}</p>
                    <p className="mt-0.5 flex items-center gap-1.5 text-[12px] text-ink-3">
                      {remembered ? <Badge tone="olive">{tx("Your saved mapping", "ربطك المحفوظ")}</Badge>
                        : isPending ? <Badge tone="saffron"><AlertTriangle size={11} />{tx("Check this", "تأكّد")}</Badge>
                        : confirmed[c] ? <Badge tone="olive"><Check size={11} />{tx("Confirmed", "تم التأكيد")}</Badge>
                        : m?.source === "ai" ? <Badge tone="terra"><Sparkles size={11} />AI · {Math.round((m.confidence || 0) * 100)}%</Badge>
                        : m?.source === "values" ? <Badge tone="olive"><ScanSearch size={11} />{tx("Found from values", "اكتُشف من القيم")}</Badge>
                        : m?.field ? <Badge tone="olive">{tx("Recognized", "معروف")}</Badge>
                        : <Badge>{tx("Not used", "غير مستخدم")}</Badge>}
                      {reason && <span className="truncate">{reason}</span>}
                    </p>
                  </div>
                  <div className="flex min-w-0 flex-wrap gap-1.5">
                    {samples.map((s, i) => <span key={i} className="max-w-[180px] truncate rounded-md bg-paper-2 px-2 py-0.5 font-mono text-[12px] text-ink-2">{String(s)}</span>)}
                  </div>
                  <div className="min-w-0">
                    <FieldPicker value={chosen} options={options} labelOf={label}
                      onChange={(v) => setMapping({ ...mapping, [c]: v })} />
                    {isPending && (
                      <button type="button" onClick={() => setConfirmed({ ...confirmed, [c]: true })}
                        className="mt-1 inline-flex items-center gap-1 text-[12px] font-medium text-olive hover:underline">
                        <Check size={12} />{tx("Looks right", "صحيح")}
                      </button>
                    )}
                    {unusedWithData && (
                      <p className="mt-1 text-[11.5px] text-ink-3">
                        {tx("Has data but isn't mapped — pick what it means, or leave it out.",
                            "فيه بيانات بس مش مربوط — اختار شو بيمثّل، أو خليه برّا.")}
                      </p>
                    )}
                  </div>
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
