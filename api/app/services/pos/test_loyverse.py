"""Loyverse connector: mapping/accounting, signatures, pagination, errors, OAuth requests.
Fixtures: DOC_RECEIPT is the response sample from the official Loyverse API reference
(GET /receipts/{receipt_number}); every other receipt is SYNTHETIC test data built
from the documented fields. None of this proves a real Loyverse integration."""
import copy
import datetime as dt
import hashlib
import hmac
import json
import os
import time
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.services.pos import adapter, loyverse, loyverse_oauth, model

DOC_RECEIPT = {
    "receipt_number": "2-1008", "note": None, "receipt_type": "SALE", "refund_for": None, "order": "O-1598498",
    "created_at": "2020-06-23T08:35:47.047Z", "updated_at": "2020-06-23T08:35:47.047Z", "source": "My app",
    "receipt_date": "2020-06-23T08:34:45.025Z", "cancelled_at": None, "total_money": 17.52, "total_tax": 0.92,
    "points_earned": 1.75, "points_deducted": 0, "points_balance": 332.32, "customer_id": "c71758a2-79bf-11ea-bde9-1269e7c5a22d",
    "total_discount": 7.4, "employee_id": "58f53835-7a17-11ea-bde9-1269e7c5a22d", "store_id": "42dc2cec-6f40-11ea-bde9-1269e7c5a22d",
    "pos_device_id": "1cce2f2e-8033-4b67-ad2a-b9d1c749ec26", "dining_option": "Dine in",
    "total_discounts": [{"id": "82185d34-97a9-4137-8e1b-e0d1f07a7cd7", "type": "FIXED_PERCENT", "name": "Percent discount", "percentage": 10, "money_amount": 2.4},
                        {"id": "77d2bf40-7b12-11ea-bc55-0242ac130003", "type": "DISCOUNT_BY_POINTS", "name": "Discount by points", "money_amount": 5}],
    "total_taxes": [{"id": "a94d8606-7268-11ea-bde9-1269e7c5a22d", "type": "ADDED", "name": "Added", "rate": 5.545, "money_amount": 0.92}],
    "tip": 0, "surcharge": 0,
    "line_items": [{"id": "365972a1-7268-11ea-bde9-1269e7c5a22d", "item_id": "d5fe0da6-44b3-4633-9915-e9dc5118cbfc", "variant_id": "706e2626-3329-45f8-98d7-0e1dbcbcb9d9",
                    "item_name": "Ice cream", "variant_name": None, "sku": "10010", "quantity": 2, "price": 10, "gross_total_money": 24, "total_money": 17.52,
                    "cost": 5, "cost_total": 10, "line_note": "Note for the item", "line_taxes": [], "total_discount": 7.4, "line_discounts": [], "line_modifiers": []}],
    "payments": [{"payment_type_id": "42dd2a55-6f40-11ea-bde9-1269e7c5a22d", "name": "Cash", "type": "CASH", "money_amount": 5.84, "paid_at": "2020-06-23T08:35:47.047Z", "payment_details": None},
                 {"payment_type_id": "77d2bf40-7b12-11ea-bc55-0242ac130003", "name": "Cash rounding", "type": "CASHROUNDING", "money_amount": 0.04, "paid_at": "2020-03-10T08:23:20.020Z", "payment_details": None},
                 {"payment_type_id": "42dd2d07-6f40-11ea-bde9-1269e7c5a22d", "name": "Card", "type": "NONINTEGRATEDCARD", "money_amount": 5.84, "paid_at": "2020-06-23T08:35:47.047Z", "payment_details": None},
                 {"payment_type_id": "49d306bc-4454-48c1-9a92-c878290af83e", "name": "Worldpay", "type": "WORLDPAY", "money_amount": 5.84, "paid_at": "2020-06-23T08:35:47.047Z", "payment_details": {}}],
}
STORE = "42dc2cec-6f40-11ea-bde9-1269e7c5a22d"
STORES = {STORE: {"name": "Main store"}}


def synthetic(**over):
    r = copy.deepcopy(DOC_RECEIPT)
    r.update(over)
    return r


class MappingTests(unittest.TestCase):
    def test_documented_sample_reconciles_exactly(self):
        ev = loyverse.map_receipt(DOC_RECEIPT, STORES)
        s = ev.payload
        self.assertEqual((ev.type, ev.external_id, s.invoice_number, s.status), (model.EVENT_SALE, "2-1008", "2-1008", "completed"))
        self.assertEqual((s.total(), s.tax, s.discount), (Decimal("17.520"), Decimal("0.92"), Decimal("0")))
        self.assertEqual(s.lines[0].unit_price, Decimal("12"), "gross_total_money / quantity keeps modifiers")
        self.assertEqual((s.lines[0].discount, s.lines[0].unit_cost, s.branch), (Decimal("7.4"), Decimal("5"), "Main store"))
        self.assertEqual(ev.occurred_at, dt.datetime(2020, 6, 23, 8, 34, 45, 25000, tzinfo=dt.timezone.utc), "receipt_date, UTC")
        self.assertEqual(ev.version, "2020-06-23T08:35:47.047Z")
        ev.validate()

    def test_included_tax_is_not_added_again(self):
        r = synthetic(total_taxes=[{"type": "INCLUDED", "money_amount": 1.5}], total_tax=1.5, total_money=16.6)
        self.assertEqual(loyverse.map_receipt(r, STORES).payload.total(), Decimal("16.600"))

    def test_tip_and_surcharge_reconcile_and_mismatch_is_rejected(self):
        ok = synthetic(tip=2, surcharge=1, total_money=20.52)
        self.assertEqual(loyverse.map_receipt(ok, STORES).payload.total(), Decimal("17.520"))
        with self.assertRaises(loyverse.ReconciliationError):
            loyverse.map_receipt(synthetic(total_money=99), STORES)

    def test_refund_and_cancellation(self):
        refund = loyverse.map_receipt(synthetic(receipt_number="2-1009", receipt_type="REFUND", refund_for="2-1008"), STORES)
        self.assertEqual((refund.type, refund.external_id, refund.payload.status), (model.EVENT_REFUND, "2-1009", "returned"))
        void = loyverse.map_receipt(synthetic(cancelled_at="2020-06-23T09:00:00.000Z", updated_at="2020-06-23T09:00:00.000Z"), STORES)
        self.assertEqual((void.type, void.external_id, void.payload.status), (model.EVENT_SALE_VOID, "2-1008", "void"))
        self.assertGreater(void.version_key(), loyverse.map_receipt(DOC_RECEIPT, STORES).version_key(), "the cancellation wins")

    def test_unauthorized_store_skipped_and_bad_receipts_rejected(self):
        self.assertIsNone(loyverse.map_receipt(DOC_RECEIPT, STORES, allowed={"another-store"}))
        for bad in (synthetic(receipt_number=None), synthetic(receipt_type="EXCHANGE"), synthetic(total_money="x")):
            with self.assertRaises(model.InvalidEvent):
                loyverse.map_receipt(bad, STORES)

    def test_payment_method_by_largest_non_rounding_payment(self):
        card = synthetic(payments=[{"type": "CASH", "money_amount": 2}, {"type": "NONINTEGRATEDCARD", "money_amount": 15.52}])
        self.assertEqual(loyverse.map_receipt(card, STORES).payload.payment_method, "card")
        self.assertEqual(loyverse.map_receipt(synthetic(payments=[]), STORES).payload.payment_method, "cash")


class SignatureTests(unittest.TestCase):
    def test_hmac_sha1_lowercase_hex_over_raw_body(self):
        secret, raw = "app-client-secret-for-tests", b'{"merchant_id":"m","type":"receipts.update"}'
        sig = hmac.new(secret.encode(), raw, hashlib.sha1).hexdigest()
        self.assertTrue(loyverse.verify_signature(secret, raw, sig))
        self.assertTrue(loyverse.verify_signature(secret, raw, sig.upper()))
        for bad in (None, "", sig[:-1], "0" * 40):
            self.assertFalse(loyverse.verify_signature(secret, raw, bad))
        self.assertFalse(loyverse.verify_signature(secret, raw + b" ", sig), "any byte change fails")
        self.assertFalse(loyverse.verify_signature("", raw, sig))


def transport(pages, calls, status=200):
    def handler(request):
        calls.append(request)
        if status != 200:
            return httpx.Response(status, json={"errors": [{"code": "X"}]})
        cur = request.url.params.get("cursor")
        page = pages[int(cur) if cur else 0]
        return httpx.Response(200, json=page)
    return httpx.MockTransport(handler)


class AdapterTests(unittest.TestCase):
    def adapter(self, pages, calls, status=200, now=None):
        return loyverse.LoyverseAdapter("token", {"store_names": {STORE: "Main store"}, "allowed_store_ids": [STORE],
                                                 "import_since": "2020-06-23T00:00:00.000Z"},
                                        transport=transport(pages, calls, status),
                                        now=now or (lambda: dt.datetime(2020, 6, 23, 12, tzinfo=dt.timezone.utc)))

    def test_pagination_window_and_cursor(self):
        calls = []
        pages = [{"receipts": [DOC_RECEIPT], "cursor": "1"},
                 {"receipts": [synthetic(receipt_number="2-1009", updated_at="2020-06-23T09:00:00.000Z")]}]
        events, cursor = self.adapter(pages, calls).fetch_changes(adapter.AdapterContext(org_id="o"))
        self.assertEqual([e.external_id for e in events], ["2-1008", "2-1009"])
        self.assertEqual(calls[0].url.params["updated_at_min"], "2020-06-23T00:00:00.000Z")
        self.assertEqual(calls[0].url.params["updated_at_max"], "2020-06-23T12:00:00.000Z")
        self.assertEqual((calls[0].url.params["limit"], calls[1].url.params["cursor"]), ("250", "1"))
        self.assertEqual(calls[0].headers["authorization"], "Bearer token")
        self.assertEqual(cursor["updated_at_min"], "2020-06-23T12:00:00.000Z")

    def test_next_run_rereads_a_five_minute_overlap(self):
        calls = []
        ad = self.adapter([{"receipts": []}], calls)
        ad.fetch_changes(adapter.AdapterContext(org_id="o", cursor={"updated_at_min": "2020-06-23T11:00:00.000Z"}))
        self.assertEqual(calls[0].url.params["updated_at_min"], "2020-06-23T10:55:00.000Z")
        calls.clear()
        ad.fetch_changes(adapter.AdapterContext(org_id="o", cursor={"updated_at_min": "2020-06-23T00:02:00.000Z"}))
        self.assertEqual(calls[0].url.params["updated_at_min"], "2020-06-23T00:00:00.000Z", "never before the import start")

    def test_unreconciled_receipt_becomes_reviewable_error(self):
        calls = []
        events, _ = self.adapter([{"receipts": [synthetic(total_money=1)]}], calls).fetch_changes(adapter.AdapterContext(org_id="o"))
        with self.assertRaises(model.InvalidEvent):
            events[0].validate()
        self.assertEqual(events[0].external_id, "2-1008")

    def test_errors_map_to_auth_or_temporary(self):
        for status, exc in ((401, adapter.SourceAuthError), (402, adapter.SourceAuthError), (403, adapter.SourceAuthError),
                            (429, adapter.SourceTemporaryError), (500, adapter.SourceTemporaryError)):
            with self.assertRaises(exc):
                self.adapter([{}], [], status=status).fetch_changes(adapter.AdapterContext(org_id="o"))

    def test_window_narrows_when_too_many_pages(self):
        calls = []
        many = [{"receipts": [], "cursor": str(i + 1)} for i in range(200)] + [{"receipts": []}]
        def handler(request):
            calls.append(request)
            mn = request.url.params["updated_at_min"]; mx = request.url.params["updated_at_max"]
            span = (dt.datetime.fromisoformat(mx.replace("Z", "+00:00")) - dt.datetime.fromisoformat(mn.replace("Z", "+00:00")))
            if span > dt.timedelta(hours=7):   # synthetic: a busy day needs smaller windows
                cur = request.url.params.get("cursor")
                return httpx.Response(200, json=many[int(cur) if cur else 0])
            return httpx.Response(200, json={"receipts": []})
        ad = loyverse.LoyverseAdapter("t", {"import_since": "2020-06-22T00:00:00.000Z"}, transport=httpx.MockTransport(handler),
                                      now=lambda: dt.datetime(2020, 6, 23, 0, tzinfo=dt.timezone.utc))
        _, cursor = ad.fetch_changes(adapter.AdapterContext(org_id="o"))
        spans = {(dt.datetime.fromisoformat(c.url.params["updated_at_max"].replace("Z", "+00:00")) - dt.datetime.fromisoformat(c.url.params["updated_at_min"].replace("Z", "+00:00"))) for c in calls}
        self.assertTrue(any(s <= dt.timedelta(hours=6) for s in spans), "narrowed to <= 6h windows")
        self.assertEqual(cursor["updated_at_min"], "2020-06-23T00:00:00.000Z", "advanced through the busy day in smaller windows")


class OAuthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"LOYVERSE_ENABLED": "on", "LOYVERSE_CLIENT_ID": "synthetic-client-id",
                                          "LOYVERSE_CLIENT_SECRET": "synthetic-client-secret-xyz",
                                          "LOYVERSE_REDIRECT_URI": "https://idrak.example.com/ar/app/integrations/loyverse/callback",
                                          "LOYVERSE_WEBHOOK_URL": "https://api.idrak.example.com/integrations/loyverse/webhook",
                                          "IDRAK_CONNECT_ENCRYPTION_KEY": Fernet.generate_key().decode()})
        self.env.start(); self.addCleanup(self.env.stop)
        self.org, self.user = str(uuid4()), str(uuid4())

    def test_disabled_unless_fully_configured(self):
        self.assertTrue(loyverse_oauth.available())
        for k in ("LOYVERSE_ENABLED", "LOYVERSE_CLIENT_SECRET", "LOYVERSE_REDIRECT_URI"):
            with patch.dict(os.environ, {k: ""}):
                self.assertFalse(loyverse_oauth.available())
        with patch.dict(os.environ, {"LOYVERSE_REDIRECT_URI": "http://insecure.example.com/cb"}):
            self.assertFalse(loyverse_oauth.available())

    def test_authorize_url_least_privilege_and_state_binding(self):
        a = loyverse_oauth.new_authorization(self.org, self.user, "ar")
        u = urlsplit(a["authorize_url"]); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        self.assertEqual(f"{u.scheme}://{u.netloc}{u.path}", "https://api.loyverse.com/oauth/authorize")
        self.assertEqual(q, {"client_id": "synthetic-client-id", "scope": "MERCHANT_READ STORES_READ RECEIPTS_READ", "response_type": "code",
                             "redirect_uri": "https://idrak.example.com/ar/app/integrations/loyverse/callback", "state": a["state"]})
        self.assertNotIn("synthetic-client-secret", a["authorize_url"] + a["intent"])
        loyverse_oauth.validate_intent(a["intent"], a["state"], self.org, self.user)
        other = loyverse_oauth.new_authorization(self.org, self.user, "ar")
        for intent, state, org, user in ((a["intent"], other["state"], self.org, self.user), (a["intent"], a["state"], str(uuid4()), self.user),
                                         (a["intent"], a["state"], self.org, str(uuid4())), (a["intent"][:-2] + "00", a["state"], self.org, self.user)):
            with self.assertRaises(HTTPException):
                loyverse_oauth.validate_intent(intent, state, org, user)
        with patch.object(loyverse_oauth.time, "time", return_value=time.time() + 700):
            with self.assertRaises(HTTPException):
                loyverse_oauth.validate_intent(a["intent"], a["state"], self.org, self.user)

    async def test_token_exchange_form_and_response_validation(self):
        seen = []
        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={"access_token": "a" * 36, "token_type": "Bearer", "expires_in": 43200, "refresh_token": "r" * 40, "scope": "RECEIPTS_READ"})
        t = await loyverse_oauth._token_request({"grant_type": "authorization_code", "code": "c" * 20}, httpx.MockTransport(handler))
        self.assertEqual(str(seen[0].url), "https://api.loyverse.com/oauth/token")
        self.assertEqual(seen[0].headers["content-type"], "application/x-www-form-urlencoded")
        self.assertAlmostEqual(t["expires_at"], time.time() + 43200, delta=5)
        with self.assertRaises(adapter.SourceAuthError):
            await loyverse_oauth._token_request({}, httpx.MockTransport(lambda r: httpx.Response(400, json={"error": "invalid_grant"})))
        with self.assertRaises(HTTPException):
            await loyverse_oauth._token_request({}, httpx.MockTransport(lambda r: httpx.Response(200, json={"token_type": "mac"})))

    async def test_webhook_signature_checked_before_anything(self):
        raw = json.dumps({"merchant_id": "m-1", "type": "receipts.update"}).encode()
        with patch.object(loyverse_oauth.db, "fetchrow", new=AsyncMock()) as fetch:
            with self.assertRaises(PermissionError):
                await loyverse_oauth.handle_webhook(raw, "0" * 40)
            fetch.assert_not_awaited()
        sig = hmac.new(b"synthetic-client-secret-xyz", raw, hashlib.sha1).hexdigest()
        with patch.object(loyverse_oauth.db, "fetchrow", new=AsyncMock(return_value=None)):
            self.assertEqual(await loyverse_oauth.handle_webhook(raw, sig), {"status": "ignored"}, "unknown/disconnected account")
        other = json.dumps({"merchant_id": "m-1", "type": "items.update"}).encode()
        self.assertEqual(await loyverse_oauth.handle_webhook(other, hmac.new(b"synthetic-client-secret-xyz", other, hashlib.sha1).hexdigest()), {"status": "ignored"})
