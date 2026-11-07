import Link from "next/link";
import { LogoMark } from "@/components/Logo";
import type { Locale } from "@/i18n/config";
import { CONTACT, getCopy, lh, SOLUTION_SLUGS } from "./copy";
import { Container } from "./primitives";
import { WaitlistMini } from "./WaitlistMini";

export function Footer({ locale }: { locale: Locale }) {
  const c = getCopy(locale);
  const f = c.footer;
  const L = f.links;
  const cols: { title: string; links: { href: string; label: string; ext?: boolean }[] }[] = [
    {
      title: f.product,
      links: [
        { href: lh(locale, "#product"), label: L.cleaning },
        { href: lh(locale, "#product"), label: L.leaks },
        { href: lh(locale, "#assistant"), label: L.assistant },
        { href: lh(locale, "/health-check"), label: L.healthCheck },
        { href: lh(locale, "/pricing"), label: L.pricing },
        { href: lh(locale, "/changelog"), label: L.changelog },
      ],
    },
    { title: f.solutions, links: SOLUTION_SLUGS.map((s) => ({ href: lh(locale, `/solutions/${s}`), label: c.solutions.items[s].name })) },
    {
      title: f.company,
      links: [
        { href: lh(locale, "/about"), label: L.about },
        { href: lh(locale, "/blog"), label: L.blog },
        { href: lh(locale, "/contact"), label: L.contact },
        { href: lh(locale, "/waitlist"), label: L.waitlist },
      ],
    },
    {
      title: f.legal,
      links: [
        { href: lh(locale, "/privacy"), label: L.privacy },
        { href: lh(locale, "/terms"), label: L.terms },
        { href: CONTACT.instagram, label: f.instagram, ext: true },
        { href: CONTACT.whatsapp, label: f.whatsapp, ext: true },
      ],
    },
  ];

  return (
    <footer className="bg-cocoa text-paper">
      <Container className="pb-10 pt-16 sm:pt-20">
        <div className="grid grid-cols-1 gap-14 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <p className="max-w-[16ch] font-serif text-[34px] font-[380] leading-[1.08] tracking-[-0.015em] text-paper sm:text-[40px] rtl:max-w-[20ch] rtl:font-medium rtl:leading-[1.45] rtl:tracking-normal">
              {f.tagline}
            </p>
            <div className="mt-10 max-w-[420px]">
              <p className="text-[15px] font-medium text-paper">{c.waitlistMini.title}</p>
              <p className="mb-4 mt-1 text-[14px] text-paper/60">{c.waitlistMini.body}</p>
              <WaitlistMini />
            </div>
          </div>
          <nav aria-label={f.product} className="grid grid-cols-2 gap-x-6 gap-y-10 sm:grid-cols-4 lg:col-span-7 lg:ps-10">
            {cols.map((col) => (
              <div key={col.title}>
                <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.16em] text-paper/50 rtl:font-sans rtl:text-[13px] rtl:tracking-normal">{col.title}</p>
                <ul className="space-y-2.5">
                  {col.links.map((l) => (
                    <li key={l.label}>
                      <Link
                        href={l.href}
                        {...(l.ext ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                        className="rounded-sm text-[14.5px] text-paper/80 transition-colors hover:text-paper focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-saffron"
                      >
                        {l.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        </div>

        <div className="mt-16 flex flex-col gap-4 border-t border-paper/15 pt-6 text-[13px] text-paper/55 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <LogoMark size={22} className="text-paper" />
            <span>{f.rights}</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span>{f.made}</span>
            <a href={`mailto:${CONTACT.email}`} className="hover:text-paper" dir="ltr">{CONTACT.email}</a>
          </div>
        </div>
        <p className="mt-5 max-w-[120ch] text-[12.5px] leading-relaxed text-paper/45">
          <Link href={lh(locale, "/about#team")} className="rounded-sm transition-colors hover:text-paper/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-saffron">
            {f.credit}
          </Link>
        </p>
      </Container>
    </footer>
  );
}
