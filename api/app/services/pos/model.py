"""النموذج الداخلي الموحّد لأحداث نقاط البيع + أدوات التطبيع.

منطق نقيّ بالكامل: المكتبة القياسية فقط (dataclasses / decimal / datetime /
hashlib / json). لا يستورد أيّ وحدة من التطبيق ولا asyncpg، فيبقى قابلاً
للاستيراد والاختبار بـ `python -I` وحده.

الأرقام المالية تُمثَّل بـ Decimal وتُقرّب إلى 3 منازل (فلس JOD). الأوقات
تُطبَّع إلى UTC داخليّاً؛ عرض التاريخ المحلّي (توقيت عمّان) يتمّ عبر
amman_date في قاعدة البيانات تماماً كبقية النظام.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

AMMAN = dt.timezone(dt.timedelta(hours=3))

# أنواع الأحداث التي يفهمها خطّ المزامنة.
EVENT_SALE = "sale"            # فاتورة جديدة أو محدَّثة (مكتملة)
EVENT_SALE_VOID = "sale_void"  # إلغاء فاتورة سابقة
EVENT_REFUND = "refund"        # مرتجع (كلّي/جزئي) يُسجَّل كفاتورة بحالة returned
EVENT_PRODUCT = "product"      # تحديث صنف (سعر/تكلفة/اسم)
EVENT_INVENTORY = "inventory"  # حركة مخزون

EVENT_TYPES = frozenset({EVENT_SALE, EVENT_SALE_VOID, EVENT_REFUND, EVENT_PRODUCT, EVENT_INVENTORY})

VALID_PAYMENTS = frozenset({"cash", "card", "cliq", "wallet", "online"})


class InvalidEvent(ValueError):
    """حدث مصدر غير صالح. يُلتقط في خطّ المزامنة ويُسجَّل كخطأ قابل لإعادة
    المحاولة بدل أن يُسقِط الدفعة كاملةً."""


def q3(value) -> Decimal:
    """تقريب إلى 3 منازل (دقّة الدينار/الفلس)."""
    try:
        return Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidEvent(f"bad monetary value: {value!r}") from exc


def _to_utc(value) -> dt.datetime:
    """يقبل datetime أو ISO string، ويُرجِع datetime واعياً بالمنطقة بتوقيت UTC.
    القيمة بلا منطقة تُفترَض بتوقيت عمّان (مصدر محلّي)."""
    if isinstance(value, dt.datetime):
        d = value
    elif isinstance(value, str):
        try:
            d = dt.datetime.fromisoformat(value)
        except ValueError as exc:
            raise InvalidEvent(f"bad timestamp: {value!r}") from exc
    else:
        raise InvalidEvent(f"bad timestamp type: {type(value).__name__}")
    if d.tzinfo is None:
        d = d.replace(tzinfo=AMMAN)
    return d.astimezone(dt.timezone.utc)


@dataclass(frozen=True)
class ProductRef:
    """إشارة إلى صنف كما يعرفه المصدر، دون افتراض معرّف إدراك.
    التطبيع يطابقها بالباركود ثم بالاسم داخل المؤسسة، وينشئها إن لزم."""
    name: str
    sku: str | None = None
    barcode: str | None = None
    name_ar: str | None = None
    category: str | None = None

    def canonical(self) -> dict:
        return {"name": (self.name or "").strip(), "sku": (self.sku or "").strip() or None,
                "barcode": (self.barcode or "").strip() or None,
                "name_ar": (self.name_ar or "").strip() or None,
                "category": (self.category or "").strip() or None}


@dataclass
class SaleLine:
    product: ProductRef
    quantity: Decimal
    unit_price: Decimal
    unit_cost: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")

    def line_total(self) -> Decimal:
        return q3(self.quantity * self.unit_price - self.discount)

    def canonical(self) -> dict:
        return {"product": self.product.canonical(), "quantity": str(q3(self.quantity)),
                "unit_price": str(q3(self.unit_price)), "unit_cost": str(q3(self.unit_cost)),
                "discount": str(q3(self.discount)), "line_total": str(self.line_total())}


@dataclass
class Sale:
    external_id: str
    invoice_number: str
    occurred_at: dt.datetime
    lines: list[SaleLine]
    branch: str | None = None
    cashier: str | None = None
    customer_phone: str | None = None
    payment_method: str = "cash"
    discount: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    status: str = "completed"  # completed | returned | void

    def subtotal(self) -> Decimal:
        return q3(sum((l.line_total() for l in self.lines), Decimal("0")))

    def total(self) -> Decimal:
        return q3(self.subtotal() - self.discount + self.tax)

    def canonical(self) -> dict:
        return {"external_id": self.external_id, "invoice_number": self.invoice_number,
                "occurred_at": _to_utc(self.occurred_at).isoformat(),
                "branch": (self.branch or "").strip() or None,
                "cashier": (self.cashier or "").strip() or None,
                "customer_phone": (self.customer_phone or "").strip() or None,
                "payment_method": self.payment_method, "status": self.status,
                "discount": str(q3(self.discount)), "tax": str(q3(self.tax)),
                "lines": [l.canonical() for l in self.lines]}

    def validate(self) -> None:
        if not self.external_id:
            raise InvalidEvent("sale has no external_id")
        if not self.invoice_number:
            raise InvalidEvent("sale has no invoice_number")
        if self.payment_method not in VALID_PAYMENTS:
            raise InvalidEvent(f"unknown payment method: {self.payment_method!r}")
        if self.status not in ("completed", "returned", "void"):
            raise InvalidEvent(f"bad sale status: {self.status!r}")
        if not self.lines:
            raise InvalidEvent("sale has no line items")
        for l in self.lines:
            if l.quantity == 0:
                raise InvalidEvent("sale line has zero quantity")
            if not (l.product.name or l.product.barcode or l.product.sku):
                raise InvalidEvent("sale line has no product reference")


@dataclass
class ProductUpdate:
    external_id: str
    product: ProductRef
    cost: Decimal | None = None
    price: Decimal | None = None

    def canonical(self) -> dict:
        return {"external_id": self.external_id, "product": self.product.canonical(),
                "cost": None if self.cost is None else str(q3(self.cost)),
                "price": None if self.price is None else str(q3(self.price))}

    def validate(self) -> None:
        if not self.external_id:
            raise InvalidEvent("product update has no external_id")
        if not (self.product.name or self.product.barcode or self.product.sku):
            raise InvalidEvent("product update has no product reference")


@dataclass
class InventoryMovement:
    external_id: str
    product: ProductRef
    branch: str
    delta: Decimal
    occurred_at: dt.datetime
    reason: str = "pos_sync"
    absolute: bool = False  # True: delta هو الرصيد المطلق (set)، لا دلتا (add).

    def canonical(self) -> dict:
        return {"external_id": self.external_id, "product": self.product.canonical(),
                "branch": (self.branch or "").strip(), "delta": str(q3(self.delta)),
                "absolute": bool(self.absolute),
                "occurred_at": _to_utc(self.occurred_at).isoformat(), "reason": self.reason}

    def validate(self) -> None:
        if not self.external_id:
            raise InvalidEvent("inventory movement has no external_id")
        if not self.branch:
            raise InvalidEvent("inventory movement has no branch")
        if not (self.product.name or self.product.barcode or self.product.sku):
            raise InvalidEvent("inventory movement has no product reference")


@dataclass
class Event:
    """مظروف موحّد لحدث واحد من المصدر.

    version: طابع إصدار/تحديث من المصدر لمعالجة الأحداث خارج الترتيب — الحدث
    الأحدث يفوز. يُفضَّل ISO timestamp أو عدّاد تصاعدي كنص.
    """
    type: str
    external_id: str
    occurred_at: dt.datetime
    payload: Sale | ProductUpdate | InventoryMovement
    version: str = ""

    def entity(self) -> str:
        return {EVENT_SALE: "sales", EVENT_SALE_VOID: "sales", EVENT_REFUND: "sales",
                EVENT_PRODUCT: "products", EVENT_INVENTORY: "inventory_levels"}[self.type]

    def validate(self) -> None:
        if self.type not in EVENT_TYPES:
            raise InvalidEvent(f"unknown event type: {self.type!r}")
        if not self.external_id:
            raise InvalidEvent("event has no external_id")
        self.payload.validate()

    def content_hash(self) -> str:
        """بصمة مستقرّة لمحتوى الحدث. إعادة التسليم بنفس البصمة = تكرار
        يُتخطّى؛ بصمة مختلفة = تحديث فعلي."""
        body = {"type": self.type, "external_id": self.external_id, "payload": self.payload.canonical()}
        blob = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def version_key(self) -> str:
        """مفتاح الترتيب الزمني للأحداث خارج الترتيب."""
        if self.version:
            return self.version
        try:
            return _to_utc(self.occurred_at).isoformat()
        except InvalidEvent:
            return ""
