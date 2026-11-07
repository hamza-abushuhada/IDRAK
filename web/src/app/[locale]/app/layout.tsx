"use client";
import AppShell from "@/components/app/AppShell";
import { SessionProvider } from "@/components/app/session";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
