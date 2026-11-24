"""Valid sales stay in: only what really can't be imported keeps a row out.

Run from api/:  python -m unittest app.cleaning.test_keep_sales

A restaurant export lost 408 sales rows (and flagged 4,088 cells) for things the
import can work out itself: a line total that includes 16% tax, an empty total
next to a quantity and a price, a cost written "غير محدد", a date like 08/12/2026
that is a past day read month-first.
"""

import datetime as dt
import unittest

from app.cleaning import engine
from app.routers.data import _blocks

H = ["Invoice No", "Date", "Item", "Qty", "Unit Price", "Cost", "Discount", "Total", "Payment"]
M = {"Invoice No": "invoice_number", "Date": "date", "Item": "product", "Qty": "quantity", "Unit Price": "unit_price",
     "Cost": "cost", "Discount": "discount", "Total": "total", "Payment": "payment_method"}
TODAY = dt.date(2026, 11, 24)


def run(rows):
    return engine.run(H, rows, M, today=TODAY)


def flags(res, reason):
    return {(f["row"], f["column"]) for f in res["flags"] if f["reason"] == reason}


class Totals(unittest.TestCase):

    def test_total_with_tax_or_discount_is_not_a_mismatch(self):
        res = run([["1", "2026-01-05", "Mutabbal", "2", "1.5", "0.55", "", "3.48", "cash"],     # +16% tax
                   ["2", "2026-01-05", "Zinger", "1", "3.25", "1.35", "0.25", "3.00", "cash"],   # after discount
                   ["3", "2026-01-05", "Zinger", "1", "3.25", "1.35", "0.25", "3.48", "cash"]])  # discount, then tax
        self.assertEqual(flags(res, "total_mismatch"), set())

    def test_a_total_that_nothing_explains_is_still_flagged(self):
        res = run([["1", "2026-01-05", "Zinger", "1", "3.25", "1.35", "", "9.90", "cash"]])
        self.assertEqual(flags(res, "total_mismatch"), {(0, "Total")})

    def test_empty_total_is_not_flagged(self):
        res = run([["1", "2026-01-05", "Zinger", "2", "3.25", "1.35", "", "", "cash"]])
        self.assertEqual(flags(res, "missing_total"), set())

    def test_price_from_the_total_is_not_missing(self):
        res = run([["1", "2026-01-05", "Zinger", "2", "", "1.35", "", "6.50", "cash"]])
        self.assertEqual(flags(res, "missing_required"), set())


class Values(unittest.TestCase):

    def test_not_specified_cost_is_empty_not_unreadable(self):
        res = run([["1", "2026-01-05", "Zinger", "1", "3.25", "غير محدد", "", "3.25", "cash"]])
        self.assertEqual(flags(res, "invalid_number"), set())

    def test_future_day_first_date_becomes_the_past_month_first_one(self):
        res = run([["1", "08/12/2026", "Zinger", "1", "3.25", "1.35", "", "3.25", "cash"],
                   ["2", "15/10/2026", "Zinger", "1", "3.25", "1.35", "", "3.25", "cash"]])
        dates = {c["row"]: c["new"] for c in res["changes"] if c["column"] == "Date"}
        self.assertEqual(dates[0][:10], "2026-08-12")
        self.assertEqual(flags(res, "future_date"), set())

    def test_a_date_really_in_the_future_stays_flagged(self):
        res = run([["1", "2026-12-20", "Zinger", "1", "3.25", "1.35", "", "3.25", "cash"]])
        self.assertEqual(flags(res, "future_date"), {(0, "Date")})


class WhatBlocksARow(unittest.TestCase):
    FIELDS = {"Qty": "quantity", "Unit Price": "unit_price", "Cost": "cost", "Total": "total"}.get

    def test_fixable_problems_dont_block(self):
        for reason, col in (("missing_total", "Total"), ("total_mismatch", "Total"), ("unknown_payment", "Payment"),
                            ("invalid_number", "Cost"), ("invalid_number", "Total"), ("negative_qty", "Qty")):
            self.assertFalse(_blocks({"reason": reason, "column": col}, self.FIELDS), (reason, col))

    def test_real_problems_block(self):
        for reason, col in (("invalid_date", "Date"), ("future_date", "Date"), ("missing_required", "Item"),
                            ("invalid_number", "Qty"), ("invalid_number", "Unit Price")):
            self.assertTrue(_blocks({"reason": reason, "column": col}, self.FIELDS), (reason, col))


if __name__ == "__main__":
    unittest.main()
