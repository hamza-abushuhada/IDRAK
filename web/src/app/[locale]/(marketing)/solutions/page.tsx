import type { Metadata } from "next";
import Link from "next/link";
import { getCopy, lh, resolveLocale, SOLUTION_SLUGS } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { Arrow, Container, PageHeader } from "@/components/marketing/primitives";
import { FinalCta } from "@/components/marketing/home/sections";

type P = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: P): Promise<Metadata> {
  return pageMeta(await resolveLocale(params), "solutions", "/solutions");
}

export default async function SolutionsIndex({ params }: P) {
  const locale = await resolveLocale(params);
  const c = getCopy(locale);
  const S = c.solutions;
  return (
    <>
      <PageHeader kicker={S.kicker} title={S.indexTitle} sub={S.indexIntro} />
      <Container className="py-16 sm:py-20">
        <ul className="border-t border-ink/80">
          {SOLUTION_SLUGS.map((slug, i) => {
            const s = S.items[slug];
            const top = s.leaks[0];
            return (
              <li key={slug} className="border-b border-line">
                <Link href={lh(locale, `/solutions/${slug}`)} className="group grid grid-cols-1 items-baseline gap-3 py-8 focus-visible:outline-2 focus-visible:outline-terra sm:grid-cols-12 sm:gap-6 sm:py-10">
                  <span className="num text-[13px] text-terra sm:col-span-1">0{i + 1}</span>
                  <span className="sm:col-span-5">
                    <span className="block font-serif text-[32px] leading-tight text-ink transition-colors group-hover:text-terra-2 sm:text-[40px] rtl:font-semibold">{s.name}</span>
                    <span className="mt-2 block text-[16px] text-ink-2">{s.short}</span>
                  </span>
                  <span className="text-[15px] leading-relaxed text-ink-2 sm:col-span-4">
                    {top.title} · <span className="num text-terra-2">{top.amount} {c.common.jd}</span>
                    <span className="block text-[13px] text-ink-3">{c.common.illustrative}</span>
                  </span>
                  <span className="hidden justify-end sm:col-span-2 sm:flex">
                    <span className="inline-flex size-11 items-center justify-center rounded-full border border-line transition-colors group-hover:border-ink group-hover:bg-ink group-hover:text-paper">
                      <Arrow size={17} />
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </Container>
      <FinalCta locale={locale} title={S.ctaTitle} body={S.ctaBody} primary={S.ctaPrimary} secondary={S.ctaSecondary} />
    </>
  );
}
