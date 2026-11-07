"use client";
import AppShell from "@/components/app/AppShell";
import { SessionProvider } from "@/components/app/session";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider requireOrg={false}>
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
