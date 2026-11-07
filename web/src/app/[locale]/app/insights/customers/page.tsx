"use client";
import { MessageCircle } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { date, jd, num, pct } from "@/lib/format";
import { toast } from "@/components/ui/toast";
import { AskIdrak, ErrorBox, LinkCell, Money, N, PageHeader, Section, Table, useName } from "@/components/app/kit";
import { useSession } from "@/components/app/session";
import { Badge, Button, Card, Skeleton } from "@/components/ui";
import { ShareBar, copyText } from "@/components/insights/common";
import type { Rfm, RfmCustomer } from "@/components/insights/types";

const SEG: Record<string, { tone: "olive" | "terra" | "saffron" | "sky" | "neutral" | "danger"; whoEn: string; whoAr: string; doEn: string; doAr: string }> = {
  champions: { tone: "olive", whoEn: "Visit often, spend the most, came recently.", whoAr: "بيجوا كثير، بيصرفوا أكثر إشي، وآخر زيارة قريبة.",
    doEn: "Thank them — early access to Ramadan offers, a small loyalty gift.", doAr: "اشكرهم — عروض رمضان قبل غيرهم، أو هدية ولاء صغيرة." },
  loyal: { tone: "sky", whoEn: "Come regularly with a steady basket.", whoAr: "بيجوا بانتظام وسلّتهم ثابتة.",
    doEn: "Suggest bundles to grow the basket (see “Bought together”).", doAr: "اقترح عليهم عروض مجمّعة تكبّر السلة (شوف «بيننباعوا مع بعض»)." },
  at_risk: { tone: "danger", whoEn: "Used to be regulars, haven't been back lately.", whoAr: "كانوا زباين دايمين، وصارلهم فترة ما إجوا.",
    doEn: "Send a personal win-back message this week.", doAr: "ابعثلهم رسالة شخصية ترجّعهم هالأسبوع." },
  new: { tone: "saffron", whoEn: "First few visits.", whoAr: "أول كم زيارة إلهم.",
    doEn: "Make the second visit easy — a welcome offer.", doAr: "سهّل عليهم الزيارة الثانية — عرض ترحيبي." },
  regular: { tone: "neutral", whoEn: "Occasional shoppers.", whoAr: "بيتسوقوا من وقت لوقت.",
    doEn: "Keep them in your weekly offers.", doAr: "خلّيهم ضمن عروضك الأسبوعية." },
  lost: { tone: "neutral", whoEn: "No visit in more than 75 days.", whoAr: "ما إجوا من أكثر من 75 يوم.",
    doEn: "One last offer; don't spend much here.", doAr: "عرض أخير، وما تصرف عليهم كثير." },
};

export default function CustomerInsightsPage() {
  const tx = useTx();
  const locale = useLocale();
  const nm = useName();
  const { org } = useSession();
  const q = useApiQuery<Rfm>("/insights/customers");
  const d = q.data;
  const totalRev = d?.segments.reduce((a, s) => a + s.revenue, 0) || 1;
  const totalCount = d?.segments.reduce((a, s) => a + s.count, 0) || 0;
  const riskValue = d?.at_risk.reduce((a, c) => a + (c.monetary || 0), 0) || 0;
  const shop = org ? (tx.isAr ? org.name_ar || org.name : org.name) : tx("our shop", "محلنا");

  const winBack = async (c: RfmCustomer) => {
    const first = (tx.isAr ? c.full_name_ar || c.full_name : c.full_name || c.full_name_ar || "").split(" ")[0];
    const msg = tx(
      `Hi ${first}, we've missed you at ${shop}! It's been a while since your last visit — show this message at the cashier this week and get 10% off your basket. See you soon.`,
      `مرحبا ${first}، اشتقنالك بـ${shop}! صارلك فترة ما مرّيت علينا — فرجي هالرسالة عالكاشير هالأسبوع وخذ خصم 10% على مشترياتك. بنستناك.`,
    );
    const ok = await copyText(msg);
    toast(ok ? tx("Message copied", "انسخت الرسالة") : tx("Couldn't copy", "ما قدرنا ننسخ"),
      ok ? tx(`Paste it in WhatsApp to ${c.phone || first}. Nothing was sent.`, `الصقها بالواتساب لـ ${c.phone || first}. ما انبعت إشي.`) : msg, ok ? "ok" : "error");
  };

  return (
    <div>
      <PageHeader
        eyebrow={tx("Customer insights", "تحليل الزبائن")}
        title={tx("Who your customers are", "مين زباينك")}
        subtitle={tx("Customers grouped by how recently, how often and how much they buy (last 180 days) — so you know whom to thank and whom to win back.",
          "الزباين مقسّمين حسب آخر زيارة، وكم مرة بيجوا، وقدّيش بيصرفوا (آخر 180 يوم) — عشان تعرف مين تشكر ومين ترجّع.")}
        actions={<AskIdrak q={tx("Which customers am I about to lose, and what should I offer them to come back?", "مين الزباين اللي رح أخسرهم، وشو أعرض عليهم عشان يرجعوا؟")} />}
      />
      {q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : (
        <>
          <div data-basira="rfm-segments" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {!d ? [0, 1, 2].map((i) => <Card key={i} className="p-5"><Skeleton className="h-4 w-24" /><Skeleton className="mt-3 h-8 w-32" /><Skeleton className="mt-3 h-3 w-full" /></Card>) :
              !d.segments.length ? <Card className="p-6 text-sm text-ink-3 sm:col-span-2 lg:col-span-3">{tx("No customer purchases linked yet. Link sales to customers (phone or loyalty card) to see segments.", "ما في مبيعات مربوطة بزباين لسّا. اربط المبيعات بالزبون (رقم تلفون أو بطاقة ولاء) لتشوف التقسيم.")}</Card> :
                d.segments.map((s) => {
                  const m = SEG[s.key] || SEG.regular;
                  const share = (100 * s.revenue) / totalRev;
                  return (
                    <Card key={s.key} className="flex flex-col p-5">
                      <div className="flex items-center justify-between gap-2">
                        <Badge tone={m.tone}>{tx(s.en, s.ar)}</Badge>
                        <span className="text-[12px] text-ink-3"><span className="num">{pct(totalCount ? (100 * s.count) / totalCount : 0, 0)}</span> {tx("of customers", "من الزباين")}</span>
                      </div>
                      <p className="mt-3 flex items-baseline gap-2"><span className="num font-serif text-[28px] leading-none text-ink">{num(s.count)}</span><span className="text-[13px] text-ink-3">{tx("customers", "زبون")}</span></p>
                      <p className="mt-1 text-[13px] text-ink-2"><Money v={s.revenue} decimals={0} /> · <span className="num">{pct(share, 0)}</span> {tx("of known-customer sales", "من مبيعات الزباين المعروفين")}</p>
                      <ShareBar className="mt-2" value={share} tone={m.tone === "danger" ? "terra" : m.tone === "olive" ? "olive" : m.tone === "sky" ? "sky" : "saffron"} />
                      <p className="mt-3 text-[12.5px] text-ink-3">{tx(m.whoEn, m.whoAr)}</p>
                      <p className="mt-1 text-[12.5px] text-ink"><span className="font-medium text-olive">{tx("Do: ", "اعمل: ")}</span>{tx(m.doEn, m.doAr)}</p>
                    </Card>
                  );
                })}
          </div>

          <Section id="at-risk-list" className="mt-5" bodyClass="p-0" title={tx("Regulars you're about to lose", "زباين دايمين قرّبت تخسرهم")}
            subtitle={d ? tx(`${d.at_risk.length} customers who spent ${jd(riskValue, locale, { decimals: 0 })} in the last 180 days but stopped coming`,
              `${d.at_risk.length} زبون صرفوا ${jd(riskValue, locale, { decimals: 0 })} آخر 180 يوم وبطّلوا ييجوا`) : undefined}>
            <Table rows={d?.at_risk} rowKey={(r) => r.id} empty={tx("No at-risk regulars right now", "ما في زباين معرّضين للخسارة هلأ")} cols={[
              { key: "name", label: tx("Customer", "الزبون"), render: (r) => (
                <div className="min-w-[140px]">
                  <LinkCell href={`/${locale}/app/customers/${r.id}`}>{nm(r.full_name, r.full_name_ar)}</LinkCell>
                  <p className="text-[12px] text-ink-3">{r.area || ""}{r.phone ? <span className="num" dir="ltr"> · {r.phone}</span> : null}</p>
                </div>) },
              { key: "recency", label: tx("Last visit", "آخر زيارة"), render: (r) => (
                <span><span className="num font-medium text-danger">{r.recency_days}</span> <span className="text-ink-3">{tx("days ago", "يوم")}</span>
                  <span className="num block text-[11.5px] text-ink-3">{date(r.last_visit, locale)}</span></span>) },
              { key: "freq", label: tx("Visits (180d)", "زيارات (180 يوم)"), align: "end", render: (r) => <N v={r.freq} /> },
              { key: "monetary", label: tx("Spent (180d)", "صرف (180 يوم)"), align: "end", render: (r) => <Money v={r.monetary} decimals={0} /> },
              { key: "lifetime", label: tx("Lifetime", "من البداية"), align: "end", className: "hidden md:table-cell", render: (r) => <Money v={r.lifetime} decimals={0} /> },
              { key: "act", label: "", align: "end", render: (r) => (
                <Button size="sm" variant="secondary" onClick={() => winBack(r)} title={tx("Copies a WhatsApp-style message — nothing is sent", "بينسخ رسالة واتساب — ما بيبعت إشي")}>
                  <MessageCircle size={14} />{tx("Win back", "رجّعه")}
                </Button>) },
            ]} />
          </Section>

          <Section className="mt-5" bodyClass="p-0" title={tx("Your best customers", "أحسن زباينك")} subtitle={tx("Top 10 by spend in the last 180 days", "أعلى 10 بالصرف آخر 180 يوم")}>
            <Table dense rows={d?.customers.slice(0, 10)} rowKey={(r) => r.id} cols={[
              { key: "name", label: tx("Customer", "الزبون"), render: (r) => <LinkCell href={`/${locale}/app/customers/${r.id}`}>{nm(r.full_name, r.full_name_ar)}</LinkCell> },
              { key: "segment", label: tx("Segment", "الفئة"), render: (r) => {
                const s = d?.segments.find((x) => x.key === r.segment);
                return <Badge tone={(SEG[r.segment] || SEG.regular).tone}>{s ? tx(s.en, s.ar) : r.segment}</Badge>;
              } },
              { key: "freq", label: tx("Visits", "زيارات"), align: "end", render: (r) => <N v={r.freq} /> },
              { key: "monetary", label: tx("Spent", "صرف"), align: "end", render: (r) => <Money v={r.monetary} decimals={0} /> },
              { key: "basket", label: tx("Avg basket", "متوسط السلة"), align: "end", className: "hidden sm:table-cell", render: (r) => <Money v={r.freq ? r.monetary / r.freq : 0} decimals={2} /> },
            ]} />
          </Section>
        </>
      )}
    </div>
  );
}
