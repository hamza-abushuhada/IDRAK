import type { Metadata } from "next";
import { getCopy, resolveLocale } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { Hero } from "@/components/marketing/home/Hero";
import { LensStory } from "@/components/marketing/home/LensStory";
import { AssistantShowcase } from "@/components/marketing/home/AssistantShowcase";
import { FinalCta, HowItWorks, Modules, Pilot, PricingTeaser, ProblemNumbers } from "@/components/marketing/home/sections";
import { Faq } from "@/components/marketing/Faq";

type P = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: P): Promise<Metadata> {
  return pageMeta(await resolveLocale(params), "home", "/", { absoluteTitle: true });
}

export default async function HomePage({ params }: P) {
  const locale = await resolveLocale(params);
  const c = getCopy(locale);
  return (
    <>
      <Hero locale={locale} />
      <LensStory />
      <ProblemNumbers locale={locale} />
      <HowItWorks locale={locale} />
      <Modules locale={locale} />
      <AssistantShowcase />
      <Pilot locale={locale} />
      <PricingTeaser locale={locale} />
      <Faq kicker={c.faq.kicker} title={c.faq.title} items={c.faq.items} />
      <FinalCta locale={locale} />
    </>
  );
}
