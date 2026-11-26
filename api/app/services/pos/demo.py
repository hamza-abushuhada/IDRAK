"""الموصّل المرجعي التجريبي — DemoPOSAdapter.

موصّل يعمل بالكامل ببيانات اصطناعية، يوضّح خطّ المزامنة الحقيقي من البداية
للنهاية دون أيّ مزوّد خارجي أو قاعدة إنتاج. مُعلَّم بوضوح كـ«تجريبي / Demo».
ليس تكاملاً مع NARD ولا أيّ مورّد حقيقي.

كلّ ما يُنتجه هو model.Event — نفس ما سيُنتجه موصّل حقيقي — فيمرّ على نفس
التطبيع والـ idempotency وقواعد الجودة. حتميّ (deterministic) بالكامل عبر
بذرة ثابتة، فالاختبارات تتحقّق من نفس المخرجات في كل مرّة.

يُغطّي السيناريوهات المطلوبة: استيراد أولي، بيع جديد، فاتورة محدَّثة،
مرتجع/إلغاء، تحديث صنف، حركة مخزون، تسليم مكرَّر، وحدث فاسد (فشل + تعافٍ)،
وحدث متأخّر (خارج الترتيب).
"""

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

try:  # يعمل كحزمة (داخل التطبيق) أو كوحدة مستقلّة (في الاختبار)
    from . import model, adapter
except ImportError:  # pragma: no cover
    import model, adapter  # type: ignore

AMMAN = model.AMMAN

# كتالوج تجريبي صغير (أصناف بقالة أردنية شائعة). الباركود/الـ SKU مُعلَّمة DEMO.
CATALOG = [
    # (sku, barcode, name_en, name_ar, cost, price, category)
    ("DEMO-SKU-001", "6251001000017", "Nabil Chicken 900g", "دجاج نبيل ٩٠٠غ", "3.250", "4.200", "Frozen"),
    ("DEMO-SKU-002", "6251002000024", "Hammoudeh Labneh 500g", "لبنة حمودة ٥٠٠غ", "1.100", "1.650", "Dairy"),
    ("DEMO-SKU-003", "6251003000031", "Al Durra Oil 1.5L", "زيت الدرة ١.٥ل", "2.400", "3.150", "Pantry"),
    ("DEMO-SKU-004", "6251004000048", "Nestle Water 1.5L", "مياه نستله ١.٥ل", "0.180", "0.350", "Beverages"),
    ("DEMO-SKU-005", "6251005000055", "Galaxy Chocolate 80g", "شوكولاتة جالاكسي ٨٠غ", "0.650", "1.000", "Snacks"),
    ("DEMO-SKU-006", "6251006000062", "Rummana Rice 1kg", "رز رمانة ١كغ", "0.900", "1.400", "Pantry"),
]
BRANCH_EN = "Demo Branch"
BRANCH_AR = "الفرع التجريبي"
CASHIER = "Demo Cashier"

# خريطة حالة البيع → نوع الحدث.
_SALE_EVENT_TYPE = {"completed": model.EVENT_SALE, "returned": model.EVENT_REFUND, "void": model.EVENT_SALE_VOID}


def _pref(item) -> "model.ProductRef":
    sku, barcode, en, ar, _cost, _price, cat = item
    return model.ProductRef(name=en, sku=sku, barcode=barcode, name_ar=ar, category=cat)


class DemoPOSAdapter(adapter.POSAdapter):
    provider_code = "demo"
    display_name = "Demo POS (synthetic)"
    implemented = True
    capabilities = adapter.Capabilities(
        initial_import=True, incremental=True, refunds=True, inventory=True, webhook=False)

    def __init__(self, seed: int = 20261124, now: dt.datetime | None = None):
        self.seed = seed
        # وقت ثابت افتراضيّاً لحتميّة الاختبار؛ الخطّ يمرّر الوقت الحقيقي.
        self.now = now or dt.datetime(2026, 11, 20, 12, 0, tzinfo=AMMAN)

    # -- الاستيراد الأولي: كتالوج + دفعة فواتير تاريخية --------------------
    def initial_events(self, ctx: "adapter.AdapterContext | None" = None) -> list:
        rng = random.Random(self.seed)
        events: list = []
        # 1) الأصناف أولاً (حتى تُربط بنود البيع بها).
        for item in CATALOG:
            events.append(self._product_event(item, version="1",
                                              when=self.now - dt.timedelta(days=30)))
        # 1ب) أرصدة افتتاحية للمخزون — حتى يكون المخزون "معروفاً" لا صفراً/مجهولاً،
        # وتعكس المبيعاتُ التاليةُ نقصَه بشكل صحيح. حركة واحدة لكل صنف (external_id
        # فريد) فتُطبَّق مرّة واحدة idempotently. كمية افتتاحية وافرة فيبقى الرصيد
        # موجباً بعد 14 يوم مبيعات.
        rngq = random.Random(self.seed + 777)
        opened_at = self.now - dt.timedelta(days=29)
        for item in CATALOG:
            qty = Decimal(rngq.randint(80, 160))
            eid = f"demo-open-{item[0]}"
            events.append(model.Event(
                type=model.EVENT_INVENTORY, external_id=eid, occurred_at=opened_at, version="1",
                payload=model.InventoryMovement(external_id=eid, product=_pref(item),
                                                branch=BRANCH_EN, delta=qty, occurred_at=opened_at,
                                                reason="opening")))
        # 2) فواتير تاريخية على مدى 14 يوماً.
        for d in range(14, 0, -1):
            day = self.now - dt.timedelta(days=d)
            for n in range(rng.randint(2, 4)):
                when = day.replace(hour=rng.randint(9, 21), minute=rng.randint(0, 59))
                events.append(self._sale_event(self._make_sale(rng, f"demo-inv-{d:02d}-{n}", when)))
        return events

    # -- المزامنة التزايدية: جولة سيناريوهات حسب المؤشّر ------------------
    def fetch_changes(self, ctx: "adapter.AdapterContext") -> tuple[list, dict]:
        rnd = int((ctx.cursor or {}).get("round", 0)) + 1
        events = self.script(rnd)
        return events, {"round": rnd, "at": self.now.isoformat()}

    def script(self, rnd: int) -> list:
        """يُنتج أحداث جولة تزايدية واحدة (حتميّ لكل رقم جولة).

        الجولة 1: بيع جديد + نفس البيع مكرّراً (idempotency).
        الجولة 2: تحديث فاتورة سابقة (نفس external_id، إصدار أحدث).
        الجولة 3: مرتجع (حالة returned) + تحديث صنف.
        الجولة 4: حركة مخزون + حدث فاسد (فشل + تعافٍ) + حدث متأخّر (خارج الترتيب).
        الجولات اللاحقة: بيع جديد واحد.
        """
        t = self.now + dt.timedelta(minutes=rnd * 7)
        out: list = []
        if rnd == 1:
            rng = random.Random(self.seed + rnd)
            ev = self._sale_event(self._make_sale(rng, "demo-inc-0001", t), version="1")
            out.append(ev)
            out.append(ev)  # تسليم مكرَّر حرفيّ → يجب أن يُتخطّى (idempotency)
        elif rnd == 2:
            # فاتورة محدَّثة: نفس المعرّف، بند إضافي، إصدار أحدث.
            base = self._make_sale(random.Random(self.seed + 1), "demo-inc-0001", t)
            base.lines.append(model.SaleLine(product=_pref(CATALOG[4]), quantity=Decimal("2"),
                                             unit_price=Decimal(CATALOG[4][5]), unit_cost=Decimal(CATALOG[4][4])))
            out.append(self._sale_event(base, version="2"))
        elif rnd == 3:
            # مرتجع: فاتورة بحالة returned.
            ref = self._make_sale(random.Random(self.seed + 3), "demo-ref-0001", t)
            ref.status = "returned"
            out.append(self._sale_event(ref, version="1"))
            # تحديث صنف: تغيّرت التكلفة والسعر.
            out.append(self._product_event(CATALOG[0], version="2", when=t,
                                           cost="3.400", price="4.300"))
        elif rnd == 4:
            # حركة مخزون.
            out.append(model.Event(
                type=model.EVENT_INVENTORY, external_id="demo-mv-0001", occurred_at=t, version="1",
                payload=model.InventoryMovement(external_id="demo-mv-0001", product=_pref(CATALOG[1]),
                                                branch=BRANCH_EN, delta=Decimal("-3"), occurred_at=t)))
            # حدث فاسد: طريقة دفع غير معروفة → يفشل التحقّق، يُسجَّل، ويكمل الباقي.
            bad = self._make_sale(random.Random(self.seed + 4), "demo-bad-0001", t)
            bad.payment_method = "giftcard"
            out.append(self._sale_event(bad, version="1"))
            # حدث متأخّر (خارج الترتيب): تحديث لفاتورة الجولة 1 بإصدار أقدم.
            stale = self._make_sale(random.Random(self.seed + 1), "demo-inc-0001", t)
            out.append(self._sale_event(stale, version="0"))
        else:
            rng = random.Random(self.seed + rnd)
            out.append(self._sale_event(self._make_sale(rng, f"demo-inc-{rnd:04d}", t), version="1"))
        return out

    # -- مولّدات الأحداث -------------------------------------------------
    def _sale_event(self, sale: "model.Sale", version: str = "1") -> "model.Event":
        return model.Event(type=_SALE_EVENT_TYPE[sale.status], external_id=sale.external_id,
                           occurred_at=sale.occurred_at, payload=sale, version=version)

    def _product_event(self, item, version: str, when, cost: str | None = None,
                       price: str | None = None) -> "model.Event":
        pr = _pref(item)
        eid = f"demo-prod-{item[0]}"
        return model.Event(
            type=model.EVENT_PRODUCT, external_id=eid, occurred_at=when, version=version,
            payload=model.ProductUpdate(external_id=eid, product=pr,
                                        cost=Decimal(cost or item[4]), price=Decimal(price or item[5])))

    def _make_sale(self, rng: random.Random, external_id: str, when: dt.datetime) -> "model.Sale":
        n = rng.randint(2, 4)
        items = rng.sample(CATALOG, n)
        lines = []
        for it in items:
            qty = Decimal(rng.randint(1, 4))
            lines.append(model.SaleLine(product=_pref(it), quantity=qty,
                                        unit_price=Decimal(it[5]), unit_cost=Decimal(it[4])))
        pay = rng.choice(["cash", "cash", "card", "cliq"])
        return model.Sale(
            external_id=external_id, invoice_number=external_id.upper(), occurred_at=when,
            lines=lines, branch=BRANCH_EN, cashier=CASHIER, payment_method=pay, status="completed")
