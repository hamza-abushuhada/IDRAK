"use client";
import { useCallback, useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { useRouter } from "@/lib/router";
import clsx from "clsx";
import { Lock } from "lucide-react";
import { useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { Badge, Card, Empty, Skeleton } from "@/components/ui";
import { StatSkeleton } from "@/components/app/kit";
import type { OrgDetail } from "./types";

export function useParamState(key: string, def: string): [string, (v: string) => void] {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const value = sp.get(key) ?? def;
  const set = useCallback((v: string) => {
    const p = new URLSearchParams(sp.toString());
    if (!v || v === def) p.delete(key);
    else p.set(key, v);
    const qs = p.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }, [sp, router, pathname, key, def]);
  return [value, set];
}

export function useSetParams() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  return useCallback((patch: Record<string, string>) => {
    const p = new URLSearchParams(sp.toString());
    Object.entries(patch).forEach(([k, v]) => (v ? p.set(k, v) : p.delete(k)));
    const qs = p.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }, [sp, router, pathname]);
}

export function oneOf<T extends string>(v: string, allowed: readonly T[], def: T): T {
  return (allowed as readonly string[]).includes(v) ? (v as T) : def;
}

export function useDebounced<T>(value: T, ms = 350): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function useOrgDetail() {
  return useApiQuery<OrgDetail>("/org", { staleTime: 5 * 60_000 });
}

export function PageSkeleton({ stats = 4 }: { stats?: number }) {
  return (
    <div>
      <Skeleton className="mb-2 h-3 w-24" />
      <Skeleton className="mb-8 h-8 w-72" />
      <div className={clsx("grid gap-4", stats >= 5 ? "grid-cols-2 lg:grid-cols-5" : "grid-cols-2 lg:grid-cols-4")}>
        {Array.from({ length: stats }).map((_, i) => <StatSkeleton key={i} />)}
      </div>
      <Card className="mt-5 p-5"><Skeleton className="h-64 w-full" /></Card>
    </div>
  );
}

export function ChartSkeleton({ height = 260 }: { height?: number }) {
  return <div className="animate-pulse rounded-md bg-sand/70" style={{ height }} />;
}

export function SeverityBadge({ s }: { s: "high" | "medium" | "low" | string }) {
  const tx = useTx();
  if (s === "high") return <Badge tone="danger">{tx("High", "عالية")}</Badge>;
  if (s === "medium") return <Badge tone="saffron">{tx("Medium", "متوسطة")}</Badge>;
  return <Badge tone="neutral">{tx("Low", "منخفضة")}</Badge>;
}

export const JO_WEEK_ORDER = [6, 7, 1, 2, 3, 4, 5];
export const DOW = {
  en: { 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun" } as Record<number, string>,
  ar: { 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس", 5: "الجمعة", 6: "السبت", 7: "الأحد" } as Record<number, string>,
};
export const isWeekend = (dow: number) => dow === 5 || dow === 6;

export function paymentLabel(m: string, isAr: boolean) {
  const map: Record<string, [string, string]> = {
    cash: ["Cash", "كاش"], card: ["Card", "بطاقة"], cliq: ["CliQ", "كليك"], wallet: ["E-wallet", "محفظة إلكترونية"], credit: ["On account", "دين"],
  };
  const v = map[m];
  return v ? (isAr ? v[1] : v[0]) : m;
}

export function RoleNotice({ min }: { min: "accountant" | "manager" }) {
  const tx = useTx();
  const role = min === "manager" ? tx("a manager or the owner", "مدير أو صاحب المحل") : tx("an accountant, manager or the owner", "محاسب أو مدير أو صاحب المحل");
  return (
    <Card>
      <Empty icon={<Lock size={22} />} title={tx("This screen is for finance roles", "هالشاشة لأصحاب الصلاحيات المالية")}
        body={tx(`Ask ${role} to open it, or to change your role from Settings → Team.`, `اطلب من ${role} يفتحها، أو يغيّر صلاحيتك من الإعدادات ← الفريق.`)} />
    </Card>
  );
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }
}

export function ShareBar({ value, tone = "terra", className }: { value: number; tone?: "terra" | "olive" | "saffron" | "sky" | "ink"; className?: string }) {
  const c = { terra: "bg-terra", olive: "bg-olive", saffron: "bg-saffron", sky: "bg-sky", ink: "bg-ink-2" }[tone];
  return (
    <div className={clsx("h-1.5 w-full overflow-hidden rounded-full bg-sand", className)}>
      <div className={clsx("h-full rounded-full", c)} style={{ width: `${Math.max(1.5, Math.min(100, value))}%` }} />
    </div>
  );
}
