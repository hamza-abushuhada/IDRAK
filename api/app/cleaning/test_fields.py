"""Tests for column auto-mapping and file-type detection (cleaning/fields.py).

Run from api/:  python -m unittest app.cleaning.test_fields

No DB or model needed. The restaurant cases come from a real client export
(POS sales, menu/inventory, supplier purchases, waste log) where the old matcher
let generic synonyms win and read purchase and waste logs as sales.
"""

import asyncio
import contextlib
import csv
import io
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

from app.cleaning import engine, learning, referee
from app.cleaning.fields import (ENTITY_KEY, auto_map, detect_entity, entity_check, entity_state, field_signature,
                                 guess_field, header_key, missing_for)
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

    def test_menu_with_supplier_and_unit_is_still_a_product_list(self):
        # The live account's menu: "وحدة القياس" mapped to pack_size and "المورد الافتراضي"
        # to supplier made it "supplier prices", losing its selling prices and stock.
        fields = {"sku", "product", "pack_size", "category", "cost", "unit_price", "stock", "minimum_stock",
                  "supplier", "expiry_date", "notes"}
        self.assertEqual(detect_entity(fields), "products")
        self.assertEqual(detect_entity({"supplier", "product", "carton_price", "pack_size"}), "supplier_prices")

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


# ── Phase 3: learning from what companies confirm (cleaning/learning.py) ─────

class FakeVotes:
    """mapping_votes in memory, plus the aggregate data._SHARED_SQL computes from it."""

    def __init__(self, fail=False):
        self.rows: dict[tuple[str, str], tuple[str, str]] = {}  # (org, header_key) -> (field, user)
        self.writes: list[tuple] = []
        self.fail = fail

    def transaction(self):
        store = self

        class Tx:
            async def __aenter__(self):
                conn = mock.AsyncMock()

                async def executemany(sql, args):
                    if "mapping_votes" not in sql:
                        return  # the org's own cleaning_rules
                    if store.fail:
                        raise RuntimeError('relation "mapping_votes" does not exist')
                    for org, key, field, user in args:
                        store.writes.append((org, key, field, user))
                        store.rows[(org, key)] = (field, user)
                conn.executemany = executemany
                return conn

            async def __aexit__(self, *exc):
                return False
        return Tx()

    async def fetch(self, sql, *args):
        assert "mapping_votes" in sql
        orgs, voters, total = {}, {}, {}
        for (org, key), (field, user) in self.rows.items():
            orgs.setdefault((key, field), set()).add(org)
            voters.setdefault((key, field), set()).add(user)
            total[key] = total.get(key, 0) + 1
        return [{"header_key": k, "field": f, "orgs": len(o), "voters": len(voters[(k, f)]), "total": total[k]}
                for (k, f), o in orgs.items() if len(o) >= args[0]]


DISH_H = ["رقم الطلب", "التاريخ", "اسم الطبق", "الكمية", "السعر"]
DISH_ROWS = _rows([str(50000 + i) for i in range(8)], DATES, ITEMS, ["2"] * 8, ["3.5"] * 8)
DISH = header_key("اسم الطبق")


def ctx_of(org, user="user-1"):
    return SimpleNamespace(org_id=org, user=SimpleNamespace(id=user))


async def confirm(store, org, user, headers=DISH_H, rows=DISH_ROWS, change=None):
    """One user saving the mapping screen: what Idrak showed, with `change` applied."""
    before = auto_map(headers, rows)
    chosen = {h: m["field"] for h, m in before.items()} | (change if change is not None else {"اسم الطبق": "product"})
    upload = {"columns": headers, "mapping": json.loads(json.dumps(before)), "batch_id": None}
    with mock.patch.object(data.db, "fetchrow", mock.AsyncMock(return_value=upload)), \
            mock.patch.object(data.db, "transaction", store.transaction), \
            mock.patch.object(data.db, "execute", mock.AsyncMock()):
        return await data.set_mapping("u1", data.MappingIn(mapping=chosen), ctx_of(org, user))


async def shared_now(store):
    data.db.cache_clear("shared_synonyms")
    with mock.patch.object(data.db, "fetch", store.fetch):
        return await data._shared_synonyms()


class SharedSynonyms(unittest.IsolatedAsyncioTestCase):
    """A header >= 3 companies confirmed to the same field helps every company."""

    def setUp(self):
        data.db.cache_clear("shared_synonyms")

    def tearDown(self):
        data.db.cache_clear("shared_synonyms")

    async def test_two_orgs_are_not_enough_three_are(self):
        # "اسم الطبق" (dish name) reads as customer name by fuzzy match today.
        self.assertEqual(auto_map(DISH_H, DISH_ROWS)["اسم الطبق"]["field"], "customer_name")
        store = FakeVotes()
        await confirm(store, "org-a", "user-a")
        await confirm(store, "org-b", "user-b")
        shared = await shared_now(store)
        self.assertEqual(shared, {})
        self.assertEqual(auto_map(DISH_H, DISH_ROWS, shared)["اسم الطبق"]["field"], "customer_name")

        await confirm(store, "org-c", "user-c")
        shared = await shared_now(store)
        self.assertEqual(shared, {DISH: "product"})
        m = auto_map(DISH_H, DISH_ROWS, shared)["اسم الطبق"]
        self.assertEqual((m["field"], m["source"], m["review"]), ("product", "shared", False))

    async def test_one_org_is_one_vote_however_often_it_confirms(self):
        store = FakeVotes()
        for user in ("user-a", "user-b", "user-c", "user-d"):
            await confirm(store, "org-a", user)
        await confirm(store, "org-b", "user-e")
        self.assertEqual(len(store.rows), 2)
        self.assertEqual(await shared_now(store), {})

    async def test_one_person_with_three_orgs_is_not_enough(self):
        store = FakeVotes()
        for org in ("org-a", "org-b", "org-c"):
            await confirm(store, org, "same-user")
        self.assertEqual(await shared_now(store), {})

    async def test_disagreement_blocks_promotion(self):
        store = FakeVotes()
        for org in ("org-a", "org-b", "org-c"):
            await confirm(store, org, f"user-{org}")
        await confirm(store, "org-d", "user-d", change={"اسم الطبق": None})  # "don't use" counts against
        self.assertEqual(await shared_now(store), {})                        # 3 of 4 = 75%
        await confirm(store, "org-e", "user-e")
        self.assertEqual(await shared_now(store), {DISH: "product"})          # 4 of 5 = 80%

    def test_promote_rules(self):
        row = {"header_key": DISH, "field": "product", "orgs": 3, "voters": 3, "total": 3}
        self.assertEqual(learning.promote([row]), {DISH: "product"})
        self.assertEqual(learning.promote([{**row, "total": 4}]), {})                       # 75% agree
        self.assertEqual(learning.promote([{**row, "voters": 2}]), {})                      # 2 people
        self.assertEqual(learning.promote([{**row, "field": ""}]), {})                      # "don't use" never spreads
        self.assertEqual(learning.promote([{**row, "field": "salary"}]), {})                # not an Idrak field
        self.assertEqual(learning.promote([{**row, "header_key": "تاريخ", "field": "expiry_date",
                                            "orgs": 9, "voters": 9, "total": 9}]), {})      # exact built-in
        self.assertEqual(learning.promote([{**row, "header_key": "0791234567"}]), {})        # personal-looking

    def test_never_above_an_exact_built_in_synonym(self):
        m = auto_map(["التاريخ", "Dish"], _rows(DATES, ITEMS), {"تاريخ": "expiry_date", "dish": "date"})
        self.assertEqual((m["التاريخ"]["field"], m["التاريخ"]["source"]), ("date", "rules"))
        self.assertIsNone(m["Dish"]["field"])  # its shared field is taken by the exact match

    def test_above_a_fuzzy_match(self):
        m = auto_map(["اسم الزبون", "اسم الطبق"], _rows(ITEMS, ITEMS), {DISH: "customer_name"})
        self.assertEqual(m["اسم الزبون"]["field"], "customer_name")   # exact still first
        m = auto_map(["حالة الطلب", "اسم الطبق"], _rows(ITEMS, ITEMS), {DISH: "product"})
        self.assertEqual(m["اسم الطبق"]["field"], "product")

    def test_values_contradicting_a_shared_synonym_need_review(self):
        h = ["اسم الطبق", "الكمية"]
        m = auto_map(h, _rows([str(i) for i in range(8)], ["1"] * 8), {DISH: "product"})
        self.assertEqual((m["اسم الطبق"]["field"], m["اسم الطبق"]["source"]), ("product", "shared"))
        self.assertTrue(m["اسم الطبق"]["review"])
        self.assertEqual(m["اسم الطبق"]["evidence"]["type"], "mismatch")
        self.assertIn("اسم الطبق", referee.candidates(h, m))            # not sure: the AI referees it

    def test_values_that_agree_make_it_sure_for_the_referee(self):
        h = ["اسم الطبق", "الكمية"]
        m = auto_map(h, _rows(ITEMS, ["1"] * 8), {DISH: "product"})
        self.assertNotIn("اسم الطبق", referee.candidates(h, m))

    def test_only_what_the_user_decided_is_a_vote(self):
        h = ["اسم الطبق", "Ref", "Dish", "التاريخ", "Qty Sold", "Notes 2"]
        before = {"اسم الطبق": {"field": "customer_name", "review": False},          # changed -> vote
                  "Ref": {"field": "phone", "source": "values", "review": True},     # yellow, confirmed -> vote
                  "Dish": {"field": "product", "source": "ai", "review": False},     # accepted as shown -> no
                  "التاريخ": {"field": "date", "source": "rules"},                   # exact built-in -> no
                  "Qty Sold": {"field": "quantity", "review": False},               # "don't use" -> vote ""
                  "Notes 2": {"field": None, "source": "shared"}}                   # left empty -> no
        chosen = {"اسم الطبق": "product", "Ref": "phone", "Dish": "product", "التاريخ": "expiry_date",
                  "Qty Sold": None, "Notes 2": None, "not a column": "notes", ENTITY_KEY: "notes"}
        self.assertEqual(sorted(learning.votes(h, before, chosen)),
                         sorted([(header_key("اسم الطبق"), "product"), ("qty sold", ""), ("ref", "phone")]))

    async def test_nothing_personal_is_stored_or_shared(self):
        for h in ("0791234567", "+962 79 100 1601", "ahmad.k@gmail.com", "2025-01-01", "12345",
                  "Column 7", "a", "x" * 41, "one two three four five six seven"):
            self.assertIsNone(learning.shareable(h), h)
        h = ["رقم الطلب", "0791234567", "ahmad.k@gmail.com", "اسم الطبق"]
        rows = _rows([str(i) for i in range(8)], PHONES, ITEMS, ITEMS)
        store = FakeVotes()
        for org in ("org-a", "org-b", "org-c"):
            await confirm(store, org, f"user-{org}", h, rows,
                          change={"0791234567": "phone", "ahmad.k@gmail.com": "notes", "اسم الطبق": "product"})
        self.assertEqual({w[1] for w in store.writes}, {DISH})               # only the normalized header
        dump = json.dumps(store.writes, ensure_ascii=False)
        for secret in [*PHONES, *ITEMS, "0791234567", "ahmad", "gmail"]:
            self.assertNotIn(secret, dump)
        shared = await shared_now(store)
        self.assertEqual(shared, {DISH: "product"})
        self.assertNotIn("org-", json.dumps(shared))
        self.assertNotIn("org_id", data._SHARED_SQL.split("from", 1)[0])   # counts only, never who voted

    async def test_fails_open(self):
        async def boom(*args):
            raise RuntimeError('relation "mapping_votes" does not exist')
        with mock.patch.object(data.db, "fetch", boom), self.assertLogs(data.log, "WARNING"):
            self.assertEqual(await data._shared_synonyms(), {})
        with self.assertLogs(data.log, "WARNING"):
            res = await confirm(FakeVotes(fail=True), "org-a", "user-a")   # vote write fails: the save still works
        self.assertTrue(res["ok"])


# Purchases from a supplier: a file whose type must be confirmed (phase 2).
P_H = RestaurantExport.PURCHASES
P_ROWS = _rows([f"P-{100 + i}" for i in range(8)], DATES, ["الفرع الرئيسي"] * 8, ["شركة الريحان للتوريد"] * 8, ITEMS,
               ["12.5"] * 8, ["0.5"] * 8, ["10"] * 8, ["125"] * 8, ["16%"] * 8, ["مدفوع"] * 8, PAYMENTS,
               [str(9000 + i) for i in range(8)], ["سليم"] * 8)


def csv_bytes(headers, rows):
    out = io.StringIO()
    csv.writer(out).writerows([headers, *rows])
    return out.getvalue().encode("utf-8")


async def upload_file(headers, rows, fingerprint_row, name="purchases-march.csv"):
    """data._create_upload with the DB mocked; returns (inserted mapping, entity, ai.map_columns mock, db.fetch mock)."""
    fetchval, fetch = mock.AsyncMock(return_value="u2"), mock.AsyncMock(return_value=[])
    map_columns = mock.AsyncMock(return_value={})
    with contextlib.ExitStack() as st:
        for p in (mock.patch.object(data.db, "fetchrow", mock.AsyncMock(return_value=fingerprint_row)),
                  mock.patch.object(data.db, "fetch", fetch),
                  mock.patch.object(data.db, "fetchval", fetchval),
                  mock.patch.object(data.db, "execute", mock.AsyncMock()),
                  mock.patch.object(data.db, "audit", mock.AsyncMock()),
                  mock.patch.object(data, "get_upload", mock.AsyncMock(return_value={})),
                  mock.patch.object(data, "_shared_synonyms", mock.AsyncMock(return_value={})),
                  mock.patch.object(ai, "available", return_value=True),
                  mock.patch.object(ai, "budget_reserve", mock.AsyncMock(return_value=True)),
                  mock.patch.object(ai, "budget_release", mock.AsyncMock()),
                  mock.patch.object(ai, "map_columns", map_columns)):
            st.enter_context(p)
        await data._create_upload(CTX, name, csv_bytes(headers, rows))
    args = fetchval.await_args.args
    return args[12], args[7], map_columns, fetch


async def confirmed_record(headers=P_H, rows=P_ROWS, entity="supplier_prices"):
    """What cleaning a confirmed file saves (data._remember_file), as the DB would return it."""
    cur = auto_map(headers, rows)
    body = data.MappingIn(mapping={h: m["field"] for h, m in cur.items()}, entity=entity)
    execute = mock.AsyncMock()
    upload = {"columns": headers, "mapping": json.loads(json.dumps(cur)), "batch_id": None}
    with mock.patch.object(data.db, "fetchrow", mock.AsyncMock(return_value=upload)), \
            mock.patch.object(data.db, "transaction", lambda: _Tx()), \
            mock.patch.object(data.db, "execute", execute):
        await data.set_mapping("u1", body, CTX)
    saved = execute.await_args.args[3]
    execute = mock.AsyncMock()
    with mock.patch.object(data.db, "execute", execute):
        await data._remember_file(CTX, headers, rows, saved, entity_state(headers, saved))
    sql, org, fp, columns, ent, signature, by = execute.await_args.args
    assert "mapping_fingerprints" in sql and org == "org-1" and fp == learning.fingerprint(headers)
    return json.loads(json.dumps({"columns": columns, "entity": ent, "signature": signature, "confirmed_by": by}))


class FileFingerprints(unittest.IsolatedAsyncioTestCase):
    """The same export from the same company is mapped from its last confirmed file."""

    async def test_same_file_again_is_instant_and_keeps_the_type_confirmation(self):
        # First time: purchases need the user to confirm the type.
        first, _, _, _ = await upload_file(P_H, P_ROWS, None)
        self.assertTrue(entity_state(P_H, first)["blocked"])
        record = await confirmed_record()
        self.assertEqual(record["entity"], "supplier_prices")

        # Next month, same columns (spelled a little differently), new values.
        h2 = [h.replace("الكمية الموردة", "الكميه  الموردة") for h in P_H]
        self.assertEqual(learning.fingerprint(h2), learning.fingerprint(P_H))
        rows2 = [r[:] for r in P_ROWS]
        for r in rows2:
            r[0] = r[0].replace("P-", "P-2")
        mapping, entity, map_columns, fetch = await upload_file(h2, rows2, record)
        for h in h2:
            self.assertEqual((mapping[h]["source"], mapping[h]["via"], mapping[h]["review"]), ("memory", "file", False), h)
        self.assertEqual(mapping[h2[3]]["field"], "supplier")
        map_columns.assert_not_awaited()                       # no AI call
        fetch.assert_not_awaited()                             # no shared map / per-header rules needed
        state = entity_state(h2, mapping)
        self.assertEqual((state["blocked"], state["confirmed"], state["confirmed_via"]), (False, "supplier_prices", "file"))
        self.assertEqual(entity, "supplier_prices")

    async def test_changed_export_falls_back_to_review(self):
        record = await confirmed_record()
        qty = "الكمية الموردة"
        i = P_H.index(qty)
        rows2 = [r[:i] + [item] + r[i + 1:] for r, item in zip(P_ROWS, ITEMS)]   # names where quantities were
        mapping, _, map_columns, _ = await upload_file(P_H, rows2, record)
        m = mapping[qty]
        self.assertEqual((m["field"], m["source"], m["review"]), ("quantity", "memory", True))  # field kept, flagged
        self.assertEqual(m["evidence"]["type"], "mismatch")
        self.assertEqual([h for h in P_H if mapping[h].get("review")], [qty])
        self.assertNotIn(ENTITY_KEY, mapping)                   # the type is asked again
        self.assertTrue(entity_state(P_H, mapping)["blocked"])
        judge = map_columns.await_args.args[0]
        self.assertEqual(list(judge), [qty])                    # only the changed column goes to the AI

    def test_a_column_that_never_fully_fit_is_not_flagged_again(self):
        h = ["Item", "طريقة الدفع"]
        rows = _rows(ITEMS, ["شيك", "كاش", "شيك", "CLIQ", "شيك مؤجل", "كاش", "شيك", "نقدي"])
        mapping = {"Item": {"field": "product", "source": "user"}, "طريقة الدفع": {"field": "payment_method", "source": "user"}}
        _, saved = learning.file_memory(h, rows, mapping, {})
        self.assertEqual(saved["columns"][header_key("طريقة الدفع")]["fit"], 0.5)
        out, _ = learning.apply_file_memory(h, rows, saved)
        self.assertFalse(out["طريقة الدفع"]["review"])           # the user already accepted these values

    def test_dont_use_is_remembered_and_never_sent_to_the_ai(self):
        h = ["Item", "Qty", "رقم الطاولة"]
        rows = _rows(ITEMS, ["1"] * 8, ["4"] * 8)
        mapping = {"Item": {"field": "product"}, "Qty": {"field": "quantity"}, "رقم الطاولة": {"field": None}}
        _, saved = learning.file_memory(h, rows, mapping, {})
        out, unused = learning.apply_file_memory(h, rows, saved)
        self.assertEqual((out["رقم الطاولة"]["field"], unused), (None, {"رقم الطاولة"}))
        self.assertEqual(referee.candidates(h, out, unused), [])

    def test_not_remembered_while_a_column_is_under_review(self):
        h = ["Item", "B"]
        self.assertIsNone(learning.file_memory(h, _rows(ITEMS, PHONES),
                                               {"Item": {"field": "product"}, "B": {"field": "phone", "review": True}}, {}))

    def test_fingerprint(self):
        self.assertEqual(learning.fingerprint(["Item_Name", "QTY "]), learning.fingerprint(["qty", "item name"]))
        self.assertNotEqual(learning.fingerprint(["Item", "Qty"]), learning.fingerprint(["Item", "Qty", "Price"]))
        self.assertIsNone(learning.fingerprint(["Total", "total"]))   # two columns read the same

    def test_a_record_that_does_not_fit_is_ignored(self):
        h = ["Item", "Qty"]
        rows = _rows(ITEMS, ["1"] * 8)
        _, saved = learning.file_memory(h, rows, {"Item": {"field": "product"}, "Qty": {"field": "quantity"}}, {})
        self.assertIsNone(learning.apply_file_memory(["Item", "Price"], rows, saved))
        bad = json.loads(json.dumps(saved))
        bad["columns"]["qty"]["field"] = "salary"                    # a field Idrak no longer has
        self.assertIsNone(learning.apply_file_memory(h, rows, bad))

    async def test_nothing_personal_in_file_memory(self):
        h = ["Item", "Phone", "Email"]
        rows = _rows(ITEMS, PHONES, [f"user{i}@gmail.com" for i in range(8)])
        mapping = {"Item": {"field": "product"}, "Phone": {"field": "phone"}, "Email": {"field": "email"}}
        execute = mock.AsyncMock()
        with mock.patch.object(data.db, "execute", execute):
            await data._remember_file(CTX, h, rows, mapping, {"confirmed": None})
        dump = json.dumps(execute.await_args.args[1:], ensure_ascii=False)
        for secret in [*ITEMS, *PHONES, "gmail", "purchases-march.csv"]:
            self.assertNotIn(secret, dump)

    async def test_fails_open(self):
        with mock.patch.object(data.db, "fetchrow", mock.AsyncMock(side_effect=RuntimeError("no table"))),                 self.assertLogs(data.log, "WARNING"):
            self.assertIsNone(await data._load_file_memory("org-1", P_H))
        with mock.patch.object(data.db, "execute", mock.AsyncMock(side_effect=RuntimeError("no table"))),                 self.assertLogs(data.log, "WARNING"):
            await data._remember_file(CTX, ["Item"], _rows(ITEMS), {"Item": {"field": "product"}}, {})
        # A broken record falls back to the normal mapping.
        mapping, _, _, fetch = await upload_file(P_H, P_ROWS, {"columns": "garbage"})
        self.assertEqual(mapping["اسم المورد"]["source"], "rules")
        fetch.assert_awaited()                                    # per-header rules were read as before

    async def test_clean_saves_the_file_memory(self):
        h = ["Invoice No", "Date", "Item", "Qty", "Total"]
        rows = _rows([str(i) for i in range(8)], DATES, ITEMS, ["2"] * 8, ["3.5"] * 8)
        upload = {"id": "u1", "columns": h, "mapping": auto_map(h, rows), "batch_id": None, "entity": "sales"}
        remember = mock.AsyncMock()
        with mock.patch.object(data.db, "fetchrow", mock.AsyncMock(side_effect=[upload, {"raw_rows": rows}])), \
                mock.patch.object(data.db, "transaction", lambda: _Tx()), \
                mock.patch.object(data.db, "audit", mock.AsyncMock()), \
                mock.patch.object(data, "load_context", mock.AsyncMock(return_value=engine.Context())), \
                mock.patch.object(data, "get_run", mock.AsyncMock(return_value={})), \
                mock.patch.object(data, "_remember_file", remember):
            await data.clean("u1", CTX)
        _, headers, raw, mapping, state = remember.await_args.args
        self.assertEqual((headers, raw, mapping, state["entity"]), (h, rows, upload["mapping"], "sales"))


if __name__ == "__main__":
    unittest.main()
