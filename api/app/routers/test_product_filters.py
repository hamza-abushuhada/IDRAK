"""The products list filters ("below cost", "low stock") count only what they claim to.

Run from api/:  python -m unittest app.routers.test_product_filters

A restaurant's raw materials (bread, meat, fries) have no selling price, so
"cost > price" listed every one of them as sold below cost; and with no stock
data at all, every product showed as low stock. No DB needed.
"""

import datetime as dt
import types
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.auth import org_ctx
from app.routers import workspace
from app.services import insights as insights_service

CTX = types.SimpleNamespace(org_id="org-1", role="owner", user=types.SimpleNamespace(id="user-1"), can=lambda perm: True)


def product(name, price, cost, stock=0, stock_known=True, reorder=10):
    return {"id": name, "name": name, "name_ar": None, "sku": None, "barcode": None, "price": price, "cost": cost,
            "stock": stock, "stock_known": stock_known, "reorder_level": reorder, "category_id": None, "next_expiry": None}


ROWS = [
    product("Zinger", 3.25, 1.35, stock=40),
    product("Burger at a loss", 3.75, 3.9, stock=40),
    product("Bread (raw material)", 0, 1.25, stock=40),
    product("Low", 2.0, 0.8, stock=3),
    product("Untracked", 2.0, 0.8, stock=0, stock_known=False),
]


class ProductFilters(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(workspace.router)
        app.dependency_overrides[org_ctx] = lambda: CTX
        self.client = TestClient(app)

        async def fetch(sql, *args):
            return [dict(r) for r in ROWS] if "from products p" in sql else []

        async def data_end(org_id):
            return dt.date(2026, 11, 22)

        for target, name, fake in ((db, "fetch", fetch), (insights_service, "data_end", data_end), (insights_service, "window_end", data_end)):
            p = mock.patch.object(target, name, fake)
            p.start()
            self.addCleanup(p.stop)

    def names(self, f):
        r = self.client.get("/ws/products", params={"filter": f})
        self.assertEqual(r.status_code, 200, r.text)
        return [p["name"] for p in r.json()["items"]]

    def test_below_cost_skips_products_without_a_selling_price(self):
        self.assertEqual(self.names("below_cost"), ["Burger at a loss"])

    def test_low_stock_skips_untracked_products(self):
        self.assertEqual(self.names("low_stock"), ["Low"])


if __name__ == "__main__":
    unittest.main()
