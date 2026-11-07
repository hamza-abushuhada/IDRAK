"use client";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { create } from "zustand";

type S = { active: boolean; start: () => void; done: () => void };
export const useNavProgress = create<S>((set) => ({
  active: false,
  start: () => set({ active: true }),
  done: () => set({ active: false }),
}));
export const startNavProgress = () => useNavProgress.getState().start();

function Watcher() {
  const pathname = usePathname();
  const search = useSearchParams();
  const done = useNavProgress((s) => s.done);
  useEffect(() => { done(); }, [pathname, search, done]);
  return null;
}

export default function NavProgress() {
  const active = useNavProgress((s) => s.active);
  const [width, setWidth] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as HTMLElement).closest("a");
      if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
      const href = a.getAttribute("href");
      if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) return;
      const url = new URL(href, window.location.href);
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;
      startNavProgress();
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, []);

  useEffect(() => {
    if (active) {
      setVisible(true);
      setWidth(12);
      const t = setInterval(() => setWidth((w) => (w < 90 ? w + Math.max(0.5, (90 - w) * 0.08) : w)), 200);
      return () => clearInterval(t);
    }
    if (visible) {
      setWidth(100);
      const t = setTimeout(() => { setVisible(false); setWidth(0); }, 350);
      return () => clearTimeout(t);
    }
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <Suspense fallback={null}><Watcher /></Suspense>
      <div aria-hidden className="pointer-events-none fixed inset-x-0 top-0 z-[200] h-[3px]" style={{ opacity: visible ? 1 : 0, transition: "opacity .3s" }}>
        <div className="h-full bg-terra shadow-[0_0_8px_rgba(194,89,58,.6)]"
          style={{ width: `${width}%`, transition: "width .25s ease-out", marginInlineStart: 0 }} />
      </div>
    </>
  );
}
