"use client";
import { Suspense, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useTx } from "@/i18n";
import { useApiQuery } from "@/lib/useApi";
import { num } from "@/lib/format";
import { AskIdrak, ErrorBox, Money, N, PageHeader, Section, Stat, StatSkeleton, Table, useName, type Col } from "@/components/app/kit";
import { useSession } from "@/components/app/session";
import { Badge, Card, Tabs } from "@/components/ui";
import { useQueryParams, useScrollToHighlighted } from "@/components/workspace/common";

type Emp = {
  id: string; full_name: string; full_name_ar: string | null; job_title: string | null; phone: string | null; hired_at: string | null; monthly_salary: number | null;
  branch: string | null; branch_ar: string | null; tx: number; revenue: number; discounts: number; subtotal: number; voids: number; basket: number | null;
  discount_rate: number; void_rate: number; flag: boolean;
};

const JOBS: Record<string, [string, string]> = {
  cashier: ["Cashier", "كاشير"], supervisor: ["Supervisor", "مشرف"], manager: ["Branch manager", "مدير فرع"], stock: ["Stock keeper", "أمين مستودع"],
  stocker: ["Stock keeper", "أمين مستودع"], butcher: ["Butcher", "لحّام"], baker: ["Baker", "خبّاز"], pharmacist: ["Pharmacist", "صيدلاني"],
};

export default function EmployeesPage() {
  return <Suspense><Employees /></Suspense>;
}

function Employees() {
  const tx = useTx();
  const name = useName();
  const { can } = useSession();
  const { get } = useQueryParams();
  const highlight = get("highlight");
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const { data, error, refetch, isFetching } = useApiQuery<Emp[]>(`/ws/employees?days=${days}`, { placeholderData: (p) => p });
  useScrollToHighlighted("employees-table", highlight, !!data);

  const active = data?.filter((e) => e.tx > 0) || [];
  const flagged = data?.filter((e) => e.flag) || [];
  const revenue = active.reduce((a, e) => a + e.revenue, 0);
  const txs = active.reduce((a, e) => a + e.tx, 0);
  const disc = active.reduce((a, e) => a + e.discounts, 0);
  const sub = active.reduce((a, e) => a + e.subtotal, 0);
  const job = (j: string | null) => (j && JOBS[j] ? tx(JOBS[j][0], JOBS[j][1]) : j || "—");

  const cols: Col<Emp>[] = [
    {
      key: "full_name", label: tx("Employee", "الموظف"), render: (e) => (
        <div className="min-w-[170px]">
          <span className="font-medium text-ink">{name(e.full_name, e.full_name_ar)}</span>
          <span className="block text-[11.5px] text-ink-3">{job(e.job_title)}</span>
        </div>
      ),
    },
    { key: "branch", label: tx("Branch", "الفرع"), render: (e) => <span className="whitespace-nowrap">{name(e.branch, e.branch_ar)}</span> },
    { key: "tx", label: tx("Transactions", "العمليات"), align: "end", render: (e) => <N v={e.tx} /> },
    { key: "revenue", label: tx("Revenue", "المبيعات"), align: "end", render: (e) => <Money v={e.revenue} /> },
    { key: "basket", label: tx("Avg basket", "معدّل السلة"), align: "end", render: (e) => <Money v={e.basket} /> },
    { key: "discount_rate", label: tx("Discount rate", "نسبة الخصم"), align: "end", render: (e) => <span className={`num ${e.flag && e.discount_rate > 2 ? "font-medium text-danger" : ""}`}>{e.discount_rate.toFixed(2)}%</span> },
    { key: "void_rate", label: tx("Void rate", "نسبة الإلغاء"), align: "end", render: (e) => <span className={`num ${e.void_rate > 1.5 ? "font-medium text-danger" : ""}`}>{e.void_rate.toFixed(2)}%<span className="block text-[11px] font-normal text-ink-3">{tx(`${e.voids} voids`, `${e.voids} إلغاء`)}</span></span> },
    ...(can("accountant") ? [{ key: "monthly_salary", label: tx("Salary / mo", "الراتب الشهري"), align: "end" as const, render: (e: Emp) => <Money v={e.monthly_salary} /> }] : []),
    { key: "flag", label: "", render: (e) => e.flag ? <Badge tone="danger"><AlertTriangle size={11} />{tx("Review", "راجِع")}</Badge> : null },
  ];

  const period = { "7": tx("last 7 days", "آخر 7 أيام"), "30": tx("last 30 days", "آخر 30 يوم"), "90": tx("last 90 days", "آخر 90 يوم") }[days];

  return (
    <div>
      <PageHeader
        eyebrow={tx("Business · Employees", "الشغل · الموظفين")}
        title={tx("Employees", "الموظفين")}
        subtitle={tx("How each person sells — and where discounts or voids look unusual.", "كيف كل موظف عم يبيع — ووين الخصومات أو الإلغاءات مش طبيعية.")}
        actions={<>
          <Tabs value={days} onChange={setDays} items={[{ value: "7", label: tx("7 days", "7 أيام") }, { value: "30", label: tx("30 days", "30 يوم") }, { value: "90", label: tx("90 days", "90 يوم") }]} />
          <AskIdrak q={tx("Is any cashier giving too many discounts or voiding too many sales?", "في كاشير عم يعطي خصومات كثير أو يلغي فواتير أكثر من اللازم؟")} />
        </>}
      />

      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {data ? (
          <>
            <Stat label={tx("Active staff", "موظفين نشطين")} value={<N v={active.length} />} hint={tx(`of ${data.length} on record`, `من أصل ${data.length}`)} />
            <Stat label={tx("Revenue", "المبيعات")} value={<Money v={revenue} compact />} hint={period} tone="olive" />
            <Stat label={tx("Revenue per transaction", "المعدّل لكل عملية")} value={<Money v={txs ? revenue / txs : null} />} />
            <Stat label={tx("Overall discount rate", "نسبة الخصم الكلية")} value={<span className="num">{sub ? ((disc / sub) * 100).toFixed(2) : "0"}%</span>} hint={<Money v={disc} />} />
          </>
        ) : Array.from({ length: 4 }).map((_, i) => <StatSkeleton key={i} />)}
      </div>

      {data && (
        <Card data-basira="employee-flags" className={`mb-5 px-5 py-4 ${flagged.length ? "border-danger/30" : ""}`}>
          {flagged.length ? (
            <div className="flex flex-wrap items-start gap-3">
              <AlertTriangle size={18} className="mt-0.5 shrink-0 text-danger" />
              <div className="min-w-0 flex-1">
                <p className="font-medium text-ink">{tx(`${flagged.length} ${flagged.length === 1 ? "person needs" : "people need"} a closer look`, `${flagged.length === 1 ? "موظف واحد بدّه" : `${flagged.length} موظفين بدهم`} نظرة أقرب`)}</p>
                <p className="mt-0.5 text-[13px] text-ink-2">
                  {flagged.map((e) => `${name(e.full_name, e.full_name_ar)} (${tx("discounts", "خصم")} ${e.discount_rate.toFixed(1)}% · ${tx("voids", "إلغاء")} ${e.void_rate.toFixed(1)}%)`).join(tx(", ", "، "))}
                </p>
                <p className="mt-1 text-[12px] text-ink-3">{tx("Flagged when discounts are over 3× the team's usual rate, or voids exceed 1.5%. It isn't proof of anything — just worth a friendly chat.", "بنعلّم الموظف لما خصوماته أكثر من 3 أضعاف المعتاد أو الإلغاءات فوق 1.5%. مش دليل على إشي — بس بستاهل حكي ودّي.")}</p>
              </div>
            </div>
          ) : (
            <p className="text-[13.5px] text-ink-2">{tx(`Nothing unusual in the ${period} — discounts and voids look normal for everyone.`, `ما في إشي غريب ب${period} — الخصومات والإلغاءات طبيعية عند الكل.`)}</p>
          )}
        </Card>
      )}

      {error ? <ErrorBox error={error} retry={refetch} /> : (
        <Section title={tx("Performance", "الأداء")} subtitle={tx(`Completed sales in the ${period}`, `المبيعات المكتملة ب${period}`)} bodyClass="p-0"
          action={isFetching && data ? <span className="text-[12px] text-ink-3">{tx("Updating…", "عم نحدّث…")}</span> : undefined}>
          <Table<Emp>
            id="employees-table"
            rows={data}
            cols={cols}
            highlightRow={(e) => e.id === highlight}
            empty={tx("No employees yet. Cashier names come in with your sales files.", "لسا ما في موظفين. أسماء الكاشيرية بتيجي مع ملفات المبيعات.")}
          />
          {data && <p className="border-t border-line px-4 py-2.5 text-[12px] text-ink-3">{tx(`${num(txs)} transactions in total`, `${num(txs)} عملية بالمجموع`)}</p>}
        </Section>
      )}
    </div>
  );
}
