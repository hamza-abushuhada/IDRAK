export type Branch = { id: string; name: string; name_ar: string | null };
export type OrgDetail = { id: string; name: string; name_ar: string | null; tax_number: string | null; opening_cash: number; monthly_rent: number; branches: Branch[] };

export type Kpis = { revenue: number; tx: number; discounts: number; voids: number; customers: number; profit: number; units: number; basket: number; margin: number; units_per_tx: number };
export type Deltas = Partial<Record<"revenue" | "profit" | "tx" | "basket" | "margin" | "customers" | "discounts", number | null>>;
export type Dashboard = {
  range: { start: string; end: string; days: number };
  kpis: Kpis;
  deltas: Deltas;
  series: { d: string; revenue: number; tx: number; profit: number }[];
  top_products: { id: string; name: string; name_ar: string | null; qty: number; revenue: number; profit: number }[];
  categories: { name: string; name_ar: string | null; revenue: number; profit: number }[];
  heatmap: { dow: number; h: number; n: number }[];
  payments: { m: string; n: number; revenue: number }[];
  branches: { id: string; name: string; name_ar: string | null; revenue: number; tx: number; prev_revenue: number; basket: number; growth: number | null }[];
  goals: { branch_id: string; name: string; name_ar: string | null; target: number; actual: number; pace: number }[];
};

export type LeakKind = "dead_stock" | "below_cost" | "cashier_anomaly" | "shrinkage" | "expiring" | "supplier_price" | "stockout";
export type LeakItem = Record<string, string | number | null | undefined>;
export type Leak = { kind: LeakKind; severity: "high" | "medium" | "low"; amount_jod: number | null; title: string; title_ar: string; body: string; body_ar: string; link: string; items: LeakItem[] };
export type Leaks = { items: Leak[]; total_monthly: number; tied_up: number };

export type Named = { id: string; name: string; name_ar: string | null };
export type Forecast = {
  actual: { d: string; q: number; ramadan: boolean }[];
  forecast: { d: string; q: number; low: number; high: number; ramadan: boolean }[];
  uplift_ramadan: number; avg_daily: number; next30_qty: number; next30_revenue: number; unit_price: number;
  events: { d: string; en: string; ar: string; in_days: number }[];
  ramadan_in_days: number | null;
  ramadan_movers: { id: string; name: string; name_ar: string | null; ram_daily: number; base_daily: number; uplift: number }[];
  products: Named[];
  categories: Named[];
};

export type Urgency = "critical" | "soon" | "planned";
export type ReorderLine = {
  product_id: string; name: string; name_ar: string | null; branch_id: string; branch: string; branch_ar: string | null;
  stock: number; daily: number; on_order: number; suggested_qty: number; cover_days: number | null; urgency: Urgency; amount: number; cost: number;
};
export type ReorderGroup = { supplier_id: string | null; supplier: string | null; supplier_ar: string | null; email: string | null; total: number; critical: number; lines: ReorderLine[] };
export type Reorder = { groups: ReorderGroup[]; total: number; lines: number; critical: number; ramadan_in_days: number };
export type EmailResult = { ok: boolean; error?: string; delivered_to?: string[] };
export type POResult = { ok: boolean; purchase_orders: { id: string; po_number: string; total: number; email: EmailResult; branch: string }[] };

export type Segment = { key: string; en: string; ar: string; count: number; revenue: number };
export type RfmCustomer = {
  id: string; full_name: string; full_name_ar: string | null; phone: string | null; area: string | null; recency_days: number;
  freq: number; monetary: number; lifetime: number; lifetime_tx: number; segment: string; last_visit: string;
};
export type Rfm = { segments: Segment[]; customers: RfmCustomer[]; at_risk: RfmCustomer[] };

export type Pair = { a_name: string; a_name_ar: string | null; b_name: string; b_name_ar: string | null; together: number; support: number; conf_ab: number; lift: number };

export type SimSide = { qty: number; revenue: number; profit: number; margin: number };
export type SimResult = { baseline: SimSide; scenario: SimSide; elasticity: number; period_days: number };

export type CashWeek = { week_start: string; inflow: number; supplier_payments: number; salaries: number; rent: number; outflow: number; net: number; balance: number };
export type Cashflow = { weeks: CashWeek[]; opening: number; lowest: CashWeek | null; payroll: number };

export type Goal = { id: string; branch_id: string; branch: string | null; branch_ar: string | null; metric: string; period_month: string; target: number; actual: number };

export type AlertMetric = "stock_below_reorder" | "daily_sales_drop_pct" | "discount_rate_pct" | "expiring_items" | "revenue_below";
export type AlertRule = {
  id: string; name: string; metric: AlertMetric; operator: ">" | "<"; threshold: number; channel: "in_app" | "email";
  is_active: boolean; current: number | null; triggered: boolean; last_triggered_at: string | null;
};

export type ComplianceIssue = { key: string; severity: "high" | "medium" | "low"; en: string; ar: string; count: number; items?: Record<string, unknown>[]; link?: string };
export type Compliance = { score: number; invoices_checked: number; days: number; issues: ComplianceIssue[]; tax_number: string | null; checklist: { en: string; ar: string; ok: boolean }[] };

export type Summary = {
  org: { name: string; name_ar: string | null; city: string | null; tax_number: string | null };
  period_days: number;
  dashboard: Dashboard;
  leaks: Leak[];
  reorder: { total: number; lines: number; critical: number; suppliers: { supplier: string | null; supplier_ar: string | null; total: number; lines: number }[] };
  compliance: { score: number; issues: { en: string; ar: string; count: number }[] };
};
