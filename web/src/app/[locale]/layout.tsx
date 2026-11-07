import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Alexandria, Fraunces, IBM_Plex_Mono, IBM_Plex_Sans, IBM_Plex_Sans_Arabic } from "next/font/google";
import "../globals.css";
import { dirOf, isLocale, locales } from "@/i18n/config";
import Providers from "@/components/Providers";

const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces", axes: ["SOFT", "opsz"], display: "swap" });
const alexandria = Alexandria({ subsets: ["arabic", "latin"], variable: "--font-alexandria", display: "swap" });
const plex = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-plex", display: "swap" });
const plexAr = IBM_Plex_Sans_Arabic({ subsets: ["arabic"], weight: ["400", "500", "600", "700"], variable: "--font-plex-ar", display: "swap" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex-mono", display: "swap" });

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const ar = locale === "ar";
  return {
    title: { default: ar ? "إدراك — نظّف بياناتك واعرف وين عم تخسر" : "Idrak — Clean your data. Find your money.", template: ar ? "%s · إدراك" : "%s · Idrak" },
    description: ar
      ? "منصة عربية لتنظيف بيانات المحلات والشركات الصغيرة وتحويلها لقرارات: مبيعات، مخزون، زبائن، وخسائر مخفية."
      : "Arabic-first data cleaning and decision support for small businesses: sales, stock, customers and hidden money leaks.",
    icons: { icon: "/favicon.svg" },
  };
}

export default async function LocaleLayout({ children, params }: { children: React.ReactNode; params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return (
    <html lang={locale} dir={dirOf(locale)} className={`${fraunces.variable} ${alexandria.variable} ${plex.variable} ${plexAr.variable} ${plexMono.variable}`}>
      <body className="min-h-dvh bg-paper text-ink">
        <Providers locale={locale}>{children}</Providers>
      </body>
    </html>
  );
}
