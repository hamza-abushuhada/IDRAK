"""Fils written inside dinar columns (cleaning/money.py) and how the engine shows them.

Run from api/:  python -m unittest app.cleaning.test_money

The cases come from a real restaurant export where ~10% of prices and costs
were in fils (3950 next to 3.25), which made a sandwich "cost" 1,350 JD.
"""

import unittest

from app.cleaning import engine
from app.cleaning.money import detect


def changes(res, rule="fils_detected"):
    return {(c["row"], c["column"]): c["new"] for c in res["changes"] if c["rule"] == rule}


class Detect(unittest.TestCase):

    def test_same_product_on_other_rows_is_the_reference(self):
        fixes, _ = detect({"unit_price": [3.25, 3.25, 3250, 2.75, 2.75]}, ["zinger", "zinger", "zinger", "hummus", "hummus"])
        self.assertEqual(fixes["unit_price"], {2: 3.25})

    def test_cost_twenty_times_the_price_is_fils(self):
        fixes, _ = detect({"cost": [100.0], "unit_price": [0.35]})
        self.assertEqual(fixes["cost"], {0: 0.1})

    def test_both_sides_in_fils(self):
        fixes, _ = detect({"cost": [0.6, 0.7, 600.0, 1.1], "unit_price": [1.75, 2.0, 1750.0, 2.75]})
        self.assertEqual((fixes["cost"], fixes["unit_price"]), ({2: 0.6}, {2: 1.75}))

    def test_real_dinar_amounts_are_left_alone(self):
        # An 85 JD tin, a 125.5 JD item, a 200 JD cost sold at 260 JD.
        fixes, _ = detect({"cost": [5.2, 4.0, 85.0, 125.5, 200.0, 6.1],
                           "unit_price": [7.0, 6.0, 110.0, 160.0, 260.0, 8.0]})
        self.assertEqual(fixes["cost"], {})
        self.assertEqual(fixes["unit_price"], {})

    def test_line_total_checked_against_quantity_times_price(self):
        fixes, _ = detect({"unit_price": [3.95, 3950.0], "total": [15.8, 15800.0]}, ["b", "b"], [4.0, 4.0])
        self.assertEqual(fixes["total"], {1: 15.8})

    def test_far_out_values_without_evidence_are_flagged_not_changed(self):
        vals = [5.0, 6.0, 4.5, 5.5, 900000.0]
        fixes, review = detect({"discount": vals})
        self.assertEqual(fixes["discount"], {})
        self.assertEqual(review["discount"], {4})


class Engine(unittest.TestCase):
    H = ["Invoice No", "Date", "Item", "Qty", "Unit Price", "Cost", "Total"]

    def test_sales_file_with_mixed_units(self):
        rows = [["1", "2026-01-05", "Zinger", "1", "3.25", "1.35", "3.25"],
                ["2", "2026-01-05", "Zinger", "2", "3250", "1350", "6500"],
                ["3", "2026-01-06", "Zinger", "1", "3.25", "1.35", "3.25"],
                ["4", "2026-01-06", "Water", "3", "0.35", "100", "1.05"]]
        m = {"Invoice No": "invoice_number", "Date": "date", "Item": "product", "Qty": "quantity",
             "Unit Price": "unit_price", "Cost": "cost", "Total": "total"}
        res = engine.run(self.H, rows, m)
        got = changes(res)
        self.assertEqual(got[(1, "Unit Price")], "3.250")
        self.assertEqual(got[(1, "Cost")], "1.350")
        self.assertEqual(got[(1, "Total")], "6.500")
        self.assertEqual(got[(3, "Cost")], "0.100")
        self.assertEqual(len(got), 4)
        self.assertIn("fils_detected", {i["key"] for i in res["issues"]})

    def test_explicit_fils_word(self):
        res = engine.run(["Item", "Price"], [["Water", "350 فلس"], ["Pepsi", "0.5"]], {"Item": "product", "Price": "unit_price"})
        self.assertEqual(changes(res)[(0, "Price")], "0.350")

    def test_file_wide_fils_setting_is_unchanged(self):
        res = engine.run(["Item", "Price"], [["Water", "350"], ["Pepsi", "500"]], {"Item": "product", "Price": "unit_price"},
                         price_unit="fils")
        self.assertEqual(changes(res, "fils_to_jd"), {(0, "Price"): "0.350", (1, "Price"): "0.500"})
        self.assertEqual(changes(res), {})


if __name__ == "__main__":
    unittest.main()
