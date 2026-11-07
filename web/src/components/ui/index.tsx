"use client";
import clsx from "clsx";
import Link from "next/link";
import { forwardRef } from "react";
import { Loader2 } from "lucide-react";

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "olive";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  href?: string;
};
const btnBase = "inline-flex items-center justify-center gap-2 rounded-full font-medium transition-[background,color,border,transform] duration-150 active:translate-y-px disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap";
const btnVar = {
  primary: "bg-terra text-paper hover:bg-terra-2",
  olive: "bg-olive text-paper hover:brightness-95",
  secondary: "border border-line bg-paper text-ink hover:bg-sand hover:border-sand-2",
  ghost: "text-ink-2 hover:bg-sand hover:text-ink",
  danger: "bg-danger text-paper hover:brightness-95",
};
const btnSize = { sm: "h-8 px-3.5 text-[13px]", md: "h-10 px-5 text-sm", lg: "h-12 px-7 text-[15px]" };

export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button(
  { variant = "primary", size = "md", loading, className, children, href, ...rest }, ref) {
  const cls = clsx(btnBase, btnVar[variant], btnSize[size], className);
  if (href) return <Link href={href} className={cls}>{children}</Link>;
  return (
    <button ref={ref} className={cls} disabled={loading || rest.disabled} {...rest}>
      {loading && <Loader2 size={15} className="animate-spin" />}
      {children}
    </button>
  );
});

export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx("rounded-[var(--radius-card)] border border-line bg-[#FFFCF7] shadow-[var(--shadow-paper)]", className)} {...rest}>{children}</div>;
}
export function CardHeader({ title, subtitle, action, className }: { title: React.ReactNode; subtitle?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={clsx("flex items-start justify-between gap-4 border-b border-line/70 px-5 py-4", className)}>
      <div className="min-w-0">
        <h3 className="font-serif text-[17px] leading-tight text-ink">{title}</h3>
        {subtitle && <p className="mt-1 text-[13px] text-ink-3">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={clsx("h-10 w-full rounded-lg border border-line bg-paper px-3 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-terra/60 focus:ring-2 focus:ring-terra/15", className)} {...rest} />;
});
export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={clsx("w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-terra/60 focus:ring-2 focus:ring-terra/15", className)} {...rest} />;
});
export function Select({ className, children, ...rest }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={clsx("h-10 rounded-lg border border-line bg-paper px-3 text-sm text-ink outline-none focus:border-terra/60", className)} {...rest}>{children}</select>;
}
export function Label({ children, className }: { children: React.ReactNode; className?: string }) {
  return <label className={clsx("mb-1.5 block text-[13px] font-medium text-ink-2", className)}>{children}</label>;
}
export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <div><Label>{label}</Label>{children}{hint && <p className="mt-1 text-xs text-ink-3">{hint}</p>}</div>;
}

const tones = {
  neutral: "bg-sand text-ink-2", terra: "bg-terra-soft text-terra-2", olive: "bg-olive-soft text-olive",
  saffron: "bg-saffron-soft text-[#8a5d0e]", danger: "bg-[#f6d9d3] text-danger", sky: "bg-[#dce8eb] text-sky",
};
export function Badge({ tone = "neutral", children, className }: { tone?: keyof typeof tones; children: React.ReactNode; className?: string }) {
  return <span className={clsx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11.5px] font-medium", tones[tone], className)}>{children}</span>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-md bg-sand/80", className)} />;
}
export function Empty({ title, body, action, icon }: { title: string; body?: string; action?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {icon && <div className="mb-3 text-ink-3">{icon}</div>}
      <p className="font-serif text-lg text-ink">{title}</p>
      {body && <p className="mt-1 max-w-sm text-sm text-ink-3">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
export function Divider({ className }: { className?: string }) {
  return <hr className={clsx("border-0 border-t border-line", className)} />;
}
export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="rounded border border-line bg-paper px-1.5 py-0.5 font-mono text-[11px] text-ink-3">{children}</kbd>;
}
export function Spinner({ size = 18 }: { size?: number }) {
  return <Loader2 size={size} className="animate-spin text-terra" />;
}

export function Tabs<T extends string>({ value, onChange, items, className }: { value: T; onChange: (v: T) => void; items: { value: T; label: React.ReactNode }[]; className?: string }) {
  return (
    <div className={clsx("inline-flex rounded-full border border-line bg-paper p-1", className)}>
      {items.map((i) => (
        <button key={i.value} onClick={() => onChange(i.value)}
          className={clsx("rounded-full px-3.5 py-1.5 text-[13px] transition", value === i.value ? "bg-ink text-paper" : "text-ink-2 hover:text-ink")}>
          {i.label}
        </button>
      ))}
    </div>
  );
}

export function ProgressBar({ value, tone = "terra", className }: { value: number; tone?: "terra" | "olive" | "saffron"; className?: string }) {
  const c = tone === "olive" ? "bg-olive" : tone === "saffron" ? "bg-saffron" : "bg-terra";
  return (
    <div className={clsx("h-2 w-full overflow-hidden rounded-full bg-sand", className)}>
      <div className={clsx("h-full rounded-full transition-[width] duration-700", c)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}
