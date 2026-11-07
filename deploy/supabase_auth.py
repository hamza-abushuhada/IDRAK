import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
E = {}
for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        E[k.strip()] = v.strip()
web = (sys.argv[1] if len(sys.argv) > 1 else "").rstrip("/")
url = f"https://api.supabase.com/v1/projects/{E['SUPABASE_PROJECT_REF']}/config/auth"
H = {"Authorization": f"Bearer {E['SUPABASE_ACCESS_TOKEN']}"}
cur = httpx.get(url, headers=H, timeout=30).json()
allow = set(filter(None, (cur.get("uri_allow_list") or "").split(",")))
allow |= {"http://localhost:3000/**"} | ({f"{web}/**"} if web else set())
body = {"uri_allow_list": ",".join(sorted(allow))}
if web:
    body["site_url"] = web
if E.get("GOOGLE_CLIENT_ID") and E.get("GOOGLE_CLIENT_SECRET"):
    body.update({"external_google_enabled": True, "external_google_client_id": E["GOOGLE_CLIENT_ID"], "external_google_secret": E["GOOGLE_CLIENT_SECRET"]})
r = httpx.patch(url, headers=H, json=body, timeout=30)
print("supabase auth:", r.status_code, "ok" if r.status_code < 300 else r.text[:300])
after = httpx.get(url, headers=H, timeout=30).json()
print({k: after.get(k) for k in ("site_url", "uri_allow_list", "external_google_enabled")})
