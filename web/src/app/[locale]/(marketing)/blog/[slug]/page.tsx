import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getCopy, lh, resolveLocale } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { Arrow, Container, Kicker } from "@/components/marketing/primitives";
import { BlogCover } from "@/components/marketing/BlogCover";
import { ARTICLES, getArticle, type Block } from "@/components/marketing/content/blog";
import { date } from "@/lib/format";

type P = { params: Promise<{ locale: string; slug: string }> };

export function generateStaticParams() {
  return ARTICLES.map((a) => ({ slug: a.slug }));
}

export async function generateMetadata({ params }: P): Promise<Metadata> {
  const locale = await resolveLocale(params);
  const { slug } = await params;
  const a = getArticle(slug);
  const base = pageMeta(locale, "blog", `/blog/${slug}`);
  if (!a) return base;
  return { ...base, title: a[locale].title, description: a[locale].dek, openGraph: { ...base.openGraph, title: a[locale].title, description: a[locale].dek, type: "article" } };
}

function Render({ b }: { b: Block }) {
  switch (b.t) {
    case "h2":
      return <h2 className="mt-12 font-serif text-[26px] leading-snug text-ink sm:text-[30px] rtl:font-semibold rtl:leading-[1.5]">{b.text}</h2>;
    case "ul":
      return (
        <ul className="mt-6 space-y-2.5">
          {b.items.map((i) => (
            <li key={i} className="flex gap-3 text-[18px] leading-[1.7] text-ink-2">
              <span aria-hidden className="mt-[15px] h-px w-4 shrink-0 bg-terra" />
              {i}
            </li>
          ))}
        </ul>
      );
    case "note":
      return <aside className="mt-8 rounded-[12px] border-s-[3px] border-saffron bg-saffron-soft/60 px-5 py-4 text-[16px] leading-relaxed text-ink">{b.text}</aside>;
    case "quote":
      return <blockquote className="mt-8 border-s-2 border-terra ps-5 font-serif text-[22px] leading-snug text-ink">{b.text}</blockquote>;
    default:
      return <p className="mt-6 text-[18px] leading-[1.8] text-ink-2">{b.text}</p>;
  }
}

export default async function BlogPost({ params }: P) {
  const locale = await resolveLocale(params);
  const { slug } = await params;
  const a = getArticle(slug);
  if (!a) notFound();
  const B = getCopy(locale).blog;
  const art = a[locale];
  const others = ARTICLES.filter((x) => x.slug !== slug);

  return (
    <>
      <article>
        <header className="border-b border-line">
          <Container className="max-w-[860px] pb-12 pt-12 sm:pt-16">
            <Link href={lh(locale, "/blog")} className="inline-flex items-center gap-2 rounded-sm text-[14px] text-ink-2 hover:text-ink focus-visible:outline-2 focus-visible:outline-terra">
              <Arrow size={14} className="rotate-180" /> {B.back}
            </Link>
            <Kicker tone="terra" className="mt-10">{a.tag[locale]}</Kicker>
            <h1 className="mt-4 font-serif text-[38px] font-[380] leading-[1.06] tracking-[-0.022em] text-ink text-balance sm:text-[54px] rtl:font-semibold rtl:leading-[1.35] rtl:tracking-normal">{art.title}</h1>
            <p className="mt-5 text-[20px] leading-[1.55] text-ink-2">{art.dek}</p>
            <p className="mt-6 flex flex-wrap gap-x-3 text-[13.5px] text-ink-3">
              <span>{B.by}</span>·<time dateTime={a.date}>{date(a.date, locale, { day: "numeric", month: "long", year: "numeric" })}</time>·<span>{B.minRead.replace("{n}", String(a.minutes))}</span>
            </p>
          </Container>
        </header>
        <Container className="max-w-[860px]">
          <BlogCover slug={a.slug} className="-mt-px aspect-[21/8] rounded-t-none" />
          <div className="mx-auto max-w-[68ch] pb-20 pt-6">
            {art.body.map((b, i) => <Render key={i} b={b} />)}
          </div>
        </Container>
      </article>

      <section className="border-y border-line bg-paper-2">
        <Container className="flex max-w-[860px] flex-col gap-6 py-14 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-serif text-[26px] text-ink rtl:font-semibold">{B.ctaTitle}</p>
            <p className="mt-2 text-[16px] text-ink-2">{B.ctaBody}</p>
          </div>
          <Link href={lh(locale, "/health-check")} className="inline-flex h-12 shrink-0 items-center gap-2 rounded-full bg-terra px-7 text-[15px] font-medium text-paper hover:bg-terra-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-terra">
            {B.ctaButton} <Arrow size={15} />
          </Link>
        </Container>
      </section>

      <Container className="max-w-[860px] py-16">
        <h2 className="font-mono text-[11.5px] uppercase tracking-[0.16em] text-ink-3 rtl:font-sans rtl:text-[13px] rtl:tracking-normal">{B.next}</h2>
        <ul className="mt-4 border-t border-ink/80">
          {others.map((o) => (
            <li key={o.slug} className="border-b border-line">
              <Link href={lh(locale, `/blog/${o.slug}`)} className="group flex items-center justify-between gap-6 py-6 focus-visible:outline-2 focus-visible:outline-terra">
                <span>
                  <span className="block text-[13px] text-terra-2">{o.tag[locale]}</span>
                  <span className="mt-1 block font-serif text-[22px] text-ink group-hover:text-terra-2 rtl:font-semibold">{o[locale].title}</span>
                </span>
                <Arrow size={18} className="text-ink-3" />
              </Link>
            </li>
          ))}
        </ul>
      </Container>
    </>
  );
}
