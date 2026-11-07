import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getCopy, isSolutionSlug, lh, resolveLocale, SOLUTION_SLUGS } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { Arrow, Container, Kicker } from "@/components/marketing/primitives";
import { SolutionDash } from "@/components/marketing/SolutionDash";
import { FinalCta } from "@/components/marketing/home/sections";

type P = { params: Promise<{ locale: string; slug: string }> };

export function generateStaticParams() {
  return SOLUTION_SLUGS.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: P): Promise<Metadata> {
  const locale = await resolveLocale(params);
  const { slug } = await params;
  const base = pageMeta(locale, "solutions", `/solutions/${slug}`);
  if (!isSolutionSlug(slug)) return base;
  const s = getCopy(locale).solutions.items[slug];
  return { ...base, title: `${s.name} — ${s.headline}`, description: s.intro };
}

export default async function SolutionPage({ params }: P) {
  const locale = await resolveLocale(params);
  const { slug } = await params;
  if (!isSolutionSlug(slug)) notFound();
  const c = getCopy(locale);
  const S = c.solutions;
  const s = S.items[slug];
  const total = s.leaks.reduce((a, l) => a + Number(l.amount.replace(/,/g, "")), 0);

  return (
    <>
      <header className="border-b border-line">
        <Container className="grid grid-cols-1 items-center gap-14 pb-20 pt-12 sm:pt-16 lg:grid-cols-12 lg:gap-12">
          <div className="lg:col-span-6">
            <nav aria-label="Breadcrumb" className="flex items-center gap-2">
              <Link href={lh(locale, "/solutions")} className="rounded-sm hover:text-ink"><Kicker>{S.kicker}</Kicker></Link>
              <span aria-hidden className="text-ink-3">/</span>
              <Kicker tone="terra">{s.name}</Kicker>
            </nav>
            <h1 className="mt-6 font-serif text-[42px] font-[370] leading-[1.03] tracking-[-0.025em] text-ink text-balance sm:text-[60px] rtl:font-semibold rtl:leading-[1.35] rtl:tracking-normal">{s.headline}</h1>
            <p className="mt-6 max-w-[44ch] text-[18px] leading-[1.6] text-ink-2">{s.intro}</p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Link href={lh(locale, "/health-check")} className="inline-flex h-12 items-center gap-2 rounded-full bg-terra px-7 text-[15px] font-medium text-paper transition-colors hover:bg-terra-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-terra">
                {S.ctaPrimary} <Arrow size={16} />
              </Link>
              <Link href={lh(locale, "/signup")} className="inline-flex h-12 items-center rounded-full border border-line px-7 text-[15px] font-medium text-ink transition-colors hover:bg-sand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-terra">
                {S.ctaSecondary}
              </Link>
            </div>
          </div>
          <div className="lg:col-span-6 lg:ps-6">
            <SolutionDash d={s.dash} slug={slug} title={S.dashTitle} jd={c.common.jd} note={c.common.illustrative} />
          </div>
        </Container>
      </header>

      <section aria-labelledby="pains" className="border-b border-line bg-paper-2">
        <Container className="py-20 sm:py-24">
          <Kicker className="mb-4">{s.name}</Kicker>
          <h2 id="pains" className="font-serif text-[32px] font-[400] tracking-[-0.018em] text-ink sm:text-[40px] rtl:font-semibold rtl:tracking-normal">{S.painsTitle}</h2>
          <ol className="mt-12 grid grid-cols-1 border-t border-ink/80 md:grid-cols-3">
            {s.pains.map((p, i) => (
              <li key={p.title} className={`border-b border-line py-8 md:border-b-0 ${i > 0 ? "md:border-s md:ps-8" : ""} ${i < 2 ? "md:pe-8" : ""}`}>
                <span className="num text-[13px] text-terra">0{i + 1}</span>
                <h3 className="mt-3 font-serif text-[24px] leading-snug text-ink rtl:font-semibold">{p.title}</h3>
                <p className="mt-3 text-[16px] leading-relaxed text-ink-2">{p.body}</p>
              </li>
            ))}
          </ol>
        </Container>
      </section>

      <section aria-labelledby="leaks" className="border-b border-line">
        <Container className="grid grid-cols-1 gap-12 py-20 sm:py-24 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <h2 id="leaks" className="font-serif text-[32px] font-[400] tracking-[-0.018em] text-ink sm:text-[40px] rtl:font-semibold rtl:tracking-normal">{S.leaksTitle}</h2>
            <p className="mt-4 text-[14px] text-ink-3">{S.leakNote}</p>
          </div>
          <div className="lg:col-span-8">
            <ul className="border-t border-ink/80">
              {s.leaks.map((l) => (
                <li key={l.title} className="grid grid-cols-[1fr_auto] items-baseline gap-x-6 gap-y-1 border-b border-line py-6">
                  <h3 className="text-[18px] font-medium text-ink">{l.title}</h3>
                  <p className="num row-span-2 text-end text-[22px] text-terra-2 sm:text-[26px]">
                    {l.amount} <span className="text-[12px] text-ink-3">{c.common.jd}</span>
                  </p>
                  <p className="max-w-[52ch] text-[15.5px] leading-relaxed text-ink-2">{l.body}</p>
                </li>
              ))}
            </ul>
            <div className="flex items-baseline justify-between pt-5">
              <span className="font-serif text-[20px] text-ink rtl:font-semibold">{c.lens.chartTotal}</span>
              <span className="num text-[28px] text-ink">
                {total.toLocaleString("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} <span className="text-[13px] text-ink-3">{c.common.jd}</span>
              </span>
            </div>
          </div>
        </Container>
      </section>

      <section aria-labelledby="others" className="border-b border-line">
        <Container className="py-14">
          <h2 id="others" className="font-mono text-[11.5px] uppercase tracking-[0.16em] text-ink-3 rtl:font-sans rtl:text-[13px] rtl:tracking-normal">{S.others}</h2>
          <ul className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {SOLUTION_SLUGS.filter((x) => x !== slug).map((x) => (
              <li key={x}>
                <Link href={lh(locale, `/solutions/${x}`)} className="group flex h-full items-start justify-between gap-4 rounded-[14px] border border-line bg-[#FFFCF7] p-5 transition-colors hover:border-ink/40 focus-visible:outline-2 focus-visible:outline-terra">
                  <span>
                    <span className="block font-serif text-[20px] text-ink rtl:font-semibold">{S.items[x].name}</span>
                    <span className="mt-1 block text-[14px] text-ink-3">{S.items[x].short}</span>
                  </span>
                  <Arrow size={16} className="mt-1.5 text-ink-3 transition-transform group-hover:translate-x-0.5 rtl:group-hover:-translate-x-0.5" />
                </Link>
              </li>
            ))}
          </ul>
        </Container>
      </section>

      <FinalCta locale={locale} title={S.ctaTitle} body={S.ctaBody} primary={S.ctaPrimary} secondary={S.ctaSecondary} />
    </>
  );
}
