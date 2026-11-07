"use client";
import { Suspense, useState } from "react";
import clsx from "clsx";
import { Check, ChevronDown, Mail, Moon, Send } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { useApiMutation, useApiQuery } from "@/lib/useApi";
import { num } from "@/lib/format";
import { toast } from "@/components/ui/toast";
import { AskIdrak, ErrorBox, LinkCell, Money, N, PageHeader, Stat, StatSkeleton, useName } from "@/components/app/kit";
import { useSession } from "@/components/app/session";
import { Badge, Button, Card, Empty, Input, Skeleton, Tabs } from "@/components/ui";
import { PageSkeleton, oneOf, useParamState } from "@/components/insights/common";
import type { POResult, Reorder, ReorderGroup, ReorderLine, Urgency } from "@/components/insights/types";

const COVERS = ["7", "14", "21", "30"] as const;
type Edit = { qty: number; on: boolean };
const lineKey = (l: ReorderLine) => `${l.product_id}|${l.branch_id}`;

export default function ReorderPage() {
  return <Suspense fallback={<PageSkeleton />}><ReorderScreen /></Suspense>;
}

function ReorderScreen() {
  const tx = useTx();
  const [cRaw, setCover] = useParamState("cover_days", "14");
  const cover = oneOf(cRaw, COVERS, "14");
  const q = useApiQuery<Reorder>(`/insights/reorder?cover_days=${cover}`);
  const d = q.data;

  return (
    <div>
      <PageHeader
        eyebrow={tx("Reorder planner", "مخطط الطلبيات")}
        title={tx("What to order, from whom", "شو تطلب، ومن مين")}
        subtitle={tx("Suggested quantities per supplier based on how fast each item sells at each branch. Adjust, then send the PO by email.",
          "كميات مقترحة لكل مورد حسب سرعة بيع كل صنف بكل فرع. عدّل اللي بدك، وابعث الطلبية بالإيميل.")}
        actions={<AskIdrak q={tx("Which purchase orders are most urgent today, and is anything I'm ordering too much of?", "أي طلبيات أكثر استعجال اليوم، وفي إشي عم أطلب منه زيادة عن اللزوم؟")} />}
      />

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <span className="text-[13px] text-ink-2">{tx("Order enough for", "اطلب كمية تكفي")}</span>
        <div data-basira="reorder-cover-days">
          <Tabs value={cover} onChange={(v) => setCover(v)} items={COVERS.map((c) => ({ value: c, label: tx(`${c} days`, `${c} يوم`) }))} />
        </div>
      </div>

      {q.error ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : (
        <>
          <div data-basira="reorder-summary" className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            {!d ? [0, 1, 2, 3].map((i) => <StatSkeleton key={i} />) : (<>
              <Stat tone="terra" label={tx("Suggested order value", "قيمة الطلبيات المقترحة")} value={<Money v={d.total} />} hint={tx("at cost", "بسعر التكلفة")} />
              <Stat label={tx("Items to order", "أصناف للطلب")} value={<N v={d.lines} />} hint={tx(`from ${d.groups.length} suppliers`, `من ${d.groups.length} مورد`)} />
              <Stat label={tx("Critical", "عاجلة")} value={<span className={d.critical ? "text-danger" : ""}><N v={d.critical} /></span>} hint={tx("out of stock or < 2 days left", "خلصت أو باقي أقل من يومين")} />
              <Card className="relative overflow-hidden px-5 py-4">
                <span className="absolute inset-y-0 start-0 w-1 bg-saffron" />
                <p className="flex items-center gap-1.5 text-[12.5px] text-ink-3"><Moon size={13} className="text-saffron" />{tx("Ramadan", "رمضان")}</p>
                <p className="mt-1.5 font-serif text-[26px] leading-none text-ink">{d.ramadan_in_days < 999 ? <>{tx("in ", "بعد ")}<span className="num">{d.ramadan_in_days}</span>{tx(" days", " يوم")}</> : "—"}</p>
                <p className="mt-1.5 text-[12px] text-ink-3">{d.ramadan_in_days <= 45 ? tx("Order Ramadan items early this round", "اطلب أصناف رمضان بكير هالمرة") : tx("Normal ordering for now", "طلب عادي هلأ")}</p>
              </Card>
            </>)}
          </div>

          <div data-basira="reorder-suppliers" className="mt-6 space-y-4">
            {!d ? [0, 1].map((i) => <Card key={i} className="p-5"><Skeleton className="h-5 w-56" /><Skeleton className="mt-4 h-24 w-full" /></Card>) :
              !d.groups.length ? <Card><Empty title={tx("Nothing to order right now", "ما في إشي لازم ينطلب هلأ")} body={tx("Stock covers the chosen period at every branch.", "المخزون بكفي للفترة المختارة بكل الفروع.")} /></Card> :
                <Groups key={cover} groups={d.groups} />}
          </div>
        </>
      )}
    </div>
  );
}

function Groups({ groups }: { groups: ReorderGroup[] }) {
  const [edits, setEdits] = useState<Record<string, Edit>>({});
  const [sent, setSent] = useState<Record<string, string[]>>({});
  return (
    <>
      {groups.map((g, i) => (
        <SupplierCard key={g.supplier_id || `none-${i}`} g={g} first={i === 0} defaultOpen={i < 3} edits={edits}
          setEdit={(k, e) => setEdits((s) => ({ ...s, [k]: e }))} sent={g.supplier_id ? sent[g.supplier_id] : undefined}
          onSent={(pos) => g.supplier_id && setSent((s) => ({ ...s, [g.supplier_id as string]: pos }))} />
      ))}
    </>
  );
}

function UrgencyBadge({ u }: { u: Urgency }) {
  const tx = useTx();
  if (u === "critical") return <Badge tone="danger">{tx("Critical", "عاجل")}</Badge>;
  if (u === "soon") return <Badge tone="saffron">{tx("Soon", "قريباً")}</Badge>;
  return <Badge tone="neutral">{tx("Planned", "مخطط")}</Badge>;
}

function SupplierCard({ g, first, defaultOpen, edits, setEdit, sent, onSent }: {
  g: ReorderGroup; first: boolean; defaultOpen: boolean; edits: Record<string, Edit>; setEdit: (k: string, e: Edit) => void; sent?: string[]; onSent: (pos: string[]) => void;
}) {
  const tx = useTx();
  const locale = useLocale();
  const nm = useName();
  const { can } = useSession();
  const [open, setOpen] = useState(defaultOpen);
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState(false);
  const get = (l: ReorderLine): Edit => edits[lineKey(l)] ?? { qty: l.suggested_qty, on: true };
  const chosen = g.lines.filter((l) => get(l).on && get(l).qty > 0);
  const total = chosen.reduce((a, l) => a + get(l).qty * l.cost, 0);
  const branches = new Set(chosen.map((l) => l.branch_id)).size;
  const allowed = can("manager");

  const send = useApiMutation<object, POResult>("POST", "/insights/reorder/send", {
    invalidate: ["/insights/reorder", "/insights/leaks"],
    errorTitle: tx("Couldn't create the purchase order", "ما قدرنا نعمل الطلبية"),
    onSuccess: (r) => {
      setConfirming(false);
      const pos = r.purchase_orders || [];
      onSent(pos.map((p) => p.po_number));
      const failed = pos.filter((p) => !p.email?.ok);
      const nums = pos.map((p) => p.po_number).join("، ");
      if (!failed.length) {
        const to = pos[0]?.email?.delivered_to?.join(", ") || g.email || "";
        toast(tx(`Sent ${nums}`, `انبعتت ${nums}`), tx(`Emailed to ${to}`, `انبعتت عالإيميل ${to}`));
      } else {
        const err = failed[0].email?.error || "";
        toast(tx(`PO saved: ${nums}`, `الطلبية انحفظت: ${nums}`),
          tx(`Email couldn't be delivered: ${err}. You can forward the PO yourself.`, `بس الإيميل ما وصل: ${err}. فيك تبعتها للمورد بنفسك.`), "info");
      }
    },
  });

  const doSend = () => send.mutate({
    supplier_id: g.supplier_id, note: note || null, send_email: true, locale,
    lines: chosen.map((l) => ({ product_id: l.product_id, branch_id: l.branch_id, quantity: get(l).qty })),
  });

  const supplierName = nm(g.supplier, g.supplier_ar) || tx("No supplier set", "بدون مورد");
  const disabledReason = !allowed ? tx("Only a manager or the owner can send purchase orders", "بس المدير أو صاحب المحل بيقدر يبعث طلبيات")
    : !g.supplier_id ? tx("Set a supplier for these products first", "حدد مورد لهالأصناف أول")
      : !chosen.length ? tx("Select at least one item", "اختار صنف واحد عالأقل") : undefined;

  return (
    <Card className={clsx("overflow-hidden", sent && "border-olive/40")}>
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4 text-start hover:bg-paper-2/60">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2">
            {g.supplier_id ? <span className="font-serif text-[17px] text-ink">{supplierName}</span> : <span className="font-serif text-[17px] text-ink-3">{supplierName}</span>}
            {g.critical > 0 && <Badge tone="danger"><span className="num">{g.critical}</span> {tx("critical", "عاجل")}</Badge>}
            {sent && <Badge tone="olive"><Check size={12} />{tx("Sent", "انبعتت")} · <span className="num">{sent.join(", ")}</span></Badge>}
          </p>
          <p className="mt-0.5 flex items-center gap-1.5 truncate text-[12.5px] text-ink-3">{g.email ? <><Mail size={12} />{g.email}</> : tx("No email on file", "ما في إيميل مسجّل")}</p>
        </div>
        <div className="text-end">
          <Money v={total} className="font-serif text-[20px] text-ink" />
          <p className="text-[12px] text-ink-3"><span className="num">{chosen.length}</span>/<span className="num">{g.lines.length}</span> {tx("items", "صنف")}</p>
        </div>
        <ChevronDown size={16} className={clsx("text-ink-3 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="border-t border-line/70">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-[13.5px]">
              <thead>
                <tr className="border-b border-line text-[12px] text-ink-3">
                  <th className="w-10 px-4 py-2.5" />
                  <th className="px-2 py-2.5 text-start font-medium">{tx("Item", "الصنف")}</th>
                  <th className="px-3 py-2.5 text-start font-medium">{tx("Branch", "الفرع")}</th>
                  <th className="px-3 py-2.5 text-end font-medium">{tx("In stock", "الموجود")}</th>
                  <th className="px-3 py-2.5 text-end font-medium">{tx("Sells / day", "بيع باليوم")}</th>
                  <th className="px-3 py-2.5 text-end font-medium">{tx("Days left", "بكفي لـ")}</th>
                  <th className="px-3 py-2.5 text-start font-medium">{tx("Urgency", "الأولوية")}</th>
                  <th className="px-3 py-2.5 text-end font-medium">{tx("Order qty", "كمية الطلب")}</th>
                  <th className="px-4 py-2.5 text-end font-medium">{tx("Amount", "المبلغ")}</th>
                </tr>
              </thead>
              <tbody>
                {g.lines.map((l) => {
                  const e = get(l);
                  const k = lineKey(l);
                  return (
                    <tr key={k} className={clsx("border-b border-line/60 last:border-0", !e.on && "opacity-50")}>
                      <td className="px-4 py-2">
                        <input type="checkbox" checked={e.on} onChange={(ev) => setEdit(k, { ...e, on: ev.target.checked })} className="size-4 accent-[#C2593A]"
                          aria-label={tx("Include", "ضمّن")} />
                      </td>
                      <td className="px-2 py-2"><LinkCell href={`/${locale}/app/products/${l.product_id}`}>{nm(l.name, l.name_ar)}</LinkCell></td>
                      <td className="px-3 py-2 text-ink-2">{nm(l.branch, l.branch_ar)}</td>
                      <td className={clsx("px-3 py-2 text-end", l.stock <= 0 && "text-danger")}><N v={l.stock} /></td>
                      <td className="px-3 py-2 text-end"><N v={l.daily} d={1} /></td>
                      <td className="px-3 py-2 text-end">{l.cover_days === null ? "—" : <span className={clsx("num", l.cover_days < 2 && "font-medium text-danger")}>{num(l.cover_days, 1)}</span>}</td>
                      <td className="px-3 py-2"><UrgencyBadge u={l.urgency} /></td>
                      <td className="px-3 py-2 text-end">
                        <Input type="number" min={0} step={1} inputMode="numeric" value={Number.isFinite(e.qty) ? e.qty : ""} disabled={!e.on}
                          onChange={(ev) => setEdit(k, { ...e, qty: Math.max(0, Math.round(Number(ev.target.value) || 0)) })}
                          className="num h-8 w-20 text-end" aria-label={tx("Quantity", "الكمية")} />
                        {l.on_order > 0 && <p className="mt-0.5 text-[11px] text-ink-3">+<span className="num">{num(l.on_order)}</span> {tx("on order", "مطلوب")}</p>}
                      </td>
                      <td className="px-4 py-2 text-end"><Money v={e.on ? e.qty * l.cost : 0} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="no-print flex flex-col gap-3 border-t border-line/70 bg-paper-2/50 px-5 py-4 sm:flex-row sm:items-center">
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={tx("Note to supplier (optional) — e.g. deliver before Thursday", "ملاحظة للمورد (اختياري) — مثلاً التوصيل قبل الخميس")} className="sm:flex-1" />
            {confirming ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12.5px] text-ink-2">
                  {tx(`Send ${chosen.length} items (${branches} ${branches === 1 ? "branch" : "branches"}) to ${g.email || "supplier"}?`, `تبعث ${chosen.length} صنف (${branches} فرع) لـ ${g.email || "المورد"}؟`)}
                </span>
                <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>{tx("Cancel", "إلغاء")}</Button>
                <Button size="sm" loading={send.isPending} onClick={doSend} data-basira={first ? "send-po-button" : undefined}><Send size={14} />{tx("Yes, send", "أيوه، ابعث")}</Button>
              </div>
            ) : (
              <span title={disabledReason} className="inline-flex">
                <Button size="sm" disabled={!!disabledReason} onClick={() => setConfirming(true)} data-basira={first ? "send-po-button" : undefined}>
                  <Send size={14} />{sent ? tx("Send again", "ابعث مرة ثانية") : tx("Send PO by email", "ابعث الطلبية بالإيميل")}
                </Button>
              </span>
            )}
          </div>
          {!allowed && <p className="px-5 pb-3 text-[12px] text-ink-3">{disabledReason}</p>}
        </div>
      )}
    </Card>
  );
}
