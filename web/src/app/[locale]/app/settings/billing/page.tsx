"use client";
import { useState } from "react";
import clsx from "clsx";
import { Check, Info } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { useApiMutation, useApiQuery } from "@/lib/useApi";
import { jd, num } from "@/lib/format";
import { AskIdrak, ErrorBox, PageHeader, Section } from "@/components/app/kit";
import { useSession } from "@/components/app/session";
import { Badge, Button, Card, ProgressBar, Skeleton, Tabs } from "@/components/ui";
import { toast } from "@/components/ui/toast";
import SettingsNav from "@/components/workspace/SettingsNav";
import { RoleNote } from "@/components/workspace/common";
import { PLANS, type OrgFull, type PlanKey } from "@/components/workspace/org";

export default function BillingPage() {
  const tx = useTx();
  const locale = useLocale();
  const { can, refresh } = useSession();
  const owner = can("owner");
  const [cycle, setCycle] = useState<"monthly" | "yearly">("monthly");
  const { data: org, error, refetch } = useApiQuery<OrgFull>("/org");
  const change = useApiMutation<{ plan: PlanKey }>("PATCH", "/org", {
    invalidate: ["/org"], errorTitle: tx("Couldn't change the plan", "ما قدرنا نغيّر الباقة"),
    onSuccess: (_r, b) => { const p = PLANS.find((x) => x.v === b.plan)!; toast(tx(`You're on ${p.en} now`, `صرت على باقة ${p.ar}`)); refresh(); },
  });

  const current = PLANS.find((p) => p.v === org?.plan) || PLANS[1];
  const price = (m: number) => (cycle === "yearly" ? m * 10 : m);

  const meters = org ? [
    { k: tx("Rows processed (30 days)", "الصفوف المعالجة (30 يوم)"), v: org.usage.rows_30d, max: current.limits.rows_30d },
    { k: tx("Team members", "أعضاء الفريق"), v: org.usage.members, max: current.limits.members },
    { k: tx("Branches", "الفروع"), v: org.branches.length, max: current.limits.branches },
    { k: tx("Assistant questions (30 days)", "أسئلة المساعد (30 يوم)"), v: org.usage.ai_calls_30d, max: current.limits.ai_calls_30d },
    { k: tx("File uploads (30 days)", "الملفات المرفوعة (30 يوم)"), v: org.usage.uploads_30d, max: undefined },
  ] : [];

  return (
    <div>
      <PageHeader
        eyebrow={tx("Admin · Settings", "الإدارة · الإعدادات")}
        title={tx("Billing & plan", "الاشتراك والباقة")}
        subtitle={tx("Your plan, what you've used this month, and options to grow.", "باقتك، شو استعملت هالشهر، وخيارات تكبر فيها.")}
        actions={<AskIdrak q={tx("Which plan fits my business based on how I use Idrak?", "أي باقة بتناسب شغلي حسب استعمالي لإدراك؟")} />}
      />
      <SettingsNav />

      {error ? <ErrorBox error={error} retry={refetch} /> : !org ? (
        <div className="grid gap-5 lg:grid-cols-3"><Skeleton className="h-64" /><Skeleton className="h-64 lg:col-span-2" /></div>
      ) : (
        <>
          <div className="grid gap-5 lg:grid-cols-3">
            <Card data-basira="plan-card" className="p-5">
              <p className="text-[12px] font-medium uppercase tracking-[.14em] text-terra">{tx("Current plan", "باقتك الحالية")}</p>
              <h2 className="mt-2 font-serif text-[30px] leading-none text-ink">{tx(current.en, current.ar)}</h2>
              <p className="mt-2 text-[13.5px] text-ink-2">{tx(current.blurbEn, current.blurbAr)}</p>
              <p className="mt-4 flex items-baseline gap-1.5"><span className="num font-serif text-[34px] leading-none text-ink">{jd(current.price, locale, { decimals: 0 })}</span><span className="text-[13px] text-ink-3">/ {tx("month", "شهر")}</span></p>
              {org.is_demo && <Badge tone="saffron" className="mt-4">{tx("Demo business — no charges", "مشروع تجريبي — بدون دفع")}</Badge>}
              <ul className="mt-4 space-y-1.5 border-t border-line/70 pt-4 text-[13px] text-ink-2">
                {(tx.isAr ? current.featuresAr : current.featuresEn).map((f) => <li key={f} className="flex gap-2"><Check size={14} className="mt-0.5 shrink-0 text-olive" />{f}</li>)}
              </ul>
            </Card>

            <Section id="usage-meters" className="lg:col-span-2" title={tx("Usage", "الاستعمال")} subtitle={tx("Last 30 days, against what your plan includes.", "آخر 30 يوم، مقارنة بالمسموح بباقتك.")}>
              <ul className="space-y-4">
                {meters.map((m) => {
                  const pct = m.max ? (m.v / m.max) * 100 : 0;
                  return (
                    <li key={m.k}>
                      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[13.5px]">
                        <span className="text-ink-2">{m.k}</span>
                        <span className="num text-ink">
                          {num(m.v)}
                          {m.max === undefined ? <span className="text-ink-3"> · {tx("unlimited", "بلا حدود")}</span>
                            : m.max === null ? <span className="text-ink-3"> · {tx("not in this plan", "مش ضمن باقتك")}</span>
                              : <span className="text-ink-3"> / {num(m.max)}</span>}
                        </span>
                      </div>
                      {m.max ? <ProgressBar value={pct} tone={pct >= 100 ? "terra" : pct >= 80 ? "saffron" : "olive"} /> : <div className="h-2 rounded-full bg-sand/60" />}
                      {m.max && pct >= 100 ? <p className="mt-1 text-[12px] text-terra">{tx("Over the limit — consider the next plan up.", "تجاوزت الحد — فكّر بالباقة الأعلى.")}</p> : null}
                    </li>
                  );
                })}
              </ul>
            </Section>
          </div>

          <div className="mt-8 mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-serif text-[22px] text-ink">{tx("Plans", "الباقات")}</h2>
            <Tabs value={cycle} onChange={setCycle} items={[
              { value: "monthly", label: tx("Monthly", "شهري") },
              { value: "yearly", label: <span>{tx("Yearly", "سنوي")} <span className="text-[11px] opacity-80">· {tx("2 months free", "شهرين مجاناً")}</span></span> },
            ]} />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            {PLANS.map((p) => {
              const isCurrent = p.v === current.v;
              return (
                <Card key={p.v} className={clsx("flex flex-col p-5", isCurrent && "border-ink")}>
                  <div className="flex items-center justify-between">
                    <h3 className="font-serif text-[20px] text-ink">{tx(p.en, p.ar)}</h3>
                    {isCurrent ? <Badge tone="olive">{tx("Current", "الحالية")}</Badge> : p.v === "growth" ? <Badge tone="terra">{tx("Most popular", "الأكثر طلباً")}</Badge> : null}
                  </div>
                  <p className="mt-1 text-[13px] text-ink-3">{tx(p.blurbEn, p.blurbAr)}</p>
                  <p className="mt-4 flex items-baseline gap-1.5">
                    <span className="num font-serif text-[32px] leading-none text-ink">{jd(price(p.price), locale, { decimals: 0 })}</span>
                    <span className="text-[13px] text-ink-3">/ {cycle === "yearly" ? tx("year", "سنة") : tx("month", "شهر")}</span>
                  </p>
                  <p className="mt-1 h-4 text-[12px] text-ink-3">{cycle === "yearly" ? tx(`≈ ${jd(p.price * 10 / 12, locale, { decimals: 1 })} a month`, `يعني تقريباً ${jd(p.price * 10 / 12, locale, { decimals: 1 })} بالشهر`) : ""}</p>
                  <ul className="mt-4 flex-1 space-y-1.5 text-[13px] text-ink-2">
                    {(tx.isAr ? p.featuresAr : p.featuresEn).map((f) => <li key={f} className="flex gap-2"><Check size={14} className="mt-0.5 shrink-0 text-olive" />{f}</li>)}
                  </ul>
                  <Button className="mt-5 w-full" variant={isCurrent ? "secondary" : "primary"} disabled={isCurrent || !owner}
                    loading={change.isPending && change.variables?.plan === p.v}
                    onClick={() => { if (window.confirm(tx(`Switch to ${p.en}?`, `بدك تحوّل لباقة ${p.ar}؟`))) change.mutate({ plan: p.v }); }}>
                    {isCurrent ? tx("Your plan", "باقتك") : p.price > current.price ? tx("Upgrade", "رقّي الباقة") : tx("Switch plan", "غيّر الباقة")}
                  </Button>
                </Card>
              );
            })}
          </div>

          <div className="mt-4 space-y-2">
            <p className="flex items-start gap-2 rounded-lg bg-paper-2 px-3 py-2.5 text-[13px] text-ink-2">
              <Info size={15} className="mt-0.5 shrink-0 text-sky" />
              {tx("Payments are coming soon — in this demo the plan switches instantly and nothing is charged.", "الدفع قريباً — بهالنسخة التجريبية الباقة بتتغيّر فوراً وبدون أي دفع.")}
            </p>
            {!owner && <RoleNote>{tx("Only the owner can change the plan.", "بس المالك بيقدر يغيّر الباقة.")}</RoleNote>}
          </div>
        </>
      )}
    </div>
  );
}
