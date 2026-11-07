"use client";
import { useState } from "react";
import clsx from "clsx";
import { ArrowLeft, ArrowRight, BadgePercent, CalendarClock, ChevronDown, PackageX, ScanSearch, TrendingUp, Truck, UserRoundX } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { date, jd, num, pct } from "@/lib/format";
import { AskIdrak, ErrorBox, LinkCell, Money, N, PageHeader, Table, type Col, useName } from "@/components/app/kit";
import { Badge, Button, Card, Empty, Skeleton } from "@/components/ui";
import { SeverityBadge, ShareBar } from "@/components/insights/common";
import type { Leak, LeakItem, LeakKind, Leaks } from "@/components/insights/types";

const ONE_OFF: LeakKind[] = ["dead_stock", "expiring"];

const KIND: Record<LeakKind, { en: string; ar: string; icon: React.ComponentType<{ size?: number; className?: string }>; doEn: string; doAr: string; fixEn: string; fixAr: string }> = {
  dead_stock: { en: "Dead stock", ar: "بضاعة راكدة", icon: PackageX, fixEn: "See dead stock", fixAr: "شوف البضاعة الراكدة",
    doEn: "Pick the 3 most expensive items and run a bundle or clearance this week. Stop re-ordering them until they move.",
    doAr: "اختار أغلى 3 أصناف واعمل عليهم عرض أو تصفية هالأسبوع، ووقّف طلبهم لحتى يمشوا." },
  below_cost: { en: "Sold below cost", ar: "بيع بأقل من التكلفة", icon: BadgePercent, fixEn: "Fix prices", fixAr: "عدّل الأسعار",
    doEn: "Update the shelf price to at least cost + your usual margin, or ask the supplier to hold the old cost.",
    doAr: "عدّل سعر الرف ليكون عالأقل التكلفة + هامشك المعتاد، أو اطلب من المورد يرجع للسعر القديم." },
  cashier_anomaly: { en: "Cashier discounts & voids", ar: "خصومات وإلغاءات الكاشير", icon: UserRoundX, fixEn: "Review cashier", fixAr: "راجع الكاشير",
    doEn: "Review the discounted and voided receipts with the cashier, and require manager approval above a set discount.",
    doAr: "راجع الفواتير المخصومة والملغية مع الكاشير، وخلّي أي خصم فوق حد معيّن يحتاج موافقة المدير." },
  shrinkage: { en: "Missing stock", ar: "بضاعة مفقودة", icon: ScanSearch, fixEn: "Open branch", fixAr: "افتح الفرع",
    doEn: "Do a spot count of the listed items this week and move small high-value items closer to the cashier.",
    doAr: "اعمل جرد سريع للأصناف المذكورة هالأسبوع، وقرّب الأصناف الصغيرة الغالية من الكاشير." },
  expiring: { en: "Expiring soon", ar: "قرب تنتهي صلاحيته", icon: CalendarClock, fixEn: "See expiring items", fixAr: "شوف الأصناف",
    doEn: "Move these to the front shelf, bundle them, or call the supplier for a swap before the date passes.",
    doAr: "قدّمها عالرف، اعمل عليها عرض، أو اتصل بالمورد يبدّلها قبل ما يخلص التاريخ." },
  supplier_price: { en: "Supplier price rise", ar: "المورد رفع السعر", icon: Truck, fixEn: "Open supplier", fixAr: "افتح المورد",
    doEn: "Get a quote from a second distributor and use it to negotiate before your next order.",
    doAr: "خذ عرض سعر من موزع ثاني وفاوض فيه قبل الطلبية الجاية." },
  stockout: { en: "Best sellers out of stock", ar: "أصناف مطلوبة خلصت", icon: TrendingUp, fixEn: "Reorder now", fixAr: "اطلب هلأ",
    doEn: "Send the purchase orders from the reorder planner today — every day out of stock is lost sales.",
    doAr: "ابعث الطلبيات من مخطط الطلبيات اليوم — كل يوم الصنف مش موجود هو مبيعات ضايعة." },
};

export default function LeaksPage() {
  const tx = useTx();
  const q = useApiQuery<Leaks>("/insights/leaks");
  const d = q.data;
  const items = d ? [...d.items].sort((a, b) => (b.amount_jod || 0) - (a.amount_jod || 0)) : undefined;
  const seen: Record<string, number> = {};

  return (
    <div>
      <PageHeader
        eyebrow={tx("Money leak detector", "كاشف التسريب")}
        title={tx("Where you're losing money", "وين عم تخسر مصاري")}
        subtitle={tx("Every finding comes with a JD figure and one clear thing to do — start with the biggest.", "كل مشكلة إلها رقم بالدينار وخطوة وحدة واضحة — ابدأ بالأكبر.")}
        actions={<AskIdrak q={tx("Where am I losing money? Which leak should I fix first and how exactly?", "وين عم أخسر مصاري؟ أي تسريب لازم أصلّح أول وكيف بالضبط؟")} />}
      />
      {q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : (
        <>
          <Total d={d} />
          <div className="mt-6 space-y-4">
            {!items ? [0, 1, 2].map((i) => <Card key={i} className="p-5"><Skeleton className="h-4 w-40" /><Skeleton className="mt-3 h-6 w-3/4" /><Skeleton className="mt-3 h-4 w-1/2" /></Card>) :
              !items.length ? (
                <Card><Empty title={tx("No leaks found — nice work", "ما لقينا تسريب — يعطيك العافية")} body={tx("We check again every few minutes as new sales come in.", "منرجع نفحص كل كم دقيقة مع كل مبيعات جديدة.")} /></Card>
              ) : items.map((l, i) => {
                seen[l.kind] = (seen[l.kind] || 0) + 1;
                const id = seen[l.kind] === 1 ? `leak-${l.kind}` : `leak-${l.kind}-${seen[l.kind]}`;
                return <LeakCard key={`${l.kind}-${i}`} l={l} id={id} defaultOpen={false} />;
              })}
          </div>
          <p className="mt-6 text-[12px] text-ink-3">
            {tx("Monthly figures are estimates from the last 60–90 days of sales, purchases and stock counts. Tied-up amounts are stock value at cost.",
              "الأرقام الشهرية تقديرية من آخر 60–90 يوم مبيعات ومشتريات وجرد. المبالغ العالقة هي قيمة البضاعة بسعر التكلفة.")}
          </p>
        </>
      )}
    </div>
  );
}

function Total({ d }: { d?: Leaks }) {
  const tx = useTx();
  const locale = useLocale();
  if (!d) return <Card className="p-6"><Skeleton className="h-4 w-48" /><Skeleton className="mt-4 h-10 w-80 max-w-full" /></Card>;
  const monthly = d.items.filter((i) => !ONE_OFF.includes(i.kind));
  const byKind = Object.entries(monthly.reduce<Record<string, number>>((a, i) => ({ ...a, [i.kind]: (a[i.kind] || 0) + (i.amount_jod || 0) }), {})).sort((a, b) => b[1] - a[1]);
  return (
    <Card data-basira="leaks-total" className="overflow-hidden">
      <div className="grid gap-0 md:grid-cols-[1.4fr_1fr]">
        <div className="border-b border-line/70 p-6 md:border-b-0 md:border-e">
          <p className="text-[13px] text-ink-3">{tx("Leaking every month (estimate)", "عم يتسرّب كل شهر (تقديري)")}</p>
          <p className="mt-2 font-serif text-[40px] leading-none text-danger sm:text-[46px]">
            ≈ <Money v={d.total_monthly} decimals={0} />
            <span className="ms-2 font-sans text-[15px] text-ink-3">{tx("/ month", "بالشهر")}</span>
          </p>
          <p className="mt-3 text-[14px] text-ink-2">
            {tx("plus ", "وكمان ")}<Money v={d.tied_up} decimals={0} className="font-medium text-ink" />
            {tx(" tied up in stock that isn't moving or is about to expire.", " عالقة ببضاعة ما بتتحرك أو قربت تنتهي صلاحيتها.")}
          </p>
          <p className="mt-1 text-[13px] text-ink-3">
            {tx(`That's about ${jd(d.total_monthly * 12, locale, { decimals: 0 })} a year if nothing changes.`, `يعني تقريباً ${jd(d.total_monthly * 12, locale, { decimals: 0 })} بالسنة إذا ضل الوضع هيك.`)}
          </p>
        </div>
        <div className="p-6">
          <p className="mb-3 text-[13px] text-ink-3">{tx(`${d.items.length} findings · monthly leak by type`, `${d.items.length} ملاحظة · التسريب الشهري حسب النوع`)}</p>
          {byKind.length ? (
            <ul className="space-y-3">
              {byKind.map(([k, v]) => (
                <li key={k}>
                  <div className="flex justify-between text-[13px]"><span className="text-ink-2">{KIND[k as LeakKind] ? tx(KIND[k as LeakKind].en, KIND[k as LeakKind].ar) : k}</span><Money v={v} decimals={0} className="text-ink" /></div>
                  <ShareBar className="mt-1" value={(100 * v) / (d.total_monthly || 1)} tone="terra" />
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-ink-3">{tx("No recurring leaks.", "ما في تسريب شهري.")}</p>}
        </div>
      </div>
    </Card>
  );
}

function LeakCard({ l, id, defaultOpen }: { l: Leak; id: string; defaultOpen: boolean }) {
  const tx = useTx();
  const locale = useLocale();
  const [open, setOpen] = useState(defaultOpen);
  const k = KIND[l.kind] || { en: l.kind, ar: l.kind, icon: ScanSearch, doEn: "", doAr: "", fixEn: "Open", fixAr: "افتح" };
  const oneOff = ONE_OFF.includes(l.kind);
  const Arrow = locale === "ar" ? ArrowLeft : ArrowRight;
  const Icon = k.icon;
  return (
    <Card data-basira={id} className="overflow-hidden">
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start">
        <div className={clsx("grid size-10 shrink-0 place-items-center rounded-full", l.severity === "high" ? "bg-[#f6d9d3] text-danger" : "bg-saffron-soft text-[#8a5d0e]")}>
          <Icon size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12px] font-medium uppercase tracking-[.1em] text-ink-3">{tx(k.en, k.ar)}</span>
            <SeverityBadge s={l.severity} />
          </div>
          <h3 className="mt-1.5 font-serif text-[18px] leading-snug text-ink">{tx(l.title, l.title_ar)}</h3>
          <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-2">{tx(l.body, l.body_ar)}</p>
          {k.doEn && (
            <p className="mt-3 rounded-lg bg-paper-2 px-3.5 py-2.5 text-[13px] text-ink">
              <span className="font-medium text-olive">{tx("Do this: ", "اعمل هيك: ")}</span>{tx(k.doEn, k.doAr)}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-row items-center justify-between gap-3 sm:flex-col sm:items-end">
          <div className="sm:text-end">
            <Money v={l.amount_jod} decimals={0} className="font-serif text-[26px] leading-none text-ink" />
            <p className="mt-1 text-[12px] text-ink-3">{oneOff ? tx("tied up (one-off)", "عالقة (مرة وحدة)") : tx("per month", "بالشهر")}</p>
          </div>
          <Button size="sm" href={`/${locale}${l.link}`}>{tx(k.fixEn, k.fixAr)}<Arrow size={14} /></Button>
        </div>
      </div>
      {!!l.items?.length && (
        <div className="border-t border-line/70">
          <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
            className="flex w-full items-center justify-between px-5 py-2.5 text-[13px] text-ink-2 hover:bg-paper-2">
            <span>{open ? tx("Hide details", "خبّي التفاصيل") : tx(`Show the ${l.items.length} ${l.items.length === 1 ? "item" : "items"} behind this`, `اعرض التفاصيل (${l.items.length})`)}</span>
            <ChevronDown size={15} className={clsx("transition-transform", open && "rotate-180")} />
          </button>
          {open && <div className="border-t border-line/60"><Items l={l} /></div>}
        </div>
      )}
    </Card>
  );
}

function Items({ l }: { l: Leak }) {
  const tx = useTx();
  const locale = useLocale();
  const nm = useName();
  const s = (v: unknown) => (v === null || v === undefined ? "" : String(v));
  const n = (v: unknown) => (typeof v === "number" ? v : v === null || v === undefined ? null : Number(v));
  const product: Col<LeakItem> = {
    key: "name", label: tx("Item", "الصنف"),
    render: (r) => (r.id ? <LinkCell href={`/${locale}/app/products/${r.id}`}>{nm(s(r.name), s(r.name_ar))}</LinkCell> : <span className="text-ink">{nm(s(r.name), s(r.name_ar))}</span>),
  };
  const money = (key: string, label: string): Col<LeakItem> => ({ key, label, align: "end", render: (r) => <Money v={n(r[key])} /> });
  const qty = (key: string, label: string, d = 0): Col<LeakItem> => ({ key, label, align: "end", render: (r) => <N v={n(r[key])} d={d} /> });
  const text = (key: string, label: string): Col<LeakItem> => ({ key, label, render: (r) => <span className="text-ink-2">{s(r[key]) || "—"}</span> });
  const cols: Record<LeakKind, Col<LeakItem>[]> = {
    dead_stock: [product, qty("stock", tx("In stock", "بالمخزون")), qty("sold60", tx("Sold in 60 days", "انباع آخر 60 يوم")), money("value", tx("Value at cost", "القيمة بالتكلفة"))],
    below_cost: [product, money("cost", tx("Cost", "التكلفة")), money("price", tx("Price", "سعر البيع")), money("loss_90d", tx("Lost in 90 days", "الخسارة آخر 90 يوم")),
      { key: "since", label: tx("Since", "من"), render: (r) => <span className="num text-ink-2">{date(s(r.since), locale)}</span> }],
    cashier_anomaly: [{ key: "name", label: tx("Cashier", "الكاشير"), render: (r) => <LinkCell href={`/${locale}/app/employees?highlight=${s(r.employee_id)}`}>{s(r.name)}</LinkCell> },
      { key: "discount_rate", label: tx("Discount rate", "نسبة الخصم"), align: "end", render: (r) => <span className="num font-medium text-danger">{pct(n(r.discount_rate), 2)}</span> },
      { key: "peer_rate", label: tx("Others", "الباقي"), align: "end", render: (r) => <span className="num">{pct(n(r.peer_rate), 2)}</span> },
      qty("voids", tx("Voids", "الإلغاءات")),
      { key: "void_rate", label: tx("Void rate", "نسبة الإلغاء"), align: "end", render: (r) => <span className="num">{pct(n(r.void_rate), 2)}</span> },
      money("excess_90d", tx("Excess in 90 days", "الزيادة آخر 90 يوم"))],
    shrinkage: [product, text("category", tx("Category", "القسم")), qty("expected", tx("Expected", "المفروض")), qty("actual", tx("Counted", "الموجود")), money("loss", tx("Missing value", "قيمة المفقود"))],
    expiring: [product, text("branch", tx("Branch", "الفرع")), qty("quantity", tx("Qty", "الكمية")),
      { key: "expiry_date", label: tx("Expires", "تنتهي"), render: (r) => {
        const past = s(r.expiry_date) < new Date().toISOString().slice(0, 10);
        return <span className={clsx("num", past ? "font-medium text-danger" : "text-ink-2")}>{date(s(r.expiry_date), locale)}{past && <Badge tone="danger" className="ms-2">{tx("expired", "منتهي")}</Badge>}</span>;
      } },
      money("value", tx("Value at cost", "القيمة بالتكلفة"))],
    supplier_price: [{ key: "name", label: tx("Supplier", "المورد"), render: (r) => <LinkCell href={`/${locale}/app/suppliers/${s(r.supplier_id)}`}>{s(r.name)}</LinkCell> },
      { key: "pct", label: tx("Average rise", "متوسط الزيادة"), align: "end", render: (r) => <span className="num font-medium text-danger">+{num(n(r.pct), 1)}%</span> },
      money("extra_45d", tx("Extra paid in 45 days", "زيادة الدفع آخر 45 يوم"))],
    stockout: [product, text("branch", tx("Branch", "الفرع")), money("daily_sales", tx("Sales lost per day", "مبيعات ضايعة باليوم"))],
  };
  return <Table dense rows={l.items} cols={cols[l.kind] || [product]} rowKey={(_r, i) => String(i)} />;
}
