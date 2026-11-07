import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
API_PROJECT, WEB_PROJECT = "idrak-api", "idrak-web"


def load_env() -> dict:
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


E = load_env()
TOKEN = E.get("VERCEL_TOKEN") or sys.exit("VERCEL_TOKEN missing in .env")
H = {"Authorization": f"Bearer {TOKEN}"}
API = "https://api.vercel.com"


def team_qs() -> str:
    return f"?teamId={E['VERCEL_TEAM_ID']}" if E.get("VERCEL_TEAM_ID") else ""


def ensure_project(name: str, framework: str | None, root_settings: dict) -> dict:
    r = httpx.get(f"{API}/v9/projects/{name}{team_qs()}", headers=H, timeout=30)
    if r.status_code == 200:
        return r.json()
    body = {"name": name, **({"framework": framework} if framework else {}), **root_settings}
    r = httpx.post(f"{API}/v10/projects{team_qs()}", headers=H, json=body, timeout=30)
    r.raise_for_status()
    print(f"  created project {name}")
    return r.json()


def set_env(project: str, values: dict, targets=("production", "preview")):
    body = [{"key": k, "value": v, "type": "encrypted", "target": list(targets)} for k, v in values.items() if v]
    sep = "&" if team_qs() else "?"
    r = httpx.post(f"{API}/v10/projects/{project}/env{team_qs()}{sep}upsert=true", headers=H, json=body, timeout=60)
    if r.status_code >= 300:
        sys.exit(f"  env update failed for {project}: {r.status_code} {r.text[:300]}")
    print(f"  {project}: {len(body)} environment variables set")


def deploy(folder: Path, project: str) -> str:
    cmd = ["npx", "--yes", "vercel@latest", "deploy", "--prod", "--yes", "--token", TOKEN, "--cwd", str(folder)]
    if E.get("VERCEL_TEAM_ID"):
        cmd += ["--scope", E["VERCEL_TEAM_ID"]]
    (folder / ".vercel").mkdir(exist_ok=True)
    proj = httpx.get(f"{API}/v9/projects/{project}{team_qs()}", headers=H, timeout=30).json()
    (folder / ".vercel" / "project.json").write_text(json.dumps({"projectId": proj["id"], "orgId": proj["accountId"]}))
    print(f"  deploying {project} … (this takes a few minutes)")
    p = subprocess.run(cmd, capture_output=True, text=True, shell=os.name == "nt", encoding="utf-8", errors="replace")
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    if p.returncode != 0:
        print(out.replace(TOKEN, "***")[-3000:])
        sys.exit(f"  deploy of {project} failed")
    return production_url(project)


def production_url(project: str) -> str:
    r = httpx.get(f"{API}/v9/projects/{project}/domains{team_qs()}", headers=H, timeout=30)
    if r.status_code == 200:
        names = [d["name"] for d in r.json().get("domains", [])]
        custom = [n for n in names if not n.endswith(".vercel.app")]
        vercel = sorted([n for n in names if n.endswith(".vercel.app")], key=len)
        if custom or vercel:
            return f"https://{(custom or vercel)[0]}"
    return f"https://{project}.vercel.app"


def main():
    pw = E.get("SUPABASE_DB_PASSWORD", "")
    ref = E["SUPABASE_PROJECT_REF"]
    db_url = f"postgresql://postgres.{ref}:{quote(pw, safe='')}@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"

    print("1/4 API project")
    ensure_project(API_PROJECT, None, {})
    web_url = f"https://{WEB_PROJECT}.vercel.app"
    set_env(API_PROJECT, {
        "DATABASE_URL": db_url,
        "SUPABASE_URL": E["SUPABASE_URL"], "SUPABASE_ANON_KEY": E["SUPABASE_ANON_KEY"], "SUPABASE_SERVICE_ROLE_KEY": E["SUPABASE_SERVICE_ROLE_KEY"],
        "SUPABASE_JWT_SECRET": E.get("SUPABASE_JWT_SECRET", ""), "SUPABASE_PROJECT_REF": ref,
        "GEMINI_API_KEY": E.get("GEMINI_API_KEY", ""), "RESEND_API_KEY": E.get("RESEND_API_KEY", ""),
        "RESEND_FROM_EMAIL": E.get("RESEND_FROM_EMAIL", "onboarding@resend.dev"), "RESEND_TEST_RECIPIENT": E.get("RESEND_TEST_RECIPIENT", ""),
        "WEB_URL": web_url, "CORS_ORIGINS": f"{web_url},http://localhost:3000",
    })
    print("2/4 deploy API")
    api_url = deploy(ROOT / "api", API_PROJECT)
    h = httpx.get(f"{api_url}/health", timeout=60)
    print(f"  API health: {h.status_code} {h.text[:80]}")

    print("3/4 web project")
    ensure_project(WEB_PROJECT, "nextjs", {})
    set_env(WEB_PROJECT, {"NEXT_PUBLIC_SUPABASE_URL": E["SUPABASE_URL"], "NEXT_PUBLIC_SUPABASE_ANON_KEY": E["SUPABASE_ANON_KEY"], "NEXT_PUBLIC_API_URL": api_url})
    print("4/4 deploy web")
    actual_web = deploy(ROOT / "web", WEB_PROJECT)
    if actual_web != web_url:
        web_url = actual_web
        set_env(API_PROJECT, {"WEB_URL": web_url, "CORS_ORIGINS": f"{web_url},http://localhost:3000"})
        deploy(ROOT / "api", API_PROJECT)
    r = httpx.get(f"{web_url}/en", timeout=60, follow_redirects=True)
    print(f"  website: {r.status_code} {web_url}")
    print(json.dumps({"web": web_url, "api": api_url}))


if __name__ == "__main__":
    main()
