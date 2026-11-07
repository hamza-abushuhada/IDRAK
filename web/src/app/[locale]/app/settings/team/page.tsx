"use client";
import { useState } from "react";
import { Check, Copy, Mail, Trash2, X } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { useApiMutation, useApiQuery } from "@/lib/useApi";
import { date } from "@/lib/format";
import { AskIdrak, ErrorBox, PageHeader, Section, Table, type Col } from "@/components/app/kit";
import { useSession, type Role } from "@/components/app/session";
import { Badge, Button, Field, Input, Select } from "@/components/ui";
import { toast } from "@/components/ui/toast";
import SettingsNav from "@/components/workspace/SettingsNav";
import { RoleNote, ROLES, useRoleLabel } from "@/components/workspace/common";

type Member = { id: string; role: Role; created_at: string; email: string; full_name: string | null };
type Invite = { id: string; email: string; role: Role; status: string; created_at: string; expires_at: string };
type TeamResp = { members: Member[]; invites: Invite[]; my_role: Role };

const ROLE_TONE: Record<Role, "terra" | "olive" | "sky" | "neutral"> = { owner: "terra", manager: "olive", accountant: "sky", cashier: "neutral" };

export default function TeamPage() {
  const tx = useTx();
  const locale = useLocale();
  const roleLabel = useRoleLabel();
  const { me, can } = useSession();
  const owner = can("owner");
  const { data, error, refetch } = useApiQuery<TeamResp>("/team");

  const changeRole = useApiMutation<{ id: string; role: Role }>("PATCH", (b) => `/team/${b.id}`, {
    invalidate: ["/team"], errorTitle: tx("Couldn't change the role", "ما قدرنا نغيّر الصلاحية"),
    onSuccess: () => toast(tx("Role updated", "تغيّرت الصلاحية")),
  });
  const remove = useApiMutation<{ id: string }>("DELETE", (b) => `/team/${b.id}`, {
    invalidate: ["/team", "/org"], errorTitle: tx("Couldn't remove", "ما قدرنا نشيله"),
    onSuccess: () => toast(tx("Removed from the team", "انشال من الفريق")),
  });
  const revoke = useApiMutation<{ id: string }>("DELETE", (b) => `/team/invites/${b.id}`, {
    invalidate: ["/team"], errorTitle: tx("Couldn't revoke", "ما قدرنا نلغي الدعوة"),
    onSuccess: () => toast(tx("Invitation revoked", "انلغت الدعوة")),
  });

  const owners = data?.members.filter((m) => m.role === "owner").length ?? 0;

  const cols: Col<Member>[] = [
    {
      key: "full_name", label: tx("Member", "العضو"), render: (m) => (
        <div className="min-w-[180px]">
          <span className="font-medium text-ink">{m.full_name || m.email.split("@")[0]}{m.email === me?.email && <span className="ms-1.5 text-[12px] font-normal text-ink-3">({tx("you", "إنت")})</span>}</span>
          <span className="block text-[12px] text-ink-3" dir="ltr">{m.email}</span>
        </div>
      ),
    },
    {
      key: "role", label: tx("Role", "الصلاحية"), render: (m) => {
        const self = m.email === me?.email;
        const lastOwner = m.role === "owner" && owners <= 1;
        if (!owner || self || lastOwner) return <Badge tone={ROLE_TONE[m.role]}>{roleLabel(m.role)}</Badge>;
        return (
          <Select value={m.role} disabled={changeRole.isPending} aria-label={tx("Role", "الصلاحية")} className="h-8 text-[13px]"
            onChange={(e) => changeRole.mutate({ id: m.id, role: e.target.value as Role })}>
            {ROLES.map((r) => <option key={r.v} value={r.v}>{tx(r.en, r.ar)}</option>)}
          </Select>
        );
      },
    },
    { key: "created_at", label: tx("Joined", "انضم"), render: (m) => <span className="num whitespace-nowrap text-ink-2">{date(m.created_at, locale)}</span> },
    {
      key: "actions", label: "", align: "end", render: (m) => {
        const self = m.email === me?.email;
        const lastOwner = m.role === "owner" && owners <= 1;
        if (!owner || self) return null;
        return (
          <Button variant="ghost" size="sm" disabled={lastOwner || remove.isPending} title={lastOwner ? tx("Can't remove the last owner", "ما بنقدر نشيل آخر مالك") : undefined}
            onClick={() => { if (window.confirm(tx(`Remove ${m.full_name || m.email} from the team? They'll lose access right away.`, `أكيد بدك تشيل ${m.full_name || m.email} من الفريق؟ رح يفقد الوصول فوراً.`))) remove.mutate({ id: m.id }); }}>
            <Trash2 size={14} />{tx("Remove", "شيل")}
          </Button>
        );
      },
    },
  ];

  return (
    <div>
      <PageHeader
        eyebrow={tx("Admin · Settings", "الإدارة · الإعدادات")}
        title={tx("Team", "الفريق")}
        subtitle={tx("Invite the people you work with and choose what each can do.", "ادعِ الناس اللي بتشتغل معهم واختار شو كل واحد بيقدر يعمل.")}
        actions={<AskIdrak q={tx("What role should I give my branch supervisor?", "شو الصلاحية المناسبة لمشرف الفرع؟")} />}
      />
      <SettingsNav />

      {error ? <ErrorBox error={error} retry={refetch} /> : (
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            <Section id="members-list" title={tx("Members", "الأعضاء")} subtitle={data ? tx(`${data.members.length} people`, `${data.members.length} أشخاص`) : " "} bodyClass="p-0">
              <Table<Member> rows={data?.members} cols={cols} empty={tx("Just you so far.", "لحد هلّق إنت بس.")} />
            </Section>

            {!!data?.invites.length && (
              <Section title={tx("Pending invitations", "دعوات بالانتظار")} bodyClass="p-0">
                <ul className="divide-y divide-line/60">
                  {data.invites.map((i) => (
                    <li key={i.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
                      <div className="min-w-0">
                        <p className="flex items-center gap-2 text-[14px] text-ink"><Mail size={14} className="text-ink-3" /><span dir="ltr">{i.email}</span><Badge tone={ROLE_TONE[i.role]}>{roleLabel(i.role)}</Badge></p>
                        <p className="mt-0.5 text-[12px] text-ink-3">{tx("Sent", "انبعتت")} <span className="num">{date(i.created_at, locale)}</span> · {tx("expires", "بتنتهي")} <span className="num">{date(i.expires_at, locale)}</span></p>
                      </div>
                      {owner && (
                        <Button variant="ghost" size="sm" disabled={revoke.isPending} onClick={() => revoke.mutate({ id: i.id })}><X size={14} />{tx("Revoke", "ألغِ")}</Button>
                      )}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            <Section title={tx("What each role can do", "شو بتقدر تعمل كل صلاحية")} bodyClass="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-[13.5px]">
                  <tbody>
                    {ROLES.map((r) => (
                      <tr key={r.v} className="border-b border-line/60 last:border-0">
                        <td className="w-36 whitespace-nowrap px-5 py-3 align-top"><Badge tone={ROLE_TONE[r.v]}>{tx(r.en, r.ar)}</Badge></td>
                        <td className="px-5 py-3 text-ink-2">{tx(r.descEn, r.descAr)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          </div>

          <div>
            <InviteForm owner={owner} />
          </div>
        </div>
      )}
    </div>
  );
}

function InviteForm({ owner }: { owner: boolean }) {
  const tx = useTx();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("manager");
  const [result, setResult] = useState<{ link: string; email: string; ok: boolean } | null>(null);
  const [copied, setCopied] = useState(false);
  const invite = useApiMutation<{ email: string; role: Role }, { ok: boolean; link: string; email?: { ok?: boolean; delivered_to?: string[] } }>("POST", "/team/invite", {
    invalidate: ["/team"], errorTitle: tx("Couldn't send the invitation", "ما قدرنا نبعث الدعوة"),
    onSuccess: (r, b) => {
      const reached = !!r.email?.ok && (r.email.delivered_to || []).some((d) => d.toLowerCase() === b.email.toLowerCase());
      setResult({ link: r.link, email: b.email, ok: reached }); setEmail(""); setCopied(false);
    },
  });
  const copy = async () => {
    if (!result) return;
    try { await navigator.clipboard.writeText(result.link); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { toast(tx("Couldn't copy", "ما زبط النسخ"), tx("Select the link and copy it manually.", "حدّد الرابط وانسخه يدوي."), "error"); }
  };
  const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

  return (
    <Section id="invite-form" title={tx("Invite someone", "ادعِ حدا")} subtitle={tx("They'll get a link to join this business.", "رح يوصله رابط لينضم لهالمشروع.")}>
      {!owner ? (
        <RoleNote>{tx("Only the owner can invite people or change roles.", "بس المالك بيقدر يدعي ناس أو يغيّر الصلاحيات.")}</RoleNote>
      ) : (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (valid) invite.mutate({ email: email.trim(), role }); }}>
          <Field label={tx("Email", "الإيميل")}><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com" dir="ltr" required /></Field>
          <Field label={tx("Role", "الصلاحية")} hint={tx(ROLES.find((r) => r.v === role)!.descEn, ROLES.find((r) => r.v === role)!.descAr)}>
            <Select value={role} onChange={(e) => setRole(e.target.value as Role)} className="w-full">
              {ROLES.map((r) => <option key={r.v} value={r.v}>{tx(r.en, r.ar)}</option>)}
            </Select>
          </Field>
          <Button type="submit" loading={invite.isPending} disabled={!valid} className="w-full">{tx("Send invitation", "ابعث الدعوة")}</Button>
        </form>
      )}
      {result && (
        <div className="mt-5 rounded-xl border border-olive/30 bg-olive-soft/50 p-4">
          <p className="text-[13.5px] font-medium text-ink">{tx("Invitation created", "انعملت الدعوة")}</p>
          <p className="mt-1 text-[12.5px] text-ink-2">
            {result.ok
              ? tx(`We emailed ${result.email}. You can also share the link yourself:`, `بعتنا إيميل لـ ${result.email}. وبتقدر كمان تبعث الرابط بنفسك:`)
              : tx(`The email to ${result.email} may not arrive (our mail is in test mode), so share this link with them on WhatsApp:`, `ممكن الإيميل لـ ${result.email} ما يوصل (البريد عنا بوضع التجربة)، فابعتله هالرابط عالواتساب:`)}
          </p>
          <div className="mt-3 flex items-center gap-2">
            <input readOnly value={result.link} onFocus={(e) => e.currentTarget.select()} dir="ltr"
              className="h-9 min-w-0 flex-1 rounded-lg border border-line bg-paper px-2.5 font-mono text-[11.5px] text-ink-2 outline-none" />
            <Button type="button" size="sm" variant="secondary" onClick={copy}>{copied ? <Check size={14} className="text-olive" /> : <Copy size={14} />}{copied ? tx("Copied", "انتسخ") : tx("Copy", "انسخ")}</Button>
          </div>
        </div>
      )}
    </Section>
  );
}
