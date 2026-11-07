"use client";
import { create } from "zustand";

export type ToolLine = { id: string; name: string; label: string; args?: Record<string, unknown>; sql?: string | null; summary?: string; ok?: boolean; done?: boolean };
export type ChartSpec = { type: "bar" | "line" | "pie"; title: string; labels: string[]; series: { name: string; values: number[] }[] };
export type Block =
  | { kind: "text"; text: string }
  | { kind: "tool"; tool: ToolLine }
  | { kind: "chart"; spec: ChartSpec }
  | { kind: "nav"; path: string }
  | { kind: "highlight"; target: string; message: string }
  | { kind: "draft"; draft: { supplier_id: string | null; supplier: string; items: { product_id: string; product: string; product_ar?: string; quantity: number }[]; note?: string } }
  | { kind: "refused" }
  | { kind: "error"; text: string };
export type Msg = { id: string; role: "user" | "assistant"; text?: string; blocks: Block[]; streaming?: boolean };

type S = {
  open: boolean;
  msgs: Msg[];
  sessionId: string | null;
  pending: string | null;
  setOpen: (v: boolean) => void;
  toggle: () => void;
  ask: (q: string) => void;
  takePending: () => string | null;
  reset: () => void;
  set: (fn: (s: S) => Partial<S>) => void;
};

export const useAssistant = create<S>((set, get) => ({
  open: false,
  msgs: [],
  sessionId: null,
  pending: null,
  setOpen: (v) => set({ open: v }),
  toggle: () => set({ open: !get().open }),
  ask: (q) => set({ open: true, pending: q }),
  takePending: () => { const p = get().pending; set({ pending: null }); return p; },
  reset: () => set({ msgs: [], sessionId: null }),
  set: (fn) => set(fn(get())),
}));
