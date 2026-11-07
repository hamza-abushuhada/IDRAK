import json
import logging

from google import genai
from google.genai import types

from .. import db
from ..config import settings

log = logging.getLogger("idrak.ai")
_client: genai.Client | None = None

PRICE_IN, PRICE_OUT = 0.30, 2.50


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def track(org_id, user_id, model, kind, usage) -> None:
    try:
        it = (usage.prompt_token_count or 0) if usage else 0
        ot = ((usage.candidates_token_count or 0) + (getattr(usage, "thoughts_token_count", 0) or 0)) if usage else 0
        await db.execute("insert into ai_usage(org_id,user_id,model,kind,input_tokens,output_tokens,cost_usd) values($1,$2,$3,$4,$5,$6,$7)",
                         org_id, user_id, model, kind, it, ot, round(it * PRICE_IN / 1e6 + ot * PRICE_OUT / 1e6, 6))
    except Exception:
        pass


async def generate_json(prompt: str, system: str, org_id=None, user_id=None, kind="json") -> dict | list | None:
    if not settings.gemini_api_key:
        return None
    for model in (settings.gemini_model, settings.gemini_fallback_model):
        try:
            r = await client().aio.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", temperature=0.1))
            await track(org_id, user_id, model, kind, r.usage_metadata)
            return json.loads(r.text)
        except Exception as e:
            log.warning("gemini %s failed: %s", model, e)
    return None


MAPPING_SYSTEM = """You map spreadsheet columns from Jordanian small businesses (Arabic, English or mixed headers) to Idrak fields.
Allowed fields: invoice_number, date, branch, cashier, product, barcode, sku, category, quantity, unit_price, cost, total, discount,
payment_method, customer_name, phone, email, city, area, supplier, carton_price, pack_size, stock, expiry_date, updated_at, notes, gender.
Use null when no field fits. Each field can be used at most once. Look at sample values, not only headers.
Return JSON: {"columns": {"<header>": {"field": "<field or null>", "confidence": 0..1, "reason": "<short english>"}}}"""


async def map_columns(headers: list[str], samples: dict[str, list], org_id=None, user_id=None) -> dict | None:
    prompt = json.dumps({"headers": headers, "samples": {h: [str(v) for v in samples.get(h, [])[:6]] for h in headers}}, ensure_ascii=False)
    res = await generate_json(prompt, MAPPING_SYSTEM, org_id, user_id, "mapping")
    if isinstance(res, dict) and isinstance(res.get("columns"), dict):
        return res["columns"]
    return None
