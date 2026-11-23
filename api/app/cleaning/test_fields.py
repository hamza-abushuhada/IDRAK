"""Tests for column auto-mapping and file-type detection (cleaning/fields.py).

Run from api/:  python -m unittest app.cleaning.test_fields

No DB or model needed. The restaurant cases come from a real client export
(POS sales, menu/inventory, supplier purchases, waste log) where the old matcher
let generic synonyms win and read purchase and waste logs as sales.
"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

from app.cleaning import engine, referee
from app.cleaning.fields import (ENTITY_KEY, auto_map, detect_entity, entity_check, entity_state, field_signature,
                                 guess_field, missing_for)
from app.routers import data
from app.services import ai


def fields_of(headers):
    return {h: m["field"] for h, m in auto_map(headers).items()}


def entity_of(headers):
    m = auto_map(headers)
    return detect_entity({v["field"] for v in m.values() if v["field"]}, headers)


class SpecificSynonymWins(unittest.TestCase):
    """A synonym that covers more of the header beats a generic one."""

    def test_expiry_beats_date(self):
        self.assertEqual(guess_field("تاريخ الانتهاء للصلاحية")[0], "expiry_date")

    def test_stock_beats_quantity(self):
        self.assertEqual(guess_field("الكمية المتوفرة بالمخزون")[0], "stock")

    def test_supplier_name_is_not_a_customer(self):
        self.assertEqual(guess_field("اسم المورد")[0], "supplier")

    def test_item_code_is_sku_not_product(self):
        self.assertEqual(guess_field("كود الصنف / المادة")[0], "sku")

    def test_minimum_stock(self):
        self.assertEqual(guess_field("الحد الأدنى للطلب")[0], "minimum_stock")

    def test_fuzzy_never_scores_as_exact(self):
        f, conf = guess_field("تاريخ الانتهاء للصلاحية")
        self.assertLess(conf, 1.0)


class ConflictResolution(unittest.TestCase):

    def test_exact_header_wins_over_fuzzy_one(self):
        m = fields_of(["حالة الدفع", "طريقة الدفع"])
        self.assertEqual(m["طريقة الدفع"], "payment_method")
        self.assertIsNone(m["حالة الدفع"])

    def test_separate_time_column_becomes_sale_time(self):
        m = fields_of(["التاريخ", "الوقت"])
        self.assertEqual((m["التاريخ"], m["الوقت"]), ("date", "sale_time"))

    def test_time_before_date_still_gives_date_to_the_date_column(self):
        m = fields_of(["Time", "Date"])
        self.assertEqual((m["Date"], m["Time"]), ("date", "sale_time"))

    def test_lone_time_column_is_still_the_date(self):
        # Some systems export one "Time" column holding the full datetime.
        self.assertEqual(fields_of(["Time", "Item", "Qty"])["Time"], "date")


class RestaurantExport(unittest.TestCase):
    SALES = ["رقم الطلب", "التاريخ", "الوقت", "الفرع", "الكاشير", "نوع الطلب", "رقم الطاولة",
             "اسم الوجبة / الصنف", "الفئة", "الكمية", "سعر الوجبة", "التكلفة التقديرية", "الإجمالي",
             "الخصم", "الضريبة (16%)", "طريقة الدفع", "اسم الزبون", "هاتف الزبون", "ملاحظات وتعديلات الزبون"]
    MENU = ["كود الصنف / المادة", "اسم الصنف أو المادة الأولية", "النوع (وجبة جاهزة / مادة أولية)", "الفئة",
            "وحدة القياس", "تكلفة الوحدة", "سعر البيع للزبون", "هامش الربح التقديري",
            "الكمية المتوفرة بالمخزون", "الحد الأدنى للطلب", "المورد الافتراضي", "تاريخ الانتهاء للصلاحية", "ملاحظات"]
    PURCHASES = ["رقم فاتورة المورد", "تاريخ الشراء", "الفرع المستلم", "اسم المورد", "المادة الموردة",
                 "سعر الوحدة / الكرتونة", "سعر الحبة المفردة", "الكمية الموردة", "الإجمالي المحسوب",
                 "ضريبة المبيعات", "حالة الدفع", "طريقة الدفع", "رقم سند القبض", "ملاحظات الفحص والاستلام"]
    WASTE = ["رقم تقرير الهدر", "التاريخ", "الوقت", "الفرع", "المسؤول / الشيف", "الصنف أو المادة التالفة",
             "الكمية التالفة / المهدورة", "وحدة القياس", "تكلفة الوحدة التقديرية", "إجمالي الخسارة المالية (د.ا)",
             "سبب الهدر والتلف الرئيسي", "تصنيف نوع الهدر", "الإجراء التصحيحي المتخذ", "معتمد من مدير الصالة"]

    def test_sales_maps_order_number_time_and_phone(self):
        m = fields_of(self.SALES)
        self.assertEqual(m["رقم الطلب"], "invoice_number")
        self.assertEqual(m["الوقت"], "sale_time")
        self.assertEqual(m["هاتف الزبون"], "phone")
        self.assertEqual(m["اسم الزبون"], "customer_name")
        self.assertEqual(entity_of(self.SALES), "sales")

    def test_menu_inventory_is_a_product_catalog(self):
        m = fields_of(self.MENU)
        self.assertEqual((m["كود الصنف / المادة"], m["اسم الصنف أو المادة الأولية"]), ("sku", "product"))
        self.assertEqual(m["الكمية المتوفرة بالمخزون"], "stock")
        self.assertEqual(m["تاريخ الانتهاء للصلاحية"], "expiry_date")
        self.assertEqual(entity_of(self.MENU), "products")

    def test_supplier_purchases_are_never_sales(self):
        m = fields_of(self.PURCHASES)
        self.assertEqual(m["اسم المورد"], "supplier")
        self.assertNotIn("customer_name", m.values())
        self.assertEqual(entity_of(self.PURCHASES), "supplier_prices")

    def test_waste_log_is_never_sales(self):
        self.assertEqual(entity_of(self.WASTE), "unknown")


class NoRegressions(unittest.TestCase):

    def test_english_pos_export(self):
        h = ["Invoice No", "Date", "Item", "Qty", "Unit Price", "Total", "Payment Method", "Cashier", "Branch"]
        m = fields_of(h)
        self.assertEqual([m[x] for x in h], ["invoice_number", "date", "product", "quantity", "unit_price",
                                              "total", "payment_method", "cashier", "branch"])
        self.assertEqual(entity_of(h), "sales")

    def test_sales_with_a_supplier_column_stay_sales(self):
        h = ["Invoice No", "Date", "Item", "Qty", "Price", "Cashier", "Supplier"]
        self.assertEqual(entity_of(h), "sales")

    def test_customer_list(self):
        self.assertEqual(entity_of(["الاسم", "رقم الهاتف", "المدينة"]), "customers")

    def test_detect_entity_without_headers_is_unchanged(self):
        self.assertEqual(detect_entity({"product", "quantity", "date"}), "sales")
        self.assertEqual(detect_entity({"supplier", "product", "carton_price"}), "supplier_prices")


def _ean13(body12: str) -> str:
    # Independent of profile._gtin_ok: weights counted from the left (1,3,1,3…).
    s = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body12))
    return body12 + str((10 - s % 10) % 10)


PHONES = ["+962 79 100 1601", "0791234567", "00962781790528", "962772437391", "+962-77-927-5018",
          "0785551234", "+962 79 584 7321", "0771112233"]
TIMES = ["19:26", "17:32", "23:33", "21:37", "08:05", "12:00", "14:45", "10:10"]
PAYMENTS = ["كاش", "CLIQ", "نقدي", "visa", "كاش", "محفظة", "cash", "كليك"]
DATES = ["08/02/2026", "18/10/2025", "2025-12-26", "03/21/2025", "12-11-26", "2026-01-05", "15/03/2026", "2026-02-11"]
ITEMS = ["شاورما دجاج", "فلافل", "حمص", "برجر", "سلطة سيزر", "بطاطا", "متبل", "كنافة"]


def _rows(*cols):
    return [list(r) for r in zip(*cols)]


class ValueEvidence(unittest.TestCase):
    """The values are a second witness next to the header (profile.py)."""

    def test_unknown_headers_are_recovered_from_values_and_flagged(self):
        m = auto_map(["A", "B", "C", "D"], _rows(ITEMS, PHONES, TIMES, PAYMENTS))
        self.assertEqual([m[h]["field"] for h in "BCD"], ["phone", "sale_time", "payment_method"])
        for h in "BCD":
            self.assertTrue(m[h]["review"], h)
            self.assertEqual(m[h]["source"], "values")
            self.assertEqual(m[h]["evidence"]["type"], "discovered")

    def test_mislabelled_columns_are_corrected(self):
        h = ["رقم الفاتورة", "يوم العملية", "التاريخ", "الصنف", "الكمية", "اسم العميل"]
        m = auto_map(h, _rows([str(50000 + i) for i in range(8)], DATES, TIMES, ITEMS, ["1"] * 8, PHONES))
        self.assertEqual(m["التاريخ"]["field"], "sale_time")      # a "date" column full of times
        self.assertEqual(m["يوم العملية"]["field"], "date")       # the real dates, found from values
        self.assertEqual(m["اسم العميل"]["field"], "phone")       # a "name" column full of phones
        self.assertTrue(all(m[x]["review"] for x in ("التاريخ", "يوم العملية", "اسم العميل")))

    def test_header_contradicted_by_values_is_flagged_not_trusted(self):
        m = auto_map(["Phone", "Qty"], _rows(ITEMS, ["1"] * 8))
        self.assertEqual(m["Phone"]["field"], "phone")
        self.assertTrue(m["Phone"]["review"])
        self.assertEqual(m["Phone"]["evidence"]["type"], "mismatch")

    def test_partly_unknown_payment_methods_ask_for_review(self):
        m = auto_map(["طريقة الدفع"], [["شيك"], ["كاش"], ["شيك"], ["CLIQ"], ["شيك مؤجل"], ["كاش"], ["شيك"], ["نقدي"]])
        self.assertTrue(m["طريقة الدفع"]["review"])

    def test_clean_well_named_file_needs_no_review(self):
        h = ["Invoice No", "Date", "Item", "Qty", "Total", "Payment Method"]
        m = auto_map(h, _rows([str(i) for i in range(8)], DATES, ITEMS, ["2"] * 8, ["3.5"] * 8, PAYMENTS))
        self.assertEqual([x for x in h if m[x]["review"]], [])

    def test_order_numbers_are_not_mistaken_for_dates_or_phones(self):
        # 5-digit ids parse as Excel serial dates; 8-digit ids parse as landlines.
        m = auto_map(["رقم الطلب", "Ref", "Ref2"],
                     _rows([str(50001 + i) for i in range(8)], [str(50001 + i) for i in range(8)],
                           [str(50001234 + i) for i in range(8)]))
        self.assertIsNone(m["Ref"]["field"])
        self.assertIsNone(m["Ref2"]["field"])

    def test_catalog_does_not_gain_a_date_and_become_sales(self):
        h = ["Item", "Qty", "X"]
        m = auto_map(h, _rows(ITEMS, ["5"] * 8, DATES))
        self.assertIsNone(m["X"]["field"])
        self.assertNotEqual(detect_entity({v["field"] for v in m.values() if v["field"]}, h), "sales")

    CODES = [_ean13(b) for b in ("400638133393", "590123412345", "978030640615", "625100000001",
                                 "625100000002", "625100000003", "625100000004", "625100000005")]

    def test_barcodes_found_by_check_digit(self):
        m = auto_map(["Item", "Ref"], _rows(ITEMS, self.CODES))
        self.assertEqual(m["Ref"]["field"], "barcode")
        self.assertTrue(m["Ref"]["review"])

    def test_code_column_holding_barcodes_becomes_barcode(self):
        m = auto_map(["Item", "Code"], _rows(ITEMS, self.CODES))
        self.assertEqual(m["Code"]["field"], "barcode")

    def test_code_column_holding_item_codes_stays_sku(self):
        m = auto_map(["Item", "Code"], _rows(ITEMS, [f"REST-01{i:02d}" for i in range(8)]))
        self.assertEqual(m["Code"]["field"], "sku")
        self.assertFalse(m["Code"]["review"])

    def test_without_rows_the_result_keeps_its_old_shape(self):
        self.assertNotIn("review", auto_map(["Date", "Item"])["Date"])


# ── Phase 2: the file type must be confirmed when its signals are weak ────────

def check_of(headers, rows=None):
    return entity_check(headers, auto_map(headers, rows))


def codes(check):
    return [r["code"] for r in check["reasons"]]


class EntityNeedsConfirmation(unittest.TestCase):

    def test_purchase_invoices_ask_because_the_guard_fired(self):
        c = check_of(RestaurantExport.PURCHASES)
        self.assertEqual(c["detected"], "supplier_prices")
        self.assertTrue(c["needs_confirmation"])
        self.assertEqual(c["reasons"][0], {"code": "purchase_guard", "instead_of": "sales"})
        self.assertNotIn("sales", c["suggested"])  # the misreading the guard prevents is never suggested

    def test_waste_log_asks_because_the_guard_fired(self):
        c = check_of(RestaurantExport.WASTE)
        self.assertEqual((c["detected"], codes(c)), ("unknown", ["waste_guard"]))

    def test_well_named_files_do_not_ask(self):
        for h in (RestaurantExport.SALES, RestaurantExport.MENU,
                  ["Invoice No", "Date", "Item", "Qty", "Unit Price", "Total", "Payment Method"],
                  ["الاسم", "رقم الهاتف", "المدينة"],
                  ["المورد", "الصنف", "سعر الكرتونة", "عدد الحبات بالكرتونة", "سعر الحبة"]):
            self.assertFalse(check_of(h)["needs_confirmation"], h)

    def test_sales_with_supplier_column_is_mixed(self):
        c = check_of(["Invoice No", "Date", "Item", "Qty", "Price", "Cashier", "Supplier"])
        self.assertEqual(c["detected"], "sales")
        self.assertEqual(c["reasons"], [{"code": "mixed_signals", "signal": "purchase"}])
        self.assertEqual(c["suggested"], ["supplier_prices"])

    def test_missing_required_field(self):
        c = check_of(["Invoice No", "Item", "Qty", "Price"])  # sales without a date
        self.assertEqual((c["detected"], c["reasons"]), ("sales", [{"code": "missing_required", "fields": ["date"]}]))
        self.assertIn({"code": "missing_required", "fields": ["phone"]}, check_of(["Customer Name", "City"])["reasons"])

    def test_total_stands_in_for_unit_price_in_sales(self):
        self.assertFalse(check_of(["Invoice No", "Date", "Item", "Qty", "Total"])["needs_confirmation"])
        self.assertEqual(missing_for("sales", {"date", "product", "quantity"}), ["unit_price"])

    def test_unrecognized_file(self):
        self.assertEqual(codes(check_of(["Foo", "Bar"])), ["unrecognized"])

    def test_type_that_rests_on_a_column_under_review(self):
        h = ["Item", "Ref"]
        m = auto_map(h, _rows(ITEMS, ValueEvidence.CODES))  # Ref found as a barcode from its values
        c = entity_check(h, m)
        self.assertEqual(c["detected"], "products")
        self.assertIn({"code": "unconfirmed_fields", "columns": ["Ref"], "instead_of": "unknown"}, c["reasons"])
        m["Ref"]["review"] = False  # the user (or the AI) confirmed the column
        self.assertNotIn("unconfirmed_fields", codes(entity_check(h, m)))

    def test_type_that_rests_on_an_ai_only_column(self):
        h = ["Item", "Qty", "X"]
        m = auto_map(h, _rows(ITEMS, ["5"] * 8, DATES))
        m["X"] = {"field": "date", "confidence": 0.95, "source": "ai", "review": False}  # trusted AI fill
        c = entity_check(h, m)
        self.assertEqual(c["detected"], "sales")
        self.assertIn({"code": "unconfirmed_fields", "columns": ["X"], "instead_of": "unknown"}, c["reasons"])


class EntityConfirmationState(unittest.TestCase):
    H = RestaurantExport.PURCHASES

    def stored(self, entity, mapping=None):
        mapping = mapping or auto_map(self.H)
        return {**mapping, ENTITY_KEY: {"entity": entity, "fields": field_signature(mapping)}}

    def test_unconfirmed_is_blocked(self):
        s = entity_state(self.H, auto_map(self.H))
        self.assertTrue(s["blocked"])
        self.assertIsNone(s["confirmed"])
        self.assertEqual(s["entity"], "supplier_prices")

    def test_confirmation_unblocks_and_the_users_choice_wins(self):
        s = entity_state(self.H, self.stored("supplier_prices"))
        self.assertEqual((s["blocked"], s["entity"]), (False, "supplier_prices"))
        s = entity_state(self.H, self.stored("unknown"))
        self.assertEqual((s["blocked"], s["entity"], s["detected"]), (False, "unknown", "supplier_prices"))

    def test_confirmation_expires_when_the_mapping_changes(self):
        mapping = self.stored("supplier_prices")
        mapping["اسم المورد"] = {**mapping["اسم المورد"], "field": None}
        self.assertTrue(entity_state(self.H, mapping)["blocked"])

    def test_bogus_confirmation_is_ignored(self):
        self.assertTrue(entity_state(self.H, self.stored("payroll"))["blocked"])

    def test_engine_uses_the_confirmed_type(self):
        h = ["Invoice No", "Date", "Item", "Qty", "Price"]
        rows = [["1", "2026-01-05", "حمص", "2", "1.5"]]
        mapping = {x: m["field"] for x, m in auto_map(h).items()}
        self.assertEqual(engine.run(h, rows, mapping)["entity"], "sales")
        self.assertEqual(engine.run(h, rows, mapping, entity="supplier_prices")["entity"], "supplier_prices")


# ── Phase 2: the AI referees uncertain columns ───────────────────────────────

def ask_returning(verdicts):
    calls = []

    async def ask(judge, decided):
        calls.append((judge, decided))
        return verdicts
    ask.calls = calls
    return ask


def run(coro):
    return asyncio.run(coro)


class AiReferee(unittest.TestCase):

    def test_only_empty_and_review_columns_are_sent(self):
        h = ["التاريخ", "A", "B", "Phone", "Qty"]
        m = auto_map(h, _rows(DATES, ITEMS, PHONES, ITEMS, ["1"] * 8))
        m["Qty"] = {**m["Qty"], "source": "user"}
        ask = ask_returning({})
        run(referee.arbitrate(h, _rows(DATES, ITEMS, PHONES, ITEMS, ["1"] * 8), m, ask, skip={"A"}))
        judge, decided = ask.calls[0]
        self.assertEqual(list(judge), ["B", "Phone"])          # A skipped ("don't use"), exact matches not sent
        self.assertEqual(decided, {"التاريخ": "date", "Qty": "quantity"})
        self.assertEqual(judge["Phone"]["current_guess"], "phone")
        self.assertIn("only 0% of the values look like phone", judge["Phone"]["value_check"])

    def test_agreement_with_high_confidence_clears_review(self):
        h = ["A", "B"]
        rows = _rows(ITEMS, PHONES)
        m = run(referee.arbitrate(h, rows, auto_map(h, rows), ask_returning({
            "A": {"field": "product", "confidence": 0.92, "reason": "dish names"},
            "B": {"field": "phone", "confidence": 0.95, "reason": "Jordanian mobiles"}})))
        self.assertEqual((m["B"]["field"], m["B"]["review"]), ("phone", False))
        self.assertTrue(m["B"]["ai"]["agrees"])
        self.assertEqual(m["B"]["source"], "values")           # still found from values, now confirmed by the AI
        self.assertEqual((m["A"]["field"], m["A"]["source"], m["A"]["review"]), ("product", "ai", False))

    def test_low_confidence_agreement_keeps_review(self):
        h = ["A", "B"]
        rows = _rows(ITEMS, PHONES)
        m = run(referee.arbitrate(h, rows, auto_map(h, rows), ask_returning({"B": {"field": "phone", "confidence": 0.7}})))
        self.assertTrue(m["B"]["review"])
        self.assertTrue(m["B"]["ai"]["agrees"])

    def test_agreement_never_clears_a_value_mismatch(self):
        h = ["Phone", "Qty"]
        rows = _rows(ITEMS, ["1"] * 8)
        m = run(referee.arbitrate(h, rows, auto_map(h, rows), ask_returning({"Phone": {"field": "phone", "confidence": 0.99}})))
        self.assertTrue(m["Phone"]["review"])

    def test_a_proposal_is_recorded_but_never_moves_the_field(self):
        h = ["Phone", "Qty"]
        rows = _rows(ITEMS, ["1"] * 8)
        m = run(referee.arbitrate(h, rows, auto_map(h, rows), ask_returning({
            "Phone": {"field": "product", "confidence": 0.97, "reason": "these are dishes"}})))
        self.assertEqual((m["Phone"]["field"], m["Phone"]["review"]), ("phone", True))
        self.assertEqual(m["Phone"]["ai"], {"field": "product", "confidence": 0.97, "reason": "these are dishes",
                                            "agrees": False})

    def test_never_takes_the_field_of_a_sure_column(self):
        h = ["التاريخ", "X"]
        rows = _rows(DATES, [f"R-{i}" for i in range(8)])
        m = run(referee.arbitrate(h, rows, auto_map(h, rows), ask_returning({
            "X": {"field": "date", "confidence": 0.99}, "التاريخ": {"field": "notes", "confidence": 1}})))
        self.assertEqual(m["التاريخ"]["field"], "date")
        self.assertNotIn("ai", m["التاريخ"])                    # never sent, its answer is ignored
        self.assertIsNone(m["X"]["field"])
        self.assertEqual(m["X"]["ai"]["taken_by"], "التاريخ")

    def test_one_field_per_column(self):
        h = ["A", "B"]
        rows = _rows(ITEMS, ITEMS)
        m = run(referee.arbitrate(h, rows, auto_map(h, rows), ask_returning({
            "A": {"field": "product", "confidence": 0.9}, "B": {"field": "product", "confidence": 0.9}})))
        self.assertEqual((m["A"]["field"], m["B"]["field"]), ("product", None))
        self.assertEqual(m["B"]["ai"]["taken_by"], "A")

    def test_fields_outside_the_catalog_are_ignored(self):
        h = ["A", "B"]
        rows = _rows(ITEMS, PHONES)
        before = auto_map(h, rows)
        m = run(referee.arbitrate(h, rows, before, ask_returning({
            "A": {"field": "dish", "confidence": 1}, "B": {"field": "DROP TABLE", "confidence": 1}})))
        self.assertEqual(m, before)

    def test_ai_fill_contradicted_by_values_needs_review(self):
        h = ["Item", "Ref"]
        rows = _rows(ITEMS, ITEMS)
        m = run(referee.arbitrate(h, rows, auto_map(h, rows), ask_returning({"Ref": {"field": "quantity", "confidence": 0.95}})))
        self.assertEqual(m["Ref"]["field"], "quantity")
        self.assertTrue(m["Ref"]["review"])
        self.assertEqual(m["Ref"]["evidence"]["type"], "mismatch")

    def test_percent_confidence_is_read_as_percent(self):
        h = ["A", "B"]
        rows = _rows(ITEMS, PHONES)
        m = run(referee.arbitrate(h, rows, auto_map(h, rows), ask_returning({"B": {"field": "phone", "confidence": "60"}})))
        self.assertEqual(m["B"]["ai"]["confidence"], 0.6)
        self.assertTrue(m["B"]["review"])

    def test_fails_open(self):
        h = ["A", "B", "Phone"]
        rows = _rows(ITEMS, PHONES, ITEMS)
        before = auto_map(h, rows)

        async def boom(judge, decided):
            raise RuntimeError("quota")

        async def slow(judge, decided):
            await asyncio.sleep(1)
            return {"B": {"field": "phone", "confidence": 1}}

        for ask in (boom, slow, ask_returning(None), ask_returning(["not", "a", "dict"]),
                    ask_returning({"B": "phone"})):
            self.assertEqual(run(referee.arbitrate(h, rows, before, ask, timeout=0.05)), before)

    def test_samples_are_redacted(self):
        self.assertEqual(referee._redact("+962 79 100 1601"), "+962 xx xxx xx01")
        self.assertEqual(referee._redact("ahmad.k@gmail.com"), "a***@gmail.com")
        self.assertEqual(referee._redact("2025-12-26"), "2025-12-26")
        self.assertEqual(referee._redact("12.500"), "12.500")


class _Tx:
    def __init__(self):
        self.conn = mock.AsyncMock()

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


CTX = SimpleNamespace(org_id="org-1", user=SimpleNamespace(id="user-1"))


class RefereeInTheUploadFlow(unittest.IsolatedAsyncioTestCase):
    """data._ai_referee with ai.map_columns mocked: budget, payload and fail-open."""

    H = ["A", "B"]
    ROWS = _rows(ITEMS, PHONES)

    def patches(self, reserve=True, answer=None):
        return (mock.patch.object(ai, "available", return_value=True),
                mock.patch.object(ai, "budget_reserve", mock.AsyncMock(return_value=reserve)),
                mock.patch.object(ai, "budget_release", mock.AsyncMock()),
                mock.patch.object(ai, "map_columns", mock.AsyncMock(return_value=answer)))

    async def test_calls_the_ai_within_the_budget(self):
        p = self.patches(answer={"B": {"field": "phone", "confidence": 0.95, "reason": "mobiles"}})
        with p[0], p[1] as reserve, p[2] as release, p[3] as map_columns:
            m = await data._ai_referee(CTX, self.H, self.ROWS, auto_map(self.H, self.ROWS), set())
        reserve.assert_awaited_once_with("org-1")
        release.assert_awaited_once_with("org-1")
        judge, decided, org, user = map_columns.await_args.args
        self.assertEqual((list(judge), decided, org, user), (["A", "B"], {}, "org-1", "user-1"))
        self.assertNotIn("100 1601", str(judge))                # phone digits never leave
        self.assertFalse(m["B"]["review"])

    async def test_over_budget_keeps_the_mapping(self):
        before = auto_map(self.H, self.ROWS)
        p = self.patches(reserve=False)
        with p[0], p[1], p[2] as release, p[3] as map_columns:
            m = await data._ai_referee(CTX, self.H, self.ROWS, before, set())
        map_columns.assert_not_awaited()
        release.assert_not_awaited()
        self.assertEqual(m, before)

    async def test_error_keeps_the_mapping_and_releases_the_budget(self):
        before = auto_map(self.H, self.ROWS)
        p = self.patches()
        with p[0], p[1], p[2] as release, p[3] as map_columns:
            map_columns.side_effect = TimeoutError
            m = await data._ai_referee(CTX, self.H, self.ROWS, before, set())
        release.assert_awaited_once()
        self.assertEqual(m, before)

    async def test_nothing_uncertain_means_no_call(self):
        h = ["Invoice No", "Date", "Item", "Qty", "Total", "Payment Method"]
        rows = _rows([str(i) for i in range(8)], DATES, ITEMS, ["2"] * 8, ["3.5"] * 8, PAYMENTS)
        p = self.patches()
        with p[0], p[1] as reserve, p[2], p[3] as map_columns:
            await data._ai_referee(CTX, h, rows, auto_map(h, rows), set())
        reserve.assert_not_awaited()
        map_columns.assert_not_awaited()


class ServerRefusesUnconfirmedType(unittest.IsolatedAsyncioTestCase):
    """clean / apply_run refuse, set_mapping saves the user's confirmation (DB mocked)."""

    H = RestaurantExport.PURCHASES

    def upload(self, mapping):
        return {"id": "u1", "columns": self.H, "mapping": mapping, "batch_id": None, "entity": "supplier_prices"}

    async def test_clean_refuses_until_confirmed(self):
        fetchrow = mock.AsyncMock(side_effect=[self.upload(auto_map(self.H)), {"raw_rows": [[""] * len(self.H)]}])
        with mock.patch.object(data.db, "fetchrow", fetchrow):
            with self.assertRaises(HTTPException) as e:
                await data.clean("u1", CTX)
        self.assertEqual(e.exception.status_code, 409)

    async def test_apply_refuses_an_unconfirmed_run(self):
        run_row = {"columns": self.H, "mapping": auto_map(self.H), "entity": "supplier_prices", "stats": {},
                   "imported_at": None, "reverted_at": None, "upload_id": "u1"}
        with mock.patch.object(data.db, "fetchrow", mock.AsyncMock(return_value=run_row)):
            with self.assertRaises(HTTPException) as e:
                await data.apply_run("r1", CTX)
        self.assertEqual(e.exception.status_code, 409)

    async def test_apply_refuses_when_the_type_changed_after_cleaning(self):
        h = ["Invoice No", "Date", "Item", "Qty", "Unit Price"]
        run_row = {"columns": h, "mapping": auto_map(h), "entity": "sales", "stats": {"entity": "products"},
                   "imported_at": None, "reverted_at": None, "upload_id": "u1"}
        with mock.patch.object(data.db, "fetchrow", mock.AsyncMock(return_value=run_row)):
            with self.assertRaises(HTTPException) as e:
                await data.apply_run("r1", CTX)
        self.assertIn("changed after", e.exception.detail)

    async def test_set_mapping_saves_the_confirmation(self):
        cur = auto_map(self.H)
        body = data.MappingIn(mapping={h: m["field"] for h, m in cur.items()} | {ENTITY_KEY: "notes"},
                              entity="supplier_prices")
        execute = mock.AsyncMock()
        with mock.patch.object(data.db, "fetchrow", mock.AsyncMock(return_value=self.upload(cur))), \
                mock.patch.object(data.db, "transaction", lambda: _Tx()), \
                mock.patch.object(data.db, "execute", execute):
            res = await data.set_mapping("u1", body, CTX)
        saved, entity = execute.await_args.args[3], execute.await_args.args[4]
        self.assertEqual(saved[ENTITY_KEY]["entity"], "supplier_prices")   # the injected column key was ignored
        self.assertEqual(entity, "supplier_prices")
        self.assertFalse(res["entity_check"]["blocked"])
        self.assertFalse(entity_state(self.H, saved)["blocked"])

    async def test_set_mapping_rejects_an_unknown_type(self):
        with mock.patch.object(data.db, "fetchrow", mock.AsyncMock(return_value=self.upload(auto_map(self.H)))):
            with self.assertRaises(HTTPException) as e:
                await data.set_mapping("u1", data.MappingIn(mapping={}, entity="payroll"), CTX)
        self.assertEqual(e.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
