"""Tests for column auto-mapping and file-type detection (cleaning/fields.py).

Run from api/:  python -m unittest app.cleaning.test_fields

No DB or model needed. The restaurant cases come from a real client export
(POS sales, menu/inventory, supplier purchases, waste log) where the old matcher
let generic synonyms win and read purchase and waste logs as sales.
"""

import unittest

from app.cleaning.fields import auto_map, detect_entity, guess_field


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


if __name__ == "__main__":
    unittest.main()
