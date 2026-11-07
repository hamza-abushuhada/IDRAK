"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { Building2, CreditCard, ScrollText, Users } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { useSession } from "@/components/app/session";

const TABS = [
  { href: "/app/settings", en: "Business", ar: "المشروع", icon: Building2 },
  { href: "/app/settings/team", en: "Team", ar: "الفريق", icon: Users },
  { href: "/app/settings/billing", en: "Billing", ar: "الاشتراك", icon: CreditCard },
  { href: "/app/settings/audit", en: "Audit log", ar: "سجل النشاط", icon: ScrollText, min: "manager" as const },
];

export default function SettingsNav() {
  const locale = useLocale();
  const tx = useTx();
  const pathname = usePathname();
  const { can } = useSession();
  const rel = pathname.replace(/^\/(ar|en)/, "");
  return (
    <nav className="-mx-1 mb-6 overflow-x-auto border-b border-line" aria-label={tx("Settings", "الإعدادات")}>
      <div className="flex min-w-max gap-1 px-1">
        {TABS.filter((t) => !t.min || can(t.min)).map((t) => {
          const active = rel === t.href;
          return (
            <Link key={t.href} href={`/${locale}${t.href}`}
              className={clsx("-mb-px inline-flex items-center gap-1.5 border-b-2 px-3.5 py-2.5 text-[13.5px] transition",
                active ? "border-terra font-medium text-ink" : "border-transparent text-ink-3 hover:text-ink")}>
              <t.icon size={15} className={active ? "text-terra" : ""} />{tx(t.en, t.ar)}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
