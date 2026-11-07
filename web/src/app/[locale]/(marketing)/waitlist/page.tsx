import type { Metadata } from "next";
import { getCopy, resolveLocale } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { Container, Kicker } from "@/components/marketing/primitives";
import { WaitlistForm } from "@/components/marketing/Forms";

type P = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: P): Promise<Metadata> {
  return pageMeta(await resolveLocale(params), "waitlist", "/waitlist");
}

export default async function WaitlistPage({ params }: P) {
  const locale = await resolveLocale(params);
  const W = getCopy(locale).waitlist;
  return (
    <Container className="grid grid-cols-1 gap-14 pb-24 pt-12 sm:pt-16 lg:grid-cols-12 lg:gap-16">
      <div className="lg:col-span-5">
        <Kicker tone="terra" className="mb-5">{W.kicker}</Kicker>
        <h1 className="font-serif text-[40px] font-[380] leading-[1.04] tracking-[-0.022em] text-ink sm:text-[56px] rtl:font-semibold rtl:leading-[1.35] rtl:tracking-normal">{W.title}</h1>
        <p className="mt-6 max-w-[42ch] text-[17px] leading-[1.65] text-ink-2">{W.sub}</p>
        <div className="mt-12 border-t border-ink/80 pt-6">
          <p className="text-[13.5px] text-ink-3">{W.perksTitle}</p>
          <ol className="mt-4 space-y-4">
            {W.perks.map((p, i) => (
              <li key={p} className="flex items-baseline gap-4 text-[17px] text-ink">
                <span className="num text-[13px] text-terra">0{i + 1}</span>
                {p}
              </li>
            ))}
          </ol>
        </div>
      </div>
      <div className="lg:col-span-7">
        <div className="rounded-[18px] border border-line bg-paper-2 p-6 sm:p-10">
          <WaitlistForm />
        </div>
      </div>
    </Container>
  );
}
