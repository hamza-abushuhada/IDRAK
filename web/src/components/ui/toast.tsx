"use client";
import { create } from "zustand";
import { X } from "lucide-react";
import clsx from "clsx";

type Toast = { id: number; title: string; body?: string; tone?: "ok" | "error" | "info" };
type S = { toasts: Toast[]; push: (t: Omit<Toast, "id">) => void; drop: (id: number) => void };

export const useToasts = create<S>((set) => ({
  toasts: [],
  push: (t) => {
    const id = Date.now() + Math.random();
    set((s) => ({ toasts: [...s.toasts, { ...t, id }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })), 5200);
  },
  drop: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));

export const toast = (title: string, body?: string, tone: Toast["tone"] = "ok") => useToasts.getState().push({ title, body, tone });

export function Toaster() {
  const { toasts, drop } = useToasts();
  return (
    <div className="pointer-events-none fixed bottom-5 start-5 z-[100] flex w-[340px] max-w-[calc(100vw-2.5rem)] flex-col gap-2">
      {toasts.map((t) => (
        <div key={t.id} className={clsx("pointer-events-auto rounded-xl border bg-paper px-4 py-3 shadow-[var(--shadow-lift)]",
          t.tone === "error" ? "border-danger/40" : t.tone === "info" ? "border-sky/40" : "border-olive/40")}>
          <div className="flex items-start gap-3">
            <span className={clsx("mt-1.5 size-2 shrink-0 rounded-full", t.tone === "error" ? "bg-danger" : t.tone === "info" ? "bg-sky" : "bg-olive")} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink">{t.title}</p>
              {t.body && <p className="mt-0.5 text-xs text-ink-2">{t.body}</p>}
            </div>
            <button onClick={() => drop(t.id)} className="text-ink-3 hover:text-ink"><X size={14} /></button>
          </div>
        </div>
      ))}
    </div>
  );
}
