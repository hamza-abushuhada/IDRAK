import type { Metadata } from "next";
import { getT } from "@/i18n/server";
import type { Locale } from "@/i18n/config";

export function pageMeta(locale: Locale, key: string, path: string, opts: { absoluteTitle?: boolean } = {}): Metadata {
  const t = getT(locale, "marketing");
  const title = t(`meta.${key}.title`);
  const description = t(`meta.${key}.description`);
  const p = path === "/" ? "" : path;
  return {
    title: opts.absoluteTitle ? { absolute: title } : title,
    description,
    alternates: { canonical: `/${locale}${p}`, languages: { ar: `/ar${p}`, en: `/en${p}` } },
    openGraph: { title, description, locale: locale === "ar" ? "ar_JO" : "en_US", siteName: locale === "ar" ? "إدراك" : "Idrak", type: "website" },
  };
}
