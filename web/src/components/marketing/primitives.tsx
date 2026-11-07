import clsx from "clsx";
import { ArrowRight, ArrowUpRight } from "lucide-react";

export function Container({ className, children, as: Tag = "div" }: { className?: string; children: React.ReactNode; as?: "div" | "section" | "header" | "footer" | "article" }) {
  return <Tag className={clsx("mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-8", className)}>{children}</Tag>;
}

export function Kicker({ children, className, tone = "muted" }: { children: React.ReactNode; className?: string; tone?: "muted" | "terra" | "paper" }) {
  return (
    <p className={clsx(
      "font-mono text-[11.5px] font-medium uppercase tracking-[0.16em] rtl:font-sans rtl:text-[13px] rtl:font-semibold rtl:normal-case rtl:tracking-normal",
      tone === "muted" && "text-ink-3", tone === "terra" && "text-terra", tone === "paper" && "text-paper/70",
      className)}>
      {children}
    </p>
  );
}

export function SectionHead({ kicker, title, intro, className, align = "start", size = "md" }: {
  kicker?: React.ReactNode; title: React.ReactNode; intro?: React.ReactNode; className?: string; align?: "start" | "center"; size?: "md" | "lg";
}) {
  return (
    <div className={clsx(align === "center" && "mx-auto text-center", "max-w-[44rem]", className)}>
      {kicker && <Kicker className="mb-4">{kicker}</Kicker>}
      <h2 className={clsx(
        "font-serif font-[400] tracking-[-0.018em] text-ink text-balance rtl:font-semibold rtl:tracking-normal",
        size === "lg" ? "text-[36px] leading-[1.06] sm:text-[48px] rtl:leading-[1.35]" : "text-[30px] leading-[1.1] sm:text-[40px] rtl:leading-[1.4]")}>
        {title}
      </h2>
      {intro && <p className="mt-5 max-w-[38rem] text-[17px] leading-[1.65] text-ink-2 text-pretty">{intro}</p>}
    </div>
  );
}

export function Arrow({ size = 16, className }: { size?: number; className?: string }) {
  return <ArrowRight size={size} className={clsx("shrink-0 rtl:-scale-x-100", className)} aria-hidden />;
}
export function ArrowOut({ size = 16, className }: { size?: number; className?: string }) {
  return <ArrowUpRight size={size} className={clsx("shrink-0 rtl:-scale-x-100", className)} aria-hidden />;
}

export function Rule({ className }: { className?: string }) {
  return <hr className={clsx("border-0 border-t border-line", className)} />;
}

export function Ltr({ children, className }: { children: React.ReactNode; className?: string }) {
  return <bdi dir="ltr" className={className}>{children}</bdi>;
}

export function PageHeader({ kicker, title, sub, children, className }: { kicker: React.ReactNode; title: React.ReactNode; sub?: React.ReactNode; children?: React.ReactNode; className?: string }) {
  return (
    <header className={clsx("border-b border-line", className)}>
      <Container className="pb-14 pt-14 sm:pb-20 sm:pt-20">
        <Kicker className="mb-5">{kicker}</Kicker>
        <h1 className="max-w-[18ch] font-serif text-[40px] font-[380] leading-[1.03] tracking-[-0.022em] text-ink text-balance sm:text-[60px] rtl:max-w-[22ch] rtl:font-semibold rtl:leading-[1.3] rtl:tracking-normal">
          {title}
        </h1>
        {sub && <p className="mt-6 max-w-[40rem] text-[18px] leading-[1.6] text-ink-2 text-pretty">{sub}</p>}
        {children}
      </Container>
    </header>
  );
}

export const linkCls = "underline decoration-line decoration-1 underline-offset-[5px] transition-colors hover:decoration-terra hover:text-terra-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-terra rounded-sm";

export const monoAr = "[font-family:var(--font-plex-mono),var(--font-plex-ar),ui-monospace,monospace]";
