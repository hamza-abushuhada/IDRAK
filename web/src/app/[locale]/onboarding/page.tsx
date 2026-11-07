"use client";
import { useRouter } from "@/lib/router";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { Check, Plus, Trash2 } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { supabase } from "@/lib/supabase";
import { api, setOrgId } from "@/lib/api";
import { Logo } from "@/components/Logo";
import { Button, Card, Field, Input, Select } from "@/components/ui";
import { toast } from "@/components/ui/toast";

const INDUSTRIES = [
  { v: "minimarket", en: "Mini-market / grocery", ar: "ميني ماركت / بقالة" },
  { v: "pharmacy", en: "Pharmacy", ar: "صيدلية" },
  { v: "restaurant", en: "Restaurant / café / bakery", ar: "مطعم / كافيه / مخبز" },
  { v: "fashion", en: "Fashion & retail", ar: "ألبسة ومحلات تجزئة" },
  { v: "other", en: "Other", ar: "غير ذلك" },
];
const CITIES = ["Amman", "Irbid", "Zarqa", "Aqaba", "Salt", "Madaba", "Jerash", "Karak", "Mafraq", "Ajloun"];
const CITIES_AR: Record<string, string> = { Amman: "عمّان", Irbid: "إربد", Zarqa: "الزرقاء", Aqaba: "العقبة", Salt: "السلط", Madaba: "مادبا", Jerash: "جرش", Karak: "الكرك", Mafraq: "المفرق", Ajloun: "عجلون" };

export default function Onboarding() {
  const locale = useLocale();
  const tx = useTx();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState("");
  const [nameAr, setNameAr] = useState("");
  const [industry, setIndustry] = useState("minimarket");
  const [city, setCity] = useState("Amman");
  const [tax, setTax] = useState("");
  const [branches, setBranches] = useState([{ name: "", name_ar: "", area: "" }]);

  useEffect(() => {
    supabase().auth.getSession().then(({ data }) => { if (!data.session) router.replace(`/${locale}/login?next=/${locale}/onboarding`); });
  }, [locale, router]);

  async function create(then: "upload" | "app") {
    setLoading(true);
    try {
      const res = await api<{ id: string }>("/orgs", { method: "POST", json: {
        name: name || nameAr, name_ar: nameAr || null, industry, city, locale, tax_number: tax || null,
        branches: branches.filter((b) => b.name || b.name_ar).map((b) => ({ name: b.name || b.name_ar, name_ar: b.name_ar || null, city, area: b.area || null })),
      } });
      setOrgId(res.id);
      router.replace(`/${locale}/app${then === "upload" ? "/data" : ""}`);
    } catch (e) {
      toast(tx("Couldn't create your business", "ما قدرنا ننشئ المشروع"), (e as Error).message, "error");
      setLoading(false);
    }
  }
  async function demo() {
    setLoading(true);
    try {
      const r = await api<{ id: string }>("/me/join-demo", { method: "POST" });
      setOrgId(r.id);
      router.replace(`/${locale}/app`);
    } catch (e) {
      toast(tx("Demo not available", "العرض التجريبي مش متاح"), (e as Error).message, "error");
      setLoading(false);
    }
  }

  const steps = [tx("Your business", "مشروعك"), tx("Branches", "الفروع"), tx("Start", "البداية")];
  return (
    <div className="grain min-h-dvh bg-paper px-5 py-8">
      <div className="mx-auto max-w-2xl">
        <Logo locale={locale} />
        <div className="mt-10 flex items-center gap-3 text-[13px]">
          {steps.map((s, i) => (
            <div key={s} className="flex items-center gap-3">
              <span className={clsx("grid size-7 place-items-center rounded-full border text-[12px]", i < step ? "border-olive bg-olive text-paper" : i === step ? "border-ink bg-ink text-paper" : "border-line text-ink-3")}>
                {i < step ? <Check size={14} /> : i + 1}
              </span>
              <span className={i === step ? "text-ink" : "text-ink-3"}>{s}</span>
              {i < steps.length - 1 && <span className="h-px w-8 bg-line" />}
            </div>
          ))}
        </div>

        <Card className="mt-8 p-7">
          {step === 0 && (
            <div className="space-y-5">
              <div>
                <h1 className="font-serif text-[28px] text-ink">{tx("Tell us about your business", "احكيلنا عن مشروعك")}</h1>
                <p className="mt-1 text-ink-2">{tx("Idrak tunes its cleaning rules and insights to your type of shop.", "إدراك بيظبط قواعد التنظيف والتحليلات حسب نوع محلّك.")}</p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={tx("Business name (English)", "اسم المشروع (إنجليزي)")}><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Al-Salam Market" dir="ltr" /></Field>
                <Field label={tx("Business name (Arabic)", "اسم المشروع (عربي)")}><Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} placeholder="سوق السلام" dir="rtl" /></Field>
                <Field label={tx("Type", "النوع")}>
                  <Select value={industry} onChange={(e) => setIndustry(e.target.value)} className="w-full">{INDUSTRIES.map((i) => <option key={i.v} value={i.v}>{tx(i.en, i.ar)}</option>)}</Select>
                </Field>
                <Field label={tx("City", "المدينة")}>
                  <Select value={city} onChange={(e) => setCity(e.target.value)} className="w-full">{CITIES.map((c) => <option key={c} value={c}>{tx(c, CITIES_AR[c])}</option>)}</Select>
                </Field>
                <Field label={tx("Tax number (optional)", "الرقم الضريبي (اختياري)")} hint={tx("Needed for the e-invoice readiness check", "بنحتاجه لفحص جاهزية الفوترة الإلكترونية")}>
                  <Input value={tax} onChange={(e) => setTax(e.target.value)} dir="ltr" />
                </Field>
              </div>
              <div className="flex justify-end"><Button disabled={!name && !nameAr} onClick={() => setStep(1)}>{tx("Continue", "متابعة")}</Button></div>
            </div>
          )}
          {step === 1 && (
            <div className="space-y-5">
              <div>
                <h1 className="font-serif text-[28px] text-ink">{tx("Your branches", "فروعك")}</h1>
                <p className="mt-1 text-ink-2">{tx("Add each location. You can change this later in settings.", "أضف كل فرع. بتقدر تعدّل لاحقاً من الإعدادات.")}</p>
              </div>
              {branches.map((b, i) => (
                <div key={i} className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_1fr_auto]">
                  <Field label={tx("Name (EN)", "الاسم (EN)")}><Input value={b.name} dir="ltr" placeholder="Khalda" onChange={(e) => setBranches(branches.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} /></Field>
                  <Field label={tx("Name (AR)", "الاسم (ع)")}><Input value={b.name_ar} placeholder="خلدا" onChange={(e) => setBranches(branches.map((x, j) => (j === i ? { ...x, name_ar: e.target.value } : x)))} /></Field>
                  <Field label={tx("Area / street", "المنطقة / الشارع")}><Input value={b.area} onChange={(e) => setBranches(branches.map((x, j) => (j === i ? { ...x, area: e.target.value } : x)))} /></Field>
                  <button onClick={() => setBranches(branches.filter((_, j) => j !== i))} disabled={branches.length === 1} className="mb-2 text-ink-3 hover:text-danger disabled:opacity-30"><Trash2 size={16} /></button>
                </div>
              ))}
              <button onClick={() => setBranches([...branches, { name: "", name_ar: "", area: "" }])} className="inline-flex items-center gap-1.5 text-sm text-terra"><Plus size={15} />{tx("Add another branch", "أضف فرع ثاني")}</button>
              <div className="flex justify-between"><Button variant="ghost" onClick={() => setStep(0)}>{tx("Back", "رجوع")}</Button><Button onClick={() => setStep(2)}>{tx("Continue", "متابعة")}</Button></div>
            </div>
          )}
          {step === 2 && (
            <div className="space-y-5">
              <div>
                <h1 className="font-serif text-[28px] text-ink">{tx("How do you want to start?", "كيف حابب تبدأ؟")}</h1>
                <p className="mt-1 text-ink-2">{tx("Most owners start by uploading one POS export.", "أغلب أصحاب المحلات بيبدأوا برفع ملف واحد من نظام الكاشير.")}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <button disabled={loading} onClick={() => create("upload")} className="rounded-xl border border-ink bg-ink p-5 text-start text-paper hover:bg-ink-2">
                  <p className="font-serif text-lg">{tx("Upload my data", "ارفع بياناتي")}</p>
                  <p className="mt-1 text-[13px] text-paper/70">{tx("Excel or CSV from your POS, Google Sheets, or a supplier list.", "ملف إكسل أو CSV من الكاشير، Google Sheets، أو قائمة مورد.")}</p>
                </button>
                <button disabled={loading} onClick={() => create("app")} className="rounded-xl border border-line p-5 text-start hover:bg-sand">
                  <p className="font-serif text-lg text-ink">{tx("Open my empty workspace", "افتح مساحة شغلي فاضية")}</p>
                  <p className="mt-1 text-[13px] text-ink-3">{tx("Invite your team first, upload later.", "ادعِ فريقك أول وارفع لاحقاً.")}</p>
                </button>
              </div>
              <div className="rounded-xl border border-dashed border-sand-2 p-4 text-sm text-ink-2">
                {tx("Just want to look around?", "بس حابب تتفرج؟")}{" "}
                <button disabled={loading} onClick={demo} className="font-medium text-terra underline-offset-4 hover:underline">{tx("Explore the demo mini-market (Al-Nashama Market, Amman)", "استكشف الميني ماركت التجريبي (أسواق النشامى، عمّان)")}</button>
              </div>
              <div className="flex justify-start"><Button variant="ghost" onClick={() => setStep(1)}>{tx("Back", "رجوع")}</Button></div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
