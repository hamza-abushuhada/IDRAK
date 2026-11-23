"use client";
import { useParams } from "next/navigation";
import { useRouter } from "@/lib/router";
import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { AlertTriangle, Check, History, ScanSearch, Sparkles, Users, Wand2 } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { api } from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { ErrorBox, PageHeader, Section } from "@/components/app/kit";
import { Badge, Button, Select, Skeleton } from "@/components/ui";
import { toast } from "@/components/ui/toast";

// ما يقوله شكل القيم عن العمود (api/app/cleaning/profile.py).
type Evidence = { type: "mismatch" | "discovered"; kind: string; share: number };
// رأي الذكاء الاصطناعي كحَكَم (api/app/cleaning/referee.py): يوافق أو يقترح حقلاً آخر.
type AiVerdict = { field: string | null; confidence: number; reason: string; agrees: boolean; taken_by?: string };
// لماذا نوع الملف يحتاج تأكيد (api/app/cleaning/fields.py: entity_check).
type EntityReason =
  | { code: "purchase_guard" | "waste_guard"; instead_of: string }
  | { code: "mixed_signals"; signal: "purchase" | "waste" }
  | { code: "missing_required"; fields: string[] }
  | { code: "unconfirmed_fields"; columns: string[]; instead_of: string }
  | { code: "unrecognized" };
type EntityCheck = {
  detected: string; entity: string; confirmed: string | null; needs_confirmation: boolean; blocked: boolean;
  reasons: EntityReason[]; suggested: string[];
  // "file": التأكيد انتقل من آخر ملف للشركة بنفس الأعمدة (api/app/cleaning/learning.py).
  confirmed_via?: string | null;
};
type Upload = {
  id: string; file_name: string; entity: string; row_count: number; column_count: number; columns: string[];
  // source: rules | shared (اسم أكّدته ≥3 شركات) | values | ai | memory | user.
  // via "file": الربط رجع من آخر ملف للشركة بنفس الأعمدة (بصمة الملف).
  mapping: Record<string, {
    field: string | null; confidence: number; source: string | null; reason?: string;
    review?: boolean; evidence?: Evidence | null; ai?: AiVerdict | null; via?: string | null;
  }>;
  preview: unknown[][]; fields: { key: string; kind: string; en: string; ar: string }[]; entity_label: [string, string]; last_run_id: string | null;
  entity_check: EntityCheck; entities: Record<string, { en: string; ar: string; needs: string[][] }>;
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
  // نوع الملف اللي اختاره أو أكّده المستخدم بهالجلسة (null = ما لمسه).
  const [entityChoice, setEntityChoice] = useState<string | null>(null);
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

  // نوع الملف: إذا إشاراته ضعيفة أو متضاربة، التنظيف ينتظر تأكيد المستخدم
  // (والسيرفر كمان يرفض). نفس فكرة الأعمدة الصفراء.
  const check = u?.entity_check;
  const entity = entityChoice ?? check?.entity ?? u?.entity ?? "unknown";
  const entityLabel = (e: string) => { const l = u?.entities?.[e]; return l ? tx(l.en, l.ar) : e; };
  const entityPending = !!check && check.needs_confirmation && !check.confirmed && entityChoice === null;
  const mappedFields = new Set(Object.values(mapping).filter((f): f is string => !!f));
  const missingForEntity = (u?.entities?.[entity]?.needs ?? []).filter((alts) => !alts.some((f) => mappedFields.has(f))).map((alts) => alts[0]);
  const reasonText = (r: EntityReason) => {
    switch (r.code) {
      case "purchase_guard":
        return tx("The column names say these are purchases from a supplier, not sales. Idrak will only update your item costs from it.",
                  "أسماء الأعمدة بتقول إنها مشتريات من مورد مش مبيعات. إدراك رح يحدّث تكلفة الأصناف منه بس.");
      case "waste_guard":
        return tx("This looks like a waste or spoilage log. Idrak doesn't import waste yet, so nothing will be imported from it.",
                  "شكله سجل هدر وتالف. إدراك لسا ما بيستورد الهدر، فما رح ينستورد منه إشي.");
      case "mixed_signals":
        return r.signal === "purchase"
          ? tx("It reads like sales, but some column names talk about suppliers or purchases.", "بينقرأ كمبيعات، بس في أعمدة أسماؤها عن موردين أو مشتريات.")
          : tx("It reads like sales, but some column names talk about waste or spoilage.", "بينقرأ كمبيعات، بس في أعمدة أسماؤها عن هدر أو تالف.");
      case "missing_required":
        return tx(`Missing for this type: ${r.fields.map(label).join(", ")}`, `ناقص لهالنوع: ${r.fields.map(label).join("، ")}`);
      case "unconfirmed_fields":
        return tx(`The type depends on columns Idrak isn't sure about: ${r.columns.join(", ")}`,
                  `النوع معتمد على أعمدة إدراك مش متأكد منها: ${r.columns.join("، ")}`);
      case "unrecognized":
        return tx("Idrak couldn't tell what this file is.", "إدراك ما عرف شو نوع هالملف.");
    }
  };

  async function clean() {
    setCleaning(true);
    try {
      const saved = await api<{ entity_check: EntityCheck }>(`/data/uploads/${id}/mapping`, {
        method: "PUT", json: { mapping, ...(entityChoice ? { entity: entityChoice } : {}) },
      });
      // تغيير الأعمدة ممكن يغيّر نوع الملف: إذا صار بدّه تأكيد، نوقف ونسأل.
      if (saved.entity_check?.blocked) {
        toast(tx("Confirm the file type", "أكّد نوع الملف"),
              tx("Your column changes made Idrak unsure what this file is. Pick its type, then clean.",
                 "تعديل الأعمدة خلّى إدراك مش متأكد من نوع الملف. اختار نوعه وبعدين نظّف."), "info");
        setCleaning(false);
        q.refetch();
        return;
      }
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
        subtitle={u ? tx(`${u.row_count.toLocaleString()} rows · ${u.column_count} columns · detected: ${entityLabel(entity)}`, `${u.row_count.toLocaleString()} صف · ${u.column_count} عمود · نوع الملف: ${entityLabel(entity)}`) : undefined}
        actions={<Button size="lg" onClick={clean} loading={cleaning} disabled={!u || pending.length > 0 || entityPending} data-basira="clean-button"
          title={entityPending ? tx("Confirm the file type first", "أكّد نوع الملف أولاً")
            : pending.length ? tx("Check the yellow columns first", "راجع الأعمدة الصفراء أولاً") : undefined}>
          <Wand2 size={16} />{tx("Clean with Idrak", "نظّف بإدراك")}</Button>} />

      {u && check && (check.needs_confirmation || check.confirmed || entityChoice) && (
        <div className={clsx("mb-4 rounded-[var(--radius-card)] border px-5 py-3.5",
          entityPending ? "border-saffron/40 bg-saffron-soft" : "border-line bg-paper")} data-basira="entity-confirm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className={clsx("flex items-center gap-2 text-[13.5px]", entityPending ? "text-[#8a5d0e]" : "text-ink-2")}>
              {entityPending ? <AlertTriangle size={16} className="shrink-0" /> : <Check size={16} className="shrink-0 text-olive" />}
              {entityPending
                ? tx(`Idrak thinks this is a ${entityLabel(entity)} file, but isn't sure. Confirm or choose its type before cleaning.`,
                     `إدراك بيتوقع إنه الملف ${entityLabel(entity)}، بس مش متأكد. أكّد نوعه أو اختار غيره قبل التنظيف.`)
                : check.confirmed_via === "file" && !entityChoice
                  ? tx(`File type: ${entityLabel(entity)} (confirmed on your last file with these columns)`,
                       `نوع الملف: ${entityLabel(entity)} (مؤكَّد من ملفك السابق بنفس الأعمدة)`)
                  : tx(`File type: ${entityLabel(entity)} (confirmed)`, `نوع الملف: ${entityLabel(entity)} (مؤكَّد)`)}
            </p>
            <div className="flex items-center gap-2">
              <Select value={entity} onChange={(e) => setEntityChoice(e.target.value)} className="h-9 text-[13px]"
                aria-label={tx("File type", "نوع الملف")}>
                {Object.keys(u.entities).map((k) => <option key={k} value={k}>{entityLabel(k)}</option>)}
              </Select>
              {entityPending && (
                <Button size="sm" variant="secondary" onClick={() => setEntityChoice(entity)}>
                  <Check size={14} />{tx("Yes, that's right", "صح، هيك")}
                </Button>
              )}
            </div>
          </div>
          {entityPending && check.reasons.length > 0 && (
            <ul className="mt-2 list-disc space-y-0.5 ps-9 text-[12.5px] text-[#8a5d0e]">
              {check.reasons.map((r, i) => <li key={i}>{reasonText(r)}</li>)}
            </ul>
          )}
          {entity === "unknown" ? (
            <p className="mt-2 ps-6 text-[12px] text-ink-3">
              {tx("A generic table is checked and cleaned, but nothing from it is imported.", "الجدول العام بينفحص وبيتنظّف، بس ما بينستورد منه إشي.")}
            </p>
          ) : missingForEntity.length > 0 && !entityPending && (
            <p className="mt-2 ps-6 text-[12px] text-[#8a5d0e]">
              {tx(`Missing for this type: ${missingForEntity.map(label).join(", ")}`, `ناقص لهالنوع: ${missingForEntity.map(label).join("، ")}`)}
            </p>
          )}
        </div>
      )}

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
              const fromLastFile = remembered && m?.via === "file";
              const unusedWithData = !chosen && samples.length > 0;
              const isPending = pending.includes(c);
              const reason = m?.evidence
                ? (fromLastFile && m.evidence.type === "mismatch" ? tx("Changed since your last file · ", "تغيّر عن ملفك السابق · ") : "") + why(m.evidence)
                : m?.reason || (isPending ? tx("Not sure about this match", "إدراك مش متأكد من هالربط") : null);
              // اقتراح الحَكَم: لا نعرض زر "استخدمه" لحقل مأخوذ بعمود ثاني الآن.
              const ai = m?.ai;
              const aiTaken = ai?.field ? takenBy(ai.field) : undefined;
              return (
                <div key={c} className={clsx("grid items-center gap-3 px-5 py-3 md:grid-cols-[1.1fr_1.6fr_1fr]", isPending && "bg-saffron-soft/50")}>
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{c}</p>
                    <p className="mt-0.5 flex items-center gap-1.5 text-[12px] text-ink-3">
                      {isPending ? <Badge tone="saffron"><AlertTriangle size={11} />{tx("Check this", "تأكّد")}</Badge>
                        : fromLastFile ? <Badge tone="olive"><History size={11} />{tx("Learned from your last file", "من ملفك السابق")}</Badge>
                        : remembered ? <Badge tone="olive">{tx("Your saved mapping", "ربطك المحفوظ")}</Badge>
                        : confirmed[c] ? <Badge tone="olive"><Check size={11} />{tx("Confirmed", "تم التأكيد")}</Badge>
                        : m?.source === "ai" ? <Badge tone="terra"><Sparkles size={11} />AI · {Math.round((m.confidence || 0) * 100)}%</Badge>
                        : m?.source === "values" ? <Badge tone="olive"><ScanSearch size={11} />{tx("Found from values", "اكتُشف من القيم")}</Badge>
                        : m?.source === "shared" ? <Badge tone="olive"><Users size={11} />{tx("Common name across Idrak users", "اسم شائع عند مستخدمي إدراك")}</Badge>
                        : m?.field ? <Badge tone="olive">{tx("Recognized", "معروف")}</Badge>
                        : <Badge>{tx("Not used", "غير مستخدم")}</Badge>}
                      {reason && <span className="truncate">{reason}</span>}
                    </p>
                    {ai && m?.source !== "ai" && (ai.agrees ? (
                      <p className="mt-0.5 flex items-center gap-1 text-[11.5px] text-olive">
                        <Sparkles size={11} className="shrink-0" />
                        <span className="truncate">{tx("AI agrees", "الذكاء الاصطناعي موافق")}{ai.reason ? ` · ${ai.reason}` : ""}</span>
                      </p>
                    ) : (
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-[11.5px] text-terra">
                        <Sparkles size={11} className="shrink-0" />
                        <span>{tx("AI suggests:", "الذكاء الاصطناعي بيقترح:")} <b className="font-medium">{ai.field ? label(ai.field) : tx("don't use", "لا تستخدم")}</b>
                          {ai.reason ? ` · ${ai.reason}` : ""}</span>
                        {aiTaken ? (
                          <span className="text-ink-3">{tx(`(already used by “${aiTaken}”)`, `(مستخدم بعمود “${aiTaken}”)`)}</span>
                        ) : chosen !== (ai.field ?? "") && (
                          <button type="button" onClick={() => setMapping({ ...mapping, [c]: ai.field })}
                            className="font-medium underline-offset-2 hover:underline">
                            {tx("Use it", "استخدمه")}
                          </button>
                        )}
                      </p>
                    ))}
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
