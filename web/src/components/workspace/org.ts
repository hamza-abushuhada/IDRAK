import type { Role } from "@/components/app/session";

export type OrgBranch = { id: string; name: string; name_ar: string | null; city: string | null; area: string | null; opened_at: string | null };
export type OrgFull = {
  id: string; name: string; name_ar: string | null; slug: string; industry: string; city: string | null; country: string; currency: string; locale: string;
  plan: string; tax_number: string | null; is_demo: boolean; created_at: string; monthly_rent: number | null; opening_cash: number | null;
  branches: OrgBranch[]; role: Role;
  usage: { uploads_30d: number; rows_30d: number; ai_calls_30d: number; members: number };
};

export const INDUSTRIES = [
  { v: "minimarket", en: "Mini-market / grocery", ar: "ميني ماركت / بقالة" },
  { v: "pharmacy", en: "Pharmacy", ar: "صيدلية" },
  { v: "restaurant", en: "Restaurant / café / bakery", ar: "مطعم / كافيه / مخبز" },
  { v: "fashion", en: "Fashion & retail", ar: "ألبسة ومحلات تجزئة" },
  { v: "other", en: "Other", ar: "غير ذلك" },
];

export const CITIES: { v: string; ar: string }[] = [
  { v: "Amman", ar: "عمّان" }, { v: "Irbid", ar: "إربد" }, { v: "Zarqa", ar: "الزرقاء" }, { v: "Aqaba", ar: "العقبة" }, { v: "Salt", ar: "السلط" },
  { v: "Madaba", ar: "مادبا" }, { v: "Jerash", ar: "جرش" }, { v: "Karak", ar: "الكرك" }, { v: "Mafraq", ar: "المفرق" }, { v: "Ajloun", ar: "عجلون" },
];

export const PLANS = [
  {
    v: "starter", en: "Starter", ar: "الأساسية", price: 19,
    blurbEn: "For one shop getting its data in order.", blurbAr: "لمحل واحد بدّه يرتّب بياناته.",
    limits: { branches: 1, rows_30d: 5000, members: 2, ai_calls_30d: null as number | null },
    featuresEn: ["1 branch", "5,000 rows / month", "Cleaning Studio & Health Score", "Money Leak Detector"],
    featuresAr: ["فرع واحد", "5,000 صف بالشهر", "استوديو التنظيف ومؤشر الصحة", "كاشف تسريب المصاري"],
  },
  {
    v: "growth", en: "Growth", ar: "النمو", price: 49,
    blurbEn: "For growing shops that want answers, not reports.", blurbAr: "للمحلات اللي عم تكبر وبدها أجوبة، مش تقارير.",
    limits: { branches: 3, rows_30d: 50000, members: 8, ai_calls_30d: 2000 as number | null },
    featuresEn: ["Up to 3 branches", "Idrak Assistant", "Ramadan-aware forecasts & reorder", "Customer segments & win-back"],
    featuresAr: ["لحد 3 فروع", "مساعد إدراك", "توقّعات وطلبيات بتحسب حساب رمضان", "شرائح الزبائن وترجيعهم"],
  },
  {
    v: "business", en: "Business", ar: "الأعمال", price: 99,
    blurbEn: "For multi-branch shops and pharmacies with compliance needs.", blurbAr: "للمحلات متعددة الفروع والصيدليات اللي عندها متطلبات امتثال.",
    limits: { branches: 10, rows_30d: 250000, members: 25, ai_calls_30d: 10000 as number | null },
    featuresEn: ["Up to 10 branches", "E-invoice readiness checks", "API access", "Priority support in Arabic & English"],
    featuresAr: ["لحد 10 فروع", "فحص جاهزية الفوترة الإلكترونية", "وصول للـ API", "دعم بأولوية بالعربي والإنجليزي"],
  },
] as const;
export type PlanKey = (typeof PLANS)[number]["v"];
