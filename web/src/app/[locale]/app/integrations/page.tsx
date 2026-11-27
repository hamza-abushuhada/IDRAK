"use client";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, CheckCircle2, CircleOff, Clock, FlaskConical, Globe, Info, KeyRound, Pencil, PlugZap, Plus,
  RefreshCw, Settings2, ShoppingBag, Sparkles, Store, Trash2, Unplug, Upload, XCircle,
} from "lucide-react";
import { useTx } from "@/i18n";
import { api, ApiError } from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { timeAgo } from "@/lib/format";
import { toast } from "@/components/ui/toast";
import { PageHeader, Section, ErrorBox } from "@/components/app/kit";
import { Badge, Button, Card, Empty, Input, Skeleton } from "@/components/ui";
import { Drawer } from "@/components/workspace/common";
import { useSession } from "@/components/app/session";
import ConnectWizard, { type Choice } from "@/components/app/connect/ConnectWizard";
import { VendorLogo } from "@/components/app/connect/vendors";
import { takeFlash, type Flash } from "@/components/app/connect/pending";
import {
  friendlyError, groupSystems, systemAutoSync, type Channel, type ConnectedSystem, type Connection, type Counts, type Job,
  type Provider, type SystemStatus,
} from "@/components/app/connect/model";

const STATUS_UI: Record<SystemStatus, { tone: "olive" | "saffron" | "neutral"; en: string; ar: string; icon: React.ComponentType<{ size?: number }> }> = {
  connected: { tone: "olive", en: "Connected", ar: "متصل", icon: CheckCircle2 },
  attention: { tone: "saffron", en: "Needs attention", ar: "يحتاج انتباه", icon: AlertTriangle },
  disconnected: { tone: "neutral", en: "Not connected", ar: "غير متصل", icon: CircleOff },
};
const CHANNEL_UI: Record<Channel, { en: string; ar: string; icon: React.ComponentType<{ size?: number; className?: string }> }> = {
  in_store: { en: "Cashier", ar: "الكاشير", icon: ShoppingBag },
  online: { en: "Online store", ar: "المتجر الإلكتروني", icon: Globe },
  other: { en: "Sales source", ar: "مصدر مبيعات", icon: PlugZap },
};

function useSystemLabels() {
  const tx = useTx();
  return {
    name: (s: ConnectedSystem) => s.customName
      ?? (s.kind === "lab" ? tx(`Test shop ${s.ordinal}`, `محل تجريبي ${s.ordinal}`)
        : s.kind === "demo" ? tx("Demo POS", "كاشير تجريبي") : tx(`Sales system ${s.ordinal}`, `نظام مبيعات ${s.ordinal}`)),
    vendor: (s: ConnectedSystem) => s.kind === "lab" ? "IDRAK Connect Lab" : s.kind === "demo" ? tx("Demo POS", "كاشير تجريبي")
      : tx(s.channels[0].conn.provider_name, s.channels[0].conn.provider_name_ar || s.channels[0].conn.provider_name),
  };
}

export default function IntegrationsPage() {
  const tx = useTx();
  const qc = useQueryClient();
  const { can } = useSession();
  const canManage = can("manager");
  const providersQ = useApiQuery<Provider[]>("/integrations/providers");
  const statusQ = useApiQuery<{ auto_sync_active: boolean; lab_linking?: boolean; loyverse_available?: boolean; store_key_available?: boolean }>("/integrations/status");
  const connsQ = useApiQuery<Connection[]>("/integrations/connections", { refetchInterval: 15000, refetchOnWindowFocus: true });
  const [wizard, setWizard] = useState<{ open: boolean; choice: Choice | null }>({ open: false, choice: null });
  const storeKeys = !!statusQ.data?.store_key_available;
  // Safety net for missed store notifications: pull stores linked by API key that haven't synced lately.
  useEffect(() => {
    if (!storeKeys) return;
    void api<{ imported: number }>("/integrations/catch-up", { method: "POST" })
      .then((r) => { if (r.imported) void qc.invalidateQueries({ predicate: (q) => /^\/integrations\/connections/.test(String(q.queryKey[1] || "")) }); })
      .catch(() => {});
  }, [storeKeys, qc]);
  const [manageKey, setManageKey] = useState<string | null>(null);
  // Success message after returning from the POS approval (set by the callback page).
  const [flash, setFlash] = useState<Flash | null>(null);
  useEffect(() => {
    const value = takeFlash();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time read of tab storage after mount
    if (value) setFlash(value);
  }, []);
  const systems = connsQ.data ? groupSystems(connsQ.data) : undefined;
  const managed = systems?.find((s) => s.key === manageKey) ?? null;
  const refresh = () => {
    void qc.invalidateQueries({ predicate: (q) => /^\/(integrations\/connections|ws\/)/.test(String(q.queryKey[1] || "")) });
  };
  const autoSync = statusQ.data?.auto_sync_active;
  const labLinking = !!statusQ.data?.lab_linking;
  // "Try again" from an expired or failed approval returns here with ?connect=lab.
  useEffect(() => {
    if (!canManage || !labLinking) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("connect") !== "lab") return;
    params.delete("connect");
    window.history.replaceState(null, "", window.location.pathname + (params.size ? `?${params}` : ""));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time read of the URL after mount
    setWizard({ open: true, choice: "lab" });
  }, [canManage, labLinking]);

  return (
    <div>
      <PageHeader
        eyebrow={tx("Integrations", "التكاملات")}
        title="IDRAK Connect"
        subtitle={tx("Connect your sales systems to IDRAK and follow your data from one place.", "اربط أنظمة مبيعاتك بإدراك وتابع بياناتك من مكان واحد")}
        actions={canManage ? (
          <Button onClick={() => setWizard({ open: true, choice: null })} data-basira="connect-new"><Plus size={16} />{tx("Connect a new system", "ربط نظام جديد")}</Button>
        ) : undefined}
      />

      {flash && (
        <div role="status" className="mb-5 flex items-start gap-2 rounded-xl border border-olive/30 bg-olive-soft p-3 text-[13.5px] text-ink">
          <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-olive" />
          <p className="flex-1">
            {flash.name ? tx(`“${flash.name}” is now linked and appears under your connected systems.`, `تم ربط «${flash.name}» بنجاح وأصبح ضمن أنظمتك المرتبطة.`)
              : tx("Your shop is now linked and appears under your connected systems.", "تم ربط محلك بنجاح وأصبح ضمن أنظمتك المرتبطة.")}
            {!flash.ok && " " + tx("The connection check hasn't passed yet: open “Manage connection” to test it again.", "لم ينجح فحص الاتصال بعد: افتح «إدارة الاتصال» لإعادة الاختبار.")}
          </p>
          <button type="button" onClick={() => setFlash(null)} className="text-ink-3 hover:text-ink" aria-label={tx("Dismiss", "إغلاق")}><XCircle size={16} /></button>
        </div>
      )}

      {autoSync === false && !systems?.some((s) => systemAutoSync(s, false)) && (
        <p className="mb-5 flex items-start gap-2 rounded-xl border border-line bg-paper-2/60 p-3 text-[13px] text-ink-2" role="note">
          <Info size={16} className="mt-0.5 shrink-0 text-ink-3" />
          {tx("Syncing is manual in this environment: press “Sync now” to bring in the latest sales.", "المزامنة في هذه البيئة يدوية: اضغط «مزامنة الآن» لجلب أحدث المبيعات.")}
        </p>
      )}

      <Section id="pos-connections" title={tx("Your connected systems", "أنظمتك المرتبطة")}
        subtitle={tx("Sales systems linked to this business.", "أنظمة المبيعات المرتبطة بهذه المؤسسة.")} className="mb-6" bodyClass="p-0">
        {connsQ.error ? (
          <div className="p-5"><ErrorBox error={connsQ.error} retry={() => connsQ.refetch()} /></div>
        ) : !systems ? (
          <div className="space-y-3 p-5">{[0, 1].map((i) => <Skeleton key={i} className="h-24 w-full" />)}</div>
        ) : !systems.length ? (
          <Empty icon={<PlugZap size={28} />} title={tx("No systems connected yet", "لا توجد أنظمة مرتبطة بعد")}
            body={canManage
              ? tx("Connect your POS or online store to bring your sales into IDRAK automatically.", "اربط نظام الكاشير أو متجرك الإلكتروني لتصل مبيعاتك إلى إدراك تلقائيًا.")
              : tx("Ask a manager of this business to connect a sales system.", "اطلب من مدير المؤسسة ربط نظام مبيعات.")}
            action={canManage ? <Button onClick={() => setWizard({ open: true, choice: null })}><Plus size={16} />{tx("Connect a new system", "ربط نظام جديد")}</Button> : undefined} />
        ) : (
          <div className="divide-y divide-line/60">
            {systems.map((s) => <SystemCard key={s.key} system={s} canManage={canManage} autoSync={systemAutoSync(s, !!autoSync)} onManage={() => setManageKey(s.key)} onChanged={refresh} />)}
          </div>
        )}
      </Section>

      <Card className="flex flex-col items-start justify-between gap-3 p-5 sm:flex-row sm:items-center">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-sand text-ink-2"><Upload size={18} /></span>
          <div>
            <p className="font-serif text-[15px] text-ink">{tx("Prefer to upload a file?", "تفضّل رفع ملف؟")}</p>
            <p className="mt-0.5 text-[12.5px] text-ink-3">{tx("Excel and CSV import keeps working alongside connected systems.", "استيراد Excel وCSV يبقى متاحًا بجانب الأنظمة المرتبطة.")}</p>
          </div>
        </div>
        <Button href="/app/data" variant="secondary" size="sm">{tx("Go to file import", "الانتقال لرفع الملفات")}</Button>
      </Card>

      {canManage && (
        <ConnectWizard key={`${wizard.choice}-${wizard.open}`} open={wizard.open} initialChoice={wizard.choice} labLinking={labLinking} loyverseAvailable={!!statusQ.data?.loyverse_available}
          storeKeyAvailable={storeKeys}
          onOpenChange={(o) => setWizard((w) => ({ ...w, open: o }))} providers={providersQ.data} onConnected={refresh} />
      )}
      {managed && (
        <ManageSystem system={managed} canManage={canManage} autoSync={systemAutoSync(managed, !!autoSync)} labLinking={labLinking} storeKeys={storeKeys}
          onClose={() => setManageKey(null)} onChanged={refresh}
          onReconnect={(choice) => { setManageKey(null); setWizard({ open: true, choice }); }} />
      )}
    </div>
  );
}

/** Official logo for systems of a real vendor (Loyverse today); null keeps the generic icon. */
function vendorCode(system: ConnectedSystem): string | null {
  return system.channels.some((c) => c.conn.provider_code === "loyverse") ? "loyverse" : null;
}
const byApiKey = (system: ConnectedSystem) => system.channels.some((c) => !!c.conn.config?.store_api_key);

async function syncSystem(system: ConnectedSystem) {
  const totals: Counts = { imported: 0, updated: 0, failed: 0 };
  for (const { conn } of system.channels.filter((c) => c.conn.status !== "disconnected")) {
    const r = await api<{ sync?: Counts }>(`/integrations/connections/${conn.id}/sync`, { method: "POST" });
    totals.imported! += r.sync?.imported ?? 0; totals.updated! += r.sync?.updated ?? 0; totals.failed! += r.sync?.failed ?? 0;
  }
  return totals;
}

function SystemCard({ system, canManage, autoSync, onManage, onChanged }: {
  system: ConnectedSystem; canManage: boolean; autoSync: boolean; onManage: () => void; onChanged: () => void;
}) {
  const tx = useTx();
  const labels = useSystemLabels();
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");
  const st = STATUS_UI[system.status];
  const SI = st.icon;
  const KindIcon = system.kind === "lab" ? FlaskConical : system.kind === "demo" ? Sparkles : Store;

  async function sync() {
    setSyncing(true); setError("");
    try {
      const t = await syncSystem(system);
      toast(tx("Sync complete", "تمت المزامنة"),
        t.imported || t.updated ? tx(`${t.imported} new · ${t.updated} updated`, `${t.imported} جديد · ${t.updated} محدّث`) : tx("Everything is already up to date.", "كل شيء محدّث بالفعل."), "ok");
    } catch (e) {
      setError(friendlyError(e instanceof ApiError ? e.status : undefined, tx.isAr));
    } finally { setSyncing(false); onChanged(); }
  }

  return (
    <div className="px-4 py-4 sm:px-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          {vendorCode(system) ? <VendorLogo code={vendorCode(system)!} name={labels.vendor(system)} />
            : <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-terra-soft text-terra-2"><KindIcon size={20} /></span>}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="truncate font-medium text-ink">{labels.name(system)}</p>
              <Badge tone={st.tone}><SI size={11} />{tx(st.en, st.ar)}</Badge>
              {system.kind === "lab" && <Badge tone="saffron">{tx("Test system", "نظام اختبار")}</Badge>}
              {byApiKey(system) && <Badge tone="neutral"><KeyRound size={11} />{tx("API key", "مفتاح API")}</Badge>}
              {system.kind === "demo" && <Badge tone="neutral">{tx("Sample data", "بيانات وهمية")}</Badge>}
            </div>
            <p className="mt-0.5 text-[12.5px] text-ink-3">{labels.vendor(system)}</p>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-3">
              {system.channels.map(({ channel, conn }) => {
                const ch = CHANNEL_UI[channel]; const CI = ch.icon; const on = conn.status !== "disconnected";
                return <span key={conn.id} className="inline-flex items-center gap-1"><CI size={12} className={on ? "text-olive" : "text-ink-3"} />{tx(ch.en, ch.ar)}{!on && <span>· {tx("off", "متوقف")}</span>}</span>;
              })}
              <span className="inline-flex items-center gap-1"><Clock size={12} />
                {system.lastSuccess ? tx(`Last sync ${timeAgo(system.lastSuccess, tx.locale)}`, `آخر مزامنة ${timeAgo(system.lastSuccess, tx.locale)}`) : tx("Not synced yet", "لم تتم المزامنة بعد")}
              </span>
              <span>{autoSync ? tx("Automatic sync", "مزامنة تلقائية") : tx("Manual sync", "مزامنة يدوية")}</span>
            </div>
            {system.status === "attention" && !error && (
              <p className="mt-2 text-[12.5px] text-[#8a5d0e]">{system.openErrors
                ? tx(`${system.openErrors} records couldn't be imported. Open “Manage connection” for details.`, `تعذّر استيراد ${system.openErrors} سجلّ. افتح «إدارة الاتصال» للتفاصيل.`)
                : tx("The last sync didn't complete. Try “Sync now” again.", "لم تكتمل آخر مزامنة. جرّب «مزامنة الآن» مجددًا.")}</p>
            )}
          </div>
        </div>
        <div className="flex gap-2 sm:shrink-0">
          {canManage && system.status !== "disconnected" && (
            <Button size="sm" loading={syncing} onClick={sync} data-basira="pos-sync-now"><RefreshCw size={14} />{tx("Sync now", "مزامنة الآن")}</Button>
          )}
          <Button size="sm" variant="secondary" onClick={onManage}><Settings2 size={14} />{tx("Manage connection", "إدارة الاتصال")}</Button>
        </div>
      </div>
      {error && (
        <div role="alert" className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-danger/10 p-3 text-[12.5px] text-danger">
          <XCircle size={14} /><span className="flex-1">{tx("Sync failed: ", "فشلت المزامنة: ")}{error}</span>
          <Button size="sm" variant="secondary" onClick={sync} loading={syncing}>{tx("Retry", "إعادة المحاولة")}</Button>
        </div>
      )}
    </div>
  );
}

function ManageSystem({ system, canManage, autoSync, labLinking, storeKeys, onClose, onChanged, onReconnect }: {
  system: ConnectedSystem; canManage: boolean; autoSync: boolean; labLinking: boolean; storeKeys: boolean; onClose: () => void; onChanged: () => void;
  onReconnect: (choice: Choice) => void;
}) {
  const tx = useTx();
  const labels = useSystemLabels();
  const [name, setName] = useState(system.customName ?? "");
  const [busy, setBusy] = useState<"" | "rename" | "test" | "disconnect" | "sync" | "reconnect" | "remove">("");
  const [error, setError] = useState("");
  const [confirmOff, setConfirmOff] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const apiKey = byApiKey(system);
  const [tests, setTests] = useState<Record<string, boolean | string>>({});
  const st = STATUS_UI[system.status];
  const active = system.channels.filter((c) => c.conn.status !== "disconnected");
  const fail = (e: unknown) => setError(friendlyError(e instanceof ApiError ? e.status : undefined, tx.isAr));

  async function rename(event: React.FormEvent) {
    event.preventDefault();
    const value = name.trim(); if (!value) return;
    setBusy("rename"); setError("");
    try { for (const { conn } of system.channels) await api(`/integrations/connections/${conn.id}`, { method: "PATCH", json: { display_name: value } });
      toast(tx("Name saved", "تم حفظ الاسم"), "", "ok"); onChanged(); }
    catch (e) { fail(e); } finally { setBusy(""); }
  }
  async function runTests() {
    setBusy("test"); setError(""); setTests({});
    const out: Record<string, boolean | string> = {};
    for (const { conn } of active) {
      try { out[conn.id] = (await api<{ ok: boolean }>(`/integrations/connections/${conn.id}/test`, { method: "POST" })).ok; }
      catch (e) { out[conn.id] = friendlyError(e instanceof ApiError ? e.status : undefined, tx.isAr); }
      setTests({ ...out });
    }
    setBusy("");
  }
  async function sync() {
    setBusy("sync"); setError("");
    try { const t = await syncSystem(system); toast(tx("Sync complete", "تمت المزامنة"), tx(`${t.imported} new · ${t.updated} updated`, `${t.imported} جديد · ${t.updated} محدّث`), "ok"); }
    catch (e) { fail(e); } finally { setBusy(""); onChanged(); }
  }
  // Demo POS reconnects in place (same sample source, no duplicates). A Lab shop always goes
  // back through its owner's approval: there is no shortcut that skips it.
  async function reconnectDemo() {
    setBusy("reconnect"); setError("");
    try { await api("/integrations/connections", { method: "POST", json: { provider_code: "demo" } });
      toast(tx("Reconnected", "تمت إعادة الربط"), "", "ok"); onChanged(); }
    catch (e) { fail(e); } finally { setBusy(""); }
  }
  async function disconnect() {
    setBusy("disconnect"); setError("");
    try { for (const { conn } of active) await api(`/integrations/connections/${conn.id}`, { method: "DELETE" });
      toast(tx("Disconnected", "تم قطع الاتصال"), tx("Your imported sales were kept.", "تم الاحتفاظ بمبيعاتك المستوردة."), "ok"); setConfirmOff(false); onChanged(); }
    catch (e) { fail(e); } finally { setBusy(""); }
  }
  // Remove = stop syncing + hide from your systems. Every imported invoice, return and the
  // history stay; linking the same system again later continues without duplicates.
  async function remove() {
    setBusy("remove"); setError("");
    try { for (const { conn } of system.channels) await api(`/integrations/connections/${conn.id}/remove`, { method: "POST" });
      toast(tx("System removed", "تمت إزالة النظام"), tx("Its sales, returns and history stay in IDRAK.", "بقيت مبيعاته ومرتجعاته وسجلاته في إدراك."), "ok");
      onChanged(); onClose(); }
    catch (e) { fail(e); setBusy(""); }
  }

  return (
    <Drawer open onOpenChange={(o) => { if (!o) onClose(); }} title={labels.name(system)}
      subtitle={<span className="inline-flex flex-wrap items-center gap-2">{labels.vendor(system)} <Badge tone={st.tone}>{tx(st.en, st.ar)}</Badge></span>}>
      {error && <p role="alert" className="mb-4 rounded-lg bg-danger/10 p-3 text-[13px] text-danger">{error}</p>}

      <h4 className="text-[13px] font-medium text-ink-2">{tx("Channels", "القنوات")}</h4>
      <ul className="mt-2 space-y-2">
        {system.channels.map(({ channel, conn }) => {
          const ch = CHANNEL_UI[channel]; const CI = ch.icon; const t = tests[conn.id];
          const connected = conn.status === "connected" && !conn.last_error && !conn.open_errors;
          return (
            <li key={conn.id} className="rounded-xl border border-line bg-paper p-3">
              <div className="flex flex-wrap items-center gap-2">
                <CI size={15} className="text-ink-2" /><span className="font-medium text-ink">{tx(ch.en, ch.ar)}</span>
                <Badge tone={conn.status === "disconnected" ? "neutral" : connected ? "olive" : "saffron"}>
                  {conn.status === "disconnected" ? tx("Not connected", "غير متصل") : connected ? tx("Connected", "متصل") : tx("Needs attention", "يحتاج انتباه")}
                </Badge>
                {t !== undefined && (t === true ? <Badge tone="olive"><CheckCircle2 size={11} />{tx("Test passed", "الاختبار ناجح")}</Badge>
                  : <Badge tone="danger"><XCircle size={11} />{typeof t === "string" ? t : tx("Test failed", "فشل الاختبار")}</Badge>)}
              </div>
              <p className="mt-1 text-[12px] text-ink-3">
                {conn.last_success_at ? tx(`Last sync ${timeAgo(conn.last_success_at, tx.locale)}`, `آخر مزامنة ${timeAgo(conn.last_success_at, tx.locale)}`) : tx("Not synced yet", "لم تتم المزامنة بعد")}
                {" · "}{tx(`${conn.sync_count} syncs`, `${conn.sync_count} مزامنة`)}
                {!!conn.open_errors && <> · <span className="text-danger">{tx(`${conn.open_errors} records need review`, `${conn.open_errors} سجلّ يحتاج مراجعة`)}</span></>}
              </p>
              <ChannelHistory id={conn.id} />
            </li>
          );
        })}
      </ul>
      {system.status !== "disconnected" && (
        <p className="mt-3 text-[12px] text-ink-3">{autoSync ? tx("New sales sync automatically.", "تتم مزامنة المبيعات الجديدة تلقائيًا.") : tx("Syncing is manual: use “Sync now” to bring in new sales.", "المزامنة يدوية: استخدم «مزامنة الآن» لجلب المبيعات الجديدة.")}</p>
      )}
      {system.status === "disconnected" && (
        <p className="mt-3 text-[12px] text-ink-3">{tx("Syncing is stopped. Sales imported earlier are still in IDRAK.", "المزامنة متوقفة. المبيعات المستوردة سابقًا ما زالت في إدراك.")}</p>
      )}

      {canManage && (
        <>
          <div className="mt-5 flex flex-wrap gap-2">
            {active.length > 0 && <Button size="sm" onClick={sync} loading={busy === "sync"} disabled={!!busy}><RefreshCw size={14} />{tx("Sync now", "مزامنة الآن")}</Button>}
            {active.length > 0 && <Button size="sm" variant="secondary" onClick={runTests} loading={busy === "test"} disabled={!!busy}><FlaskConical size={14} />{tx("Test connection", "اختبار الاتصال")}</Button>}
            {system.status === "disconnected" && system.kind === "lab" && !apiKey && labLinking && <Button size="sm" onClick={() => onReconnect("lab")} disabled={!!busy}><PlugZap size={14} />{tx("Reconnect (owner approval)", "إعادة الربط (بموافقة المالك)")}</Button>}
            {apiKey && storeKeys && (system.status !== "connected") && <Button size="sm" onClick={() => onReconnect("storekey")} disabled={!!busy}><KeyRound size={14} />{tx("Reconnect with an API key", "إعادة الربط بمفتاح API")}</Button>}
            {system.status === "disconnected" && system.kind === "demo" && <Button size="sm" onClick={reconnectDemo} loading={busy === "reconnect"} disabled={!!busy}><PlugZap size={14} />{tx("Reconnect", "إعادة الربط")}</Button>}
          </div>

          <form onSubmit={rename} className="mt-6">
            <label htmlFor="m-name" className="text-[13px] font-medium text-ink-2">{tx("Shop or branch name", "اسم المحل أو الفرع")}</label>
            <div className="mt-1 flex gap-2">
              <Input id="m-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder={labels.name(system)} />
              <Button type="submit" size="sm" variant="secondary" loading={busy === "rename"} disabled={!!busy || !name.trim()}><Pencil size={13} />{tx("Save", "حفظ")}</Button>
            </div>
          </form>

          {active.length > 0 && (
            <div className="mt-6 rounded-xl border border-line p-3">
              {confirmOff ? (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex-1 text-[12.5px] text-ink-2">{tx("Stop syncing this system? Imported sales stay in IDRAK.", "إيقاف مزامنة هذا النظام؟ ستبقى المبيعات المستوردة في إدراك.")}</span>
                  <Button size="sm" variant="danger" onClick={disconnect} loading={busy === "disconnect"}><Unplug size={13} />{tx("Disconnect", "قطع الاتصال")}</Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirmOff(false)}>{tx("Cancel", "إلغاء")}</Button>
                </div>
              ) : (
                <Button size="sm" variant="ghost" onClick={() => setConfirmOff(true)} disabled={!!busy}><Unplug size={13} />{tx("Disconnect…", "قطع الاتصال…")}</Button>
              )}
              <p className="mt-1 text-[11.5px] text-ink-3">{tx("Stops syncing. The system stays in your list so you can reconnect it.", "يوقف المزامنة، ويبقى النظام في قائمتك لتعيد ربطه.")}</p>
            </div>
          )}

          <div className="mt-3 rounded-xl border border-danger/25 p-3">
            {confirmRemove ? (
              <div role="alertdialog" aria-labelledby="rm-title" aria-describedby="rm-body">
                <p id="rm-title" className="font-medium text-ink">{tx(`Remove “${labels.name(system)}”?`, `إزالة «${labels.name(system)}»؟`)}</p>
                <ul id="rm-body" className="mt-2 list-disc space-y-1 ps-5 text-[12.5px] text-ink-2">
                  <li>{tx("Syncing stops and the connection is turned off at the source.", "تتوقف المزامنة ويُعطَّل الاتصال من جهة النظام.")}</li>
                  <li>{tx("It disappears from your active systems.", "يختفي من قائمة أنظمتك النشطة.")}</li>
                  <li>{tx("All imported invoices, sales, returns, profits and the audit history are kept.", "تبقى كل الفواتير والمبيعات والمرتجعات والأرباح وسجلات التدقيق المستوردة.")}</li>
                  <li>{tx("You can link it again later without duplicate invoices.", "يمكنك ربطه لاحقًا من جديد دون تكرار الفواتير.")}</li>
                </ul>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" variant="danger" onClick={remove} loading={busy === "remove"}><Trash2 size={13} />{tx("Remove system", "إزالة النظام")}</Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirmRemove(false)} disabled={busy === "remove"}>{tx("Cancel", "إلغاء")}</Button>
                </div>
              </div>
            ) : (
              <>
                <Button size="sm" variant="ghost" onClick={() => setConfirmRemove(true)} disabled={!!busy} className="text-danger"><Trash2 size={13} />{tx("Remove system…", "إزالة النظام…")}</Button>
                <p className="mt-1 text-[11.5px] text-ink-3">{tx("Disconnects and hides it from your systems. Your data stays.", "يقطع الاتصال ويخفيه من أنظمتك، وتبقى بياناتك.")}</p>
              </>
            )}
          </div>

          <details className="mt-6 rounded-xl border border-line bg-paper-2/40 p-3">
            <summary className="cursor-pointer text-[12.5px] text-ink-3">{tx("Advanced details (for support)", "تفاصيل متقدمة (للدعم الفني)")}</summary>
            <dl className="mt-3 space-y-2 text-[12px]">
              {system.channels.map(({ channel, conn }) => (
                <div key={conn.id} className="rounded-lg bg-paper p-2">
                  <dt className="font-medium text-ink-2">{tx(CHANNEL_UI[channel].en, CHANNEL_UI[channel].ar)}</dt>
                  <dd className="mt-1 grid gap-0.5 text-ink-3" dir="ltr">
                    <span>connection: <code>{conn.id}</code></span>
                    <span>connector: <code>{conn.provider_code}</code></span>
                    {conn.account_ref && <span>source account: <code>{conn.account_ref}</code></span>}
                    {conn.last_error && <span>last error: <code className="break-all">{conn.last_error}</code></span>}
                  </dd>
                </div>
              ))}
            </dl>
          </details>
        </>
      )}
    </Drawer>
  );
}

function ChannelHistory({ id }: { id: string }) {
  const tx = useTx();
  const q = useApiQuery<{ recent_jobs?: Job[]; sales_count?: number }>(`/integrations/connections/${id}`);
  if (q.error) return <p className="mt-2 text-[12px] text-danger">{tx("Couldn't load sync history.", "تعذّر تحميل سجل المزامنة.")}</p>;
  if (!q.data) return <Skeleton className="mt-2 h-5 w-40" />;
  const jobs = (q.data.recent_jobs || []).slice(0, 3);
  return (
    <div className="mt-2 text-[12px] text-ink-3">
      {!!q.data.sales_count && <p>{tx(`${q.data.sales_count} sales imported`, `${q.data.sales_count} فاتورة مستوردة`)}</p>}
      {jobs.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {jobs.map((j) => (
            <li key={j.id} className="flex items-center gap-1.5">
              <span className={clsx("size-1.5 rounded-full", j.status === "success" ? "bg-olive" : j.status === "failed" ? "bg-danger" : "bg-saffron")} />
              <span>{timeAgo(j.started_at, tx.locale)}</span>
              <span>· {j.status === "failed" ? tx("didn't complete", "لم تكتمل")
                : j.status === "running" ? tx("in progress", "جارية")
                : tx(`${j.counts?.imported ?? 0} new · ${j.counts?.updated ?? 0} updated`, `${j.counts?.imported ?? 0} جديد · ${j.counts?.updated ?? 0} محدّث`)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
