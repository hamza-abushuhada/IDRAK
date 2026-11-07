import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


class Settings:
    supabase_url = _env("SUPABASE_URL").rstrip("/")
    supabase_anon_key = _env("SUPABASE_ANON_KEY")
    supabase_service_key = _env("SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret = _env("SUPABASE_JWT_SECRET")
    supabase_ref = _env("SUPABASE_PROJECT_REF")
    gemini_api_key = _env("GEMINI_API_KEY")
    gemini_model = _env("GEMINI_MODEL", "gemini-3.5-flash")
    gemini_fallback_model = _env("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")
    resend_api_key = _env("RESEND_API_KEY")
    resend_from = _env("RESEND_FROM_EMAIL", "onboarding@resend.dev")
    web_url = _env("WEB_URL", "http://localhost:3000").rstrip("/")
    cors_origins = [o.strip() for o in _env("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        url = _env("DATABASE_URL")
        pw = _env("SUPABASE_DB_PASSWORD")
        if pw and (not url or "[YOUR-PASSWORD]" in url):
            if not url:
                url = (f"postgresql://postgres.{self.supabase_ref}:[YOUR-PASSWORD]"
                       f"@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres")
            url = url.replace("[YOUR-PASSWORD]", quote(pw, safe=""))
        return url


settings = Settings()
