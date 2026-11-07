"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useRouter } from "@/lib/router";
import { useQueryClient } from "@tanstack/react-query";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";
import { api, getOrgId, setOrgId } from "@/lib/api";
import { useLocale } from "@/i18n";

export type Role = "owner" | "manager" | "accountant" | "cashier";
export type Org = { id: string; name: string; name_ar: string | null; industry: string; city: string | null; plan: string; role: Role; is_demo: boolean; branches: number };
export type Me = { id: string; email: string; full_name: string | null; locale: string; is_super_admin: boolean; orgs: Org[] };

type Ctx = {
  session: Session | null;
  me: Me | null;
  org: Org | null;
  role: Role | null;
  loading: boolean;
  switchOrg: (id: string) => void;
  refresh: () => Promise<Me | null>;
  signOut: () => Promise<void>;
  can: (min: Role) => boolean;
};

const RANK: Record<Role, number> = { cashier: 1, accountant: 2, manager: 3, owner: 4 };
const SessionCtx = createContext<Ctx | null>(null);

export function SessionProvider({ children, requireOrg = true }: { children: React.ReactNode; requireOrg?: boolean }) {
  const [session, setSession] = useState<Session | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [orgId, setOrg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();
  const locale = useLocale();
  const qc = useQueryClient();

  const refresh = useCallback(async () => {
    try {
      const m = await api<Me>("/me");
      setMe(m);
      let current = getOrgId();
      if (!current || !m.orgs.some((o) => o.id === current)) {
        current = m.orgs[0]?.id ?? null;
        setOrgId(current);
      }
      setOrg(current);
      return m;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    let alive = true;
    supabase().auth.getSession().then(async ({ data }) => {
      if (!alive) return;
      setSession(data.session);
      if (!data.session) {
        setLoading(false);
        router.replace(`/${locale}/login?next=${encodeURIComponent(pathname)}`);
        return;
      }
      let m = await refresh();
      for (let i = 0; !m && alive && i < 20; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        m = await refresh();
      }
      setLoading(false);
      if (m && requireOrg && m.orgs.length === 0) router.replace(`/${locale}/onboarding`);
    });
    const { data: sub } = supabase().auth.onAuthStateChange((_e, s) => setSession(s));
    return () => { alive = false; sub.subscription.unsubscribe(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const org = me?.orgs.find((o) => o.id === orgId) ?? null;
  const value: Ctx = {
    session, me, org, role: org?.role ?? null, loading, refresh,
    switchOrg: (id) => { setOrgId(id); setOrg(id); qc.clear(); router.push(`/${locale}/app`); },
    signOut: async () => { await supabase().auth.signOut(); setOrgId(null); qc.clear(); router.replace(`/${locale}/login`); },
    can: (min) => !!org && RANK[org.role] >= RANK[min],
  };
  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>;
}

export function useSession() {
  const c = useContext(SessionCtx);
  if (!c) throw new Error("useSession outside SessionProvider");
  return c;
}
