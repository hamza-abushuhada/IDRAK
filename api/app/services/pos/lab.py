"""موصّلات IDRAK Connect Lab — LabPOSAdapter و LabWebAdapter.

تربطان «مختبر إدراك التجريبي» (كاشير POS + متجر أونلاين، demo_server.py) بخطّ
مزامنة إدراك الحقيقي. تقرآن الأحداث التزايدية من واجهات المختبر الموثَّقة:

  GET {base_url}/api/pos/events?after=<seq>&limit=<n>   (الكاشير)
  GET {base_url}/api/web/events?after=<seq>&limit=<n>   (المتجر)

وتحوّلان كل حدث إلى model.Event موحّد. الهوية الثابتة = source.system +
account_id + order.external_id (مستقلّة عن connection_id)، فإعادة الربط لا
تُكرّر. تدعمان كذلك التحقّق من توقيع webhook (HMAC-SHA256) لمسار الدفع اللحظي.

منطق التحويل (map_payload) نقيّ وقابل للاختبار بلا شبكة؛ الجلب عبر urllib
بمهلة قصيرة (مصدر محلّي على 127.0.0.1 فقط).

قرار الحالات المالية:
  completed → بيع (sale)            | يُحتسب إيراداً + مخزون.
  refunded  → مرتجع (refund)        | يعكس الإيراد + يعيد المخزون.
  pending   → لا يُنشأ بيع            | لا إيراد (ينتظر حتى يكتمل أو يُلغى).
  cancelled → لا شيء (من pending)    | لا إيراد.
المخزون من أحداث inventory.updated (on_hand مطلق) فهو مرجع المختبر؛ لذلك
اتصالات المختبر تضبط config.sales_adjust_inventory=false فلا يُحسب مرّتين.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.request
from decimal import Decimal

try:  # يعمل كحزمة (داخل التطبيق) أو كوحدة مستقلّة (في الاختبار)
    from . import model, adapter
except ImportError:  # pragma: no cover
    import model, adapter  # type: ignore

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_SECRET = "idrak-local-demo-only-secret"  # نفس سرّ المختبر الافتراضي (محلّي فقط)
DEFAULT_BRANCH = "متجر التجربة"

# خريطة طرق الدفع: من مفردات المختبر إلى VALID_PAYMENTS في إدراك.
_PAYMENT_MAP = {"cash": "cash", "card": "card", "demo_card": "online", "cash_on_delivery": "cash"}


def _norm_ts(value: str) -> str:
    return (value or "").replace("Z", "+00:00")


def map_payload(payload: dict, branch: str = DEFAULT_BRANCH) -> "model.Event | None":
    """يحوّل حمولة حدث من المختبر إلى model.Event موحّد، أو None إذا كان الحدث
    لا يُنتج سجلّاً مالياً (طلب معلّق/ملغى). منطق نقيّ — بلا شبكة ولا قاعدة."""
    etype = payload.get("event_type")
    src = payload.get("source") or {}
    if etype in ("sale.created", "sale.updated"):
        order = payload.get("order") or {}
        status = order.get("status")
        external_id = order.get("external_id")
        rev = str(order.get("revision", "1"))
        if status == "completed":
            ev_type, sale_status = model.EVENT_SALE, "completed"
        elif status == "refunded":
            ev_type, sale_status = model.EVENT_REFUND, "returned"
        else:  # pending / cancelled: لا يُنشأ بيع
            return None
        lines = []
        for it in (order.get("items") or []):
            lines.append(model.SaleLine(
                product=model.ProductRef(name=it.get("name") or it.get("sku"), sku=it.get("sku")),
                quantity=Decimal(str(it.get("quantity", 0))),
                unit_price=Decimal(str(it.get("unit_price", "0"))),
                unit_cost=Decimal("0")))  # المختبر لا يرسل التكلفة
        sale = model.Sale(
            external_id=external_id, invoice_number=external_id,
            occurred_at=_norm_ts(order.get("updated_at") or payload.get("occurred_at") or ""),
            lines=lines, branch=branch, cashier=None,
            payment_method=_PAYMENT_MAP.get(order.get("payment_method"), "cash"),
            status=sale_status)
        return model.Event(type=ev_type, external_id=external_id,
                           occurred_at=sale.occurred_at, payload=sale, version=rev)
    if etype == "inventory.updated":
        inv = payload.get("inventory") or {}
        sku = inv.get("sku")
        ext = f"inv:{sku}"
        when = _norm_ts(payload.get("occurred_at") or "")
        return model.Event(
            type=model.EVENT_INVENTORY, external_id=ext, occurred_at=when,
            version=str(payload.get("source_sequence", "")),
            payload=model.InventoryMovement(
                external_id=ext, product=model.ProductRef(name=sku, sku=sku),
                branch=branch, delta=Decimal(str(inv.get("on_hand", 0))),
                occurred_at=when, reason="lab_inventory", absolute=True))
    return None  # نوع غير مدعوم: يُتجاهَل بأمان (لا يُسقِط الدفعة)


class _LabAdapter(adapter.POSAdapter):
    """أساس مشترك لموصّلَي المختبر. القناة (pos/web) تحدّد مسار الواجهة."""
    channel = "pos"
    implemented = True
    capabilities = adapter.Capabilities(
        initial_import=True, incremental=True, refunds=True, inventory=True, webhook=True)

    def __init__(self, base_url: str = DEFAULT_BASE_URL, secret: str = DEFAULT_SECRET,
                 branch: str = DEFAULT_BRANCH, transport=None):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.secret = secret or DEFAULT_SECRET
        self.branch = branch or DEFAULT_BRANCH
        self._transport = transport  # قابل للحقن في الاختبار: fn(url)->dict

    # -- الجلب عبر HTTP (مصدر محلّي؛ مهلة قصيرة) -------------------------
    def _get(self, after: int, limit: int = 100) -> dict:
        path = "pos" if self.channel == "pos" else "web"
        url = f"{self.base_url}/api/{path}/events?after={int(after)}&limit={int(limit)}"
        if self._transport is not None:
            return self._transport(url)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 (127.0.0.1 only)
            return json.loads(r.read() or "{}")

    def _pull(self, after: int) -> tuple[list, int]:
        """يسحب كل الصفحات بعد المؤشّر، ويُرجِع (أحداث، المؤشّر التالي)."""
        events: list = []
        cursor = int(after or 0)
        for _ in range(1000):  # سقف أمان ضدّ الحلقة اللانهائية
            data = self._get(cursor)
            rows = data.get("events") or []
            for row in rows:
                ev = map_payload(row.get("payload") or {}, branch=self.branch)
                if ev is not None:
                    events.append(ev)
            cursor = int(data.get("next_cursor", cursor))
            if not data.get("has_more"):
                break
        return events, cursor

    def initial_events(self, ctx: "adapter.AdapterContext | None" = None) -> list:
        events, _ = self._pull(0)
        return events

    def fetch_changes(self, ctx: "adapter.AdapterContext") -> tuple[list, dict]:
        after = int((ctx.cursor or {}).get("after", 0))
        events, nxt = self._pull(after)
        return events, {"after": nxt}

    # -- webhook: تحقّق التوقيع + التطبيع (مسار الدفع اللحظي) --------------
    def signature_for(self, body: bytes) -> str:
        return "sha256=" + hmac.new(self.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    def verify_webhook(self, headers: dict, body: bytes, secret: str = "") -> bool:
        provided = ""
        for k, v in (headers or {}).items():
            if k.lower() == "x-idrak-signature":
                provided = v or ""
                break
        return hmac.compare_digest(self.signature_for(body), provided)

    def normalize_webhook(self, body: bytes) -> "model.Event | None":
        payload = json.loads(body.decode("utf-8"))
        return map_payload(payload, branch=self.branch)

    @staticmethod
    def event_id_of(body: bytes) -> str:
        try:
            return str(json.loads(body.decode("utf-8")).get("event_id") or "")
        except Exception:
            return ""


class LabPOSAdapter(_LabAdapter):
    provider_code = "lab_pos"
    display_name = "IDRAK Lab — POS (test)"
    channel = "pos"


class LabWebAdapter(_LabAdapter):
    provider_code = "lab_web"
    display_name = "IDRAK Lab — Online store (test)"
    channel = "web"
