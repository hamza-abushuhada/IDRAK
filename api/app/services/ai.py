import json
import logging
import os

from google import genai
from google.genai import types

from .. import db
from ..config import settings

log = logging.getLogger("idrak.ai")
_client: genai.Client | None = None

PRICE_IN, PRICE_OUT = 0.30, 2.50

# سقف تكلفة الذكاء الاصطناعي لكل مؤسسة في اليوم (توقيت عمّان، بالدولار). يمنع
# عضواً واحداً من تضخيم فاتورة Gemini. مطبَّق عبر عدّاد ذرّي في جدول
# ai_budget_day (migration 006): الحجز والفحص بجملة واحدة ذرّية فلا تتجاوز
# الدفعات المتزامنة السقف. يصمد عبر نسخ Serverless. 0 = تعطيل الحدّ.
try:
    AI_DAILY_BUDGET_USD = float(os.getenv("AI_DAILY_BUDGET_USD", "3.0") or 0)
except ValueError:
    # قيمة بيئة غير رقمية يجب ألا تُسقط إقلاع الخدمة كلها (النشر تلقائي
    # للإنتاج). نرجع للافتراضي مع تحذير بدل تعطيل الـAPI بالكامل.
    log.warning("AI_DAILY_BUDGET_USD is not a number; falling back to 3.0")
    AI_DAILY_BUDGET_USD = 3.0

# مبلغ الحجز المؤقّت لكل طلب قيد التنفيذ. يجعل الطلبات المتزامنة ترى بعضها
# فتُرفَض عند بلوغ السقف، ثم يُحرَّر عند انتهاء الطلب بينما تبقى التكلفة
# الفعلية مسجّلة. قيمة صغيرة تكفي لعدّة محادثات نموذجية.
try:
    AI_RESERVE_USD = float(os.getenv("AI_RESERVE_USD", "0.05") or 0)
except ValueError:
    AI_RESERVE_USD = 0.05

# مفتاح اليوم للعدّاد: تاريخ عمّان الحالي.
_AMMAN_DAY = "(now() at time zone 'Asia/Amman')::date"


async def org_spend_today_usd(org_id) -> float:
    """مجموع تكلفة الذكاء الاصطناعي لهذه المؤسسة في آخر ٢٤ ساعة (المسار القديم)."""
    v = await db.fetchval(
        "select coalesce(sum(cost_usd), 0) from ai_usage"
        " where org_id=$1 and created_at > now() - interval '1 day'",
        org_id)
    return float(v or 0)


async def _over_budget_legacy(org_id) -> bool:
    """فحص تقريبي قديم على ai_usage، يُستخدم كتراجع لو جدول العدّاد غير موجود."""
    try:
        return await org_spend_today_usd(org_id) >= AI_DAILY_BUDGET_USD
    except Exception:
        # فشل الاستعلام لا يجوز أن يمنع المستخدم الشرعي: نفشل مفتوحاً.
        log.warning("budget check failed for org %s", org_id)
        return False


async def budget_reserve(org_id) -> bool:
    """يحجز حصّة ويفحص السقف ذرّياً. True = مسموح بالمتابعة، False = تجاوز.

    الجملة الواحدة ترفع المنفَق بمقدار الحجز فقط إذا كان المنفَق الحالي تحت
    السقف؛ الطلبات المتزامنة تتسلسل على قفل صفّ (org_id, day) فلا تمرّ كلها.
    """
    if AI_DAILY_BUDGET_USD <= 0:
        return True
    try:
        row = await db.fetchrow(
            f"""insert into ai_budget_day(org_id, day, spent_usd)
                values($1, {_AMMAN_DAY}, $2)
                on conflict (org_id, day) do update
                  set spent_usd = ai_budget_day.spent_usd + $2, updated_at = now()
                  where ai_budget_day.spent_usd < $3
                returning spent_usd""",
            org_id, AI_RESERVE_USD, AI_DAILY_BUDGET_USD)
        return row is not None
    except Exception:
        # جدول العدّاد غير موجود (migration لم تُطبَّق بعد) أو خطأ DB:
        # نرجع للفحص التقريبي حتى لا يُعطَّل الحدّ ولا نمنع مستخدماً شرعياً.
        return not await _over_budget_legacy(org_id)


async def budget_release(org_id) -> None:
    """يحرّر الحجز بعد انتهاء الطلب (التكلفة الفعلية سُجّلت عبر track)."""
    if AI_DAILY_BUDGET_USD <= 0:
        return
    try:
        await db.execute(
            f"""update ai_budget_day set spent_usd = greatest(0, spent_usd - $2)
                where org_id=$1 and day = {_AMMAN_DAY}""",
            org_id, AI_RESERVE_USD)
    except Exception:
        # تسرّب حجز نادر يجعل الحدّ يُفعَّل أبكر بقليل (اتجاه آمن) ويُصفَّر غداً.
        pass


async def over_daily_budget(org_id) -> bool:
    """هل بلغت المؤسسة سقف اليوم؟ يُقرأ من العدّاد، مع تراجع للمسار القديم."""
    if AI_DAILY_BUDGET_USD <= 0:
        return False
    try:
        v = await db.fetchval(
            f"select spent_usd from ai_budget_day where org_id=$1 and day = {_AMMAN_DAY}",
            org_id)
        if v is None:  # لا صفّ لليوم بعد → لم يُنفَق شيء
            return False
        return float(v) >= AI_DAILY_BUDGET_USD
    except Exception:
        return await _over_budget_legacy(org_id)


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def track(org_id, user_id, model, kind, usage) -> None:
    try:
        it = (usage.prompt_token_count or 0) if usage else 0
        ot = ((usage.candidates_token_count or 0) + (getattr(usage, "thoughts_token_count", 0) or 0)) if usage else 0
        cost = round(it * PRICE_IN / 1e6 + ot * PRICE_OUT / 1e6, 6)
        await db.execute("insert into ai_usage(org_id,user_id,model,kind,input_tokens,output_tokens,cost_usd) values($1,$2,$3,$4,$5,$6,$7)",
                         org_id, user_id, model, kind, it, ot, cost)
        if cost and org_id:
            # نُسجّل التكلفة الفعلية على العدّاد اليومي ذرّياً ليعكس الإنفاق الملتزم.
            await db.execute(
                f"""insert into ai_budget_day(org_id, day, spent_usd) values($1, {_AMMAN_DAY}, $2)
                    on conflict (org_id, day) do update
                      set spent_usd = ai_budget_day.spent_usd + $2, updated_at = now()""",
                org_id, cost)
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
Also allowed: minimum_stock, tax.
Use null when no field fits. Each field can be used at most once. Look at sample values, not only headers.
Return JSON: {"columns": {"<header>": {"field": "<field or null>", "confidence": 0..1, "reason": "<short english>"}}}"""


async def map_columns(headers: list[str], samples: dict[str, list], org_id=None, user_id=None) -> dict | None:
    prompt = json.dumps({"headers": headers, "samples": {h: [str(v) for v in samples.get(h, [])[:6]] for h in headers}}, ensure_ascii=False)
    res = await generate_json(prompt, MAPPING_SYSTEM, org_id, user_id, "mapping")
    if isinstance(res, dict) and isinstance(res.get("columns"), dict):
        return res["columns"]
    return None
