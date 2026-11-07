export type Loc = "ar" | "en";

export function jd(v: number | null | undefined, locale: Loc = "en", opts: { compact?: boolean; decimals?: number } = {}) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  let s: string;
  if (opts.compact && abs >= 10000) {
    s = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(v);
  } else {
    const d = opts.decimals ?? (abs >= 1000 ? 0 : abs >= 100 ? 1 : 3);
    s = new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
  }
  return locale === "ar" ? `${s} د.أ` : `JD ${s}`;
}

export function num(v: number | null | undefined, decimals = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: decimals, minimumFractionDigits: 0 }).format(v);
}

export function pct(v: number | null | undefined, decimals = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v >= 0 ? "" : "−"}${Math.abs(v).toFixed(decimals)}%`;
}

export function delta(v: number | null | undefined) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v >= 0 ? "▲" : "▼"} ${Math.abs(v).toFixed(1)}%`;
}

export function date(v: string | Date | null | undefined, locale: Loc = "en", opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }) {
  if (!v) return "—";
  const d = typeof v === "string" ? new Date(v) : v;
  return new Intl.DateTimeFormat(locale === "ar" ? "ar-JO-u-nu-latn" : "en-GB", opts).format(d);
}

export function dateTime(v: string | Date | null | undefined, locale: Loc = "en") {
  return date(v, locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function timeAgo(v: string | Date, locale: Loc = "en") {
  const d = typeof v === "string" ? new Date(v) : v;
  const s = (Date.now() - d.getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale === "ar" ? "ar" : "en", { numeric: "auto" });
  if (s < 60) return rtf.format(-Math.round(s), "second");
  if (s < 3600) return rtf.format(-Math.round(s / 60), "minute");
  if (s < 86400) return rtf.format(-Math.round(s / 3600), "hour");
  return rtf.format(-Math.round(s / 86400), "day");
}
