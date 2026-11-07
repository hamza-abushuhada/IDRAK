"use client";
import { useLocale } from "@/i18n";
import { getCopy } from "./copy";

export function useCopy() {
  const locale = useLocale();
  return { c: getCopy(locale), locale };
}
