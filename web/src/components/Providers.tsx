"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { I18nProvider } from "@/i18n";
import type { Locale } from "@/i18n/config";
import { Toaster } from "@/components/ui/toast";
import NavProgress from "@/components/NavProgress";

export default function Providers({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  const [qc] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: 1, refetchOnWindowFocus: false } } }));
  return (
    <I18nProvider locale={locale}>
      <QueryClientProvider client={qc}>
        <NavProgress />
        {children}
        <Toaster />
      </QueryClientProvider>
    </I18nProvider>
  );
}
