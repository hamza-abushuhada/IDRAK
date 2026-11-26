"use client";
import { useState } from "react";
import clsx from "clsx";
import {
  PlugZap, RefreshCw, Unplug, CheckCircle2, AlertTriangle, Clock, Upload, Store,
  Boxes, Cloud, FileSpreadsheet, HardDrive, Link2, ChevronDown, ChevronUp,
  FlaskConical, XCircle, Zap, ShoppingBag, Globe,
} from "lucide-react";
import { useTx } from "@/i18n";
import { useApiQuery, useApiMutation } from "@/lib/useApi";
import { timeAgo } from "@/lib/format";
import { toast } from "@/components/ui/toast";
import { PageHeader, Section, Stat, StatSkeleton, Table, ErrorBox, N, useName, type Col } from "@/components/app/kit";
import { Badge, Button, Card, Empty, Skeleton } from "@/components/ui";

type Provider = {
  code: string; name: string; name_ar: string | null; category: string;
  status: "demo" | "available" | "coming_soon"; is_implemented: boolean;
  capabilities: Record<string, boolean>; description: string | null; description_ar: string | null;
};
type Counts = { imported?: number; updated?: number; skipped?: number; failed?: number };
type Job = {
  id: string; trigger: string; status: "running" | "success" | "partial" | "failed";
  counts: Counts; error: string | null; started_at: string; finished_at: string | null;
};
type Connection = {
  id: string; provider_code: string; provider_name: string; provider_name_ar: string | null;
  provider_category: string; display_name: string; status: "pending" | "connected" | "paused" | "error" | "disconnected";
  last_sync_at: string | null; last_success_at: string | null; last_error: string | null;
  sync_count: number; open_errors: number; sales_count?: number; recent_jobs?: Job[];
  config?: { channel?: string; auto_sync?: boolean } | null;
};
type TestCheck = { name: string; ok: boolean; detail: string };
type TestResult = { ok: boolean; checks: TestCheck[]; capabilities?: Record<string, boolean> };

const CHANNEL_META: Record<string, { tone: "olive" | "saffron" | "neutral"; en: string; ar: string; icon: React.ComponentType<{ size?: number; className?: string }> }> = {
  in_store: { tone: "olive", en: "In-store POS", ar: "كاشير المحل", icon: ShoppingBag },
  online: { tone: "saffron", en: "Online", ar: "متجر أونلاين", icon: Globe },
  other: { tone: "neutral", en: "Other source", ar: "مصدر آخر", icon: PlugZap },
};

const CATEGORY_ICON: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  demo: Boxes, cloud_api: Cloud, local_agent: HardDrive, file_export: FileSpreadsheet,
};

export default function IntegrationsPage() {
  const tx = useTx();
  const name = useName();
  const providersQ = useApiQuery<Provider[]>("/integrations/providers");
  // تحديث حيّ: حالة الاتصالات وعدّادات المزامنة تتحدّث مع المزامنة التلقائية بلا إعادة تحميل.
  const connsQ = useApiQuery<Connection[]>("/integrations/connections", { refetchInterval: 10000, refetchOnWindowFocus: true });
  const providers = providersQ.data;
  const conns = connsQ.data;

  const connect = useApiMutation<{ provider_code: string }, { sync: Counts }>("POST", "/integrations/connections", {
    invalidate: ["/integrations/connections"],
    onSuccess: (r) => toast(tx("Connected", "تم الربط"),
      tx(`Imported ${r.sync?.imported ?? 0} records`, `تم استيراد ${r.sync?.imported ?? 0} سجلّ`), "ok"),
  });

  const activeCount = (conns || []).filter((c) => c.status === "connected").length;
  const lastSync = (conns || []).map((c) => c.last_success_at).filter(Boolean).sort().at(-1) || null;
  const totalErrors = (conns || []).reduce((s, c) => s + (c.open_errors || 0), 0);

  return (
    <div>
      <PageHeader
        eyebrow={tx("IDRAK Connect", "ربط أنظمة نقاط البيع")}
        title={tx("Keep your data updated automatically", "خلّي بياناتك تتحدّث لحالها")}
        subtitle={tx(
          "Connect a compatible point-of-sale system and IDRAK pulls your sales, products, and returns automatically — less manual exporting, fewer missed days.",
          "اربط نظام نقطة بيع متوافق وإدراك بيسحب مبيعاتك وأصنافك ومرتجعاتك تلقائيًا — تصدير يدوي أقل، وأيام أقلّ تضيع.")}
      />

      {connsQ.error ? <ErrorBox error={connsQ.error} retry={() => connsQ.refetch()} /> : (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            {!conns ? [0, 1, 2].map((i) => <StatSkeleton key={i} />) : (
              <>
                <Stat tone="olive" label={tx("Connected systems", "أنظمة مربوطة")} value={<N v={activeCount} />}
                  hint={tx("syncing automatically", "تتزامن تلقائيًا")} />
                <Stat label={tx("Last successful sync", "آخر مزامنة ناجحة")}
                  value={lastSync ? timeAgo(lastSync, tx.locale) : "—"}
                  hint={lastSync ? tx("up to date", "محدّثة") : tx("not yet", "لسّا")} />
                <Stat tone={totalErrors ? "terra" : undefined} label={tx("Needs attention", "تحتاج انتباه")}
                  value={<span className={totalErrors ? "text-danger" : ""}><N v={totalErrors} /></span>}
                  hint={tx("records to review", "سجلّات للمراجعة")} />
              </>
            )}
          </div>

          {/* الأنظمة المربوطة */}
          <Section
            id="pos-connections"
            title={tx("Your connections", "ربطك الحالي")}
            subtitle={tx("Systems currently linked to this business.", "الأنظمة المربوطة بهالمشروع حاليًا.")}
            className="mb-6"
            bodyClass="p-0"
          >
            {!conns ? (
              <div className="space-y-2 p-5">{[0, 1].map((i) => <Skeleton key={i} className="h-16 w-full" />)}</div>
            ) : !conns.length ? (
              <Empty
                icon={<PlugZap size={28} />}
                title={tx("No systems connected yet", "ما في أنظمة مربوطة بعد")}
                body={tx("Connect the demo system below to see how automatic syncing works, or keep importing files manually.",
                  "اربط النظام التجريبي تحت لتشوف كيف بتشتغل المزامنة التلقائية، أو كمّل رفع الملفات يدويًا.")}
              />
            ) : (
              <div className="divide-y divide-line/60">
                {conns.map((c) => <ConnectionRow key={c.id} conn={c} />)}
              </div>
            )}
          </Section>

          {/* كتالوج الموصّلات */}
          <Section
            id="pos-catalog"
            title={tx("Available connectors", "الموصّلات المتاحة")}
            subtitle={tx("Pick a system to connect. More are supported as integrations are built.",
              "اختر نظام لتربطه. رح يتوفّر المزيد مع بناء التكاملات.")}
            className="mb-6"
          >
            {providersQ.error ? (
              <ErrorBox error={providersQ.error} retry={() => providersQ.refetch()} />
            ) : !providers ? (
              <div className="grid gap-3 sm:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28 w-full" />)}</div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {providers.map((p) => {
                  const Icon = CATEGORY_ICON[p.category] || Cloud;
                  const connectable = p.is_implemented;
                  return (
                    <div key={p.code}
                      className={clsx("flex flex-col rounded-xl border p-4",
                        connectable ? "border-line bg-paper" : "border-dashed border-line bg-paper-2/40")}>
                      <div className="flex items-start gap-3">
                        <span className={clsx("grid size-10 shrink-0 place-items-center rounded-lg",
                          connectable ? "bg-terra-soft text-terra-2" : "bg-sand text-ink-3")}>
                          <Icon size={19} />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <p className="font-serif text-[15.5px] text-ink">{name(p.name, p.name_ar)}</p>
                            {p.status === "demo" && <Badge tone="saffron">{tx("Demo", "تجريبي")}</Badge>}
                            {p.status === "coming_soon" && <Badge tone="neutral">{tx("Coming soon", "قريبًا")}</Badge>}
                          </div>
                          <p className="mt-1 text-[12.5px] leading-relaxed text-ink-3">{name(p.description, p.description_ar)}</p>
                        </div>
                      </div>
                      <div className="mt-3 flex items-center justify-between gap-2">
                        <CapabilityTags caps={p.capabilities} />
                        {connectable ? (
                          <Button size="sm" loading={connect.isPending}
                            onClick={() => connect.mutate({ provider_code: p.code })}
                            data-basira={`connect-${p.code}`}>
                            <Link2 size={14} />{tx("Connect", "اربط")}
                          </Button>
                        ) : (
                          <Button size="sm" variant="secondary" disabled
                            title={tx("Supported architecturally — not available to connect yet", "مدعوم معماريًا — غير متاح للربط بعد")}>
                            {tx("Not available yet", "غير متاح بعد")}
                          </Button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Section>

          {/* مسار الرفع اليدوي */}
          <Card className="flex flex-col items-start justify-between gap-3 p-5 sm:flex-row sm:items-center">
            <div className="flex items-start gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-sand text-ink-2"><Upload size={18} /></span>
              <div>
                <p className="font-serif text-[15px] text-ink">{tx("Prefer to upload a file?", "بتفضّل ترفع ملف؟")}</p>
                <p className="mt-0.5 text-[12.5px] text-ink-3">
                  {tx("Excel and CSV import still works exactly as before — connecting a POS doesn't replace it.",
                    "رفع Excel وCSV لسّا شغّال متل ما هو — ربط نقطة البيع ما بيلغيه.")}
                </p>
              </div>
            </div>
            <Button href="/app/data" variant="secondary" size="sm">{tx("Go to file import", "روح لرفع الملفات")}</Button>
          </Card>
        </>
      )}
    </div>
  );
}

function CapabilityTags({ caps }: { caps: Record<string, boolean> }) {
  const tx = useTx();
  const labels: Record<string, [string, string]> = {
    initial_import: ["Initial import", "استيراد أولي"], incremental: ["Auto sync", "مزامنة تلقائية"],
    webhook: ["Webhooks", "Webhooks"], refunds: ["Refunds", "مرتجعات"], inventory: ["Inventory", "مخزون"],
    secure_submit: ["Secure submit", "إرسال آمن"], file_import: ["File export", "تصدير ملفات"],
  };
  const on = Object.entries(caps).filter(([, v]) => v).map(([k]) => k).slice(0, 3);
  if (!on.length) return <span />;
  return (
    <div className="flex flex-wrap gap-1">
      {on.map((k) => <span key={k} className="rounded-full bg-sand px-2 py-0.5 text-[10.5px] text-ink-3">{tx(labels[k]?.[0] || k, labels[k]?.[1] || k)}</span>)}
    </div>
  );
}

const STATUS_META: Record<Connection["status"], { tone: "olive" | "saffron" | "danger" | "neutral"; en: string; ar: string }> = {
  connected: { tone: "olive", en: "Connected", ar: "متصل" },
  pending: { tone: "saffron", en: "Pending", ar: "قيد الإعداد" },
  paused: { tone: "neutral", en: "Paused", ar: "موقوف" },
  error: { tone: "danger", en: "Error", ar: "خطأ" },
  disconnected: { tone: "neutral", en: "Disconnected", ar: "غير متصل" },
};
const JOB_TONE: Record<Job["status"], "olive" | "saffron" | "danger" | "neutral"> = {
  success: "olive", partial: "saffron", failed: "danger", running: "neutral",
};

function ConnectionRow({ conn }: { conn: Connection }) {
  const tx = useTx();
  const name = useName();
  const [open, setOpen] = useState(false);
  const [confirmOff, setConfirmOff] = useState(false);
  const st = STATUS_META[conn.status];

  const detailQ = useApiQuery<Connection>(open ? `/integrations/connections/${conn.id}` : null);
  const sync = useApiMutation("POST", `/integrations/connections/${conn.id}/sync`, {
    invalidate: ["/integrations/connections"],
    onSuccess: (r: { sync?: Counts }) => toast(tx("Synced", "تمّت المزامنة"),
      tx(`+${r.sync?.imported ?? 0} new · ${r.sync?.updated ?? 0} updated`, `+${r.sync?.imported ?? 0} جديد · ${r.sync?.updated ?? 0} محدّث`), "ok"),
  });
  const disconnect = useApiMutation("DELETE", `/integrations/connections/${conn.id}`, {
    invalidate: ["/integrations/connections"],
    onSuccess: () => { setConfirmOff(false); toast(tx("Disconnected", "تم قطع الاتصال"), tx("Your imported data was kept.", "بياناتك المستوردة انحفظت."), "ok"); },
  });
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const test = useApiMutation<undefined, TestResult>("POST", `/integrations/connections/${conn.id}/test`, {
    onSuccess: (r) => { setTestResult(r); toast(
      r.ok ? tx("Connection healthy", "الاتصال سليم") : tx("Connection needs attention", "الاتصال يحتاج انتباه"),
      "", r.ok ? "ok" : "error"); },
  });
  const TEST_LABELS: Record<string, [string, string]> = {
    reachable: ["Reachable & authorized", "الوصول والصلاحية"], transform: ["Data transforms correctly", "تحويل البيانات صحيح"],
    webhook: ["Signed webhook", "Webhook موقّع"], adapter: ["Connector available", "الموصّل متاح"],
  };

  const jobs = detailQ.data?.recent_jobs;
  const jobCols: Col<Job>[] = [
    { key: "trigger", label: tx("Trigger", "المصدر"), render: (j) => tx(j.trigger, { manual: "يدوي", initial: "أولي", scheduled: "مجدول", webhook: "Webhook" }[j.trigger] || j.trigger) },
    { key: "status", label: tx("Result", "النتيجة"), render: (j) => <Badge tone={JOB_TONE[j.status]}>{tx(j.status, { success: "نجاح", partial: "جزئي", failed: "فشل", running: "جارٍ" }[j.status])}</Badge> },
    { key: "imported", label: tx("New", "جديد"), align: "end", render: (j) => <N v={j.counts?.imported ?? 0} /> },
    { key: "updated", label: tx("Updated", "محدّث"), align: "end", render: (j) => <N v={j.counts?.updated ?? 0} /> },
    { key: "skipped", label: tx("Skipped", "متخطّى"), align: "end", render: (j) => <N v={j.counts?.skipped ?? 0} /> },
    { key: "failed", label: tx("Failed", "فشل"), align: "end", render: (j) => <span className={(j.counts?.failed ?? 0) ? "text-danger" : ""}><N v={j.counts?.failed ?? 0} /></span> },
    { key: "when", label: tx("When", "الوقت"), align: "end", render: (j) => <span className="text-ink-3">{timeAgo(j.started_at, tx.locale)}</span> },
  ];

  return (
    <div className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-terra-soft text-terra-2"><Store size={18} /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate font-medium text-ink">{conn.display_name}</p>
            <Badge tone={st.tone}>{tx(st.en, st.ar)}</Badge>
            {!!conn.open_errors && <Badge tone="danger"><AlertTriangle size={11} />{tx("Needs attention", "تحتاج انتباه")} <N v={conn.open_errors} /></Badge>}
            {conn.config?.channel && CHANNEL_META[conn.config.channel] && (() => {
              const ch = CHANNEL_META[conn.config.channel!]; const CI = ch.icon;
              return <Badge tone={ch.tone}><CI size={11} />{tx(ch.en, ch.ar)}</Badge>;
            })()}
            {conn.config?.auto_sync && <Badge tone="olive"><Zap size={11} />{tx("Auto-sync", "مزامنة تلقائية")}</Badge>}
          </div>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[12px] text-ink-3">
            <span>{name(conn.provider_name, conn.provider_name_ar)}</span>
            <span className="inline-flex items-center gap-1">
              {conn.last_success_at ? <CheckCircle2 size={12} className="text-olive" /> : <Clock size={12} />}
              {conn.last_success_at
                ? tx(`Synced ${timeAgo(conn.last_success_at, tx.locale)}`, `تزامنت ${timeAgo(conn.last_success_at, tx.locale)}`)
                : tx("Waiting for first sync", "بانتظار أول مزامنة")}
            </span>
            <span>{tx(`${conn.sync_count} syncs`, `${conn.sync_count} مزامنة`)}</span>
          </p>
          {conn.status === "error" && conn.last_error && (
            <p className="mt-1 text-[12px] text-danger">{conn.last_error}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {conn.status !== "disconnected" && (
            <Button size="sm" variant="secondary" loading={sync.isPending} onClick={() => sync.mutate(undefined)}
              data-basira="pos-sync-now">
              <RefreshCw size={14} />{tx("Sync now", "زامن الآن")}
            </Button>
          )}
          <button onClick={() => setOpen((o) => !o)}
            className="grid size-9 place-items-center rounded-full text-ink-3 hover:bg-sand hover:text-ink"
            aria-label={tx("Details", "تفاصيل")}>
            {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>

      {open && (
        <div className="mt-4 rounded-xl border border-line bg-paper-2/40 p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-[13px] font-medium text-ink-2">{tx("Sync history", "سجلّ المزامنة")}</h4>
            {conn.status !== "disconnected" && (
              confirmOff ? (
                <div className="flex items-center gap-2">
                  <span className="text-[12px] text-ink-3">{tx("Disconnect? Data is kept.", "قطع الاتصال؟ البيانات بتنحفظ.")}</span>
                  <Button size="sm" variant="danger" loading={disconnect.isPending} onClick={() => disconnect.mutate(undefined)}>
                    <Unplug size={13} />{tx("Disconnect", "اقطع")}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirmOff(false)}>{tx("Cancel", "إلغاء")}</Button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="secondary" loading={test.isPending} onClick={() => test.mutate(undefined)}
                    data-basira="pos-test">
                    <FlaskConical size={13} />{tx("Test connection", "افحص الاتصال")}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirmOff(true)}>
                    <Unplug size={13} />{tx("Disconnect", "اقطع الاتصال")}
                  </Button>
                </div>
              )
            )}
          </div>

          {testResult && (
            <div className={clsx("mb-3 rounded-lg border p-3",
              testResult.ok ? "border-olive/40 bg-olive/10" : "border-danger/40 bg-danger/10")}>
              <p className="mb-2 flex items-center gap-1.5 text-[12.5px] font-medium">
                {testResult.ok ? <CheckCircle2 size={14} className="text-olive" /> : <AlertTriangle size={14} className="text-danger" />}
                {testResult.ok ? tx("Connection healthy", "الاتصال سليم") : tx("Connection needs attention", "الاتصال يحتاج انتباه")}
              </p>
              <ul className="space-y-1">
                {testResult.checks.map((ch) => (
                  <li key={ch.name} className="flex items-start gap-1.5 text-[12px] text-ink-2">
                    {ch.ok ? <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-olive" />
                           : <XCircle size={13} className="mt-0.5 shrink-0 text-danger" />}
                    <span className="font-medium">{tx(TEST_LABELS[ch.name]?.[0] || ch.name, TEST_LABELS[ch.name]?.[1] || ch.name)}</span>
                    <span className="text-ink-3">— {ch.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {detailQ.error ? (
            <ErrorBox error={detailQ.error} retry={() => detailQ.refetch()} />
          ) : !jobs ? (
            <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-7 w-full" />)}</div>
          ) : (
            <div className="overflow-hidden rounded-lg border border-line bg-paper">
              <Table<Job> rows={jobs} cols={jobCols} dense
                empty={tx("No syncs yet", "ما في مزامنات بعد")} rowKey={(j) => j.id} />
            </div>
          )}
          {!!detailQ.data?.sales_count && (
            <p className="mt-3 text-[12px] text-ink-3">
              {tx(`${detailQ.data.sales_count} sales from this connection feed your dashboard and reports.`,
                `${detailQ.data.sales_count} فاتورة من هالربط بتغذّي لوحتك وتقاريرك.`)}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
