import clsx from "clsx";

export function LogoMark({ size = 28, className, color = "currentColor" }: { size?: number; className?: string; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-hidden>
      <circle cx="16" cy="16" r="10.5" stroke={color} strokeWidth="2.6" />
      <path d="M1.5 16h29" stroke={color} strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="16" cy="16" r="3.2" fill="#C2593A" />
    </svg>
  );
}

export function Logo({ locale = "en", className, size = 26 }: { locale?: string; className?: string; size?: number }) {
  return (
    <span className={clsx("inline-flex items-center gap-2 text-ink", className)}>
      <LogoMark size={size} />
      {locale === "ar" ? (
        <span className="font-[family-name:var(--font-alexandria)] text-[21px] font-semibold leading-none tracking-tight">إدراك</span>
      ) : (
        <span className="font-serif text-[22px] font-semibold leading-none tracking-tight">idrak</span>
      )}
    </span>
  );
}
