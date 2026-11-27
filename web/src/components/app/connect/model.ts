// Pure view-model for IDRAK Connect: groups channel connections into the
// systems a shop owner thinks in, derives one honest status per system, and
// keeps technical identifiers out of everyday labels.

export type ConnStatus = "pending" | "connected" | "paused" | "error" | "disconnected";
export type Counts = { imported?: number; updated?: number; skipped?: number; failed?: number };
export type Job = {
  id: string; trigger: string; status: "running" | "success" | "partial" | "failed";
  counts: Counts; error: string | null; started_at: string; finished_at: string | null;
};
export type Connection = {
  id: string; provider_code: string; provider_name: string; provider_name_ar: string | null;
  provider_category: string; display_name: string; status: ConnStatus;
  last_sync_at: string | null; last_success_at: string | null; last_error: string | null;
  sync_count: number; open_errors: number; group_key: string;
  account_ref?: string; // managers only (advanced details)
  config?: { channel?: string; auto_sync?: boolean; paired_lab?: boolean } | null;
};
export type Provider = {
  code: string; name: string; name_ar: string | null; category: string;
  status: "demo" | "available" | "coming_soon"; is_implemented: boolean;
  capabilities: Record<string, boolean>; description: string | null; description_ar: string | null;
};

export type SystemKind = "lab" | "demo" | "other";
export type SystemStatus = "connected" | "attention" | "disconnected";
export type Channel = "in_store" | "online" | "other";
export type ConnectedSystem = {
  key: string; kind: SystemKind; customName: string | null; ordinal: number;
  channels: { channel: Channel; conn: Connection }[];
  status: SystemStatus; lastSuccess: string | null; openErrors: number;
};

export const LAB_CODES = new Set(["lab_pos", "lab_web"]);

export function systemKind(providerCode: string): SystemKind {
  return LAB_CODES.has(providerCode) ? "lab" : providerCode === "demo" ? "demo" : "other";
}

export function channelOf(c: Connection): Channel {
  const ch = c.config?.channel;
  return ch === "in_store" || ch === "online" ? ch : c.provider_code === "lab_web" ? "online" : c.provider_code === "lab_pos" || c.provider_code === "demo" ? "in_store" : "other";
}

/** A name the owner chose, or null when the stored name is a technical default. */
export function customName(c: Connection): string | null {
  const n = (c.display_name || "").trim();
  if (!n || n.startsWith("Paired Lab ") || n === c.provider_name || n === c.provider_name_ar) return null;
  return n;
}

function channelNeedsAttention(c: Connection): boolean {
  return c.status === "error" || c.status === "pending" || c.status === "paused" || (c.status === "connected" && (!!c.last_error || c.open_errors > 0));
}

export function systemStatus(conns: Connection[]): SystemStatus {
  const active = conns.filter((c) => c.status !== "disconnected");
  if (!active.length) return "disconnected";
  if (active.length < conns.length || active.some(channelNeedsAttention)) return "attention";
  return "connected";
}

const CHANNEL_ORDER: Record<Channel, number> = { in_store: 0, online: 1, other: 2 };

export function groupSystems(conns: Connection[]): ConnectedSystem[] {
  const map = new Map<string, Connection[]>();
  for (const c of conns) {
    const key = c.group_key || c.id;
    map.set(key, [...(map.get(key) || []), c]);
  }
  const systems: ConnectedSystem[] = [...map.entries()].map(([key, list]) => {
    const channels = list.map((conn) => ({ channel: channelOf(conn), conn }))
      .sort((a, b) => CHANNEL_ORDER[a.channel] - CHANNEL_ORDER[b.channel]);
    const successes = list.map((c) => c.last_success_at).filter((v): v is string => !!v).sort();
    return {
      key, kind: systemKind(list[0].provider_code), customName: list.map(customName).find(Boolean) ?? null, ordinal: 0,
      channels, status: systemStatus(list), lastSuccess: successes.at(-1) ?? null,
      openErrors: list.reduce((s, c) => s + (c.open_errors || 0), 0),
    };
  });
  // Active systems first, then by kind; number unnamed systems of the same kind.
  const rank: Record<SystemStatus, number> = { attention: 0, connected: 1, disconnected: 2 };
  systems.sort((a, b) => rank[a.status] - rank[b.status] || a.kind.localeCompare(b.kind) || a.key.localeCompare(b.key));
  const seen: Record<string, number> = {};
  for (const s of systems) { if (!s.customName) s.ordinal = (seen[s.kind] = (seen[s.kind] || 0) + 1); }
  return systems;
}

/** Friendly Arabic/English error text for API failures; never echoes internals. */
export function friendlyError(status: number | undefined, ar: boolean): string {
  const t = (en: string, a: string) => (ar ? a : en);
  if (status === 401) return t("Your session ended. Sign in again.", "انتهت الجلسة. سجّل الدخول مجددًا.");
  if (status === 403) return t("You don't have permission to manage connections in this business.", "ليست لديك صلاحية إدارة الاتصالات في هذه المؤسسة.");
  if (status === 404) return t("This connection no longer exists. Refresh the page.", "لم يعد هذا الاتصال موجودًا. حدّث الصفحة.");
  if (status === 409) return t("This connection is disconnected. Reconnect it first.", "هذا الاتصال غير متصل. أعد ربطه أولًا.");
  if (status === 400 || status === 502) return t("The sales system couldn't be reached or refused the request. Try again in a moment.", "تعذّر الوصول إلى نظام المبيعات أو رفض الطلب. حاول مجددًا بعد قليل.");
  if (status === 503) return t("Connections aren't available right now. Try again later.", "الاتصالات غير متاحة الآن. حاول لاحقًا.");
  return t("Something went wrong. Check your internet connection and try again.", "حدث خطأ. تحقق من اتصالك بالإنترنت وحاول مجددًا.");
}

/** Automatic sync is shown only when the scheduler really runs AND an active channel has it on (Demo POS is always manual). */
export function systemAutoSync(system: ConnectedSystem, schedulerActive: boolean): boolean {
  return schedulerActive && system.channels.some((c) => c.conn.status !== "disconnected" && c.conn.config?.auto_sync === true);
}

/** Wizard steps map onto the same four phases for every system, so the step count never changes mid-way. */
export type WizardStep = "type" | "provider" | "connect" | "authorize" | "name" | "test" | "done";
export const PHASES = 4;
export function phaseOf(step: WizardStep): number {
  return step === "type" ? 0 : step === "provider" ? 1 : step === "connect" || step === "authorize" ? 2 : 3;
}
