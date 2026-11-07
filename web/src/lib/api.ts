"use client";
import { supabase } from "./supabase";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const ORG_KEY = "basira_org";
export const getOrgId = () => (typeof window === "undefined" ? null : localStorage.getItem(ORG_KEY));
export const setOrgId = (id: string | null) => {
  if (typeof window === "undefined") return;
  if (id) localStorage.setItem(ORG_KEY, id);
  else localStorage.removeItem(ORG_KEY);
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function headers(extra?: HeadersInit, json = true): Promise<Headers> {
  const h = new Headers(extra);
  const { data } = await supabase().auth.getSession();
  if (data.session) h.set("Authorization", `Bearer ${data.session.access_token}`);
  const org = getOrgId();
  if (org) h.set("X-Org-Id", org);
  if (json && !h.has("Content-Type")) h.set("Content-Type", "application/json");
  return h;
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const isForm = init.body instanceof FormData;
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
    headers: await headers(init.headers, !isForm),
  }).catch(() => { throw new ApiError(0, "network"); });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || msg; } catch {}
    throw new ApiError(res.status, typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("json") ? res.json() : res.text()) as Promise<T>;
}

export async function streamApi(path: string, body: unknown, onEvent: (e: Record<string, unknown>) => void, signal?: AbortSignal) {
  const res = await fetch(`${API_URL}${path}`, { method: "POST", body: JSON.stringify(body), headers: await headers(), signal });
  if (!res.ok || !res.body) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || msg; } catch {}
    throw new ApiError(res.status, msg);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data:")) {
          try { onEvent(JSON.parse(line.slice(5).trim())); } catch {}
        }
      }
    }
  }
}

export async function publicApi<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const isForm = init.body instanceof FormData;
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
    headers: isForm ? init.headers : { "Content-Type": "application/json", ...(init.headers || {}) },
  }).catch(() => { throw new ApiError(0, "network"); });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || msg; } catch {}
    throw new ApiError(res.status, msg);
  }
  return res.json();
}
