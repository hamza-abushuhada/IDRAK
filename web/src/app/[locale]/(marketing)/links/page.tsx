import type { Metadata } from "next";
import Link from "next/link";
import clsx from "clsx";
import { LogoMark } from "@/components/Logo";
import { CONTACT, getCopy, lh, resolveLocale } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { Arrow, ArrowOut } from "@/components/marketing/primitives";

type P = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: P): Promise<Metadata> {
  return pageMeta(await resolveLocale(params), "links", "/links");
}

export default async function LinksPage({ params }: P) {
  const locale = await resolveLocale(params);
  const L = getCopy(locale).links;
  const I = L.items;
  const other = locale === "ar" ? "en" : "ar";
  const items: { title: string; sub: string; href: string; primary?: boolean; ext?: boolean }[] = [
    { ...I.health, href: lh(locale, "/health-check"), primary: true },
    { ...I.pricing, href: lh(locale, "/pricing") },
    { ...I.waitlist, href: lh(locale, "/waitlist") },
    { ...I.whatsapp, href: CONTACT.whatsapp, ext: true },
    { ...I.instagram, href: CONTACT.instagram, ext: true },
    { ...I.website, href: lh(locale) },
  ];

  return (
    <div className="min-h-dvh bg-paper px-4 pb-12 pt-14">
      <div className="mx-auto flex w-full max-w-[440px] flex-col items-center text-center">
        <span className="flex size-[88px] items-center justify-center rounded-full bg-cocoa text-paper">
          <LogoMark size={46} />
        </span>
        <h1 className="mt-5 font-serif text-[30px] font-semibold leading-none tracking-tight text-ink">{locale === "ar" ? "إدراك" : "idrak"}</h1>
        <p className="mt-1 font-mono text-[13px] text-ink-3" dir="ltr">{L.handle}</p>
        <p className="mt-4 max-w-[34ch] text-[16px] leading-relaxed text-ink-2">{L.bio}</p>
        <p className="mt-1 text-[13px] text-ink-3">{L.place}</p>

        <ul className="mt-9 w-full space-y-3">
          {items.map((it) => (
            <li key={it.title}>
              <Link
                href={it.href}
                {...(it.ext ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                className={clsx(
                  "flex items-center justify-between gap-4 rounded-[14px] border px-5 py-4 text-start transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-terra",
                  it.primary ? "border-terra bg-terra text-paper hover:bg-terra-2" : "border-line bg-[#FFFCF7] text-ink hover:border-ink/40",
                )}
              >
                <span>
                  <span className="block text-[16px] font-medium">{it.title}</span>
                  <span className={clsx("mt-0.5 block text-[13px]", it.primary ? "text-paper/80" : "text-ink-3")}>{it.sub}</span>
                </span>
                {it.ext ? <ArrowOut size={17} /> : <Arrow size={17} />}
              </Link>
            </li>
          ))}
        </ul>

        <Link href={`/${other}/links`} hrefLang={other} className="mt-8 rounded-full px-3 py-1.5 text-[14px] text-ink-2 hover:bg-sand">
          {other === "ar" ? "العربية" : "English"}
        </Link>
      </div>
    </div>
  );
}
