"use client";
import { Suspense } from "react";
import { Plus } from "lucide-react";
import { useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { num } from "@/lib/format";
import { AskIdrak, ErrorBox, PageHeader, useName } from "@/components/app/kit";
import { Badge, Card, Empty, Skeleton, Tabs } from "@/components/ui";
import { PageSkeleton, ShareBar, oneOf, useParamState } from "@/components/insights/common";
import type { Pair } from "@/components/insights/types";

const WINDOWS = ["30", "60", "90"] as const;

export default function BasketPage() {
  return <Suspense fallback={<PageSkeleton />}><BasketScreen /></Suspense>;
}

function BasketScreen() {
  const tx = useTx();
  const nm = useName();
  const [dRaw, setDays] = useParamState("days", "60");
  const days = oneOf(dRaw, WINDOWS, "60");
  const q = useApiQuery<{ pairs: Pair[] }>(`/insights/basket?days=${days}`);
  const pairs = q.data?.pairs;
  const maxLift = Math.max(1, ...(pairs || []).map((p) => p.lift));

  const idea = (p: Pair) => {
    const a = nm(p.a_name, p.a_name_ar), b = nm(p.b_name, p.b_name_ar);
    if (p.lift >= 3) return tx(`Make a bundle: “${a} + ${b}” at a small discount — they're strongly linked.`, `اعمل عرض «${a} + ${b}» بخصم بسيط — مرتبطين ببعض كثير.`);
    if (p.lift >= 1.6) return tx(`Shelf ${b} next to ${a}, or suggest it at the cashier.`, `حط ${b} جنب ${a} عالرف، أو خلّي الكاشير يقترحه.`);
    return tx(`Mild link — try them together in a weekend flyer.`, `ارتباط خفيف — جرّبهم مع بعض بعرض نهاية الأسبوع.`);
  };

  return (
    <div>
      <PageHeader
        eyebrow={tx("Basket analysis", "تحليل السلة")}
        title={tx("Bought together", "بيننباعوا مع بعض")}
        subtitle={tx("Pairs of products that land in the same receipt more often than chance — use them for bundles and shelf placement.",
          "أصناف بتيجي بنفس الفاتورة أكثر من الطبيعي — استغلها بالعروض وترتيب الرفوف.")}
        actions={<>
          <Tabs value={days} onChange={(v) => setDays(v)} items={WINDOWS.map((w) => ({ value: w, label: tx(`${w} days`, `${w} يوم`) }))} />
          <AskIdrak q={tx("Suggest 3 bundle offers from the products my customers buy together, with a price for each.", "اقترحلي 3 عروض مجمّعة من الأصناف اللي بيشتروها الزباين مع بعض، مع سعر لكل عرض.")} />
        </>}
      />

      {q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : (
        <div data-basira="basket-pairs">
          {!pairs ? (
            <div className="grid gap-4 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <Card key={i} className="p-5"><Skeleton className="h-5 w-3/4" /><Skeleton className="mt-4 h-3 w-full" /><Skeleton className="mt-3 h-3 w-1/2" /></Card>)}</div>
          ) : !pairs.length ? (
            <Card><Empty title={tx("No strong pairs yet", "ما في أزواج واضحة لسّا")} body={tx("We need at least 25 receipts with the same two items. Try a longer window.", "بنحتاج 25 فاتورة عالأقل فيها نفس الصنفين. جرّب فترة أطول.")} /></Card>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                {pairs.map((p, i) => (
                  <Card key={`${p.a_name}-${p.b_name}`} className="flex flex-col p-5">
                    <div className="flex items-start justify-between gap-3">
                      <p className="min-w-0 font-serif text-[16.5px] leading-snug text-ink">
                        {nm(p.a_name, p.a_name_ar)}
                        <Plus size={14} className="mx-1.5 inline align-middle text-terra" />
                        {nm(p.b_name, p.b_name_ar)}
                      </p>
                      {i < 3 && <Badge tone="terra">{tx("Top pick", "الأقوى")}</Badge>}
                    </div>
                    <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
                      <div className="rounded-lg bg-paper-2 px-2 py-2">
                        <dt className="text-[11px] text-ink-3">{tx("Together", "مع بعض")}</dt>
                        <dd className="num font-serif text-[18px] text-ink">{num(p.together)}</dd>
                      </div>
                      <div className="rounded-lg bg-paper-2 px-2 py-2">
                        <dt className="text-[11px] text-ink-3">{tx("Also buy", "بيشتروه كمان")}</dt>
                        <dd className="num font-serif text-[18px] text-ink">{num(p.conf_ab, 1)}%</dd>
                      </div>
                      <div className="rounded-lg bg-paper-2 px-2 py-2">
                        <dt className="text-[11px] text-ink-3">{tx("Lift", "قوة الارتباط")}</dt>
                        <dd className="num font-serif text-[18px] text-ink">×{num(p.lift, 2)}</dd>
                      </div>
                    </dl>
                    <ShareBar className="mt-3" value={(100 * p.lift) / maxLift} tone="olive" />
                    <p className="mt-3 text-[12.5px] text-ink-3">
                      {tx(`${num(p.conf_ab, 1)}% of receipts with ${nm(p.a_name, p.a_name_ar)} also had ${nm(p.b_name, p.b_name_ar)}.`,
                        `${num(p.conf_ab, 1)}% من الفواتير اللي فيها ${nm(p.a_name, p.a_name_ar)} كان فيها كمان ${nm(p.b_name, p.b_name_ar)}.`)}
                    </p>
                    <p className="mt-2 rounded-lg bg-olive-soft/60 px-3 py-2 text-[13px] text-ink"><span className="font-medium text-olive">{tx("Idea: ", "فكرة: ")}</span>{idea(p)}</p>
                  </Card>
                ))}
              </div>
              <p className="mt-5 text-[12px] text-ink-3">
                {tx("Lift ×2 means the pair appears together twice as often as if customers picked items at random. Above ×1.5 is worth acting on.",
                  "قوة ×2 يعني الصنفين بيجوا مع بعض ضعف ما لو الزباين بيختاروا عشوائي. فوق ×1.5 بيستاهل تعمل عليه إشي.")}
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
