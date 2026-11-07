import { Button } from "@/components/ui";
import type { Locale } from "@/i18n/config";
import { getCopy, lh } from "../copy";
import { Arrow, Container, Kicker } from "../primitives";
import { HeroStill } from "./HeroStill";

export function Hero({ locale }: { locale: Locale }) {
  const h = getCopy(locale).hero;
  return (
    <section className="relative border-b border-line">
      <Container className="grid grid-cols-1 items-center gap-x-12 gap-y-16 pb-20 pt-12 sm:pt-16 lg:grid-cols-12 lg:pb-28 lg:pt-20">
        <div className="lg:col-span-7">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Kicker tone="terra">{h.kicker}</Kicker>
            <span aria-hidden className="hidden h-px w-8 bg-line sm:block" />
            <Kicker className="hidden sm:block">{h.place}</Kicker>
          </div>
          <h1 className="mt-7 font-serif text-[44px] font-[360] leading-[1] tracking-[-0.03em] text-ink text-balance sm:text-[66px] lg:text-[80px] rtl:text-[40px] rtl:font-medium rtl:leading-[1.38] rtl:tracking-normal sm:rtl:text-[58px] lg:rtl:text-[66px]">
            {h.titleLead} <span className="scribble whitespace-nowrap">{h.titleMark}</span>
          </h1>
          <p className="mt-7 max-w-[36ch] text-[19px] leading-[1.55] text-ink-2 text-pretty sm:text-[21px]">{h.sub}</p>
          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Button href={lh(locale, "/signup")} size="lg">
              {h.ctaPrimary} <Arrow size={16} />
            </Button>
            <Button href={lh(locale, "/health-check")} size="lg" variant="secondary">
              {h.ctaSecondary}
            </Button>
          </div>
          <p className="mt-5 text-[13.5px] text-ink-3">{h.note}</p>
        </div>
        <div className="lg:col-span-5">
          <HeroStill locale={locale} />
        </div>
      </Container>
    </section>
  );
}
