"use client";
import clsx from "clsx";
import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, Sparkles } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { jd, num } from "@/lib/format";
import { Card, Skeleton } from "@/components/ui";
import { useAssistant } from "@/components/assistant/store";

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode; eyebrow?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <p className="mb-1.5 text-[12px] font-medium uppercase tracking-[.14em] text-terra">{eyebrow}</p>}
        <h1 className="font-serif text-[28px] leading-tight text-ink sm:text-[32px]">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-[14.5px] text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Money({ v, compact, decimals, className }: { v: number | null | undefined; compact?: boolean; decimals?: number; className?: string }) {
  const locale = useLocale();
  return <span className={clsx("num", className)}>{jd(v, locale, { compact, decimals })}</span>;
}

export function Delta({ v, inverse, className }: { v: number | null | undefined; inverse?: boolean; className?: string }) {
  if (v === null || v === undefined) return <span className={clsx("text-ink-3 text-xs", className)}>—</span>;
  const good = inverse ? v < 0 : v >= 0;
  const Icon = v >= 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={clsx("num inline-flex items-center gap-0.5 text-[12px] font-medium", good ? "text-olive" : "text-danger", className)}>
      <Icon size={13} />{Math.abs(v).toFixed(1)}%
    </span>
  );
}

export function Stat({ label, value, delta, hint, id, inverse, tone }: { label: string; value: React.ReactNode; delta?: number | null; hint?: React.ReactNode; id?: string; inverse?: boolean; tone?: "terra" | "olive" | "saffron" }) {
  return (
    <Card data-basira={id} className="relative overflow-hidden px-5 py-4">
      {tone && <span className={clsx("absolute inset-y-0 start-0 w-1", tone === "terra" ? "bg-terra" : tone === "olive" ? "bg-olive" : "bg-saffron")} />}
      <p className="text-[12.5px] text-ink-3">{label}</p>
      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className={clsx("min-w-0 font-serif text-ink", typeof value === "string" && value.length > 14 ? "text-[19px] leading-snug" : "text-[26px] leading-none whitespace-nowrap")}>{value}</span>
        {delta !== undefined && <Delta v={delta} inverse={inverse} />}
      </div>
      {hint && <p className="mt-1.5 text-[12px] text-ink-3">{hint}</p>}
    </Card>
  );
}

export function StatSkeleton() {
  return <Card className="px-5 py-4"><Skeleton className="h-3 w-20" /><Skeleton className="mt-3 h-7 w-28" /></Card>;
}

export function Section({ title, subtitle, action, children, id, className, bodyClass }: { title: React.ReactNode; subtitle?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; id?: string; className?: string; bodyClass?: string }) {
  return (
    <Card data-basira={id} className={clsx("min-w-0", className)}>
      <div className="flex items-start justify-between gap-3 border-b border-line/70 px-5 py-3.5">
        <div className="min-w-0">
          <h3 className="font-serif text-[16.5px] text-ink">{title}</h3>
          {subtitle && <p className="mt-0.5 text-[12.5px] text-ink-3">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className={clsx("p-5", bodyClass)}>{children}</div>
    </Card>
  );
}

export type Col<T> = { key: string; label: React.ReactNode; render?: (row: T, i: number) => React.ReactNode; align?: "start" | "end" | "center"; className?: string };
export function Table<T extends Record<string, any>>({ rows, cols, onRow, empty, id, dense, rowKey, highlightRow }: {
  rows: T[] | undefined; cols: Col<T>[]; onRow?: (r: T) => void; empty?: React.ReactNode; id?: string; dense?: boolean; rowKey?: (r: T, i: number) => string; highlightRow?: (r: T) => boolean;
}) {
  if (!rows) {
    return <div className="space-y-2 p-4">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}</div>;
  }
  if (!rows.length) return <div className="px-6 py-12 text-center text-sm text-ink-3">{empty || "—"}</div>;
  return (
    <div data-basira={id} className="overflow-x-auto">
      <table className="w-full border-collapse text-[13.5px]">
        <thead>
          <tr className="border-b border-line text-ink-3">
            {cols.map((c) => (
              <th key={c.key} className={clsx("whitespace-nowrap px-4 py-2.5 text-[12px] font-medium", c.align === "end" ? "text-end" : c.align === "center" ? "text-center" : "text-start", c.className)}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={rowKey ? rowKey(r, i) : (r.id ?? i)} onClick={onRow ? () => onRow(r) : undefined}
              className={clsx("border-b border-line/60 last:border-0", onRow && "cursor-pointer hover:bg-paper-2", highlightRow?.(r) && "bg-saffron-soft/50")}>
              {cols.map((c) => (
                <td key={c.key} className={clsx(dense ? "px-4 py-2" : "px-4 py-3", "align-middle", c.align === "end" ? "text-end" : c.align === "center" ? "text-center" : "text-start", c.className)}>
                  {c.render ? c.render(r, i) : (r[c.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Chip({ active, onClick, children, id, count }: { active?: boolean; onClick?: () => void; children: React.ReactNode; id?: string; count?: number }) {
  return (
    <button data-basira={id} onClick={onClick}
      className={clsx("inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] transition",
        active ? "border-ink bg-ink text-paper" : "border-line bg-paper text-ink-2 hover:border-sand-2 hover:bg-sand")}>
      {children}
      {count !== undefined && <span className={clsx("num rounded-full px-1.5 text-[11px]", active ? "bg-paper/20" : "bg-sand")}>{count}</span>}
    </button>
  );
}

export function AskIdrak({ q, className, label }: { q: string; className?: string; label?: string }) {
  const tx = useTx();
  const open = useAssistant((s) => s.ask);
  return (
    <button onClick={() => open(q)} className={clsx("inline-flex items-center gap-1.5 rounded-full border border-dashed border-terra/50 px-3 py-1 text-[12.5px] text-terra hover:bg-terra-soft/60", className)}>
      <Sparkles size={13} />{label || tx("Ask Idrak", "اسأل إدراك")}
    </button>
  );
}

export function LinkCell({ href, children }: { href: string; children: React.ReactNode }) {
  return <Link href={href} className="font-medium text-ink underline-offset-4 hover:text-terra hover:underline">{children}</Link>;
}

export function N({ v, d = 0 }: { v: number | null | undefined; d?: number }) {
  return <span className="num">{num(v, d)}</span>;
}

export function useName() {
  const locale = useLocale();
  return (en?: string | null, ar?: string | null) => (locale === "ar" ? ar || en : en || ar) || "—";
}

export function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  const tx = useTx();
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <Card className="border-danger/30 px-6 py-8 text-center">
      <p className="font-serif text-lg text-ink">{tx("Couldn't load this", "ما قدرنا نحمّل هالصفحة")}</p>
      <p className="mt-1 text-sm text-ink-3">{msg === "network" ? tx("The Idrak API isn't reachable. Start it with api\\run.ps1", "سيرفر إدراك مش شغّال. شغّله من api\\run.ps1") : msg}</p>
      {retry && <button onClick={retry} className="mt-4 text-sm text-terra underline">{tx("Try again", "جرّب مرة ثانية")}</button>}
    </Card>
  );
}
