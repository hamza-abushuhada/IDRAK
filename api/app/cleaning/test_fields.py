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


if __name__ == "__main__":
    unittest.main()
