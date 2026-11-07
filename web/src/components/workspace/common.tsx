"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useRouter } from "@/lib/router";
import clsx from "clsx";
import * as Dialog from "@radix-ui/react-dialog";
import { ArrowLeft, ArrowRight, Search, X } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { Card, Skeleton } from "@/components/ui";
import type { Role } from "@/components/app/session";

export function useHref() {
  const locale = useLocale();
  return useCallback((p: string) => `/${locale}${p}`, [locale]);
}

export function useDebounced<T>(value: T, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function useQueryParams() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const get = useCallback((k: string) => sp.get(k) ?? "", [sp]);
  const set = useCallback(
    (patch: Record<string, string | null | undefined>) => {
      const n = new URLSearchParams(sp.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === null || v === undefined || v === "") n.delete(k);
        else n.set(k, v);
      }
      const qs = n.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [sp, router, pathname],
  );
  return { get, set };
}

export function qs(params: Record<string, string | number | null | undefined>) {
  const n = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") n.set(k, String(v));
  const s = n.toString();
  return s ? `?${s}` : "";
}

export function SearchBox({ value, onChange, placeholder, id, className }: { value: string; onChange: (v: string) => void; placeholder: string; id?: string; className?: string }) {
  return (
    <div data-basira={id} className={clsx("relative w-full sm:w-72", className)}>
      <Search size={15} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-ink-3" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-10 w-full rounded-lg border border-line bg-paper ps-9 pe-3 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-terra/60 focus:ring-2 focus:ring-terra/15"
      />
    </div>
  );
}

export function Drawer({ open, onOpenChange, title, subtitle, children, footer }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: React.ReactNode; subtitle?: React.ReactNode; children: React.ReactNode; footer?: React.ReactNode;
}) {
  const tx = useTx();
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/25" />
        <Dialog.Content
          className="fixed inset-y-0 end-0 z-50 flex w-full max-w-[520px] flex-col border-s border-line bg-paper shadow-[var(--shadow-lift)] outline-none"
          aria-describedby={undefined}
        >
          <div className="flex items-start justify-between gap-3 border-b border-line px-6 py-4">
            <div className="min-w-0">
              <Dialog.Title className="font-serif text-[20px] leading-tight text-ink">{title}</Dialog.Title>
              {subtitle && <div className="mt-1 text-[13px] text-ink-3">{subtitle}</div>}
            </div>
            <Dialog.Close className="rounded-full p-1.5 text-ink-3 hover:bg-sand hover:text-ink" aria-label={tx("Close", "إغلاق")}>
              <X size={18} />
            </Dialog.Close>
          </div>
          <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
          {footer && <div className="border-t border-line px-6 py-3">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function BackLink({ href, children }: { href: string; children: React.ReactNode }) {
  const tx = useTx();
  const Icon = tx.isAr ? ArrowRight : ArrowLeft;
  return (
    <Link href={href} className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-ink-3 hover:text-terra">
      <Icon size={14} />{children}
    </Link>
  );
}

export function DetailSkeleton() {
  return (
    <div>
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-3 h-8 w-72" />
      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => <Card key={i} className="px-5 py-4"><Skeleton className="h-3 w-20" /><Skeleton className="mt-3 h-7 w-28" /></Card>)}
      </div>
      <Card className="mt-6 p-5"><Skeleton className="h-56 w-full" /></Card>
    </div>
  );
}

export function KV({ k, v, className }: { k: React.ReactNode; v: React.ReactNode; className?: string }) {
  return (
    <div className={clsx("flex items-baseline justify-between gap-4 border-b border-line/60 py-2 text-[13.5px] last:border-0", className)}>
      <span className="text-ink-3">{k}</span>
      <span className="text-end text-ink">{v}</span>
    </div>
  );
}

export const ROLES: { v: Role; en: string; ar: string; descEn: string; descAr: string }[] = [
  { v: "owner", en: "Owner", ar: "المالك", descEn: "Everything, including billing, business settings and the team.", descAr: "كل إشي، ومعه الاشتراك وإعدادات المشروع والفريق." },
  { v: "manager", en: "Manager", ar: "مدير", descEn: "Upload & clean data, edit prices and stock, send supplier orders, see the audit log.", descAr: "يرفع وينظّف البيانات، يعدّل الأسعار والمخزون، يبعث طلبيات للموردين، ويشوف سجل النشاط." },
  { v: "accountant", en: "Accountant", ar: "محاسب", descEn: "Read everything plus cash flow, finance and e-invoice readiness.", descAr: "يشوف كل إشي ومعه التدفق النقدي والمالية وجاهزية الفوترة." },
  { v: "cashier", en: "Cashier", ar: "كاشير", descEn: "Dashboard, sales, products and customers — read only.", descAr: "لوحة التحكم والمبيعات والأصناف والزبائن — قراءة بس." },
];

export function useRoleLabel() {
  const tx = useTx();
  return useCallback((r: string | null | undefined) => {
    const x = ROLES.find((i) => i.v === r);
    return x ? tx(x.en, x.ar) : r || "—";
  }, [tx]);
}

export const PAYMENTS = [
  { v: "cash", en: "Cash", ar: "كاش" },
  { v: "card", en: "Card", ar: "بطاقة" },
  { v: "cliq", en: "CliQ", ar: "كليك" },
  { v: "wallet", en: "Wallet", ar: "محفظة" },
];
export const SALE_STATUSES = [
  { v: "completed", en: "Completed", ar: "مكتملة", tone: "olive" as const },
  { v: "void", en: "Voided", ar: "ملغاة", tone: "danger" as const },
  { v: "returned", en: "Returned", ar: "مرتجعة", tone: "saffron" as const },
];

export const SEGMENT_TONE: Record<string, "olive" | "terra" | "saffron" | "danger" | "sky" | "neutral"> = {
  champions: "olive", loyal: "sky", regular: "neutral", new: "saffron", at_risk: "terra", lost: "danger",
};

export function RoleNote({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-dashed border-sand-2 bg-paper-2 px-3 py-2 text-[12.5px] text-ink-2">{children}</p>;
}

export function useScrollToHighlighted(tableId: string, active: unknown, ready: boolean) {
  useEffect(() => {
    if (!active || !ready) return;
    const t = setTimeout(() => {
      const row = document.querySelector<HTMLElement>(`[data-basira="${tableId}"] tr[class*="saffron-soft"]`);
      row?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 150);
    return () => clearTimeout(t);
  }, [tableId, active, ready]);
}
