"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLocale, useTx } from "@/i18n";
import { Logo } from "@/components/Logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const locale = useLocale();
  const tx = useTx();
  const pathname = usePathname();
  const other = locale === "ar" ? "en" : "ar";
  return (
    <div className="grain grid min-h-dvh lg:grid-cols-[1fr_1.05fr]">
      <div className="flex flex-col px-6 py-6 sm:px-12">
        <div className="flex items-center justify-between">
          <Link href={`/${locale}`}><Logo locale={locale} /></Link>
          <Link href={pathname.replace(/^\/(ar|en)/, `/${other}`)} onClick={() => { document.cookie = `basira_locale=${other};path=/;max-age=31536000`; }}
            className="text-sm text-ink-2 hover:text-terra">{locale === "ar" ? "English" : "العربية"}</Link>
        </div>
        <div className="mx-auto flex w-full max-w-[420px] flex-1 flex-col justify-center py-10">{children}</div>
        <p className="text-xs text-ink-3">© 2026 Idrak · {tx("Made in Amman", "صُنع في عمّان")}</p>
      </div>
      <aside className="relative hidden overflow-hidden border-s border-line bg-paper-2 lg:block">
        <div className="absolute inset-0 flex flex-col justify-center px-16">
          <p className="text-[12px] font-medium uppercase tracking-[.16em] text-terra">{tx("What owners told us", "شو حكولنا أصحاب المحلات")}</p>
          <blockquote className="mt-5 max-w-lg font-serif text-[30px] leading-[1.3] text-ink">
            {tx("“I thought my numbers were fine. Idrak showed me JD 400 a month walking out the door — in a week.”",
              "«كنت مفكر أرقامي تمام. إدراك ورّاني 400 دينار بالشهر طالعة من الباب — خلال أسبوع.»")}
          </blockquote>
          <p className="mt-4 text-sm text-ink-3">{tx("Pilot mini-market owner, Amman (illustrative)", "صاحب ميني ماركت تجريبي، عمّان (مثال توضيحي)")}</p>
          <div className="mt-12 grid max-w-lg grid-cols-3 gap-6 border-t border-line pt-6">
            {[["42 → 97", tx("Data Health Score", "صحة البيانات")], ["7", tx("kinds of money leaks", "أنواع خسائر")], ["AR / EN", tx("built for Jordan", "مصمم للأردن")]].map(([a, b]) => (
              <div key={b}><p className="num text-[22px] text-ink">{a}</p><p className="mt-1 text-[12.5px] text-ink-3">{b}</p></div>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}
