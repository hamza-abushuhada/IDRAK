"use client";
import { useState } from "react";
import Link from "next/link";
import { publicApi } from "@/lib/api";
import { Button, Input, Select, Textarea } from "@/components/ui";
import { toast } from "@/components/ui/toast";
import { useCopy } from "./use-copy";
import { lh } from "./copy";
import { Arrow } from "./primitives";
import { EMAIL_RE } from "./WaitlistMini";

const lbl = "mb-1.5 block text-[13px] font-medium text-ink-2";
const fieldErr = "mt-1.5 text-[13px] text-danger";

export function ContactForm() {
  const { c, locale } = useCopy();
  const F = c.contact.form;
  const [v, setV] = useState({ name: "", email: "", phone: "", message: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [sent, setSent] = useState(false);
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setV((s) => ({ ...s, [k]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!v.name.trim() || !v.email.trim() || !v.message.trim()) return setErr(F.required);
    if (!EMAIL_RE.test(v.email.trim())) return setErr(F.invalidEmail);
    setErr("");
    setBusy(true);
    try {
      await publicApi("/public/contact", { method: "POST", json: { name: v.name.trim(), email: v.email.trim(), phone: v.phone.trim() || null, message: v.message.trim(), locale } });
      toast(F.successTitle, F.successBody, "ok");
      setSent(true);
      setV({ name: "", email: "", phone: "", message: "" });
    } catch {
      toast(F.errorTitle, F.errorBody, "error");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div role="status" className="rounded-[16px] border border-olive/30 bg-olive-soft/50 p-8">
        <p className="font-serif text-[26px] text-ink rtl:font-semibold">{F.successTitle}</p>
        <p className="mt-2 text-[16px] text-ink-2">{F.successBody}</p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-5">
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <div>
          <label htmlFor="cf-name" className={lbl}><span id="cf-name-l">{F.name}</span></label>
          <Input id="cf-name" autoComplete="name" value={v.name} onChange={set("name")} className="h-11 bg-[#FFFCF7]" required />
        </div>
        <div>
          <label htmlFor="cf-email" className={lbl}><span id="cf-email-l">{F.email}</span></label>
          <Input id="cf-email" type="email" dir="ltr" autoComplete="email" value={v.email} onChange={set("email")} className="h-11 bg-[#FFFCF7] rtl:text-right" required />
        </div>
      </div>
      <div>
        <label htmlFor="cf-phone" className={lbl}><span id="cf-phone-l">{F.phone}</span> <span className="font-normal text-ink-3">({F.optional})</span></label>
        <Input id="cf-phone" type="tel" dir="ltr" autoComplete="tel" placeholder={F.phonePlaceholder} value={v.phone} onChange={set("phone")} className="h-11 bg-[#FFFCF7] rtl:text-right" />
      </div>
      <div>
        <label htmlFor="cf-msg" className={lbl}><span id="cf-msg-l">{F.message}</span></label>
        <Textarea id="cf-msg" rows={6} placeholder={F.messagePlaceholder} value={v.message} onChange={set("message")} className="bg-[#FFFCF7] text-[15px]" required />
      </div>
      {err && <p role="alert" className={fieldErr}>{err}</p>}
      <Button type="submit" size="lg" loading={busy}>
        {F.send} {!busy && <Arrow size={15} />}
      </Button>
    </form>
  );
}

export function WaitlistForm() {
  const { c, locale } = useCopy();
  const F = c.waitlist.form;
  const [v, setV] = useState({ name: "", email: "", business_name: "", business_type: "", city: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setV((s) => ({ ...s, [k]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!v.email.trim()) return setErr(F.required);
    if (!EMAIL_RE.test(v.email.trim())) return setErr(F.invalidEmail);
    setErr("");
    setBusy(true);
    try {
      const n = (s: string) => s.trim() || null;
      await publicApi("/public/waitlist", { method: "POST", json: { email: v.email.trim(), name: n(v.name), business_name: n(v.business_name), business_type: n(v.business_type), city: n(v.city), locale } });
      setDone(true);
      toast(F.successTitle, F.successBody, "ok");
    } catch {
      toast(F.errorTitle, F.errorBody, "error");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div role="status" className="rounded-[16px] border border-olive/30 bg-olive-soft/50 p-8">
        <p className="font-serif text-[28px] text-ink rtl:font-semibold">{F.successTitle}</p>
        <p className="mt-2 text-[16px] text-ink-2">{F.successBody}</p>
        <Link href={lh(locale, "/health-check")} className="mt-6 inline-flex items-center gap-2 text-[15px] font-medium text-terra-2 underline decoration-terra/40 underline-offset-4">
          {F.successCta} <Arrow size={15} />
        </Link>
      </div>
    );
  }

  const types = Object.entries(F.types) as [string, string][];
  return (
    <form onSubmit={submit} noValidate className="space-y-5">
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <div>
          <label htmlFor="wl-name" className={lbl}><span id="wl-name-l">{F.name}</span></label>
          <Input id="wl-name" autoComplete="name" value={v.name} onChange={set("name")} className="h-11 bg-[#FFFCF7]" />
        </div>
        <div>
          <label htmlFor="wl-email" className={lbl}><span id="wl-email-l">{F.email}</span> <span aria-hidden className="text-terra">*</span></label>
          <Input id="wl-email" type="email" dir="ltr" autoComplete="email" required value={v.email} onChange={set("email")} className="h-11 bg-[#FFFCF7] rtl:text-right" />
        </div>
        <div>
          <label htmlFor="wl-biz" className={lbl}><span id="wl-biz-l">{F.business}</span></label>
          <Input id="wl-biz" autoComplete="organization" value={v.business_name} onChange={set("business_name")} className="h-11 bg-[#FFFCF7]" />
        </div>
        <div>
          <label htmlFor="wl-type" className={lbl}><span id="wl-type-l">{F.type}</span></label>
          <Select id="wl-type" value={v.business_type} onChange={set("business_type")} className="h-11 w-full bg-[#FFFCF7]">
            <option value="">{F.typePlaceholder}</option>
            {types.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </Select>
        </div>
        <div className="sm:col-span-2">
          <label htmlFor="wl-city" className={lbl}><span id="wl-city-l">{F.city}</span></label>
          <Input id="wl-city" autoComplete="address-level2" placeholder={F.cityPlaceholder} value={v.city} onChange={set("city")} className="h-11 bg-[#FFFCF7]" />
        </div>
      </div>
      {err && <p role="alert" className={fieldErr}>{err}</p>}
      <Button type="submit" size="lg" loading={busy}>
        {F.submit} {!busy && <Arrow size={15} />}
      </Button>
    </form>
  );
}
