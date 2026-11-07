import type { Metadata } from "next";
import { CONTACT, getCopy, resolveLocale } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { Container, Kicker } from "@/components/marketing/primitives";
import { ContactForm } from "@/components/marketing/Forms";

type P = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: P): Promise<Metadata> {
  return pageMeta(await resolveLocale(params), "contact", "/contact");
}

export default async function ContactPage({ params }: P) {
  const locale = await resolveLocale(params);
  const C = getCopy(locale).contact;
  const D = C.details;
  const rows = [
    { k: D.office, v: <>{D.officeValue}<span className="block text-[14px] text-ink-3">{D.officeNote}</span></> },
    { k: D.email, v: <a href={`mailto:${CONTACT.email}`} dir="ltr" className="underline decoration-line underline-offset-4 hover:decoration-terra">{D.emailValue}</a> },
    { k: D.whatsapp, v: <a href={CONTACT.whatsapp} target="_blank" rel="noopener noreferrer" className="underline decoration-line underline-offset-4 hover:decoration-terra">{D.whatsappValue}</a> },
    { k: D.hours, v: D.hoursValue },
  ];
  return (
    <Container className="grid grid-cols-1 gap-14 pb-24 pt-12 sm:pt-16 lg:grid-cols-12 lg:gap-16">
      <div className="lg:col-span-5">
        <Kicker tone="terra" className="mb-5">{C.kicker}</Kicker>
        <h1 className="font-serif text-[40px] font-[380] leading-[1.04] tracking-[-0.022em] text-ink text-balance sm:text-[56px] rtl:font-semibold rtl:leading-[1.35] rtl:tracking-normal">{C.title}</h1>
        <p className="mt-6 max-w-[40ch] text-[17px] leading-[1.65] text-ink-2">{C.sub}</p>
        <dl className="mt-12 border-t border-ink/80">
          {rows.map((r) => (
            <div key={r.k} className="grid grid-cols-[7.5rem_1fr] gap-4 border-b border-line py-4">
              <dt className="text-[13.5px] text-ink-3">{r.k}</dt>
              <dd className="text-[16px] text-ink">{r.v}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="lg:col-span-7">
        <div className="rounded-[18px] border border-line bg-paper-2 p-6 sm:p-10">
          <ContactForm />
        </div>
      </div>
    </Container>
  );
}
