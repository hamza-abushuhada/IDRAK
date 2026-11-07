"use client";
import { createContext, useContext, useMemo } from "react";
import type { Locale } from "./config";
import common from "./messages/common";
import marketing from "./messages/marketing";
import app from "./messages/app";
import assistant from "./messages/assistant";

const NS = { common, marketing, app, assistant } as const;
export type Namespace = keyof typeof NS;

const LocaleCtx = createContext<Locale>("ar");

export function I18nProvider({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return <LocaleCtx.Provider value={locale}>{children}</LocaleCtx.Provider>;
}

export const useLocale = () => useContext(LocaleCtx);

function lookup(obj: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((o, k) => (o && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined), obj);
}

export function translate(locale: Locale, ns: Namespace, key: string, vars?: Record<string, string | number>): string {
  const dict = NS[ns] as unknown as Record<Locale, unknown>;
  let v = lookup(dict[locale], key);
  if (v === undefined) v = lookup(dict.en, key);
  if (typeof v !== "string") return key;
  return vars ? v.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? "")) : v;
}

export function translateRaw<T = unknown>(locale: Locale, ns: Namespace, key: string): T {
  const dict = NS[ns] as unknown as Record<Locale, unknown>;
  return (lookup(dict[locale], key) ?? lookup(dict.en, key)) as T;
}

export function useTx() {
  const locale = useLocale();
  return useMemo(() => {
    const tx = (en: string, ar: string) => (locale === "ar" ? ar : en);
    tx.locale = locale;
    tx.isAr = locale === "ar";
    return tx;
  }, [locale]);
}

export function useT(ns: Namespace = "common") {
  const locale = useLocale();
  return useMemo(() => {
    const t = (key: string, vars?: Record<string, string | number>) => translate(locale, ns, key, vars);
    t.raw = <T,>(key: string) => translateRaw<T>(locale, ns, key);
    t.locale = locale;
    return t;
  }, [locale, ns]);
}
