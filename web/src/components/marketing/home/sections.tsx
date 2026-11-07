import clsx from "clsx";
import Link from "next/link";
import { LogoMark } from "@/components/Logo";
import type { Locale } from "@/i18n/config";
import { getCopy, lh } from "../copy";
import { Arrow, Container, Kicker, SectionHead, linkCls } from "../primitives";
import { Gauge } from "../Gauge";
import { ModuleArt } from "./ModuleArt";

export function ProblemNumbers({ locale }: { locale: Locale }) {
  const p = getCopy(locale).problem;
  return (
    <section aria-labelledby="problem-title" className="border-b border-line bg-paper-2">
      <Container className="grid grid-cols-1 gap-14 py-20 sm:py-28 lg:grid-cols-12 lg:gap-12">
        <div className="lg:col-span-5">
          <Kicker className="mb-4">{p.kicker}</Kicker>
          <h2 id="problem-title" className="font-serif text-[32px] font-[400] leading-[1.1] tracking-[-0.018em] text-ink text-balance sm:text-[42px] rtl:font-semibold rtl:leading-[1.45] rtl:tracking-normal">{p.title}</h2>
          <p className="mt-6 max-w-[42ch] text-[17px] leading-[1.65] text-ink-2">{p.intro}</p>
        </div>
        <div className="lg:col-span-7">
          <dl className="grid grid-cols-1 border-t border-ink/80 sm:grid-cols-2">
            {p.stats.map((s, i) => (
              <div key={i} className={clsx("border-b border-line py-7 sm:py-8", i % 2 === 0 ? "sm:pe-8" : "sm:border-s sm:ps-8")}>
                <dt className="sr-only">{s.label}</dt>
                <dd>
                  <p className="font-serif text-[52px] font-[340] leading-none tracking-[-0.03em] text-ink sm:text-[60px] rtl:font-medium rtl:tracking-normal">
                    <bdi>{s.value}</bdi>
                  </p>
                  <p className="mt-4 max-w-[30ch] text-[16px] leading-snug text-ink-2">{s.label}</p>
                  <p className="mt-3 flex items-center gap-1.5 text-[12.5px] text-ink-3">
                    <span className="num text-terra">*</span> {s.note}
                  </p>
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-6 max-w-[60ch] text-[13px] leading-relaxed text-ink-3">
            <span className="num me-1 text-terra">*</span>{p.footnote}
          </p>
        </div>
      </Container>
    </section>
  );
}

export function HowItWorks({ locale }: { locale: Locale }) {
  const h = getCopy(locale).how;
  const a = h.art;
  const art = [
    <div key="u" className="space-y-2" aria-hidden>
      <div className="flex items-center justify-between rounded-lg border border-line bg-[#FFFCF7] px-3 py-2">
        <span dir="ltr" className="font-mono text-[12px] text-ink">{a.file}</span>
        <span className="text-[11.5px] text-ink-3">{a.rows}</span>
      </div>
      {a.map.map((m) => (
        <div key={m.from} className="flex items-center gap-2 text-[12.5px]">
          <span className="min-w-0 flex-1 truncate rounded-md border border-dashed border-ink-3/40 px-2 py-1 text-ink-2"><bdi>{m.from}</bdi></span>
          <Arrow size={12} className="text-ink-3" />
          <span className="min-w-0 flex-1 truncate rounded-md bg-olive-soft px-2 py-1 text-ink">{m.to}</span>
        </div>
      ))}
    </div>,
    <div key="c" className="flex flex-col items-center pt-1" aria-hidden>
      <Gauge value={97} ghost={97} size={190}>
        <span className="num text-[30px] leading-none text-ink">97</span>
      </Gauge>
      <p className="mt-2 text-[12px] text-ink-3"><span dir="ltr"><span className="num text-terra line-through">42</span> → <span className="num text-olive">97</span></span> · {a.score}</p>
    </div>,
    <div key="d" className="rounded-xl border border-line bg-[#FFFCF7] p-4 shadow-[var(--shadow-paper)]" aria-hidden>
      <p className="font-serif text-[18px] leading-snug text-ink rtl:font-semibold">{a.decision}</p>
      <p className="mt-2 text-[12.5px] text-ink-3">{a.decisionMeta}</p>
      <div className="mt-3 flex h-10 items-end gap-1">
        {[30, 34, 31, 38, 44, 62, 80, 96, 88].map((v, i) => (
          <span key={i} className={clsx("flex-1 rounded-t-[2px]", i >= 5 ? "bg-saffron" : "bg-ink/15")} style={{ height: `${v}%` }} />
        ))}
      </div>
    </div>,
  ];
  return (
    <section aria-labelledby="how-title" className="border-b border-line">
      <Container className="py-20 sm:py-28">
        <SectionHead kicker={h.kicker} title={<span id="how-title">{h.title}</span>} />
        <ol className="mt-14 grid grid-cols-1 border-t border-ink/80 md:grid-cols-3">
          {h.steps.map((s, i) => (
            <li key={s.verb} className={clsx("flex flex-col border-b border-line py-8 md:border-b-0 md:py-10", i > 0 && "md:border-s md:ps-8", i < 2 && "md:pe-8")}>
              <div className="flex items-baseline justify-between gap-4">
                <span className="num text-[13px] text-terra">0{i + 1}</span>
                <span className="text-[12.5px] text-ink-3">{s.time}</span>
              </div>
              <h3 className="mt-3 font-serif text-[34px] font-[400] tracking-[-0.02em] text-ink rtl:font-semibold rtl:tracking-normal">{s.verb}</h3>
              <p className="mt-3 max-w-[38ch] text-[16px] leading-relaxed text-ink-2">{s.body}</p>
              <div className="mt-8 md:mt-auto md:pt-8">{art[i]}</div>
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}

export function Modules({ locale }: { locale: Locale }) {
  const c = getCopy(locale);
  const m = c.modules;
  return (
    <section id="product" aria-labelledby="modules-title" className="scroll-mt-20 border-b border-line">
      <Container className="py-20 sm:py-28">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:items-end">
          <div className="lg:col-span-6">
            <Kicker className="mb-4">{m.kicker}</Kicker>
            <h2 id="modules-title" className="font-serif text-[32px] font-[400] leading-[1.08] tracking-[-0.018em] text-ink sm:text-[44px] rtl:font-semibold rtl:leading-[1.4] rtl:tracking-normal">{m.title}</h2>
          </div>
          <p className="max-w-[46ch] text-[17px] leading-[1.65] text-ink-2 lg:col-span-5 lg:col-start-8">{m.intro}</p>
        </div>
        <ul className="mt-14 grid grid-cols-1 border-s border-t border-line sm:grid-cols-2 lg:grid-cols-3">
          {m.items.map((it, i) => (
            <li key={it.key} className="flex flex-col border-b border-e border-line p-6 sm:p-7">
              <ModuleArt k={it.key} a={m.art} jd={c.common.jd} />
              <div className="mt-6 flex items-baseline gap-3">
                <span className="num text-[12px] text-terra">0{i + 1}</span>
                <h3 className="font-serif text-[23px] font-[450] tracking-[-0.01em] text-ink rtl:font-semibold rtl:tracking-normal">{it.name}</h3>
              </div>
              <p className="mt-3 text-[15.5px] leading-relaxed text-ink-2">{it.body}</p>
              <ul className="mt-5 space-y-1.5 border-t border-line/70 pt-4 text-[13.5px] text-ink-2">
                {it.points.map((p) => (
                  <li key={p} className="flex gap-2"><span aria-hidden className="mt-[9px] h-px w-3 shrink-0 bg-terra" />{p}</li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}

export function Pilot({ locale }: { locale: Locale }) {
  const p = getCopy(locale).pilot;
  const f = p.feature;
  return (
    <section aria-labelledby="pilot-title" className="border-b border-line bg-paper-2">
      <Container className="py-20 sm:py-28">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <Kicker className="mb-4">{p.kicker}</Kicker>
            <h2 id="pilot-title" className="font-serif text-[32px] font-[400] leading-[1.1] tracking-[-0.018em] text-ink sm:text-[44px] rtl:font-semibold rtl:leading-[1.4] rtl:tracking-normal">{p.title}</h2>
          </div>
          <p className="max-w-[44ch] rounded-lg border border-dashed border-ink-3/50 px-3.5 py-2.5 text-[13px] leading-snug text-ink-3">{p.note}</p>
        </div>

        <figure className="mt-14 grid grid-cols-1 gap-10 border-t border-ink/80 pt-10 lg:grid-cols-12">
          <div className="lg:col-span-8">
            <span aria-hidden className="block font-serif text-[64px] leading-[0.6] text-terra">“</span>
            <blockquote className="mt-2 font-serif text-[26px] font-[380] leading-[1.3] tracking-[-0.01em] text-ink text-pretty sm:text-[34px] rtl:font-medium rtl:leading-[1.6] rtl:tracking-normal">
              {f.quote}
            </blockquote>
            <figcaption className="mt-6 text-[14.5px] text-ink-2">
              <span className="font-medium text-ink">{f.who}</span> · {f.shop}, {f.area}
            </figcaption>
          </div>
          <dl className="grid content-start gap-0 lg:col-span-4">
            {f.stats.map((s) => (
              <div key={s.label} className="border-b border-line py-4 first:pt-0">
                <dd className="num text-[28px] text-ink"><bdi>{s.value}</bdi></dd>
                <dt className="mt-1 text-[13.5px] text-ink-3">{s.label}</dt>
              </div>
            ))}
          </dl>
        </figure>

        <div className="mt-14 grid grid-cols-1 gap-6 md:grid-cols-2">
          {p.quotes.map((q) => (
            <figure key={q.shop} className="rounded-[14px] border border-line bg-[#FFFCF7] p-7 shadow-[var(--shadow-paper)]">
              <blockquote className="font-serif text-[20px] leading-[1.45] text-ink rtl:font-medium rtl:leading-[1.75]">“{q.quote}”</blockquote>
              <figcaption className="mt-5 text-[13.5px] text-ink-2"><span className="font-medium text-ink">{q.who}</span> · {q.shop}</figcaption>
            </figure>
          ))}
        </div>
      </Container>
    </section>
  );
}

export function PricingTeaser({ locale }: { locale: Locale }) {
  const c = getCopy(locale);
  const t = c.pricingTeaser;
  return (
    <section aria-labelledby="pt-title" className="border-b border-line">
      <Container className="py-20 sm:py-28">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:items-end">
          <div className="lg:col-span-7">
            <Kicker className="mb-4">{t.kicker}</Kicker>
            <h2 id="pt-title" className="font-serif text-[32px] font-[400] leading-[1.08] tracking-[-0.018em] text-ink sm:text-[44px] rtl:font-semibold rtl:leading-[1.4] rtl:tracking-normal">{t.title}</h2>
          </div>
          <p className="text-[17px] leading-relaxed text-ink-2 lg:col-span-5">{t.body}</p>
        </div>
        <ul className="mt-12 grid grid-cols-1 border-t border-ink/80 md:grid-cols-3">
          {c.plans.items.map((p, i) => {
            const pop = p.key === "growth";
            return (
              <li key={p.key} className={clsx("relative border-b border-line py-8 md:border-b-0", i > 0 && "md:border-s md:ps-8", i < 2 && "md:pe-8")}>
                {pop && <span aria-hidden className="absolute inset-x-0 -top-px h-[3px] bg-terra md:start-8 md:end-8" />}
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-serif text-[22px] text-ink rtl:font-semibold">{p.name}</h3>
                  {pop && <span className="rounded-full bg-terra-soft px-2.5 py-0.5 text-[11.5px] font-medium text-terra-2">{c.plans.popular}</span>}
                </div>
                <p className="mt-4 flex items-baseline gap-2">
                  <span className="num text-[44px] leading-none text-ink">{p.monthly}</span>
                  <span className="text-[14px] text-ink-2">{c.common.jd} {c.common.perMonth}</span>
                </p>
                <p className="mt-3 max-w-[32ch] text-[14.5px] leading-relaxed text-ink-2">{p.tagline}</p>
              </li>
            );
          })}
        </ul>
        <div className="mt-10">
          <Link href={lh(locale, "/pricing")} className={clsx(linkCls, "inline-flex items-center gap-2 text-[15px] font-medium text-ink")}>
            {t.seeAll} <Arrow size={15} />
          </Link>
        </div>
      </Container>
    </section>
  );
}

export function FinalCta({ locale, title, body, primary, secondary, primaryHref, secondaryHref }: {
  locale: Locale; title?: string; body?: string; primary?: string; secondary?: string; primaryHref?: string; secondaryHref?: string;
}) {
  const c = getCopy(locale).cta;
  return (
    <section aria-labelledby="cta-title" className="bg-terra text-paper">
      <Container className="relative py-20 sm:py-28">
        <LogoMark size={44} color="currentColor" className="text-paper/90" />
        <h2 id="cta-title" className="mt-8 max-w-[16ch] font-serif text-[40px] font-[360] leading-[1.02] tracking-[-0.025em] text-balance sm:text-[64px] rtl:max-w-[20ch] rtl:font-semibold rtl:leading-[1.35] rtl:tracking-normal">
          {title ?? c.title}
        </h2>
        <p className="mt-6 max-w-[44ch] text-[18px] leading-relaxed text-paper/85">{body ?? c.body}</p>
        <div className="mt-10 flex flex-wrap gap-3">
          <Link href={primaryHref ?? lh(locale, "/health-check")} className="inline-flex h-12 items-center gap-2 rounded-full bg-paper px-7 text-[15px] font-medium text-ink transition-colors hover:bg-sand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-paper">
            {primary ?? c.primary} <Arrow size={16} />
          </Link>
          <Link href={secondaryHref ?? lh(locale, "/signup")} className="inline-flex h-12 items-center rounded-full border border-paper/45 px-7 text-[15px] font-medium text-paper transition-colors hover:bg-paper/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-paper">
            {secondary ?? c.secondary}
          </Link>
        </div>
      </Container>
    </section>
  );
}
