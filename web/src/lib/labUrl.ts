// Where the "Open the Lab" link points. Mirrors the API's IDRAK_LAB_ORIGIN rules:
// unset → the published Lab; otherwise an exact HTTPS origin that is the published
// Lab or listed in NEXT_PUBLIC_LAB_ALLOWED_ORIGINS. Anything else hides the link
// rather than falling back to a different Lab.
export const DEFAULT_LAB_ORIGIN = "https://idrak-connect-lab.vercel.app";

const HOST_RE = /^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$/;
const RESERVED = [".localhost", ".local", ".internal", ".test", ".invalid", ".example", ".lan", ".home.arpa"];

export function canonicalLabOrigin(value: string): string | null {
  if (!value || value !== value.trim() || value.length > 300) return null;
  let url: URL;
  try { url = new URL(value); } catch { return null; }
  const host = url.hostname;
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) return null;
  if (url.pathname !== "/" || /[?#@]/.test(value.slice("https://".length))) return null;
  if (url.port !== "" || !HOST_RE.test(host) || host === "localhost" || RESERVED.some((s) => host.endsWith(s))) return null;
  // Top-level label must contain a letter: rejects IPv4 literals and shorthand like 127.1.
  if (!/[a-z]/.test(host.slice(host.lastIndexOf(".") + 1))) return null;
  return `https://${host}`;
}

export function resolveLabOrigin(configured: string | undefined, allowedList: string | undefined): string | null {
  if (!configured) return DEFAULT_LAB_ORIGIN;
  const origin = canonicalLabOrigin(configured);
  if (!origin) return null;
  const allowed = new Set([DEFAULT_LAB_ORIGIN]);
  for (const item of (allowedList || "").split(",").map((s) => s.trim()).filter(Boolean)) {
    const entry = canonicalLabOrigin(item);
    if (!entry) return null; // one bad entry fails closed
    allowed.add(entry);
  }
  return allowed.has(origin) ? origin : null;
}

// Literal references so Next.js inlines them at build time.
const LAB_ORIGIN = resolveLabOrigin(process.env.NEXT_PUBLIC_LAB_URL, process.env.NEXT_PUBLIC_LAB_ALLOWED_ORIGINS);
export const LAB_LOGIN_URL: string | null = LAB_ORIGIN ? `${LAB_ORIGIN}/login` : null;
