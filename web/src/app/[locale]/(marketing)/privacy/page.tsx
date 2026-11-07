import type { Metadata } from "next";
import { resolveLocale } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { LegalPage } from "@/components/marketing/LegalPage";

type P = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: P): Promise<Metadata> {
  return pageMeta(await resolveLocale(params), "privacy", "/privacy");
}

export default async function Page({ params }: P) {
  return <LegalPage locale={await resolveLocale(params)} doc="privacy" />;
}
