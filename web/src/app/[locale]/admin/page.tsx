"use client";
import { useMemo, useState } from "react";
import { Crown } from "lucide-react";
import type { EChartsCoreOption } from "echarts/core";
import { useLocale, useTx } from "@/i18n";
import { ApiError } from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { date, jd, num, timeAgo } from "@/lib/format";
import Chart, { axisStyle, PALETTE } from "@/components/app/Chart";
import { ErrorBox, N, PageHeader, Section, Stat, StatSkeleton, Table, useName, type Col } from "@/components/app/kit";
import { Badge, Button, Card, Empty, Skeleton, Tabs } from "@/components/ui";
import { useHref } from "@/components/workspace/common";
import { INDUSTRIES, PLANS } from "@/components/workspace/org";

type Tenant = {
  id: string; name: string; name_ar: string | null; industry: string; city: string | null; plan: string; created_at: string; is_demo: boolean;
  members: number; branches: number; sales: number; uploads: number; ai_cost_30d: number;
};
type Waitlist = { id: string; email: string; name: string | null; business_name: string | null; business_type: string | null; city: string | null; locale: string | null; created_at: string };
type Contact = { id: string; name: string; email: string; phone: string | null; message: string; locale: string | null; created_at: string };
type Overview = {
  tenants: Tenant[]; mrr_jod: number; arr_jod: number; by_plan: Record<string, number>; signups: { w: string; n: number }[];
  waitlist: Waitlist[]; waitlist_total: number; waitlist_weekly: { w: string; n: number }[];
  ai_daily: { d: string; calls: number; tin: number | null; tout: number | null; cost: number | null }[]; ai_cost_30d: number;
  health_checks: { n: number; avg_score: number | null }; contacts: Contact[]; users: number;
};

const usd = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? "—" : `$${v.toFixed(d)}`);

export default function FounderConsole() {
  const tx = useTx();
  const locale = useLocale();
  const name = useName();
  const href = useHref();
  const { data, error, refetch } = useApiQuery<Overview>("/admin/overview", { retry: (n, e) => !(e instanceof ApiError && e.status === 403) && n < 2 });
  const [tenantView, setTenantView] = useState<"real" | "all">("all");

  const growthOpt = useMemo<EChartsCoreOption | null>(() => {
    if (!data) return null;
    const weeks = Array.from(new Set([...data.signups.map((s) => s.w), ...data.waitlist_weekly.map((s) => s.w)])).sort();
    if (!weeks.length) return null;
    const su = new Map(data.signups.map((s) => [s.w, s.n]));
    const wl = new Map(data.waitlist_weekly.map((s) => [s.w, s.n]));
    let run = 0;
    const cumulative = weeks.map((w) => (run += wl.get(w) || 0));
    return {
      legend: { top: 0, data: [tx("Business signups", "تسجيل مشاريع"), tx("Waitlist joins", "انضمام لقائمة الانتظار"), tx("Waitlist total", "مجموع قائمة الانتظار")] },
      grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
      xAxis: { type: "category", data: weeks.map((w) => date(w, locale, { day: "numeric", month: "short" })), ...axisStyle },
      yAxis: [{ type: "value", minInterval: 1, ...axisStyle }, { type: "value", minInterval: 1, ...axisStyle, splitLine: { show: false } }],
      series: [
        { name: tx("Business signups", "تسجيل مشاريع"), type: "bar", data: weeks.map((w) => su.get(w) || 0), itemStyle: { color: PALETTE[0], borderRadius: [3, 3, 0, 0] }, barMaxWidth: 14 },
        { name: tx("Waitlist joins", "انضمام لقائمة الانتظار"), type: "bar", data: weeks.map((w) => wl.get(w) || 0), itemStyle: { color: PALETTE[2], borderRadius: [3, 3, 0, 0] }, barMaxWidth: 14 },
        { name: tx("Waitlist total", "مجموع قائمة الانتظار"), type: "line", yAxisIndex: 1, data: cumulative, symbol: "none", smooth: 0.2, lineStyle: { width: 2, color: PALETTE[1] }, itemStyle: { color: PALETTE[1] } },
      ],
    };
  }, [data, locale, tx]);

  const aiOpt = useMemo<EChartsCoreOption | null>(() => {
    if (!data?.ai_daily.length) return null;
    return {
      legend: { top: 0, data: [tx("Calls", "الطلبات"), tx("Cost (USD)", "الكلفة (دولار)")] },
      grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
      xAxis: { type: "category", data: data.ai_daily.map((a) => date(a.d, locale, { day: "numeric", month: "short" })), ...axisStyle },
      yAxis: [{ type: "value", minInterval: 1, ...axisStyle }, { type: "value", ...axisStyle, splitLine: { show: false }, axisLabel: { ...axisStyle.axisLabel, formatter: (v: number) => `$${v.toFixed(2)}` } }],
      series: [
        { name: tx("Calls", "الطلبات"), type: "bar", data: data.ai_daily.map((a) => a.calls), itemStyle: { color: PALETTE[3], borderRadius: [3, 3, 0, 0] }, barMaxWidth: 12 },
        { name: tx("Cost (USD)", "الكلفة (دولار)"), type: "line", yAxisIndex: 1, data: data.ai_daily.map((a) => +(a.cost || 0).toFixed(4)), symbol: "none", lineStyle: { width: 2, color: PALETTE[0] }, itemStyle: { color: PALETTE[0] } },
      ],
    };
  }, [data, locale, tx]);

  const forbidden = error instanceof ApiError && error.status === 403;
  if (forbidden) {
    return (
      <Card className="mx-auto mt-10 max-w-lg">
        <Empty icon={<Crown size={26} />} title={tx("Founder console only", "لوحة المؤسس بس")}
          body={tx("This page shows numbers across all Idrak customers, so it's limited to the founding team.", "هالصفحة فيها أرقام كل عملاء إدراك، فهي للفريق المؤسس بس.")}
          action={<Button href={href("/app")} variant="secondary">{tx("Back to your dashboard", "ارجع للوحة التحكم")}</Button>} />
      </Card>
    );
  }

  const tenants = data ? (tenantView === "real" ? data.tenants.filter((t) => !t.is_demo) : data.tenants) : undefined;
  const totalTenants = data?.tenants.length ?? 0;
  const tokens = data?.ai_daily.reduce((a, d) => a + (d.tin || 0) + (d.tout || 0), 0) ?? 0;
  const calls = data?.ai_daily.reduce((a, d) => a + d.calls, 0) ?? 0;
  const industry = (v: string) => { const i = INDUSTRIES.find((x) => x.v === v); return i ? tx(i.en, i.ar) : v; };
  const planName = (v: string) => { const p = PLANS.find((x) => x.v === v); return p ? tx(p.en, p.ar) : v; };

  const tenantCols: Col<Tenant>[] = [
    {
      key: "name", label: tx("Business", "المشروع"), render: (t) => (
        <div className="min-w-[180px]">
          <span className="font-medium text-ink">{name(t.name, t.name_ar)}</span>{t.is_demo && <Badge className="ms-2">{tx("demo", "تجريبي")}</Badge>}
          <span className="block text-[11.5px] text-ink-3">{industry(t.industry)} · {t.city || "—"}</span>
        </div>
      ),
    },
    { key: "plan", label: tx("Plan", "الباقة"), render: (t) => <Badge tone={t.plan === "business" ? "terra" : t.plan === "growth" ? "olive" : "neutral"}>{planName(t.plan)}</Badge> },
    { key: "created_at", label: tx("Joined", "انضم"), render: (t) => <span className="num whitespace-nowrap text-ink-2">{date(t.created_at, locale)}</span> },
    { key: "members", label: tx("Users", "المستخدمين"), align: "end", render: (t) => <N v={t.members} /> },
    { key: "branches", label: tx("Branches", "الفروع"), align: "end", render: (t) => <N v={t.branches} /> },
    { key: "sales", label: tx("Sales rows", "صفوف المبيعات"), align: "end", render: (t) => <N v={t.sales} /> },
    { key: "uploads", label: tx("Uploads", "الملفات"), align: "end", render: (t) => <N v={t.uploads} /> },
    { key: "ai_cost_30d", label: tx("AI cost 30d", "كلفة الذكاء 30 يوم"), align: "end", render: (t) => <span className="num">{usd(t.ai_cost_30d, 3)}</span> },
  ];

  return (
    <div>
      <PageHeader
        eyebrow={<span className="inline-flex items-center gap-1.5 text-plum"><Crown size={13} />{tx("Founder console", "لوحة المؤسس")}</span>}
        title={tx("How Idrak is doing", "كيف ماشي إدراك")}
        subtitle={tx("Revenue, growth, demand and AI spend across every tenant.", "الإيرادات، النمو، الطلب، وكلفة الذكاء الاصطناعي لكل العملاء.")}
      />

      {error ? <ErrorBox error={error} retry={refetch} /> : (
        <>
          <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {!data ? Array.from({ length: 8 }).map((_, i) => <StatSkeleton key={i} />) : (
              <>
                <Stat label={tx("MRR", "الإيراد الشهري المتكرر")} value={<span className="num">{jd(data.mrr_jod, locale, { decimals: 0 })}</span>} hint={tx("list price, all tenants", "بسعر الباقات، كل العملاء")} tone="terra" />
                <Stat label={tx("ARR", "الإيراد السنوي المتكرر")} value={<span className="num">{jd(data.arr_jod, locale, { decimals: 0 })}</span>} hint={tx("MRR × 12", "الشهري × 12")} />
                <Stat label={tx("Tenants", "المشاريع")} value={<N v={totalTenants} />} hint={tx(`${data.tenants.filter((t) => !t.is_demo).length} real · ${data.users} user accounts`, `${data.tenants.filter((t) => !t.is_demo).length} حقيقي · ${data.users} حساب مستخدم`)} />
                <Stat label={tx("Waitlist", "قائمة الانتظار")} value={<N v={data.waitlist_total} />} hint={data.waitlist_weekly.length ? tx(`${data.waitlist_weekly[data.waitlist_weekly.length - 1].n} in the latest week`, `${data.waitlist_weekly[data.waitlist_weekly.length - 1].n} بآخر أسبوع`) : undefined} tone="saffron" />
                <Stat label={tx("Free health checks run", "فحوصات الصحة المجانية")} value={<N v={data.health_checks.n} />} hint={data.health_checks.avg_score !== null ? tx(`avg score ${num(data.health_checks.avg_score)} / 100 · lead magnet`, `معدّل النتيجة ${num(data.health_checks.avg_score)} / 100 · لجذب العملاء`) : undefined} tone="olive" />
                <Stat label={tx("AI cost, 30 days", "كلفة الذكاء، 30 يوم")} value={<span className="num">{usd(data.ai_cost_30d)}</span>} hint={tx(`${num(calls)} calls · ${num(tokens / 1000)}k tokens`, `${num(calls)} طلب · ${num(tokens / 1000)} ألف توكن`)} />
                <Stat label={tx("AI cost per tenant", "كلفة الذكاء لكل مشروع")} value={<span className="num">{usd(totalTenants ? data.ai_cost_30d / totalTenants : 0, 3)}</span>} hint={tx("vs. average plan price", "مقارنة بمعدّل سعر الباقة")} />
                <Stat label={tx("Avg revenue per tenant", "معدّل الإيراد لكل مشروع")} value={<span className="num">{jd(totalTenants ? data.mrr_jod / totalTenants : 0, locale, { decimals: 1 })}</span>} hint={tx("per month", "بالشهر")} />
              </>
            )}
          </div>

          <div className="grid gap-5 lg:grid-cols-3">
            <Section title={tx("Tenants by plan", "المشاريع حسب الباقة")}>
              {!data ? <Skeleton className="h-40" /> : (
                <ul className="space-y-4">
                  {PLANS.map((p, i) => {
                    const n = data.by_plan[p.v] || 0;
                    return (
                      <li key={p.v}>
                        <div className="mb-1 flex items-baseline justify-between text-[13.5px]">
                          <span className="text-ink">{tx(p.en, p.ar)} <span className="num text-[12px] text-ink-3">· {jd(p.price, locale, { decimals: 0 })}</span></span>
                          <span className="num text-ink">{n} <span className="text-[12px] text-ink-3">· {jd(n * p.price, locale, { decimals: 0 })}</span></span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-sand"><div className="h-full rounded-full" style={{ width: `${totalTenants ? (n / totalTenants) * 100 : 0}%`, background: [PALETTE[3], PALETTE[1], PALETTE[0]][i] }} /></div>
                      </li>
                    );
                  })}
                  {Object.keys(data.by_plan).filter((k) => !PLANS.some((p) => p.v === k)).map((k) => (
                    <li key={k} className="flex justify-between text-[13px] text-ink-3"><span>{k}</span><span className="num">{data.by_plan[k]}</span></li>
                  ))}
                </ul>
              )}
            </Section>

            <Section className="lg:col-span-2" title={tx("Signups & waitlist", "التسجيلات وقائمة الانتظار")} subtitle={tx("Per week. Line shows the waitlist growing over time.", "كل أسبوع. الخط بيبيّن نمو قائمة الانتظار.")}>
              {!data ? <Skeleton className="h-[260px]" /> : growthOpt ? <Chart option={growthOpt} height={260} /> : <Empty title={tx("No signups yet", "لسا ما في تسجيلات")} />}
            </Section>

            <Section className="lg:col-span-3" title={tx("AI usage — last 30 days", "استعمال الذكاء الاصطناعي — آخر 30 يوم")} subtitle={tx("Assistant & cleaning calls per day and their cost in USD.", "طلبات المساعد والتنظيف كل يوم وكلفتها بالدولار.")}>
              {!data ? <Skeleton className="h-[240px]" /> : aiOpt ? <Chart option={aiOpt} height={240} /> : <Empty title={tx("No AI calls in the last 30 days", "ما في طلبات ذكاء اصطناعي آخر 30 يوم")} />}
            </Section>

            <Section className="lg:col-span-3" title={tx("Tenants", "المشاريع")} subtitle={data ? tx(`${tenants?.length} shown`, `${tenants?.length} معروض`) : " "} bodyClass="p-0"
              action={<Tabs value={tenantView} onChange={setTenantView} items={[{ value: "all", label: tx("All", "الكل") }, { value: "real", label: tx("Real only", "الحقيقي بس") }]} />}>
              <Table<Tenant> rows={tenants} cols={tenantCols} dense empty={tx("No real tenants yet — the first one is coming.", "لسا ما في عملاء حقيقيين — أول واحد جاي.")} />
            </Section>

            <Section className="lg:col-span-2" title={tx("Latest waitlist", "آخر المنضمين لقائمة الانتظار")} subtitle={data ? tx(`${data.waitlist_total} people in total`, `${data.waitlist_total} شخص بالمجموع`) : " "} bodyClass="p-0 max-h-[420px] overflow-y-auto">
              {!data ? <div className="p-5"><Skeleton className="h-40" /></div> : data.waitlist.length ? (
                <ul className="divide-y divide-line/60">
                  {data.waitlist.slice(0, 25).map((w) => (
                    <li key={w.id} className="flex items-start justify-between gap-3 px-5 py-2.5 text-[13px]">
                      <div className="min-w-0">
                        <p className="truncate text-ink">{w.name || w.email}{w.business_name && <span className="text-ink-3"> · {w.business_name}</span>}</p>
                        <p className="truncate text-[12px] text-ink-3"><span dir="ltr">{w.email}</span>{w.business_type && ` · ${w.business_type}`}{w.city && ` · ${w.city}`}</p>
                      </div>
                      <span className="shrink-0 text-[11.5px] text-ink-3">{timeAgo(w.created_at, locale)}</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="px-5 py-8 text-center text-[13px] text-ink-3">{tx("Nobody yet.", "لسا ما في حدا.")}</p>}
            </Section>

            <Section title={tx("Contact messages", "رسائل التواصل")} bodyClass="p-0 max-h-[420px] overflow-y-auto">
              {!data ? <div className="p-5"><Skeleton className="h-40" /></div> : data.contacts.length ? (
                <ul className="divide-y divide-line/60">
                  {data.contacts.map((c) => (
                    <li key={c.id} className="px-5 py-3 text-[13px]">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="truncate font-medium text-ink">{c.name}</span>
                        <span className="shrink-0 text-[11.5px] text-ink-3">{timeAgo(c.created_at, locale)}</span>
                      </div>
                      <a href={`mailto:${c.email}`} className="block truncate text-[12px] text-ink-3 hover:text-terra" dir="ltr">{c.email}{c.phone && ` · ${c.phone}`}</a>
                      <p className="mt-1 line-clamp-3 text-ink-2">{c.message}</p>
                    </li>
                  ))}
                </ul>
              ) : <p className="px-5 py-8 text-center text-[13px] text-ink-3">{tx("No messages yet.", "لسا ما في رسائل.")}</p>}
            </Section>
          </div>
        </>
      )}
    </div>
  );
}
