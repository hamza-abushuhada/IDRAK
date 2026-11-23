"""Date-range filters reach the database as dates, not strings.

Run from api/:  python -m unittest app.routers.test_date_params

asyncpg encodes a "$n::date" parameter only from a datetime.date; a "2024-07-25"
string raised "'str' object has no attribute 'toordinal'", so the sales list
returned 500 ("the server is busy") whenever a date range was picked. The fake
DB below fails the same way asyncpg does. No DB or model needed.
"""

import datetime as dt
import types
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.auth import org_ctx
from app.routers import insights, workspace
from app.services import insights as insights_service

CTX = types.SimpleNamespace(org_id="org-1", role="owner", user=types.SimpleNamespace(id="user-1"), can=lambda perm: True)


def _like_asyncpg(sql, args):
    # Every "$n::date" parameter must be a date, as asyncpg's date encoder requires.
    for i, a in enumerate(args, start=1):
        if f"${i}::date" in sql and not isinstance(a, dt.date):
            raise AttributeError(f"{type(a).__name__!r} object has no attribute 'toordinal'")


class DateParams(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(workspace.router)
        app.include_router(insights.router)
        app.dependency_overrides[org_ctx] = lambda: CTX
        self.client = TestClient(app)
        self.calls = []

        async def fetchval(sql, *args):
            _like_asyncpg(sql, args)
            self.calls.append(args)
            return 0

        async def fetch(sql, *args):
            _like_asyncpg(sql, args)
            self.calls.append(args)
            return []

        for name, fake in (("fetchval", fetchval), ("fetch", fetch)):
            p = mock.patch.object(db, name, fake)
            p.start()
            self.addCleanup(p.stop)

    def test_sales_with_a_date_range_and_filters(self):
        r = self.client.get("/ws/sales", params={"start": "2024-07-25", "end": "2026-12-02",
                                                 "payment": "cash", "status": "completed"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"total": 0, "items": []})
        self.assertIn(dt.date(2024, 7, 25), self.calls[0])
        self.assertIn(dt.date(2026, 12, 2), self.calls[0])

    def test_sales_without_dates_still_works(self):
        self.assertEqual(self.client.get("/ws/sales").status_code, 200)

    def test_malformed_date_is_a_clear_422_not_a_500(self):
        self.assertEqual(self.client.get("/ws/sales", params={"start": "25/07/2024"}).status_code, 422)
        self.assertEqual(self.client.get("/insights/dashboard", params={"start": "nope", "end": "2026-01-01"}).status_code, 422)

    def test_dashboard_custom_range_gets_dates(self):
        seen = {}

        async def fake_dashboard(org_id, days, branch_id, start, end):
            seen.update(start=start, end=end)
            return {}

        with mock.patch.object(insights_service, "dashboard", fake_dashboard):
            r = self.client.get("/insights/dashboard", params={"start": "2024-07-25", "end": "2026-12-02"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(seen, {"start": dt.date(2024, 7, 25), "end": dt.date(2026, 12, 2)})


if __name__ == "__main__":
    unittest.main()
