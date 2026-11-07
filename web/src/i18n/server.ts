import type { Locale } from "./config";
import common from "./messages/common";
import marketing from "./messages/marketing";
import app from "./messages/app";
import assistant from "./messages/assistant";

const NS = { common, marketing, app, assistant } as const;
type Namespace = keyof typeof NS;

function lookup(obj: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((o, k) => (o && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined), obj);
}

export function getT(locale: Locale, ns: Namespace = "common") {
  const dict = NS[ns] as unknown as Record<Locale, unknown>;
  const t = (key: string, vars?: Record<string, string | number>) => {
    let v = lookup(dict[locale], key);
    if (v === undefined) v = lookup(dict.en, key);
    if (typeof v !== "string") return key;
    return vars ? v.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? "")) : v;
  };
  t.raw = <T,>(key: string) => (lookup(dict[locale], key) ?? lookup(dict.en, key)) as T;
  return t;
}
