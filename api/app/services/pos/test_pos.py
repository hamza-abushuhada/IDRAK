"""اختبارات IDRAK Connect — المكتبة القياسية فقط (unittest)، بلا قاعدة
بيانات ولا شبكة ولا اعتماديّات خارجية.

تشغيل:
  python -I api/app/services/pos/test_pos.py
أو:
  python -I -m unittest discover -s api/app/services/pos -p 'test_*.py'

تغطّي: التطبيع ودقّة الدينار، الـ idempotency (التكرار)، الأحداث خارج
الترتيب، المرتجعات، رفض الحمولات الفاسدة، حتميّة الموصّل التجريبي،
المطابقة (reconciliation)، وعزل المستأجر/الصلاحيات بفحص المصدر.
"""

import os
import re
import sys
import unittest
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import model  # noqa: E402
import sync_logic  # noqa: E402
import demo  # noqa: E402
from model import (Event, Sale, SaleLine, ProductRef, ProductUpdate, InventoryMovement,  # noqa: E402
                   InvalidEvent, q3, EVENT_SALE, EVENT_REFUND, EVENT_PRODUCT, EVENT_INVENTORY)
import datetime as dt  # noqa: E402

AMMAN = model.AMMAN


def _line(sku, qty, price, cost="1.000"):
    return SaleLine(product=ProductRef(name=sku, sku=sku), quantity=Decimal(str(qty)),
                    unit_price=Decimal(str(price)), unit_cost=Decimal(str(cost)))


def _sale(eid="E1", status="completed", pay="cash", lines=None):
    return Sale(external_id=eid, invoice_number=eid, occurred_at=dt.datetime(2026, 11, 20, 10, 0, tzinfo=AMMAN),
                lines=lines or [_line("A", 2, "1.500"), _line("B", 1, "0.750")],
                branch="Demo Branch", cashier="C", payment_method=pay, status=status)


def _ev(sale, etype=EVENT_SALE, version="1"):
    return Event(type=etype, external_id=sale.external_id, occurred_at=sale.occurred_at, payload=sale, version=version)


class TestNormalizationAndMoney(unittest.TestCase):
    def test_jod_precision_three_places(self):
        self.assertEqual(q3("1.23456"), Decimal("1.235"))
        self.assertEqual(q3(2), Decimal("2.000"))

    def test_line_total_and_subtotal(self):
        s = _sale(lines=[_line("A", 2, "1.500"), _line("B", 1, "0.750")])
        self.assertEqual(s.lines[0].line_total(), Decimal("3.000"))
        self.assertEqual(s.subtotal(), Decimal("3.750"))
        self.assertEqual(s.total(), Decimal("3.750"))

    def test_line_discount_and_sale_tax(self):
        ln = SaleLine(product=ProductRef(name="A"), quantity=Decimal("2"), unit_price=Decimal("2.000"),
                      unit_cost=Decimal("1.000"), discount=Decimal("0.500"))
        self.assertEqual(ln.line_total(), Decimal("3.500"))  # 2*2 - 0.5
        s = _sale(lines=[ln])
        s.discount, s.tax = Decimal("0.250"), Decimal("0.400")
        self.assertEqual(s.total(), Decimal("3.650"))  # 3.5 - 0.25 + 0.4

    def test_timestamp_naive_assumed_amman(self):
        d = model._to_utc("2026-11-20T10:00:00")  # لا منطقة → عمّان (+3) → 07:00 UTC
        self.assertEqual(d.hour, 7)
        self.assertEqual(d.tzinfo, dt.timezone.utc)


class TestContentHash(unittest.TestCase):
    def test_same_content_same_hash(self):
        self.assertEqual(_ev(_sale()).content_hash(), _ev(_sale()).content_hash())

    def test_changed_content_changed_hash(self):
        a = _ev(_sale())
        b = _ev(_sale(lines=[_line("A", 3, "1.500")]))  # كمية مختلفة
        self.assertNotEqual(a.content_hash(), b.content_hash())

    def test_hash_ignores_version(self):
        self.assertEqual(_ev(_sale(), version="1").content_hash(), _ev(_sale(), version="9").content_hash())


class TestIdempotencyDecide(unittest.TestCase):
    def test_new_record_inserts(self):
        self.assertEqual(sync_logic.decide(None, "h1", "1"), sync_logic.INSERT)

    def test_duplicate_delivery_skipped(self):
        existing = sync_logic.ExistingRecord(content_hash="h1", source_version="1")
        self.assertEqual(sync_logic.decide(existing, "h1", "1"), sync_logic.SKIP_DUPLICATE)

    def test_newer_version_updates(self):
        existing = sync_logic.ExistingRecord(content_hash="h1", source_version="1")
        self.assertEqual(sync_logic.decide(existing, "h2", "2"), sync_logic.UPDATE)

    def test_out_of_order_stale_skipped(self):
        existing = sync_logic.ExistingRecord(content_hash="h2", source_version="2")
        self.assertEqual(sync_logic.decide(existing, "h0", "0"), sync_logic.SKIP_STALE)

    def test_duplicate_wins_over_version(self):
        # نفس البصمة = تكرار حتى لو الإصدار أقدم.
        existing = sync_logic.ExistingRecord(content_hash="h1", source_version="5")
        self.assertEqual(sync_logic.decide(existing, "h1", "1"), sync_logic.SKIP_DUPLICATE)

    def test_numeric_versions_compare_numerically(self):
        # عدّادات صحيحة: "12" أحدث من "8" (لا كسر معجميّ).
        existing = sync_logic.ExistingRecord(content_hash="h1", source_version="8")
        self.assertEqual(sync_logic.decide(existing, "h2", "12"), sync_logic.UPDATE)
        self.assertEqual(sync_logic.decide(existing, "h3", "9"), sync_logic.UPDATE)
        self.assertEqual(sync_logic.decide(existing, "h4", "7"), sync_logic.SKIP_STALE)

    def test_iso_versions_compare_lexically(self):
        existing = sync_logic.ExistingRecord(content_hash="h1", source_version="2026-11-20T10:00:00")
        self.assertEqual(sync_logic.decide(existing, "h2", "2026-11-20T11:00:00"), sync_logic.UPDATE)
        self.assertEqual(sync_logic.decide(existing, "h3", "2026-11-20T09:00:00"), sync_logic.SKIP_STALE)


class TestSyncCounts(unittest.TestCase):
    def test_counts_and_status(self):
        c = sync_logic.SyncCounts()
        c.record(sync_logic.INSERT)
        c.record(sync_logic.UPDATE)
        c.record(sync_logic.SKIP_DUPLICATE)
        self.assertEqual(c.as_dict(), {"imported": 1, "updated": 1, "skipped": 1, "failed": 0})
        self.assertEqual(c.status(), "success")
        c.failed = 1
        self.assertEqual(c.status(), "partial")
        c2 = sync_logic.SyncCounts(); c2.failed = 2
        self.assertEqual(c2.status(), "failed")


class TestReconcile(unittest.TestCase):
    def test_gap_detected(self):
        self.assertEqual(sync_logic.reconcile(10, 8), {"expected": 10, "present": 8, "missing": 2, "ok": False})

    def test_no_expectation(self):
        self.assertTrue(sync_logic.reconcile(None, 5)["ok"])

    def test_complete(self):
        self.assertTrue(sync_logic.reconcile(5, 5)["ok"])


class TestInvalidPayloadRejection(unittest.TestCase):
    def test_unknown_payment_rejected(self):
        with self.assertRaises(InvalidEvent):
            _ev(_sale(pay="giftcard")).validate()

    def test_empty_lines_rejected(self):
        s = _sale(); s.lines = []
        with self.assertRaises(InvalidEvent):
            _ev(s).validate()

    def test_missing_invoice_rejected(self):
        s = _sale(); s.invoice_number = ""
        with self.assertRaises(InvalidEvent):
            _ev(s).validate()

    def test_unknown_event_type_rejected(self):
        with self.assertRaises(InvalidEvent):
            Event(type="telepathy", external_id="X", occurred_at=dt.datetime.now(AMMAN), payload=_sale()).validate()

    def test_bad_monetary_rejected(self):
        with self.assertRaises(InvalidEvent):
            q3("not-a-number")


class TestDemoAdapter(unittest.TestCase):
    def setUp(self):
        self.a = demo.DemoPOSAdapter(seed=7)

    def test_initial_deterministic(self):
        h1 = [e.content_hash() for e in demo.DemoPOSAdapter(seed=7).initial_events()]
        h2 = [e.content_hash() for e in demo.DemoPOSAdapter(seed=7).initial_events()]
        self.assertEqual(h1, h2)
        self.assertGreater(len(h1), len(demo.CATALOG))  # أصناف + فواتير

    def test_initial_all_valid_and_products_first(self):
        events = self.a.initial_events()
        for e in events:
            e.validate()  # يجب ألا يرفع
        # قبل أول بيع: أصناف ثم أرصدة مخزون افتتاحية فقط (حتى تُربط البنود
        # ويكون المخزون معروفاً). كل حدث صنف يسبق أول بيع.
        first_sale = next(i for i, e in enumerate(events) if e.type == EVENT_SALE)
        self.assertTrue(all(events[i].type in (EVENT_PRODUCT, EVENT_INVENTORY) for i in range(first_sale)))
        last_product = max(i for i, e in enumerate(events) if e.type == EVENT_PRODUCT)
        self.assertLess(last_product, first_sale)

    def test_initial_has_opening_inventory_for_every_product(self):
        events = self.a.initial_events()
        opens = [e for e in events if e.type == EVENT_INVENTORY and e.external_id.startswith("demo-open-")]
        # رصيد افتتاحي واحد لكل صنف، بكمية موجبة، قبل أول بيع.
        self.assertEqual(len(opens), len(demo.CATALOG))
        for e in opens:
            self.assertGreater(e.payload.delta, Decimal("0"))
            self.assertEqual(e.payload.reason, "opening")

    def test_round1_duplicate_delivery(self):
        evs = self.a.script(1)
        self.assertEqual(len(evs), 2)
        self.assertEqual(evs[0].content_hash(), evs[1].content_hash())  # تكرار حرفيّ

    def test_round2_is_update_same_external_id(self):
        r1, r2 = self.a.script(1)[0], self.a.script(2)[0]
        self.assertEqual(r1.external_id, r2.external_id)       # نفس الفاتورة
        self.assertNotEqual(r1.content_hash(), r2.content_hash())  # محتوى مختلف
        self.assertGreater(r2.version_key(), r1.version_key())     # إصدار أحدث

    def test_round3_refund_and_product(self):
        evs = self.a.script(3)
        kinds = {e.type for e in evs}
        self.assertIn(EVENT_REFUND, kinds)
        self.assertIn(EVENT_PRODUCT, kinds)
        refund = next(e for e in evs if e.type == EVENT_REFUND)
        self.assertEqual(refund.payload.status, "returned")

    def test_round4_inventory_bad_and_stale(self):
        evs = self.a.script(4)
        self.assertIn(EVENT_INVENTORY, {e.type for e in evs})
        # حدث فاسد موجود ويفشل التحقّق.
        bad = [e for e in evs if e.external_id == "demo-bad-0001"]
        self.assertEqual(len(bad), 1)
        with self.assertRaises(InvalidEvent):
            bad[0].validate()
        # حدث متأخّر لفاتورة الجولة 1 بإصدار "0".
        stale = next(e for e in evs if e.external_id == "demo-inc-0001")
        self.assertEqual(stale.version_key(), "0")

    def test_stale_decided_against_prior_update(self):
        # محاكاة: بعد الجولة 2 (إصدار 2)، يصل الحدث المتأخّر من الجولة 4.
        r2 = self.a.script(2)[0]
        prior = sync_logic.ExistingRecord(content_hash=r2.content_hash(), source_version=r2.version_key())
        stale = next(e for e in self.a.script(4) if e.external_id == "demo-inc-0001")
        self.assertEqual(sync_logic.decide(prior, stale.content_hash(), stale.version_key()), sync_logic.SKIP_STALE)


class TestTenantIsolationAndAuthByConstruction(unittest.TestCase):
    """تُنفَّذ قراءة المصدر فقط (لا قاعدة بيانات). تضمن أن كل كتابة في الجداول
    القانونية مقيّدة بـ org_id، وأن مسارات الإدارة محميّة بالصلاحية الصحيحة —
    حارس انحدار لعزل المستأجر والتفويض."""

    def _read(self, *parts):
        with open(os.path.join(HERE, *parts), encoding="utf-8") as f:
            return f.read()

    def test_pipeline_scopes_canonical_writes_by_org(self):
        src = self._read("pipeline.py")
        # كل جملة تلمس sales/sale_items/products يجب أن تذكر org_id.
        for stmt in re.findall(r"(insert into (?:sales|sale_items|products)[^\"]*?\))", src, re.S):
            self.assertIn("org_id", stmt, f"canonical insert missing org_id: {stmt[:60]}")
        for stmt in re.findall(r"(delete from sales[^\"]*)", src):
            self.assertIn("org_id", stmt)
        # كل تحديث للمبيعات في الخطّ مقيّد بـ org_id.
        for stmt in re.findall(r"(update sales set [^\"]*)", src):
            self.assertIn("org_id", stmt, f"sales update missing org scope: {stmt[:70]}")

    def test_router_mutations_require_manage_integrations(self):
        src = self._read("..", "..", "routers", "integrations.py")
        for ep in ("create_connection", "sync_now", "disconnect"):
            m = re.search(rf"async def {ep}\(.*?\):", src, re.S)
            self.assertIsNotNone(m)
            self.assertIn('require("manage_integrations")', m.group(0), f"{ep} must require manage_integrations")

    def test_router_reads_require_view_dashboard(self):
        src = self._read("..", "..", "routers", "integrations.py")
        for ep in ("list_connections", "get_connection", "connection_jobs", "connection_errors", "providers"):
            m = re.search(rf"async def {ep}\(.*?\):", src, re.S)
            self.assertIsNotNone(m)
            self.assertIn('require("view_dashboard")', m.group(0))

    def test_no_secret_columns_selected_to_frontend(self):
        src = self._read("..", "..", "routers", "integrations.py")
        # credential_ref يجب ألا يظهر في أي select يُرجَع للواجهة.
        self.assertNotIn("credential_ref", re.sub(r"#.*", "", src).split("_CONN_COLS")[-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
