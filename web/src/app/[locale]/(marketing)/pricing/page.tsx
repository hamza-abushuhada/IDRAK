import type { Metadata } from "next";
import { getCopy, resolveLocale } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { PageHeader } from "@/components/marketing/primitives";
import { PricingPlans } from "@/components/marketing/PricingPlans";
import { Faq } from "@/components/marketing/Faq";
import { FinalCta } from "@/components/marketing/home/sections";

type P = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: P): Promise<Metadata> {
  return pageMeta(await resolveLocale(params), "pricing", "/pricing");
}

export default async function PricingPage({ params }: P) {
  const locale = await resolveLocale(params);
  const p = getCopy(locale).pricing;
  return (
    <>
      <PageHeader kicker={p.kicker} title={p.title} sub={p.sub} className="border-b-0" />
      <PricingPlans />
      <Faq title={p.faqTitle} items={p.faq} id="pricing-faq" bg="border-t bg-paper-2" />
      <FinalCta locale={locale} />
    </>
  );
}
