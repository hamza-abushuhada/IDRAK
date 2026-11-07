import type { Metadata } from "next";
import { getCopy, lh, resolveLocale } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { Container, Kicker, PageHeader } from "@/components/marketing/primitives";
import { FinalCta } from "@/components/marketing/home/sections";

type P = { params: Promise<{ locale: string }> };

function Monogram({ letters, tone = "solid" }: { letters: readonly string[]; tone?: "solid" | "outline" }) {
  return (
    <div
      aria-hidden
      className={`flex size-16 shrink-0 items-center justify-center gap-[0.06em] rounded-full font-serif text-[24px] leading-none rtl:font-semibold ${
        tone === "solid" ? "bg-terra text-paper" : "border-[1.5px] border-ink bg-paper text-ink sm:size-20 sm:text-[28px]"
      }`}
    >
      {letters.join("‌")}
    </div>
  );
}

export async function generateMetadata({ params }: P): Promise<Metadata> {
  return pageMeta(await resolveLocale(params), "about", "/about");
}

export default async function AboutPage({ params }: P) {
  const locale = await resolveLocale(params);
  const c = getCopy(locale);
  const A = c.about;

  return (
    <>
      <PageHeader kicker={A.kicker} title={A.title} />

      <section className="border-b border-line">
        <Container className="grid grid-cols-1 gap-10 py-16 sm:py-24 lg:grid-cols-12">
          <aside className="lg:col-span-4">
            <div className="lg:sticky lg:top-28">
              <p className="num text-[13px] text-terra">2026 · {locale === "ar" ? "عمّان" : "Amman"}</p>
              <div className="mt-5 h-px w-16 bg-ink" />
            </div>
          </aside>
          <div className="space-y-6 lg:col-span-8">
            {A.story.map((p, i) => (
              <p key={i} className={i === 0 ? "font-serif text-[24px] leading-[1.5] text-ink sm:text-[28px] rtl:font-medium rtl:leading-[1.8]" : "max-w-[62ch] text-[18px] leading-[1.75] text-ink-2"}>
                {p}
              </p>
            ))}
          </div>
        </Container>
      </section>

      <section className="border-b border-line bg-paper-2">
        <Container className="py-20 sm:py-28">
          <Kicker tone="terra" className="mb-6">{A.missionKicker}</Kicker>
          <p className="max-w-[24ch] font-serif text-[34px] font-[360] leading-[1.15] tracking-[-0.02em] text-ink text-balance sm:text-[52px] rtl:max-w-[28ch] rtl:font-semibold rtl:leading-[1.45] rtl:tracking-normal">
            {A.mission}
          </p>
        </Container>
      </section>

      <section aria-labelledby="values" className="border-b border-line">
        <Container className="py-20 sm:py-24">
          <h2 id="values" className="font-serif text-[30px] font-[400] text-ink sm:text-[38px] rtl:font-semibold">{A.valuesTitle}</h2>
          <ul className="mt-12 grid grid-cols-1 border-t border-ink/80 sm:grid-cols-2 lg:grid-cols-4">
            {A.values.map((v, i) => (
              <li key={v.title} className={`border-b border-line py-8 sm:pe-6 lg:border-b-0 ${i > 0 ? "lg:border-s lg:ps-6" : ""}`}>
                <span className="num text-[13px] text-terra">0{i + 1}</span>
                <h3 className="mt-3 font-serif text-[21px] leading-snug text-ink rtl:font-semibold">{v.title}</h3>
                <p className="mt-3 text-[15.5px] leading-relaxed text-ink-2">{v.body}</p>
              </li>
            ))}
          </ul>
        </Container>
      </section>

      <section id="team" aria-labelledby="team-title" className="scroll-mt-24 border-b border-line">
        <Container className="grid grid-cols-1 gap-12 py-20 sm:py-24 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <Kicker tone="terra" className="mb-4">{A.gradNote} · <span className="num rtl:font-sans">2026</span></Kicker>
            <h2 id="team-title" className="font-serif text-[30px] font-[400] text-ink sm:text-[38px] rtl:font-semibold">{A.teamTitle}</h2>
            <p className="mt-4 max-w-[38ch] text-[16.5px] leading-relaxed text-ink-2">{A.teamIntro}</p>
          </div>
          <div className="lg:col-span-8">
            <ul className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {A.founders.map((p) => (
                <li key={p.id}>
                  <article className="flex h-full flex-col rounded-[16px] border border-line bg-[#FFFCF7] p-6 shadow-[var(--shadow-paper)]">
                    <Monogram letters={p.initials} />
                    <h3 className="mt-6 font-serif text-[21px] leading-snug text-ink text-balance rtl:font-semibold rtl:leading-[1.6]">{p.name}</h3>
                    <p className="mt-1 text-[14px] font-medium text-terra-2">{A.founderRole}</p>
                    <p className="mt-auto pt-5 font-mono text-[11.5px] tracking-[0.04em] text-ink-3">
                      {A.studentNo} <span className="num" dir="ltr">{p.id}</span>
                    </p>
                  </article>
                </li>
              ))}
            </ul>

            <article className="mt-4 flex flex-col gap-6 rounded-[16px] border border-ink/80 bg-paper-2 p-6 sm:flex-row sm:items-center sm:p-8">
              <Monogram letters={A.supervisor.initials} tone="outline" />
              <div className="min-w-0">
                <Kicker>{A.supervisorRole}</Kicker>
                <h3 className="mt-2 font-serif text-[26px] leading-snug text-ink rtl:font-semibold">{A.supervisor.name}</h3>
                <p className="mt-3 max-w-[54ch] text-[15.5px] leading-relaxed text-ink-2">{A.supervisor.body}</p>
                <p className="mt-4 font-mono text-[11.5px] tracking-[0.04em] text-ink-3">
                  {A.supervisorIdLabel} <span className="num" dir="ltr">{A.supervisor.id}</span>
                </p>
              </div>
            </article>
          </div>
        </Container>
      </section>

      <section aria-labelledby="roadmap" className="border-b border-line bg-paper-2">
        <Container className="py-20 sm:py-24">
          <h2 id="roadmap" className="font-serif text-[30px] font-[400] text-ink sm:text-[38px] rtl:font-semibold">{A.roadmapTitle}</h2>
          <ol className="relative mt-14 grid grid-cols-1 gap-10 md:grid-cols-3 md:gap-8">
            <span aria-hidden className="absolute inset-x-0 top-[13px] hidden h-px bg-ink/70 md:block" />
            {A.roadmap.map((r, i) => (
              <li key={r.when} className="relative">
                <span aria-hidden className={`relative flex size-[27px] items-center justify-center rounded-full border-[1.5px] border-ink ${i === 0 ? "bg-ink" : "bg-paper-2"}`}>
                  <span className={`size-2 rounded-full ${i === 0 ? "bg-terra" : "bg-ink-3"}`} />
                </span>
                <p className="num mt-5 text-[13px] text-terra"><bdi>{r.when}</bdi></p>
                <h3 className="mt-1 font-serif text-[26px] text-ink rtl:font-semibold">{r.where}</h3>
                <p className="mt-3 max-w-[34ch] text-[15.5px] leading-relaxed text-ink-2">{r.body}</p>
              </li>
            ))}
          </ol>
          <p className="mt-12 text-[14px] text-ink-3">{A.roadmapNote}</p>
        </Container>
      </section>

      <FinalCta locale={locale} secondary={A.cta} secondaryHref={lh(locale, "/contact")} />
    </>
  );
}
