// The one piece of browser state the redirect flow needs: what this tab asked
// the Lab for, so the return can be matched to it (state check, CSRF) and sent
// back to the server, which re-verifies intent + state against the signed-in
// user and business. Tab-scoped (sessionStorage), short-lived, read once.
const KEY = "idrak-connect-pending";
const FLASH = "idrak-connect-flash";

export type Pending = { intent: string; state: string; org: string; user: string; expires_at: number };
export type Flash = { name: string; ok: boolean };

export function savePending(value: Pending) {
  sessionStorage.setItem(KEY, JSON.stringify(value));
}

/** Returns the pending request once and removes it, so a return can't be replayed. */
export function takePending(): Pending | null {
  const raw = sessionStorage.getItem(KEY);
  sessionStorage.removeItem(KEY);
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
