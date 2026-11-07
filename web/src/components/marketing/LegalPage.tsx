import type { Locale } from "@/i18n/config";
import { getCopy } from "./copy";
import { Container, PageHeader } from "./primitives";

export function LegalPage({ locale, doc }: { locale: Locale; doc: "privacy" | "terms" }) {
  const L = getCopy(locale).legal;
  const d = L[doc];
  return (
    <>
      <PageHeader kicker={d.kicker} title={d.title} sub={d.intro}>
        <p className="mt-6 text-[13.5px] text-ink-3">{L.updated}</p>
      </PageHeader>
      <Container className="grid grid-cols-1 gap-12 py-14 sm:py-20 lg:grid-cols-12">
        <nav aria-label={L.contents} className="lg:col-span-3">
          <div className="lg:sticky lg:top-28">
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-3 rtl:font-sans rtl:text-[13px] rtl:tracking-normal">{L.contents}</p>
            <ol className="mt-4 space-y-2 border-s border-line ps-4">
              {d.sections.map((s, i) => (
                <li key={s.h}>
                  <a href={`#s${i + 1}`} className="text-[14px] text-ink-2 hover:text-terra-2 focus-visible:outline-2 focus-visible:outline-terra">{s.h}</a>
                </li>
              ))}
            </ol>
          </div>
        </nav>
        <div className="max-w-[68ch] lg:col-span-8 lg:col-start-5">
          <aside className="mb-10 rounded-[12px] border-s-[3px] border-saffron bg-saffron-soft/60 px-5 py-4 text-[14.5px] leading-relaxed text-ink">{L.draftNote}</aside>
          {d.sections.map((s, i) => (
            <section key={s.h} id={`s${i + 1}`} className="scroll-mt-28 border-t border-line py-8">
              <h2 className="flex items-baseline gap-3 font-serif text-[24px] text-ink rtl:font-semibold">
                <span className="num text-[13px] text-terra">{String(i + 1).padStart(2, "0")}</span>
                {s.h}
              </h2>
              {s.p.map((p) => (
                <p key={p} className="mt-4 text-[16.5px] leading-[1.75] text-ink-2">{p}</p>
              ))}
            </section>
          ))}
        </div>
      </Container>
    </>
  );
}
