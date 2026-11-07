"use client";
import { useMemo, useState } from "react";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { dateTime, timeAgo } from "@/lib/format";
import { AskIdrak, ErrorBox, PageHeader, Section, Table, type Col } from "@/components/app/kit";
import { useSession } from "@/components/app/session";
import { Badge, Card, Empty, Select } from "@/components/ui";
import SettingsNav from "@/components/workspace/SettingsNav";
import { SearchBox } from "@/components/workspace/common";

type Entry = { id: string; action: string; entity: string | null; entity_id: string | null; details: Record<string, unknown> | null; created_at: string; full_name: string | null };

const ACTIONS: Record<string, [string, string]> = {
  "org.created": ["Business created", "انعمل المشروع"],
  "settings.updated": ["Settings changed", "تغيّرت الإعدادات"],
  "branch.created": ["Branch added", "انضاف فرع"],
  "team.invited": ["Invited a teammate", "دعوة عضو"],
  "team.joined": ["Joined the team", "انضم للفريق"],
  "team.role_changed": ["Role changed", "تغيّرت صلاحية"],
  "team.removed": ["Removed from team", "انشال من الفريق"],
  "product.updated": ["Product edited", "تعديل صنف"],
  "purchase.emailed": ["Supplier order emailed", "انبعتت طلبية لمورد"],
  "insight.dismissed": ["Insight dismissed", "تجاهل ملاحظة"],
  "report.viewed": ["Report viewed", "عرض تقرير"],
};
const toneFor = (a: string): "terra" | "olive" | "sky" | "saffron" | "neutral" =>
  a.startsWith("team.") ? "sky" : a.startsWith("settings.") || a.startsWith("org.") || a.startsWith("branch.") ? "terra" : a.startsWith("product.") || a.startsWith("purchase.") ? "saffron" : a.startsWith("clean") || a.startsWith("upload") ? "olive" : "neutral";

function Details({ d }: { d: Record<string, unknown> | null }) {
  if (!d || typeof d !== "object" || !Object.keys(d).length) return <span className="text-ink-3">—</span>;
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-0.5 text-[12px] text-ink-2">
      {Object.entries(d).slice(0, 6).map(([k, v]) => (
        <span key={k}><span className="text-ink-3">{k.replace(/_/g, " ")}:</span> <span className="num">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span></span>
      ))}
    </span>
  );
}

export default function AuditPage() {
  const tx = useTx();
  const locale = useLocale();
  const { can } = useSession();
  const allowed = can("manager");
  const { data, error, refetch } = useApiQuery<Entry[]>(allowed ? "/audit" : null);
  const [q, setQ] = useState("");
  const [action, setAction] = useState("");

  const label = (a: string) => (ACTIONS[a] ? tx(ACTIONS[a][0], ACTIONS[a][1]) : a);
  const actions = useMemo(() => Array.from(new Set((data || []).map((e) => e.action))).sort(), [data]);
  const rows = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return data?.filter((e) => (!action || e.action === action) && (!ql || [e.full_name, e.entity, e.action, JSON.stringify(e.details || {})].some((s) => (s || "").toLowerCase().includes(ql))));
  }, [data, q, action]);

  const cols: Col<Entry>[] = [
    { key: "created_at", label: tx("Time", "الوقت"), render: (e) => <span className="whitespace-nowrap"><span className="num text-ink">{dateTime(e.created_at, locale)}</span><span className="block text-[11px] text-ink-3">{timeAgo(e.created_at, locale)}</span></span> },
    { key: "full_name", label: tx("User", "المستخدم"), render: (e) => <span className="whitespace-nowrap">{e.full_name || <span className="text-ink-3">{tx("System", "النظام")}</span>}</span> },
    { key: "action", label: tx("Action", "الإجراء"), render: (e) => <Badge tone={toneFor(e.action)}>{label(e.action)}</Badge> },
    { key: "entity", label: tx("On", "على"), render: (e) => <span className="block max-w-[260px] truncate text-ink-2" title={e.entity || ""}>{e.entity || "—"}{e.entity_id && e.entity_id.length < 16 && <span className="num ms-1 text-ink-3">· {e.entity_id}</span>}</span> },
    { key: "details", label: tx("Details", "التفاصيل"), render: (e) => <Details d={e.details} /> },
  ];

  return (
    <div>
      <PageHeader
        eyebrow={tx("Admin · Settings", "الإدارة · الإعدادات")}
        title={tx("Audit log", "سجل النشاط")}
        subtitle={tx("Who changed what, and when — the last 200 actions.", "مين غيّر شو، وإمتى — آخر 200 إجراء.")}
        actions={<AskIdrak q={tx("Summarise what changed in my business settings and prices this week.", "لخّصلي شو تغيّر بإعدادات المشروع والأسعار هالأسبوع.")} />}
      />
      <SettingsNav />

      {!allowed ? (
        <Card><Empty title={tx("Managers and owners only", "للمدير والمالك بس")} body={tx("Ask the owner if you need to see the activity history.", "اطلب من المالك إذا بدك تشوف سجل النشاط.")} /></Card>
      ) : error ? <ErrorBox error={error} retry={refetch} /> : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2.5">
            <SearchBox value={q} onChange={setQ} placeholder={tx("Search user, item or detail…", "دوّر على مستخدم، عنصر أو تفصيل…")} />
            <Select value={action} onChange={(e) => setAction(e.target.value)} aria-label={tx("Action", "الإجراء")}>
              <option value="">{tx("All actions", "كل الإجراءات")}</option>
              {actions.map((a) => <option key={a} value={a}>{label(a)}</option>)}
            </Select>
          </div>
          <Section title={tx("Activity", "النشاط")} subtitle={rows ? tx(`${rows.length} entries`, `${rows.length} إجراء`) : " "} bodyClass="p-0">
            <Table<Entry> id="audit-table" rows={rows} cols={cols} dense empty={q || action ? tx("No entries match.", "ما في نتائج.") : tx("Nothing recorded yet.", "لسا ما في إشي مسجّل.")} />
          </Section>
        </>
      )}
    </div>
  );
}
