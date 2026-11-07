"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import clsx from "clsx";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import * as Dialog from "@radix-ui/react-dialog";
import { ChevronDown, Menu, X } from "lucide-react";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui";
import { useCopy } from "./use-copy";
import { lh, SOLUTION_SLUGS } from "./copy";
import { Arrow } from "./primitives";

function setLocaleCookie(l: string) {
  document.cookie = `basira_locale=${l}; path=/; max-age=31536000; samesite=lax`;
}

function useAltPath() {
  const pathname = usePathname() || "/";
  const { locale } = useCopy();
  const other = locale === "ar" ? "en" : "ar";
  const rest = pathname.replace(/^\/(ar|en)(?=\/|$)/, "");
  return { other, href: `/${other}${rest}` };
}

const navLink =
  "rounded-md px-3 py-2 text-[14.5px] text-ink-2 transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-terra aria-[current=page]:text-ink aria-[current=page]:font-medium";

export function Nav() {
  const { c, locale } = useCopy();
  const n = c.nav;
  const pathname = usePathname() || "";
  const alt = useAltPath();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  useEffect(() => setOpen(false), [pathname]);

  const cur = (p: string): "page" | undefined => (pathname === lh(locale, p) ? "page" : undefined);
  const links = [
    { href: lh(locale, "#product"), label: n.product },
    { href: lh(locale, "/pricing"), label: n.pricing, current: cur("/pricing") },
    { href: lh(locale, "/health-check"), label: n.healthCheck, current: cur("/health-check") },
    { href: lh(locale, "/blog"), label: n.blog, current: pathname.startsWith(lh(locale, "/blog")) ? ("page" as const) : undefined },
  ];

  return (
    <>
      <a href="#main" className="sr-only z-[60] rounded-md bg-ink px-4 py-2 text-paper focus:not-sr-only focus:fixed focus:start-4 focus:top-3">
        {n.skip}
      </a>
      <header className={clsx("sticky top-0 z-50 border-b bg-paper transition-colors duration-300", scrolled ? "border-line" : "border-transparent")}>
        <div className="mx-auto flex h-[68px] w-full max-w-[1200px] items-center gap-4 px-4 sm:px-6 lg:px-8">
          <Link href={lh(locale)} className="shrink-0 rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-terra" aria-label={locale === "ar" ? "إدراك — الرئيسية" : "Idrak — home"}>
            <Logo locale={locale} />
          </Link>

          <nav aria-label={locale === "ar" ? "الرئيسية" : "Main"} className="ms-6 hidden items-center lg:flex">
            <Link href={links[0].href} className={navLink}>{links[0].label}</Link>
            <Dropdown.Root modal={false} dir={locale === "ar" ? "rtl" : "ltr"}>
              <Dropdown.Trigger className={clsx(navLink, "group inline-flex items-center gap-1 data-[state=open]:text-ink")} aria-current={pathname.includes("/solutions") ? "page" : undefined}>
                {n.solutions}
                <ChevronDown size={14} className="transition-transform group-data-[state=open]:rotate-180" aria-hidden />
              </Dropdown.Trigger>
              <Dropdown.Portal>
                <Dropdown.Content
                  align="start"
                  sideOffset={10}
                  className="z-[70] w-[380px] rounded-[14px] border border-line bg-[#FFFCF7] p-2 shadow-[var(--shadow-lift)] outline-none"
                >
                  {SOLUTION_SLUGS.map((s) => (
                    <Dropdown.Item key={s} asChild>
                      <Link href={lh(locale, `/solutions/${s}`)} className="block rounded-[10px] px-3.5 py-3 outline-none transition-colors data-[highlighted]:bg-sand">
                        <span className="block text-[15px] font-medium text-ink">{c.solutions.items[s].name}</span>
                        <span className="mt-0.5 block text-[13px] text-ink-3">{c.solutions.items[s].short}</span>
                      </Link>
                    </Dropdown.Item>
                  ))}
                  <Dropdown.Separator className="mx-2 my-1.5 h-px bg-line" />
                  <Dropdown.Item asChild>
                    <Link href={lh(locale, "/solutions")} className="flex items-center justify-between rounded-[10px] px-3.5 py-2.5 text-[13.5px] text-ink-2 outline-none data-[highlighted]:bg-sand data-[highlighted]:text-ink">
                      {n.solutionsAll} <Arrow size={14} />
                    </Link>
                  </Dropdown.Item>
                </Dropdown.Content>
              </Dropdown.Portal>
            </Dropdown.Root>
            {links.slice(1).map((l) => (
              <Link key={l.href} href={l.href} className={navLink} aria-current={l.current}>{l.label}</Link>
            ))}
          </nav>

          <div className="ms-auto flex items-center gap-1.5 sm:gap-2">
            <Link
              href={alt.href}
              hrefLang={alt.other}
              lang={alt.other}
              onClick={() => setLocaleCookie(alt.other)}
              aria-label={n.switchLabel}
              className="rounded-full px-3 py-2 text-[14px] text-ink-2 transition-colors hover:bg-sand hover:text-ink focus-visible:outline-2 focus-visible:outline-terra"
            >
              {n.switchTo}
            </Link>
            <Link href={lh(locale, "/login")} className={clsx(navLink, "hidden sm:inline-flex")}>{n.login}</Link>
            <Button href={lh(locale, "/signup")} size="sm" className="hidden h-9 px-4 sm:inline-flex">{n.start}</Button>

            <Dialog.Root open={open} onOpenChange={setOpen}>
              <Dialog.Trigger className="inline-flex size-10 items-center justify-center rounded-full text-ink hover:bg-sand focus-visible:outline-2 focus-visible:outline-terra lg:hidden" aria-label={n.menu}>
                <Menu size={20} aria-hidden />
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 z-[80] bg-ink/20" />
                <Dialog.Content dir={locale === "ar" ? "rtl" : "ltr"} className="fixed inset-y-0 end-0 z-[90] flex w-full max-w-[420px] flex-col overflow-y-auto bg-paper px-5 pb-8 pt-4 shadow-[var(--shadow-lift)] outline-none">
                  <div className="flex h-[52px] items-center justify-between">
                    <Logo locale={locale} />
                    <Dialog.Close className="inline-flex size-10 items-center justify-center rounded-full hover:bg-sand focus-visible:outline-2 focus-visible:outline-terra" aria-label={n.closeMenu}>
                      <X size={20} aria-hidden />
                    </Dialog.Close>
                  </div>
                  <Dialog.Title className="sr-only">{n.menu}</Dialog.Title>
                  <Dialog.Description className="sr-only">{c.footer.tagline}</Dialog.Description>
                  <nav className="mt-6 flex flex-col" aria-label={locale === "ar" ? "القائمة" : "Mobile"}>
                    {[links[0], ...links.slice(1)].map((l) => (
                      <Link key={l.href} href={l.href} onClick={() => setOpen(false)} className="border-b border-line py-4 font-serif text-[24px] text-ink rtl:font-medium">
                        {l.label}
                      </Link>
                    ))}
                    <p className="mt-7 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-3 rtl:font-sans rtl:text-[13px] rtl:tracking-normal">{n.solutions}</p>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {SOLUTION_SLUGS.map((s) => (
                        <Link key={s} href={lh(locale, `/solutions/${s}`)} onClick={() => setOpen(false)} className="rounded-xl border border-line bg-[#FFFCF7] px-3.5 py-3 text-[14.5px] text-ink">
                          {c.solutions.items[s].name}
                        </Link>
                      ))}
                    </div>
                    <div className="mt-6 flex gap-4 text-[15px] text-ink-2">
                      <Link href={lh(locale, "/about")} onClick={() => setOpen(false)}>{n.about}</Link>
                      <Link href={lh(locale, "/contact")} onClick={() => setOpen(false)}>{n.contact}</Link>
                      <Link href={alt.href} hrefLang={alt.other} lang={alt.other} onClick={() => setLocaleCookie(alt.other)} className="ms-auto">{n.switchTo}</Link>
                    </div>
                  </nav>
                  <div className="mt-auto flex flex-col gap-3 pt-10">
                    <Button href={lh(locale, "/signup")} size="lg">{n.start}</Button>
                    <Button href={lh(locale, "/login")} size="lg" variant="secondary">{n.login}</Button>
                  </div>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          </div>
        </div>
      </header>
    </>
  );
}
