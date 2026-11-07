"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useRouter } from "@/lib/router";
import { MapPin, Plus } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { api } from "@/lib/api";
import { useApiMutation, useApiQuery } from "@/lib/useApi";
import { date } from "@/lib/format";
import { AskIdrak, ErrorBox, PageHeader, Section, useName } from "@/components/app/kit";
import { useSession } from "@/components/app/session";
import { Badge, Button, Field, Input, Label, Select, Skeleton, Tabs } from "@/components/ui";
import { toast } from "@/components/ui/toast";
import SettingsNav from "@/components/workspace/SettingsNav";
import { RoleNote } from "@/components/workspace/common";
import { CITIES, INDUSTRIES, type OrgFull } from "@/components/workspace/org";

type Form = { name: string; name_ar: string; industry: string; city: string; tax_number: string; monthly_rent: string; opening_cash: string; locale: string };
const toForm = (o: OrgFull): Form => ({
  name: o.name || "", name_ar: o.name_ar || "", industry: o.industry || "minimarket", city: o.city || "", tax_number: o.tax_number || "",
  monthly_rent: o.monthly_rent === null || o.monthly_rent === undefined ? "" : String(o.monthly_rent),
  opening_cash: o.opening_cash === null || o.opening_cash === undefined ? "" : String(o.opening_cash),
  locale: o.locale || "ar",
});

export default function SettingsPage() {
  const tx = useTx();
  const { data: org, error, refetch } = useApiQuery<OrgFull>("/org");
  const { can } = useSession();
  const owner = can("owner");

  return (
    <div>
      <PageHeader
        eyebrow={tx("Admin · Settings", "الإدارة · الإعدادات")}
        title={tx("Settings", "الإعدادات")}
        subtitle={tx("Your business details, branches and language.", "معلومات مشروعك، الفروع، واللغة.")}
        actions={<AskIdrak q={tx("Why does Idrak need my monthly rent and opening cash?", "ليش إدراك بدّه الإيجار الشهري والرصيد الافتتاحي؟")} />}
      />
      <SettingsNav />
      {error ? <ErrorBox error={error} retry={refetch} /> : !org ? (
        <div className="grid gap-5 lg:grid-cols-3"><Skeleton className="h-[460px] lg:col-span-2" /><Skeleton className="h-[300px]" /></div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            <BusinessForm org={org} owner={owner} />
          </div>
          <div className="space-y-5">
            <LanguageCard />
            <BranchesCard org={org} owner={owner} />
          </div>
        </div>
      )}
    </div>
  );
}

function BusinessForm({ org, owner }: { org: OrgFull; owner: boolean }) {
  const tx = useTx();
  const { refresh } = useSession();
  const [f, setF] = useState<Form>(() => toForm(org));
  useEffect(() => setF(toForm(org)), [org]);
  const initial = toForm(org);
  const dirty = (Object.keys(f) as (keyof Form)[]).some((k) => f[k] !== initial[k]);
  const up = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF((s) => ({ ...s, [k]: e.target.value }));

  const save = useApiMutation("PATCH", "/org", {
    invalidate: ["/org"],
    errorTitle: tx("Couldn't save settings", "ما قدرنا نحفظ الإعدادات"),
    onSuccess: () => { toast(tx("Settings saved", "انحفظت الإعدادات")); refresh(); },
  });
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!owner || !f.name.trim()) return;
    save.mutate({
      name: f.name.trim(), name_ar: f.name_ar.trim() || null, industry: f.industry, city: f.city || null, tax_number: f.tax_number.trim() || null,
      monthly_rent: f.monthly_rent === "" ? null : Number(f.monthly_rent), opening_cash: f.opening_cash === "" ? null : Number(f.opening_cash), locale: f.locale,
    });
  };

  return (
    <Section title={tx("Business details", "معلومات المشروع")} subtitle={tx("Used on reports, invoices readiness and cash-flow projections.", "بتظهر بالتقارير وفحص الفوترة وتوقّعات التدفق النقدي.")}>
      <form onSubmit={submit} className="space-y-5">
        {!owner && <RoleNote>{tx("Only the owner can change business settings. You can see them here.", "بس المالك بيقدر يغيّر إعدادات المشروع. بتقدر تشوفها هون.")}</RoleNote>}
        <div data-basira="org-name" className="grid gap-4 sm:grid-cols-2">
          <Field label={tx("Business name (English)", "اسم المشروع (إنجليزي)")}><Input value={f.name} onChange={up("name")} disabled={!owner} required dir="ltr" /></Field>
          <Field label={tx("Business name (Arabic)", "اسم المشروع (عربي)")}><Input value={f.name_ar} onChange={up("name_ar")} disabled={!owner} dir="rtl" /></Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={tx("Industry", "نوع النشاط")}>
            <Select value={f.industry} onChange={up("industry")} disabled={!owner} className="w-full">
              {INDUSTRIES.map((i) => <option key={i.v} value={i.v}>{tx(i.en, i.ar)}</option>)}
            </Select>
          </Field>
          <Field label={tx("City", "المدينة")}>
            <Select value={f.city} onChange={up("city")} disabled={!owner} className="w-full">
              <option value="">—</option>
              {f.city && !CITIES.some((c) => c.v === f.city) && <option value={f.city}>{f.city}</option>}
              {CITIES.map((c) => <option key={c.v} value={c.v}>{tx(c.v, c.ar)}</option>)}
            </Select>
          </Field>
        </div>
        <div data-basira="tax-number-field">
          <Field label={tx("Tax number", "الرقم الضريبي")} hint={tx("Needed for JoFotara e-invoicing.", "مطلوب للفوترة الإلكترونية (جوفوترة).")}>
            <Input value={f.tax_number} onChange={up("tax_number")} disabled={!owner} inputMode="numeric" className="num" dir="ltr" />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div data-basira="monthly-rent-field">
            <Field label={tx("Monthly rent (JD)", "الإيجار الشهري (د.أ)")} hint={tx("All branches together. Used in cash-flow.", "لكل الفروع مع بعض. بندخله بالتدفق النقدي.")}>
              <Input type="number" min="0" step="1" value={f.monthly_rent} onChange={up("monthly_rent")} disabled={!owner} className="num" />
            </Field>
          </div>
          <div data-basira="opening-cash-field">
            <Field label={tx("Opening cash (JD)", "الرصيد الافتتاحي (د.أ)")} hint={tx("Cash on hand when you started using Idrak.", "المصاري اللي معك لما بلّشت تستعمل إدراك.")}>
              <Input type="number" step="1" value={f.opening_cash} onChange={up("opening_cash")} disabled={!owner} className="num" />
            </Field>
          </div>
        </div>
        <Field label={tx("Language for emails & invitations", "لغة الإيميلات والدعوات")}>
          <Select value={f.locale} onChange={up("locale")} disabled={!owner} className="w-full sm:w-60">
            <option value="ar">العربية</option>
            <option value="en">English</option>
          </Select>
        </Field>
        {owner && (
          <div className="flex items-center gap-2 border-t border-line/70 pt-4">
            <Button type="submit" loading={save.isPending} disabled={!dirty || !f.name.trim()}>{tx("Save changes", "احفظ التغييرات")}</Button>
            {dirty && <Button type="button" variant="ghost" size="sm" onClick={() => setF(initial)}>{tx("Discard", "تجاهل")}</Button>}
          </div>
        )}
      </form>
    </Section>
  );
}

function LanguageCard() {
  const tx = useTx();
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const [busy, setBusy] = useState(false);
  const change = async (l: "ar" | "en") => {
    if (l === locale) return;
    setBusy(true);
    try { await api("/me", { method: "PATCH", json: { locale: l } }); } catch {  }
    document.cookie = `basira_locale=${l};path=/;max-age=31536000`;
    router.push(pathname.replace(/^\/(ar|en)/, `/${l}`));
  };
  return (
    <Section title={tx("Your language", "لغتك")} subtitle={tx("Just for you — teammates choose their own.", "إلك إنت بس — كل واحد بالفريق بيختار لغته.")}>
      <Label>{tx("Interface language", "لغة الواجهة")}</Label>
      <Tabs value={locale} onChange={(v) => !busy && change(v)} items={[{ value: "ar", label: "العربية" }, { value: "en", label: "English" }]} />
    </Section>
  );
}

function BranchesCard({ org, owner }: { org: OrgFull; owner: boolean }) {
  const tx = useTx();
  const locale = useLocale();
  const name = useName();
  const { refresh } = useSession();
  const [adding, setAdding] = useState(false);
  const [b, setB] = useState({ name: "", name_ar: "", city: org.city || "Amman", area: "" });
  const add = useApiMutation<{ name: string; name_ar: string | null; city: string | null; area: string | null }>("POST", "/org/branches", {
    invalidate: ["/org", "/ws/branches"],
    errorTitle: tx("Couldn't add the branch", "ما قدرنا نضيف الفرع"),
    onSuccess: () => { toast(tx("Branch added", "انضاف الفرع")); setAdding(false); setB({ name: "", name_ar: "", city: org.city || "Amman", area: "" }); refresh(); },
  });

  return (
    <Section id="branches-list" title={tx("Branches", "الفروع")} subtitle={tx(`${org.branches.length} ${org.branches.length === 1 ? "branch" : "branches"}`, `${org.branches.length} فروع`)}
      action={owner && !adding ? <Button size="sm" variant="secondary" onClick={() => setAdding(true)}><Plus size={14} />{tx("Add", "أضف")}</Button> : undefined}
      bodyClass="p-0">
      <ul className="divide-y divide-line/60">
        {org.branches.map((br) => (
          <li key={br.id} className="flex items-start justify-between gap-3 px-5 py-3">
            <div className="min-w-0">
              <p className="text-[14px] text-ink">{name(br.name, br.name_ar)}</p>
              <p className="mt-0.5 flex items-center gap-1 text-[12px] text-ink-3"><MapPin size={11} />{[br.area, br.city].filter(Boolean).join("، ") || "—"}</p>
            </div>
            {br.opened_at && <Badge>{tx("since", "من")} <span className="num">{date(br.opened_at, locale, { month: "short", year: "numeric" })}</span></Badge>}
          </li>
        ))}
        {!org.branches.length && <li className="px-5 py-6 text-center text-[13px] text-ink-3">{tx("No branches yet.", "لسا ما في فروع.")}</li>}
      </ul>
      {adding && (
        <form className="space-y-3 border-t border-line bg-paper-2/60 px-5 py-4"
          onSubmit={(e) => { e.preventDefault(); if (b.name.trim()) add.mutate({ name: b.name.trim(), name_ar: b.name_ar.trim() || null, city: b.city || null, area: b.area.trim() || null }); }}>
          <Field label={tx("Name (English)", "الاسم (إنجليزي)")}><Input value={b.name} onChange={(e) => setB({ ...b, name: e.target.value })} required dir="ltr" placeholder="Abdoun" /></Field>
          <Field label={tx("Name (Arabic)", "الاسم (عربي)")}><Input value={b.name_ar} onChange={(e) => setB({ ...b, name_ar: e.target.value })} dir="rtl" placeholder="عبدون" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={tx("City", "المدينة")}>
              <Select value={b.city} onChange={(e) => setB({ ...b, city: e.target.value })} className="w-full">
                {CITIES.map((c) => <option key={c.v} value={c.v}>{tx(c.v, c.ar)}</option>)}
              </Select>
            </Field>
            <Field label={tx("Area / street", "المنطقة / الشارع")}><Input value={b.area} onChange={(e) => setB({ ...b, area: e.target.value })} /></Field>
          </div>
          <div className="flex gap-2">
            <Button type="submit" size="sm" loading={add.isPending} disabled={!b.name.trim()}>{tx("Add branch", "أضف الفرع")}</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setAdding(false)}>{tx("Cancel", "إلغاء")}</Button>
          </div>
        </form>
      )}
      {!owner && <div className="border-t border-line/60 px-5 py-3"><RoleNote>{tx("Only the owner can add branches.", "بس المالك بيقدر يضيف فروع.")}</RoleNote></div>}
    </Section>
  );
}
