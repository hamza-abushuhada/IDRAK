"use client";
import { useState } from "react";
import clsx from "clsx";
import { BellRing, Mail, Play, Smartphone, Trash2 } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { useApiMutation, useApiQuery } from "@/lib/useApi";
import { jd, num, timeAgo } from "@/lib/format";
import { toast } from "@/components/ui/toast";
import { AskIdrak, ErrorBox, PageHeader, Section } from "@/components/app/kit";
import { useSession } from "@/components/app/session";
import { Badge, Button, Card, Empty, Field, Input, Select, Skeleton } from "@/components/ui";
import type { AlertMetric, AlertRule } from "@/components/insights/types";

const METRICS: Record<AlertMetric, { en: string; ar: string; unitEn: string; unitAr: string; op: ">" | "<"; thr: number; nameEn: string; nameAr: string; money?: boolean; pct?: boolean }> = {
  stock_below_reorder: { en: "Items at or below reorder level", ar: "أصناف وصلت حد إعادة الطلب", unitEn: "items", unitAr: "صنف", op: ">", thr: 5, nameEn: "Items running low", nameAr: "أصناف قرّبت تخلص" },
  daily_sales_drop_pct: { en: "Yesterday's sales drop vs 4-week average", ar: "نزول مبيعات مبارح عن متوسط 4 أسابيع", unitEn: "%", unitAr: "%", op: ">", thr: 20, nameEn: "Sales dropped sharply", nameAr: "المبيعات نزلت كثير", pct: true },
  discount_rate_pct: { en: "Discounts as % of sales (last 7 days)", ar: "الخصومات كنسبة من المبيعات (آخر 7 أيام)", unitEn: "%", unitAr: "%", op: ">", thr: 5, nameEn: "Discounts too high", nameAr: "الخصومات عالية", pct: true },
  expiring_items: { en: "Batches expiring within 7 days", ar: "دفعات بتنتهي خلال 7 أيام", unitEn: "batches", unitAr: "دفعة", op: ">", thr: 0, nameEn: "Stock about to expire", nameAr: "بضاعة قربت تنتهي" },
  revenue_below: { en: "Yesterday's revenue (JD)", ar: "مبيعات مبارح (د.أ)", unitEn: "JD", unitAr: "د.أ", op: "<", thr: 1000, nameEn: "Slow sales day", nameAr: "يوم مبيعات ضعيف", money: true },
};

export default function AlertsPage() {
  const tx = useTx();
  const locale = useLocale();
  const { can } = useSession();
  const allowed = can("manager");
  const q = useApiQuery<AlertRule[]>("/alerts");
  const rules = q.data;
  const run = useApiMutation<undefined, { fired: AlertRule[] }>("POST", "/alerts/run", {
    invalidate: ["/alerts", "/notifications"],
    errorTitle: tx("Couldn't run the checks", "ما قدرنا نفحص"),
    onSuccess: (r) => {
      const n = r.fired?.length || 0;
      const emails = r.fired?.filter((f) => f.channel === "email").length || 0;
      toast(n ? tx(`${n} ${n === 1 ? "alert" : "alerts"} fired`, `${n} تنبيه اشتغل`) : tx("All clear", "كل إشي تمام"),
        n ? tx(`Added to your notifications${emails ? `; ${emails} sent by email` : ""}.`, `انضافوا للإشعارات${emails ? `، و${emails} انبعتوا بالإيميل` : ""}.`) : tx("No rule crossed its threshold.", "ولا قاعدة تعدّت الحد."), n ? "info" : "ok");
    },
  });
  const noPerm = tx("Only a manager or the owner can change alerts", "بس المدير أو صاحب المحل بيقدر يعدّل التنبيهات");

  return (
    <div>
      <PageHeader
        eyebrow={tx("Alerts", "التنبيهات")}
        title={tx("Tell me when something's off", "نبّهني إذا في إشي غلط")}
        subtitle={tx("Simple rules that watch stock, sales and discounts for you and ping you in the app or by email.",
          "قواعد بسيطة بتراقب المخزون والمبيعات والخصومات عنك، وبتنبّهك بالتطبيق أو بالإيميل.")}
        actions={<>
          <span title={!allowed ? noPerm : undefined} className="inline-flex">
            <Button data-basira="run-alerts" variant="secondary" loading={run.isPending} disabled={!allowed} onClick={() => run.mutate(undefined)}>
              <Play size={14} />{tx("Check now", "افحص هلأ")}
            </Button>
          </span>
          <AskIdrak q={tx("Which alerts should a shop like mine have, and what thresholds make sense?", "شو التنبيهات اللي لازم تكون عند محل زي محلي، وشو الحدود المنطقية؟")} />
        </>}
      />
      {q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : (
        <div className="grid gap-5 lg:grid-cols-3">
          <div data-basira="alerts-list" className="space-y-3 lg:col-span-2">
            {!rules ? [0, 1, 2].map((i) => <Card key={i} className="p-5"><Skeleton className="h-5 w-48" /><Skeleton className="mt-3 h-4 w-72 max-w-full" /></Card>) :
              !rules.length ? <Card><Empty icon={<BellRing size={22} />} title={tx("No alert rules yet", "ما في تنبيهات لسّا")} body={tx("Start with “Items running low” — it's the one shop owners use most.", "ابدأ بـ«أصناف قرّبت تخلص» — هو أكثر واحد بيستعملوه أصحاب المحلات.")} /></Card> :
                rules.map((r) => <RuleCard key={r.id} r={r} allowed={allowed} noPerm={noPerm} locale={locale} />)}
          </div>
          <NewAlert allowed={allowed} noPerm={noPerm} />
        </div>
      )}
    </div>
  );
}

function fmtVal(m: AlertMetric, v: number | null | undefined, locale: "ar" | "en") {
  if (v === null || v === undefined) return "—";
  const meta = METRICS[m];
  if (meta?.money) return jd(v, locale, { decimals: 0 });
  if (meta?.pct) return `${num(v, 1)}%`;
  return num(v);
}

function RuleCard({ r, allowed, noPerm, locale }: { r: AlertRule; allowed: boolean; noPerm: string; locale: "ar" | "en" }) {
  const tx = useTx();
  const [confirm, setConfirm] = useState(false);
  const meta = METRICS[r.metric];
  const toggle = useApiMutation<{ is_active: boolean }>("PATCH", `/alerts/${r.id}`, { invalidate: ["/alerts"], errorTitle: tx("Couldn't update", "ما قدرنا نعدّل") });
  const del = useApiMutation<undefined>("DELETE", `/alerts/${r.id}`, {
    invalidate: ["/alerts"], errorTitle: tx("Couldn't delete", "ما قدرنا نحذف"),
    onSuccess: () => toast(tx("Alert deleted", "انحذف التنبيه")),
  });
  const active = toggle.variables && (toggle.isPending || toggle.isSuccess) ? toggle.variables.is_active : r.is_active;
  return (
    <Card className={clsx("p-5", !active && "opacity-70")}>
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2">
            <span className="font-serif text-[16.5px] text-ink">{r.name}</span>
            {active && r.triggered && <Badge tone="danger">{tx("Triggered now", "شغّال هلأ")}</Badge>}
            {active && !r.triggered && <Badge tone="olive">{tx("OK", "تمام")}</Badge>}
            {!active && <Badge>{tx("Paused", "موقوف")}</Badge>}
          </p>
          <p className="mt-1 text-[13px] text-ink-2">{meta ? tx(meta.en, meta.ar) : r.metric} <span className="num">{r.operator === ">" ? tx("above", "أكثر من") : tx("below", "أقل من")} {fmtVal(r.metric, r.threshold, locale)}</span></p>
          <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-3">
            <span>{tx("Now:", "هلأ:")} <span className={clsx("num font-medium", r.triggered ? "text-danger" : "text-ink")}>{fmtVal(r.metric, r.current, locale)}</span></span>
            <span className="inline-flex items-center gap-1">{r.channel === "email" ? <Mail size={12} /> : <Smartphone size={12} />}{r.channel === "email" ? tx("Email + app", "إيميل + التطبيق") : tx("In app", "بالتطبيق")}</span>
            <span>{r.last_triggered_at ? tx(`Last fired ${timeAgo(r.last_triggered_at, locale)}`, `آخر مرة ${timeAgo(r.last_triggered_at, locale)}`) : tx("Never fired", "ما اشتغل ولا مرة")}</span>
          </p>
        </div>
        <div className="flex items-center gap-2" title={!allowed ? noPerm : undefined}>
          <button role="switch" aria-checked={active} disabled={!allowed || toggle.isPending} onClick={() => toggle.mutate({ is_active: !active })}
            aria-label={tx("Active", "مفعّل")}
            className={clsx("relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50", active ? "bg-olive" : "bg-sand-2")}>
            <span className={clsx("absolute top-0.5 size-5 rounded-full bg-paper shadow transition-[inset-inline-start]", active ? "start-[22px]" : "start-0.5")} />
          </button>
          {confirm ? (
            <>
              <Button size="sm" variant="ghost" onClick={() => setConfirm(false)}>{tx("Keep", "خلّيه")}</Button>
              <Button size="sm" variant="danger" loading={del.isPending} onClick={() => del.mutate(undefined)}>{tx("Delete", "احذف")}</Button>
            </>
          ) : (
            <button disabled={!allowed} onClick={() => setConfirm(true)} className="grid size-8 place-items-center rounded-full text-ink-3 hover:bg-sand hover:text-danger disabled:opacity-40"
              aria-label={tx("Delete alert", "احذف التنبيه")}><Trash2 size={15} /></button>
          )}
        </div>
      </div>
    </Card>
  );
}

function NewAlert({ allowed, noPerm }: { allowed: boolean; noPerm: string }) {
  const tx = useTx();
  const [metric, setMetric] = useState<AlertMetric>("stock_below_reorder");
  const meta = METRICS[metric];
  const [name, setName] = useState("");
  const [op, setOp] = useState<">" | "<">(meta.op);
  const [thr, setThr] = useState(String(meta.thr));
  const [channel, setChannel] = useState<"in_app" | "email">("in_app");
  const pick = (m: AlertMetric) => { setMetric(m); setOp(METRICS[m].op); setThr(String(METRICS[m].thr)); };
  const add = useApiMutation<{ name: string; metric: AlertMetric; operator: string; threshold: number; channel: string }>("POST", "/alerts", {
    invalidate: ["/alerts"], errorTitle: tx("Couldn't add the alert", "ما قدرنا نضيف التنبيه"),
    onSuccess: () => { toast(tx("Alert added", "انضاف التنبيه")); setName(""); },
  });
  const t = Number(thr);
  const valid = thr !== "" && Number.isFinite(t);
  const finalName = name.trim() || tx(meta.nameEn, meta.nameAr);
  return (
    <Section id="new-alert-form" className="self-start" title={tx("New alert", "تنبيه جديد")} subtitle={tx("Live values update on this page; “Check now” sends the notifications", "القيم بتتحدّث هون مباشرة؛ «افحص هلأ» بيبعت الإشعارات")}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (valid) add.mutate({ name: finalName, metric, operator: op, threshold: t, channel }); }}>
        <Field label={tx("Watch", "راقب")}>
          <Select value={metric} onChange={(e) => pick(e.target.value as AlertMetric)} className="w-full" disabled={!allowed}>
            {(Object.keys(METRICS) as AlertMetric[]).map((m) => <option key={m} value={m}>{tx(METRICS[m].en, METRICS[m].ar)}</option>)}
          </Select>
        </Field>
        <div className="grid grid-cols-[auto_1fr] gap-3">
          <Field label={tx("When", "لما")}>
            <Select value={op} onChange={(e) => setOp(e.target.value as ">" | "<")} disabled={!allowed}>
              <option value=">">{tx("above", "أكثر من")}</option>
              <option value="<">{tx("below", "أقل من")}</option>
            </Select>
          </Field>
          <Field label={tx(`Threshold (${meta.unitEn})`, `الحد (${meta.unitAr})`)}>
            <Input type="number" inputMode="decimal" value={thr} onChange={(e) => setThr(e.target.value)} disabled={!allowed} className="num" />
          </Field>
        </div>
        <Field label={tx("Name", "الاسم")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={tx(meta.nameEn, meta.nameAr)} disabled={!allowed} />
        </Field>
        <Field label={tx("Notify me", "نبّهني")}>
          <Select value={channel} onChange={(e) => setChannel(e.target.value as "in_app" | "email")} className="w-full" disabled={!allowed}>
            <option value="in_app">{tx("In the app", "بالتطبيق")}</option>
            <option value="email">{tx("In the app + by email", "بالتطبيق + بالإيميل")}</option>
          </Select>
        </Field>
        <span title={!allowed ? noPerm : undefined} className="block">
          <Button type="submit" className="w-full" loading={add.isPending} disabled={!allowed || !valid}>{tx("Add alert", "ضيف التنبيه")}</Button>
        </span>
        {!allowed && <p className="text-[12px] text-ink-3">{noPerm}.</p>}
      </form>
    </Section>
  );
}
