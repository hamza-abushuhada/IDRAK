// The one piece of browser state the redirect flow needs: what this tab asked
// the Lab for, so the return can be matched to it (state check, CSRF) and sent
// back to the server, which re-verifies intent + state against the signed-in
// user and business. Tab-scoped (sessionStorage), short-lived, read once.
const KEY = "idrak-connect-pending";
const LOYVERSE_KEY = "idrak-loyverse-pending";
const FLASH = "idrak-connect-flash";

export type Pending = { intent: string; state: string; org: string; user: string; expires_at: number };
export type Flash = { name: string; ok: boolean };

export function savePending(value: Pending, provider: "lab" | "loyverse" = "lab") {
  sessionStorage.setItem(provider === "loyverse" ? LOYVERSE_KEY : KEY, JSON.stringify(value));
}

/** Returns the pending request once and removes it, so a return can't be replayed. */
export function takePending(provider: "lab" | "loyverse" = "lab"): Pending | null {
  const key = provider === "loyverse" ? LOYVERSE_KEY : KEY;
  const raw = sessionStorage.getItem(key);
  sessionStorage.removeItem(key);
  try {
    const v = raw ? (JSON.parse(raw) as Pending) : null;
    if (!v || typeof v.intent !== "string" || typeof v.state !== "string" || typeof v.org !== "string" || typeof v.user !== "string") return null;
    if (typeof v.expires_at !== "number" || v.expires_at * 1000 < Date.now()) return null;
    return v;
  } catch { return null; }
}

export function setFlash(value: Flash) {
  sessionStorage.setItem(FLASH, JSON.stringify(value));
}

export function takeFlash(): Flash | null {
  const raw = sessionStorage.getItem(FLASH);
  sessionStorage.removeItem(FLASH);
  try { return raw ? (JSON.parse(raw) as Flash) : null; } catch { return null; }
}

/** The callback's parameters arrive in the URL fragment: never sent to a server or written to logs. */
export function readReturn(hash: string) {
  const p = new URLSearchParams(hash.replace(/^#/, ""));
  const code = p.get("code") || "", state = p.get("state") || "", error = p.get("error") || "";
  return {
    code: /^[A-Za-z0-9_-]{20,128}$/.test(code) ? code : "",
    state: /^[A-Za-z0-9_-]{43}$/.test(state) ? state : "",
    denied: error === "access_denied",
  };
}

export type OAuthDiag = { query: string[]; fragment: string[]; code: { present: boolean; length: number; classes: string[] } };

/** Raw query/fragment parsing: decodeURIComponent only, so a literal "+" in a code is
 *  never turned into a space (URLSearchParams would). No format is assumed for the
 *  vendor's authorization code beyond sane bounds; the server-side exchange decides. */
export function readOAuthReturn(search: string, hash: string) {
  const parse = (s: string) => {
    const out = new Map<string, string>();
    for (const part of s.replace(/^[?#]/, "").split("&")) {
      if (!part) continue;
      const i = part.indexOf("=");
      const k = i < 0 ? part : part.slice(0, i);
      const v = i < 0 ? "" : part.slice(i + 1);
      try { out.set(decodeURIComponent(k), decodeURIComponent(v)); } catch { out.set(k, ""); }
    }
    return out;
  };
  const q = parse(search), f = parse(hash);
  const raw = q.get("code") ?? f.get("code") ?? "";
  const state = q.get("state") ?? f.get("state") ?? "";
  const code = raw.length >= 1 && raw.length <= 4096 && !/[\s\u0000-\u001f\u007f]/.test(raw) ? raw : "";
  const classes = [/[A-Za-z]/.test(raw) && "letters", /\d/.test(raw) && "digits",
    ...Array.from(new Set(raw.replace(/[A-Za-z0-9]/g, "").split(""))).map((ch) => (/\s/.test(ch) ? "space" : ch))].filter(Boolean) as string[];
  const diag: OAuthDiag = { query: [...q.keys()], fragment: [...f.keys()], code: { present: raw.length > 0, length: raw.length, classes } };
  return { code, state: /^[A-Za-z0-9_-]{43}$/.test(state) ? state : "", denied: !!(q.get("error") ?? f.get("error")), diag };
}
