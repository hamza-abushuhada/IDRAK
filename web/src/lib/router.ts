"use client";
import { useRouter as useNextRouter } from "next/navigation";
import { useMemo } from "react";
import { startNavProgress } from "@/components/NavProgress";

export function useRouter() {
  const r = useNextRouter();
  return useMemo(() => ({
    ...r,
    push: (href: string, opts?: Parameters<typeof r.push>[1]) => {
      if (typeof window !== "undefined") {
        const u = new URL(href, window.location.href);
        if (u.pathname + u.search !== window.location.pathname + window.location.search) startNavProgress();
      }
      r.push(href, opts);
    },
    replace: (href: string, opts?: Parameters<typeof r.replace>[1]) => {
      if (typeof window !== "undefined") {
        const u = new URL(href, window.location.href);
        if (u.pathname + u.search !== window.location.pathname + window.location.search) startNavProgress();
      }
      r.replace(href, opts);
    },
  }), [r]);
}
