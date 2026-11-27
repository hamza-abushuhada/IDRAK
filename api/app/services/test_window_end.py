"""User-facing "last N days" windows end TODAY (Amman) for live businesses."""
import datetime as dt
import unittest
from unittest.mock import AsyncMock, patch

from app import db
from app.services import insights as I

TODAY = dt.date(2026, 11, 27)


class WindowEndTests(unittest.IsolatedAsyncioTestCase):
    async def end_for(self, last):
        db.cache_clear()
        with patch.object(I, "today", return_value=TODAY), patch.object(db, "fetchval", new=AsyncMock(return_value=last)) as q:
            end = await I.window_end("org")
        return end, q.await_args.args[0]

    async def test_cases(self):
        cases = {
            "new business (no sales)": (None, TODAY),
            "sales only today": ("2026-11-27", TODAY),
            "no sales yesterday (last sale 2 days ago)": ("2026-11-25", TODAY),
            "last sale 90 days ago still live": (TODAY - dt.timedelta(days=90), TODAY),
            "old import only (March)": ("2026-03-15", dt.date(2026, 3, 15)),
        }
        for name, (last, expected) in cases.items():
            with self.subTest(name):
                end, sql = await self.end_for(last)
                self.assertEqual(end, expected)
                self.assertIn("<= amman_date(now())", sql, "future-dated imports never stretch the window")

    async def test_cached_per_org_and_cleared_by_sync(self):
        db.cache_clear()
        with patch.object(I, "today", return_value=TODAY), patch.object(db, "fetchval", new=AsyncMock(return_value="2026-03-15")) as q:
            await I.window_end("org"); await I.window_end("org")
            self.assertEqual(q.await_count, 1)
            db.cache_clear()   # what pipeline.run_sync does after importing sales
            await I.window_end("org")
            self.assertEqual(q.await_count, 2)

    async def test_dashboard_default_window_ends_today_custom_ranges_untouched(self):
        db.cache_clear()
        with patch.object(I, "window_end", new=AsyncMock(return_value=TODAY)) as we, \
                patch.object(db, "fetchrow", new=AsyncMock(return_value={k: 0 for k in ("gross_sales", "returns_value", "revenue", "tx", "discounts", "voids",
                                                                                        "returns", "customers", "gross_profit", "profit", "units")})), \
                patch.object(db, "fetch", new=AsyncMock(return_value=[])):
            d = await I.dashboard.__wrapped__("org", 30) if hasattr(I.dashboard, "__wrapped__") else await I.dashboard("org-a", 30)
            self.assertEqual((d["range"]["start"], d["range"]["end"]), ("2026-10-29", "2026-11-27"))
            we.assert_awaited()
            db.cache_clear()
            d = await I.dashboard("org-b", 30, None, dt.date(2026, 11, 20), dt.date(2026, 11, 27))
            self.assertEqual((d["range"]["start"], d["range"]["end"]), ("2026-11-20", "2026-11-27"))
