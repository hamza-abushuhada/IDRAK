import type { Metadata } from "next";
import Link from "next/link";
import { getCopy, lh, resolveLocale } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { Arrow, Container, PageHeader } from "@/components/marketing/primitives";
import { BlogCover } from "@/components/marketing/BlogCover";
import { ARTICLES } from "@/components/marketing/content/blog";
import { date } from "@/lib/format";

type P = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: P): Promise<Metadata> {
  return pageMeta(await resolveLocale(params), "blog", "/blog");
}

export default async function BlogIndex({ params }: P) {
  const locale = await resolveLocale(params);
  const B = getCopy(locale).blog;
  const list = [...ARTICLES].sort((a, b) => b.date.localeCompare(a.date));
  const [first, ...rest] = list;

  return (
    <>
      <PageHeader kicker={B.kicker} title={B.title} sub={B.intro} />
      <Container className="py-16 sm:py-20">
        <article className="group relative grid grid-cols-1 gap-8 border-b border-line pb-14 lg:grid-cols-12 lg:items-center">
          <BlogCover slug={first.slug} className="aspect-[16/10] lg:col-span-7" />
          <div className="lg:col-span-5">
            <p className="flex flex-wrap gap-x-3 text-[13px] text-ink-3">
              <span className="text-terra-2">{first.tag[locale]}</span>
              <time dateTime={first.date}>{date(first.date, locale)}</time>
              <span>{B.minRead.replace("{n}", String(first.minutes))}</span>
            </p>
            <h2 className="mt-3 font-serif text-[32px] leading-[1.12] tracking-[-0.015em] text-ink sm:text-[40px] rtl:font-semibold rtl:leading-[1.4] rtl:tracking-normal">
              <Link href={lh(locale, `/blog/${first.slug}`)} className="after:absolute after:inset-0 focus-visible:outline-2 focus-visible:outline-terra group-hover:text-terra-2">
                {first[locale].title}
              </Link>
            </h2>
            <p className="mt-4 text-[17px] leading-relaxed text-ink-2">{first[locale].dek}</p>
            <p className="mt-6 inline-flex items-center gap-2 text-[15px] font-medium text-ink">{B.readMore} <Arrow size={15} /></p>
          </div>
        </article>

        <ul className="grid grid-cols-1 gap-10 pt-14 md:grid-cols-2">
          {rest.map((a) => (
            <li key={a.slug}>
              <article className="group relative">
                <BlogCover slug={a.slug} className="aspect-[16/9]" />
                <p className="mt-5 flex flex-wrap gap-x-3 text-[13px] text-ink-3">
                  <span className="text-terra-2">{a.tag[locale]}</span>
                  <time dateTime={a.date}>{date(a.date, locale)}</time>
                  <span>{B.minRead.replace("{n}", String(a.minutes))}</span>
                </p>
                <h2 className="mt-2 font-serif text-[26px] leading-[1.2] text-ink rtl:font-semibold rtl:leading-[1.5]">
                  <Link href={lh(locale, `/blog/${a.slug}`)} className="after:absolute after:inset-0 focus-visible:outline-2 focus-visible:outline-terra group-hover:text-terra-2">
                    {a[locale].title}
                  </Link>
                </h2>
                <p className="mt-3 text-[16px] leading-relaxed text-ink-2">{a[locale].dek}</p>
              </article>
            </li>
          ))}
        </ul>
      </Container>
    </>
  );
}
