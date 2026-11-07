"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRouter } from "@/lib/router";
import { useEffect, useState } from "react";
import clsx from "clsx";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  BarChart3, Bell, Building2, Calculator, ChevronDown, ClipboardCheck, Coins, Database, FileText, Gauge, Goal, LineChart, LogOut, Menu, PackageSearch,
  Receipt, Settings, ShieldCheck, ShoppingBasket, Sparkles, Store, Truck, UserRound, Users, Wallet, X, Siren, Crown, Languages,
} from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { Logo } from "@/components/Logo";
import { Kbd } from "@/components/ui";
import { Loader2 } from "lucide-react";
import { useSession } from "./session";
import { useApiQuery, useApiMutation } from "@/lib/useApi";
import { timeAgo } from "@/lib/format";
import AssistantPanel from "@/components/assistant/AssistantPanel";
import { useAssistant } from "@/components/assistant/store";

type Item = { href: string; en: string; ar: string; icon: React.ComponentType<{ size?: number; className?: string }>; min?: "cashier" | "accountant" | "manager" | "owner" };
const NAV: { en: string; ar: string; items: Item[] }[] = [
  { en: "Overview", ar: "نظرة عامة", items: [{ href: "/app", en: "Dashboard", ar: "لوحة التحكم", icon: Gauge }] },
  { en: "Data", ar: "البيانات", items: [{ href: "/app/data", en: "Data hub & cleaning", ar: "البيانات والتنظيف", icon: Database, min: "manager" }] },
  {
    en: "Business", ar: "الشغل", items: [
      { href: "/app/sales", en: "Sales", ar: "المبيعات", icon: Receipt },
      { href: "/app/products", en: "Products & stock", ar: "الأصناف والمخزون", icon: PackageSearch },
      { href: "/app/customers", en: "Customers", ar: "الزبائن", icon: Users },
      { href: "/app/suppliers", en: "Suppliers", ar: "الموردين", icon: Truck },
      { href: "/app/employees", en: "Employees", ar: "الموظفين", icon: UserRound },
      { href: "/app/branches", en: "Branches", ar: "الفروع", icon: Store },
    ],
  },
  {
    en: "Decide", ar: "القرارات", items: [
      { href: "/app/insights/leaks", en: "Money leaks", ar: "وين عم تخسر", icon: Siren },
      { href: "/app/insights/forecast", en: "Forecast", ar: "توقّع الطلب", icon: LineChart },
      { href: "/app/insights/reorder", en: "Reorder planner", ar: "مخطط الطلبيات", icon: ShoppingBasket },
      { href: "/app/insights/customers", en: "Customer insights", ar: "تحليل الزبائن", icon: BarChart3 },
      { href: "/app/insights/basket", en: "Bought together", ar: "بيننباعوا مع بعض", icon: Coins },
      { href: "/app/insights/simulator", en: "Price simulator", ar: "محاكي الأسعار", icon: Calculator },
      { href: "/app/insights/cashflow", en: "Cash flow", ar: "التدفق النقدي", icon: Wallet, min: "accountant" },
      { href: "/app/goals", en: "Goals", ar: "الأهداف", icon: Goal },
      { href: "/app/alerts", en: "Alerts", ar: "التنبيهات", icon: Bell },
    ],
  },
  {
    en: "Admin", ar: "الإدارة", items: [
      { href: "/app/compliance", en: "E-invoice readiness", ar: "جاهزية الفوترة", icon: ShieldCheck, min: "accountant" },
      { href: "/app/reports", en: "Reports", ar: "التقارير", icon: FileText },
      { href: "/app/settings", en: "Settings", ar: "الإعدادات", icon: Settings },
    ],
  },
];

const RANK = { cashier: 1, accountant: 2, manager: 3, owner: 4 };

export default function AppShell({ children }: { children: React.ReactNode }) {
  const locale = useLocale();
  const tx = useTx();
  const pathname = usePathname();
  const router = useRouter();
  const { me, org, role, switchOrg, signOut, loading } = useSession();
  const [mobileNav, setMobileNav] = useState(false);
  const assistantOpen = useAssistant((s) => s.open);
  const toggleAssistant = useAssistant((s) => s.toggle);
  const rel = pathname.replace(/^\/(ar|en)/, "") || "/";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); toggleAssistant(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleAssistant]);
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  useEffect(() => { setMobileNav(false); setPendingHref(null); }, [pathname]);

  const switchLang = () => {
    const other = locale === "ar" ? "en" : "ar";
    document.cookie = `basira_locale=${other};path=/;max-age=31536000`;
    router.push(pathname.replace(/^\/(ar|en)/, `/${other}`) + window.location.search);
  };

  if (loading || !me || !org) {
    return (
      <div className="grid min-h-dvh place-items-center bg-paper">
        <div className="flex flex-col items-center gap-3 text-ink-3"><Logo locale={locale} /><span className="text-sm">{tx("Opening your workspace…", "عم نفتح مساحة شغلك…")}</span></div>
      </div>
    );
  }

  const isActive = (href: string) => (href === "/app" ? rel === "/app" : rel === href || rel.startsWith(href + "/"));
  const orgName = (o: { name: string; name_ar: string | null }) => (locale === "ar" ? o.name_ar || o.name : o.name);

  const nav = (
    <nav className="flex h-full flex-col">
      <div className="flex h-16 items-center justify-between px-5">
        <Link href={`/${locale}/app`}><Logo locale={locale} size={24} /></Link>
        <button className="lg:hidden text-ink-3" onClick={() => setMobileNav(false)}><X size={18} /></button>
      </div>
      <div className="px-3 pb-3">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button className="flex w-full items-center gap-2.5 rounded-xl border border-line bg-[#FFFCF7] px-3 py-2.5 text-start hover:border-sand-2">
              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-terra-soft font-serif text-[15px] text-terra-2">{orgName(org).slice(0, 1)}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13.5px] font-medium text-ink">{orgName(org)}</span>
                <span className="block text-[11.5px] text-ink-3">{tx({ owner: "Owner", manager: "Manager", accountant: "Accountant", cashier: "Cashier" }[org.role], { owner: "المالك", manager: "مدير", accountant: "محاسب", cashier: "كاشير" }[org.role])} · {org.branches} {tx("branches", "فروع")}</span>
              </span>
              <ChevronDown size={15} className="text-ink-3" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content align="start" sideOffset={6} className="z-50 w-64 rounded-xl border border-line bg-paper p-1.5 shadow-[var(--shadow-lift)]">
              <p className="px-2.5 py-1.5 text-[11px] uppercase tracking-wider text-ink-3">{tx("Your businesses", "مشاريعك")}</p>
              {me.orgs.map((o) => (
                <DropdownMenu.Item key={o.id} onSelect={() => switchOrg(o.id)} className={clsx("flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-sm outline-none hover:bg-sand", o.id === org.id && "bg-sand")}>
                  <Building2 size={15} className="text-ink-3" /><span className="truncate">{orgName(o)}</span>
                </DropdownMenu.Item>
              ))}
              <DropdownMenu.Separator className="my-1 h-px bg-line" />
              <DropdownMenu.Item onSelect={() => router.push(`/${locale}/onboarding?new=1`)} className="cursor-pointer rounded-lg px-2.5 py-2 text-sm text-terra outline-none hover:bg-sand">+ {tx("Add a business", "أضف مشروع")}</DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>
      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {NAV.map((g) => {
          const items = g.items.filter((i) => !i.min || RANK[role!] >= RANK[i.min]);
          if (!items.length) return null;
          return (
            <div key={g.en} className="mt-3">
              <p className="px-2.5 pb-1 text-[11px] font-medium uppercase tracking-[.12em] text-ink-3">{tx(g.en, g.ar)}</p>
              {items.map((i) => (
                <Link key={i.href} href={`/${locale}${i.href}`} data-basira={`nav-${i.href.replace(/\//g, "-").slice(1)}`}
                  onClick={() => { if (!isActive(i.href)) setPendingHref(i.href); }}
                  className={clsx("group flex items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-[13.5px] transition",
                    (pendingHref ? pendingHref === i.href : isActive(i.href)) ? "bg-ink text-paper" : "text-ink-2 hover:bg-sand hover:text-ink")}>
                  <i.icon size={16} className={(pendingHref ? pendingHref === i.href : isActive(i.href)) ? "text-saffron" : "text-ink-3 group-hover:text-ink-2"} />
                  {tx(i.en, i.ar)}
                  {pendingHref === i.href && <Loader2 size={14} className="ms-auto animate-spin text-saffron" />}
                </Link>
              ))}
            </div>
          );
        })}
        {me.is_super_admin && (
          <div className="mt-3">
            <Link href={`/${locale}/admin`} className="flex items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-[13.5px] text-plum hover:bg-sand"><Crown size={16} />{tx("Founder console", "لوحة المؤسس")}</Link>
          </div>
        )}
      </div>
      <div className="border-t border-line px-4 py-3 text-[12px] text-ink-3">
        <div className="flex items-center justify-between"><span className="truncate">{me.full_name || me.email}</span>
          <button onClick={signOut} title={tx("Sign out", "تسجيل الخروج")} className="rounded p-1 hover:bg-sand hover:text-ink"><LogOut size={15} /></button></div>
      </div>
    </nav>
  );

  return (
    <div className="flex min-h-dvh bg-paper">
      <aside className="no-print sticky top-0 hidden h-dvh w-[252px] shrink-0 border-e border-line bg-paper-2/60 lg:block">{nav}</aside>
      {mobileNav && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-ink/30" onClick={() => setMobileNav(false)} />
          <aside className="absolute inset-y-0 start-0 w-[270px] bg-paper shadow-xl">{nav}</aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-paper/90 px-4 backdrop-blur sm:px-6">
          <button className="lg:hidden text-ink-2" onClick={() => setMobileNav(true)}><Menu size={20} /></button>
          <button onClick={toggleAssistant} data-basira="ask-basira"
            className="group flex h-10 min-w-0 flex-1 items-center gap-2.5 rounded-full border border-line bg-[#FFFCF7] px-4 text-start text-[13.5px] text-ink-3 hover:border-terra/40 sm:max-w-md">
            <Sparkles size={15} className="text-terra" />
            <span className="truncate">{tx("Ask Idrak about your business…", "اسأل إدراك عن شغلك…")}</span>
            <span className="ms-auto hidden sm:block"><Kbd>Ctrl K</Kbd></span>
          </button>
          <div className="ms-auto flex items-center gap-1.5">
            <button onClick={switchLang} className="flex h-9 items-center gap-1.5 rounded-full px-3 text-[13px] text-ink-2 hover:bg-sand" data-basira="language-switch">
              <Languages size={15} />{locale === "ar" ? "EN" : "عربي"}
            </button>
            <Notifications />
          </div>
        </header>
        <div className="flex min-w-0 flex-1">
          <main className={clsx("min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8", assistantOpen && "xl:pe-6")}>
            <div className="mx-auto max-w-[1280px]">{children}</div>
          </main>
          <AssistantPanel />
        </div>
      </div>
    </div>
  );
}

function Notifications() {
  const tx = useTx();
  const locale = useLocale();
  const router = useRouter();
  const { data } = useApiQuery<{ items: { id: string; kind: string; title: string; link: string | null; read_at: string | null; created_at: string }[]; unread: number }>("/notifications", { refetchInterval: 60000 });
  const readAll = useApiMutation("POST", "/notifications/read", { invalidate: ["/notifications"] });
  return (
    <DropdownMenu.Root onOpenChange={(o) => { if (!o && data?.unread) readAll.mutate(undefined); }}>
      <DropdownMenu.Trigger asChild>
        <button className="relative grid size-9 place-items-center rounded-full text-ink-2 hover:bg-sand" data-basira="notifications">
          <Bell size={17} />
          {!!data?.unread && <span className="num absolute -top-0.5 -end-0.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-terra px-1 text-[10px] text-paper">{data.unread}</span>}
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={8} className="z-50 w-[340px] rounded-xl border border-line bg-paper p-1.5 shadow-[var(--shadow-lift)]">
          <p className="px-3 py-2 font-serif text-[15px]">{tx("Notifications", "الإشعارات")}</p>
          {(data?.items || []).slice(0, 8).map((n) => (
            <DropdownMenu.Item key={n.id} onSelect={() => n.link && router.push(`/${locale}${n.link}`)}
              className="flex cursor-pointer gap-2.5 rounded-lg px-3 py-2.5 outline-none hover:bg-sand">
              <span className={clsx("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-sand-2" : "bg-terra")} />
              <span className="min-w-0"><span className="block text-[13px] text-ink">{n.title}</span><span className="block text-[11.5px] text-ink-3">{timeAgo(n.created_at, locale)}</span></span>
            </DropdownMenu.Item>
          ))}
          {!data?.items?.length && <p className="px-3 py-6 text-center text-sm text-ink-3">{tx("All caught up", "ما في إشي جديد")}</p>}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
