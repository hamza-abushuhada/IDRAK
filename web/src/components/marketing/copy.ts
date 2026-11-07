import marketing from "@/i18n/messages/marketing";
import { isLocale, type Locale } from "@/i18n/config";

export type Copy = typeof marketing.en;

export const getCopy = (l: Locale): Copy => marketing[l];

export async function resolveLocale(params: Promise<{ locale: string }>): Promise<Locale> {
  const { locale } = await params;
  return isLocale(locale) ? locale : "ar";
}

export const lh = (locale: Locale, path = "") => `/${locale}${path === "/" ? "" : path}`;

export const SOLUTION_SLUGS = ["minimarkets", "pharmacies", "restaurants", "fashion"] as const;
export type SolutionSlug = (typeof SOLUTION_SLUGS)[number];
export const isSolutionSlug = (s: string): s is SolutionSlug => (SOLUTION_SLUGS as readonly string[]).includes(s);

export const CONTACT = {
  email: "hello@idrak.jo",
  whatsapp: "https://wa.me/962790000000",
  instagram: "https://instagram.com/idrak.jo",
};
