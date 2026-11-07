"use client";
import { useMemo, useState } from "react";
import clsx from "clsx";
import { Target } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { useApiMutation, useApiQuery } from "@/lib/useApi";
import { date, jd, num } from "@/lib/format";
import { toast } from "@/components/ui/toast";
import { AskIdrak, ErrorBox, Money, PageHeader, Section, useName } from "@/components/app/kit";
import { useSession } from "@/components/app/session";
import { Badge, Button, Card, Empty, Field, Input, Select, Skeleton } from "@/components/ui";
import { useOrgDetail } from "@/components/insights/common";
import type { Goal } from "@/components/insights/types";

function ammanToday() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Amman" }).format(new Date());
}
const monthKey = (iso: string) => iso.slice(0, 7);
const addMonths = (ym: string, n: number) => {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + n, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};

export default function GoalsPage() {
  const tx = useTx();
  const q = useApiQuery<Goal[]>("/goals");
  const goals = q.data;
  const today = ammanToday();
  const thisMonth = monthKey(today);

  const months = useMemo(() => {
    const m = new Map<string, Goal[]>();
    (goals || []).forEach((g) => {
      const k = monthKey(g.period_month);
      m.set(k, [...(m.get(k) || []), g]);
    });
    return [...m.entries()].sort((a, b) => b[0].localeCompare(a[0]));
  }, [goals]);

  return (
    <div>
      <PageHeader
        eyebrow={tx("Goals", "الأهداف")}
        title={tx("Monthly revenue goals", "أهداف المبيعات الشهرية")}
        subtitle={tx("Set a target per branch and see early in the month whether you're on pace — so you can push a promotion while there's still time.",
          "حط هدف لكل فرع وشوف من بداية الشهر إذا ماشي عالوتيرة الصح — عشان تلحق تعمل عرض قبل ما يفوت الوقت.")}
        actions={<AskIdrak q={tx("Which branch is behind its goal this month and what can I do in the remaining days?", "أي فرع متأخر عن هدفه هالشهر، وشو بقدر أعمل بالأيام الباقية؟")} />}
      />
      {q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : (
        <div className="grid gap-5 lg:grid-cols-3">
          <div data-basira="goals-list" className="space-y-5 lg:col-span-2">
            {!goals ? [0, 1].map((i) => <Card key={i} className="p-5"><Skeleton className="h-5 w-40" /><Skeleton className="mt-4 h-20 w-full" /></Card>) :
              !months.length ? <Card><Empty icon={<Target size={22} />} title={tx("No goals yet", "ما في أهداف لسّا")} body={tx("Add your first monthly target with the “New goal” form.", "ضيف أول هدف شهري من النموذج.")} /></Card> :
                months.map(([m, gs]) => <MonthCard key={m} month={m} goals={gs} isCurrent={m === thisMonth} today={today} />)}
          </div>
          <NewGoal goals={goals} thisMonth={thisMonth} />
        </div>
      )}
    </div>
  );
}

function MonthCard({ month, goals: gs, isCurrent, today: t }: { month: string; goals: Goal[]; isCurrent: boolean; today: string }) {
    const tx = useTx();
    const locale = useLocale();
    const nm = useName();
    const [y, mo] = month.split("-").map(Number);
    const dim = new Date(Date.UTC(y, mo, 0)).getUTCDate();
    const elapsed = Math.max(1, Number(t.slice(8, 10)) - 1);
    const target = gs.reduce((a, g) => a + g.target, 0);
    const actual = gs.reduce((a, g) => a + g.actual, 0);
    const past = month < monthKey(t);
    return (
      <Section title={<span className="flex items-center gap-2">{date(`${month}-01`, locale, { month: "long", year: "numeric" })}
        {isCurrent && <Badge tone="terra">{tx("This month", "هالشهر")}</Badge>}</span>}
        subtitle={<><Money v={actual} decimals={0} /> {tx("of", "من")} <Money v={target} decimals={0} /> · <span className="num">{num(target ? (100 * actual) / target : 0)}%</span>
          {isCurrent && <> · {tx(`${dim - elapsed} days left`, `باقي ${dim - elapsed} يوم`)}</>}</>}>
        <ul className="space-y-5">
          {gs.map((g) => {
            const done = g.target ? (100 * g.actual) / g.target : 0;
            const pace = isCurrent ? (g.actual / elapsed) * dim : g.actual;
            const paceP = g.target ? (100 * pace) / g.target : 0;
            const ok = isCurrent ? pace >= g.target : g.actual >= g.target;
            const needDaily = isCurrent ? Math.max(0, (g.target - g.actual) / Math.max(1, dim - elapsed)) : 0;
            return (
              <li key={g.id}>
                <div className="flex flex-wrap items-baseline justify-between gap-2 text-[13.5px]">
                  <span className="font-medium text-ink">{nm(g.branch, g.branch_ar)}</span>
                  <span className="text-ink-3"><Money v={g.actual} decimals={0} className="text-ink" /> / <Money v={g.target} decimals={0} /></span>
                </div>
                <div className="relative mt-2 h-2.5 w-full overflow-hidden rounded-full bg-sand">
                  {isCurrent && <div className={clsx("absolute inset-y-0 start-0 rounded-full opacity-30", ok ? "bg-olive" : "bg-saffron")} style={{ width: `${Math.min(100, paceP)}%` }} />}
                  <div className={clsx("absolute inset-y-0 start-0 rounded-full", ok ? "bg-olive" : past ? "bg-terra" : "bg-saffron")} style={{ width: `${Math.min(100, done)}%` }} />
                </div>
                <p className={clsx("mt-1.5 text-[12px]", ok ? "text-olive" : past ? "text-danger" : "text-[#8a5d0e]")}>
                  {isCurrent ? (ok
                    ? tx(`On pace for ${jd(pace, locale, { decimals: 0 })} (${num(paceP)}%)`, `على هالوتيرة: ${jd(pace, locale, { decimals: 0 })} (${num(paceP)}%)`)
                    : tx(`Pace ${jd(pace, locale, { decimals: 0 })} — needs ${jd(needDaily, locale, { decimals: 0 })}/day from now`, `الوتيرة ${jd(pace, locale, { decimals: 0 })} — بدك ${jd(needDaily, locale, { decimals: 0 })} باليوم من هلأ`))
                    : past ? (ok ? tx(`Reached — ${num(done)}% of target`, `تحقق — ${num(done)}% من الهدف`) : tx(`Missed by ${jd(g.target - g.actual, locale, { decimals: 0 })} (${num(done)}%)`, `ما تحقق — ناقص ${jd(g.target - g.actual, locale, { decimals: 0 })} (${num(done)}%)`))
                      : tx("Not started yet", "لسّا ما بلّش")}
                </p>
              </li>
            );
          })}
        </ul>
      </Section>
    );
}

function NewGoal({ goals, thisMonth }: { goals?: Goal[]; thisMonth: string }) {
  const tx = useTx();
  const locale = useLocale();
  const nm = useName();
  const { can } = useSession();
  const org = useOrgDetail();
  const branches = org.data?.branches || [];
  const [branch, setBranch] = useState("");
  const [month, setMonth] = useState(addMonths(thisMonth, 1));
  const [target, setTarget] = useState("");
  const b = branch || branches[0]?.id || "";
  const allowed = can("manager");

  const last = goals?.filter((g) => g.branch_id === b && monthKey(g.period_month) < thisMonth).sort((x, y) => y.period_month.localeCompare(x.period_month))[0];
  const existing = goals?.find((g) => g.branch_id === b && monthKey(g.period_month) === month);
  const suggestion = last ? Math.round((last.actual * 1.05) / 100) * 100 : null;

  const save = useApiMutation<{ branch_id: string; period_month: string; target: number }>("POST", "/goals", {
    invalidate: ["/goals", "/insights/dashboard"],
    errorTitle: tx("Couldn't save the goal", "ما قدرنا نحفظ الهدف"),
    onSuccess: () => { toast(tx("Goal saved", "انحفظ الهدف")); setTarget(""); },
  });
  const t = Number(target);
  const valid = !!b && /^\d{4}-\d{2}$/.test(month) && t > 0;

  return (
    <Section id="new-goal-form" title={existing ? tx("Update a goal", "عدّل هدف") : tx("New goal", "هدف جديد")} className="self-start"
      subtitle={tx("One revenue target per branch per month", "هدف مبيعات واحد لكل فرع بالشهر")}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (valid) save.mutate({ branch_id: b, period_month: month, target: t }); }}>
        <Field label={tx("Branch", "الفرع")}>
          {org.isLoading ? <Skeleton className="h-10 w-full" /> : (
            <Select value={b} onChange={(e) => setBranch(e.target.value)} className="w-full" disabled={!allowed}>
              {branches.map((br) => <option key={br.id} value={br.id}>{nm(br.name, br.name_ar)}</option>)}
            </Select>
          )}
        </Field>
        <Field label={tx("Month", "الشهر")}>
          <Input type="month" value={month} min={addMonths(thisMonth, -1)} onChange={(e) => setMonth(e.target.value)} disabled={!allowed} className="num" />
        </Field>
        <Field label={tx("Revenue target (JD)", "هدف المبيعات (د.أ)")}
          hint={existing ? tx(`Replaces the current target of ${jd(existing.target, locale, { decimals: 0 })}.`, `بيحلّ محل الهدف الحالي ${jd(existing.target, locale, { decimals: 0 })}.`) : undefined}>
          <Input type="number" inputMode="decimal" min={0} step={100} value={target} onChange={(e) => setTarget(e.target.value)} placeholder={suggestion ? String(suggestion) : "10000"}
            disabled={!allowed} className="num" />
        </Field>
        {suggestion && allowed && (
          <button type="button" onClick={() => setTarget(String(suggestion))} className="block text-start text-[12.5px] text-terra hover:underline">
            {tx(`Use ${jd(suggestion, locale, { decimals: 0 })} — last month's ${jd(last!.actual, locale, { decimals: 0 })} + 5%`,
              `استخدم ${jd(suggestion, locale, { decimals: 0 })} — الشهر الماضي ${jd(last!.actual, locale, { decimals: 0 })} + 5%`)}
          </button>
        )}
        <span title={!allowed ? tx("Only a manager or the owner can set goals", "بس المدير أو صاحب المحل بيقدر يحط أهداف") : undefined} className="block">
          <Button type="submit" className="w-full" loading={save.isPending} disabled={!allowed || !valid}>{existing ? tx("Update goal", "عدّل الهدف") : tx("Save goal", "احفظ الهدف")}</Button>
        </span>
        {!allowed && <p className="text-[12px] text-ink-3">{tx("Only a manager or the owner can set goals.", "بس المدير أو صاحب المحل بيقدر يحط أهداف.")}</p>}
      </form>
    </Section>
  );
}
