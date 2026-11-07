import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import app as fastapi_app


async def app(scope, receive, send):
    if scope.get("type") in ("http", "websocket") and scope.get("path", "").startswith("/api/index"):
        qs = parse_qsl((scope.get("query_string") or b"").decode(), keep_blank_values=True)
        vp = next((v for k, v in qs if k == "__vp"), None)
        if vp is not None:
            path = "/" + vp.lstrip("/")
            rest = urlencode([(k, v) for k, v in qs if k != "__vp"])
            scope = dict(scope, path=path, raw_path=path.encode(), query_string=rest.encode())
    await fastapi_app(scope, receive, send)
