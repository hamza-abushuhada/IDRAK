"""The import (apply_run) on a fake database: what it writes for sales and purchases.

Run from api/:  python -m unittest app.routers.test_import_apply

Covers the level-1 fixes from a restaurant account: returns kept as returns,
customers created from sales, a missing cost taken from the product's other rows,
a missing payment method kept as "other", and supplier invoices imported as real
purchases (suppliers, purchases, purchase lines).
"""

import types
import unittest
import uuid
from decimal import Decimal
from unittest import mock

from app.cleaning.fields import ENTITY_KEY, field_signature
from app.routers import data

CTX = types.SimpleNamespace(org_id=str(uuid.uuid4()), role="owner", user=types.SimpleNamespace(id=str(uuid.uuid4())),
                            can=lambda perm: True)


class FakeConn:
    """Records what the import writes; every lookup table starts empty."""

    def __init__(self):
        self.copies: dict[str, list[dict]] = {}
        self.inserts: list[tuple[str, tuple]] = []
        self.executed: list[tuple[str, object]] = []

    async def fetch(self, sql, *args):
        return []

    async def fetchrow(self, sql, *args):
        return None

    async def fetchval(self, sql, *args):
        if "returning id" in sql:
            table = sql.split("into", 1)[1].split("(", 1)[0].strip()
            self.inserts.append((table, args))
            return uuid.uuid4()
        return None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "DELETE 0"

    async def executemany(self, sql, records):
        self.executed.append((sql, list(records)))

    async def copy_records_to_table(self, table, records, columns):
        self.copies.setdefault(table, []).extend(dict(zip(columns, r)) for r in records)


class _Tx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


def mapping_of(fields: dict[str, str], entity: str | None = None) -> dict:
    m = {h: {"field": f, "confidence": 1.0, "source": "user"} for h, f in fields.items()}
    if entity:
        m[ENTITY_KEY] = {"entity": entity, "fields": field_signature(m)}
    return m


async def import_rows(headers, rows, mapping, entity):
    conn = FakeConn()
    run_row = {"columns": headers, "mapping": mapping, "entity": entity, "stats": {"entity": entity},
               "imported_at": None, "reverted_at": None, "upload_id": str(uuid.uuid4()), "file_name": "f.csv",
               "batch_id": None, "batch_contract": None, "score_before": {"score": 50}, "score_after": {"score": 90}}
    fetchrow = mock.AsyncMock(side_effect=[run_row, {"raw_rows": rows}])
    with mock.patch.object(data.db, "fetchrow", fetchrow), \
            mock.patch.object(data.db, "fetch", mock.AsyncMock(return_value=[])), \
            mock.patch.object(data.db, "execute", mock.AsyncMock()), \
            mock.patch.object(data.db, "audit", mock.AsyncMock()), \
            mock.patch.object(data.db, "cache_clear", lambda: None), \
            mock.patch.object(data.db, "transaction", lambda: _Tx(conn)):
        res = await data.apply_run("r1", CTX)
    return res, conn


class Sales(unittest.IsolatedAsyncioTestCase):
    H = ["Invoice No", "Date", "Branch", "Item", "Qty", "Unit Price", "Cost", "Payment", "Customer", "Phone"]
    FIELDS = {"Invoice No": "invoice_number", "Date": "date", "Branch": "branch", "Item": "product", "Qty": "quantity",
              "Unit Price": "unit_price", "Cost": "cost", "Payment": "payment_method", "Customer": "customer_name",
              "Phone": "phone"}
    ROWS = [["1", "2026-01-05", "Khalda", "Zinger", "2", "3.250", "1.350", "cash", "Ali", "+962791234567"],
            ["1", "2026-01-05", "Khalda", "Pepsi", "-1", "0.500", "0.220", "cash", "Ali", "+962791234567"],
            ["2", "2026-01-06", "Khalda", "Fries", "1", "1.750", "", "", "", ""],
            ["3", "2026-01-06", "Khalda", "Fries", "1", "1.750", "0.600", "card", "Ali", "+962791234567"]]

    async def asyncSetUp(self):
        self.res, self.conn = await import_rows(self.H, self.ROWS, mapping_of(self.FIELDS), "sales")
        self.sales = self.conn.copies["sales"]

    async def test_return_line_is_a_returned_sale(self):
        returned = [s for s in self.sales if s["status"] == "returned"]
        self.assertEqual(len(returned), 1)
        self.assertEqual(returned[0]["total"], Decimal("0.500"))
        self.assertEqual(returned[0]["invoice_number"], "1")
        self.assertEqual(self.res["returns"], {"lines": 1, "invoices": 1, "value": 0.5, "imported": True})

    async def test_every_valid_sale_is_kept(self):
        completed = [s for s in self.sales if s["status"] == "completed"]
        self.assertEqual(sorted(s["invoice_number"] for s in completed), ["1", "2", "3"])
        self.assertEqual(self.res["skipped"]["count"], 0)

    async def test_missing_payment_is_other(self):
        inv2 = next(s for s in self.sales if s["invoice_number"] == "2")
        self.assertEqual(inv2["payment_method"], "other")

    async def test_customer_created_from_the_phone_and_linked(self):
        custs = self.conn.copies["customers"]
        self.assertEqual([(c["full_name"], c["phone"], str(c["first_seen"])) for c in custs],
                         [("Ali", "+962791234567", "2026-01-05")])
        linked = {s["invoice_number"] for s in self.sales if s["customer_id"] == custs[0]["id"]}
        self.assertEqual(linked, {"1", "3"})

    async def test_new_product_without_cost_on_its_row_takes_its_other_rows_cost(self):
        fries = [args for table, args in self.conn.inserts if table == "products" and args[1] == "Fries"]
        self.assertEqual(len(fries), 1)
        self.assertEqual(fries[0][5], Decimal("0.600"))  # (org, name, sku, barcode, price, cost, ...)


class Purchases(unittest.IsolatedAsyncioTestCase):
    H = ["Invoice", "Date", "Branch", "Supplier", "Item", "Carton Price", "Piece Price", "Qty", "Total", "Notes"]
    FIELDS = {"Invoice": "invoice_number", "Date": "date", "Branch": "branch", "Supplier": "supplier", "Item": "product",
              "Carton Price": "carton_price", "Piece Price": "unit_price", "Qty": "quantity", "Total": "total",
              "Notes": "notes"}
    ROWS = [["90101", "2026-01-05", "Khalda", "Al Wafa", "Chicken breast", "", "2.500", "10", "25.000", "checked"],
            ["90101", "2026-01-05", "Khalda", "Al Wafa", "Bread", "3.919", "", "2", "", ""],
            ["90102", "2026-01-06", "Gardens", "Taybeh", "Chicken breast", "", "2.600", "5", "", ""],
            ["90103", "2026-01-07", "Gardens", "Taybeh", "Garlic", "", "", "", "4.000", ""]]  # no quantity: skipped

    async def asyncSetUp(self):
        self.res, self.conn = await import_rows(self.H, self.ROWS, mapping_of(self.FIELDS, "purchases"), "purchases")

    async def test_invoices_become_purchases_with_lines(self):
        purchases = self.conn.copies["purchases"]
        self.assertEqual(sorted(p["po_number"] for p in purchases), ["90101", "90102"])
        p1 = next(p for p in purchases if p["po_number"] == "90101")
        self.assertEqual((p1["total"], p1["status"], p1["notes"]), (Decimal("32.838"), "received", "checked"))
        lines = sorted((i["quantity"], i["unit_cost"], i["line_total"]) for i in self.conn.copies["purchase_items"])
        self.assertEqual(lines, [(Decimal("2"), Decimal("3.919"), Decimal("7.838")),
                                 (Decimal("5"), Decimal("2.600"), Decimal("13.000")),
                                 (Decimal("10"), Decimal("2.500"), Decimal("25.000"))])

    async def test_suppliers_are_created_once_each(self):
        made = [args[1] for table, args in self.conn.inserts if table == "suppliers"]
        self.assertEqual(made, ["Al Wafa", "Taybeh"])
        self.assertEqual(self.res["imported"]["suppliers_created"], ["Al Wafa", "Taybeh"])

    async def test_line_without_quantity_is_skipped_with_a_reason(self):
        self.assertEqual(self.res["skipped"]["count"], 1)
        self.assertIn("كمية", self.res["skipped"]["sample"][0]["reason_ar"])

    async def test_purchase_ids_are_kept_for_undo_but_not_shown(self):
        self.assertNotIn("purchase_ids", self.res["imported"])
        self.assertEqual(self.res["imported"]["purchases"], 2)
        saved = next(args for sql, args in self.conn.executed if "status='imported'" in sql)
        self.assertEqual(len(saved[1]["purchase_ids"]), 2)


if __name__ == "__main__":
    unittest.main()
