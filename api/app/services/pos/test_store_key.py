"""Online store by API key: address allow-list (SSRF), key format, probe checks,
error mapping, notification parsing and that the key never appears in messages."""
import asyncio
import json
import os
import time
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.services.pos import adapter, store_key

LAB = "https://idrak-connect-lab-staging.vercel.app"
KEY = "lsk_0123456789ab_" + "A" * 43
STORE = "shop-abc123"
ENV = {"IDRAK_LAB_ORIGIN": LAB, "IDRAK_LAB_ALLOWED_ORIGINS": LAB, "IDRAK_STORE_API_KEYS": "all", "IDRAK_STORE_API_KEYS_ORGS": "",
       "IDRAK_CONNECT_ENCRYPTION_KEY": Fernet.generate_key().decode(), "IDRAK_LAB_PAIRING_KEY": "p" * 40}


def store_info(**over):
    return {"api_version": "1", "store_id": STORE, "name": "Store A", "currency": "JOD", "channel": "web",
            "source_system": "idrak-lab-store", "key_id": "0123456789ab", "scopes": ["orders:read"], "key_expires_at": None, **over}


def event(account=STORE, channel="web", system="idrak-lab-store"):
    return {"cursor": 1, "payload": {"event_type": "sale.created", "source": {"system": system, "account_id": account, "channel": channel},
                                      "order": {"external_id": "WEB-000001", "status": "completed", "items": [], "updated_at": "2026-11-27T10:00:00Z"}}}


def transport(info=None, events=None, status=200, redirect=False):
    seen = []

    def handler(request):
        seen.append(request)
        if redirect:
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/"})
        if status != 200:
            return httpx.Response(status, json={"error": "nope"})
        if request.url.path == "/api/v1/store":
            return httpx.Response(200, json=info or store_info())
        if request.url.path == "/api/web/events":
            return httpx.Response(200, json={"events": events if events is not None else [event()], "next_cursor": 1, "has_more": False})
        if request.url.path == "/api/v1/notifications":
            return httpx.Response(200, json={"enabled": True, "signing_secret": "f" * 64})
        return httpx.Response(404)
    return httpx.MockTransport(handler), seen


class StoreKeyTests(unittest.TestCase):
    def setUp(self):
        p = patch.dict(os.environ, ENV)
        p.start()
        self.addCleanup(p.stop)

    def test_only_the_allow_listed_https_store_origin_is_accepted(self):
        for ok in (LAB, LAB + "/", LAB + "/shop", " " + LAB + " "):
            self.assertEqual(store_key.store_origin(ok), LAB)
        for bad in ("http://idrak-connect-lab-staging.vercel.app", "https://127.0.0.1", "https://localhost", "https://169.254.169.254",
                    "https://evil.example.com", "https://idrak-connect-lab-staging.vercel.app.evil.com", f"{LAB}:8443", f"{LAB}/admin",
                    f"{LAB}?x=1", f"https://user:pw@{LAB[8:]}", "https://[::1]", "https://2130706433", "file:///etc/passwd", "", None, 5,
                    "https://idrak-connect-lab.vercel.app"):  # the published Lab is not the configured one here
            with self.assertRaises(ValueError, msg=repr(bad)):
                store_key.store_origin(bad)

    def test_key_format(self):
        self.assertEqual(store_key.key_id_of(KEY), "0123456789ab")
        for bad in ("lc.shop.x", "lsk_0123456789ab_short", KEY + "x", "Bearer " + KEY, None, KEY.replace("lsk", "LSK")):
            with self.assertRaises(ValueError):
                store_key.key_id_of(bad)

    def test_probe_accepts_owned_read_only_store(self):
        t, seen = transport()
        info = asyncio.run(store_key.probe(LAB, KEY, t))
        self.assertEqual((info["store_id"], info["name"], info["key_id"]), (STORE, "Store A", "0123456789ab"))
        self.assertTrue(all(r.headers["authorization"] == "Bearer " + KEY and str(r.url).startswith(LAB) for r in seen))

    def test_probe_rejects_foreign_or_wrong_answers_without_leaking(self):
        cases = {
            "key from another store": dict(info=store_info(key_id="ffffffffffff")),
            "wider scope": dict(info=store_info(scopes=["orders:read", "orders:write"])),
            "events of another store": dict(events=[event(account="shop-other")]),
            "pos events": dict(events=[event(channel="pos")]),
            "bad store id": dict(info=store_info(store_id="../../etc")),
            "server error": dict(status=500),
            "redirect": dict(redirect=True),
        }
        for name, kw in cases.items():
            with self.subTest(name), self.assertRaises(HTTPException) as caught:
                asyncio.run(store_key.probe(LAB, KEY, transport(**kw)[0]))
            self.assertEqual(caught.exception.status_code, 502)
            self.assertNotIn(KEY[-20:], caught.exception.detail)
        for status in (401, 403):
            with self.assertRaises(store_key.KeyRejected):
                asyncio.run(store_key.probe(LAB, KEY, transport(status=status)[0]))

    def test_adapter_maps_auth_and_outage_errors_without_the_key(self):
        creds = {"origin": LAB, "store_id": STORE, "api_key": KEY, "signing_secret": "f" * 64}
        a = store_key.LabStoreKeyAdapter(creds, "Lab " + STORE, transport(status=401)[0])
        with self.assertRaises(adapter.SourceAuthError) as e:
            a._pull(0)
        self.assertNotIn(KEY[-20:], str(e.exception))
        a = store_key.LabStoreKeyAdapter(creds, "Lab " + STORE, transport(status=503)[0])
        with self.assertRaises(adapter.SourceTemporaryError):
            a._pull(0)
        a = store_key.LabStoreKeyAdapter(creds, "Lab " + STORE, transport(events=[event(account="shop-other")])[0])
        with self.assertRaises(ValueError):  # another store's event is never imported
            a._pull(0)
        ok = store_key.LabStoreKeyAdapter(creds, "Lab " + STORE, transport()[0])
        events, cursor = ok._pull(0)
        self.assertEqual((len(events), cursor, events[0].external_id), (1, 1, "WEB-000001"))

    def test_notification_parsing_and_signature(self):
        body = {"key_id": "0123456789ab", "shop_id": STORE, "channel": "web", "ts": int(time.time()), "nonce": "n" * 22}
        raw = json.dumps(body).encode()
        self.assertEqual(store_key.parse(raw)["shop_id"], STORE)
        for bad in ({**body, "ts": int(time.time()) - 3600}, {**body, "channel": "pos"}, {**body, "extra": 1},
                    {**body, "shop_id": "../x"}, {**body, "nonce": "short"}, {**body, "key_id": "nothex"}):
            with self.assertRaises(store_key.Rejected):
                store_key.parse(json.dumps(bad).encode())
        with self.assertRaises(store_key.Rejected):
            store_key.parse(b"x" * 2000)
        self.assertNotEqual(store_key.signature("a" * 64, raw), store_key.signature("b" * 64, raw))

    def test_feature_flag(self):
        self.assertTrue(store_key.available())
        with patch.dict(os.environ, {"IDRAK_STORE_API_KEYS": "off"}):
            self.assertFalse(store_key.available())
        with patch.dict(os.environ, {"IDRAK_CONNECT_ENCRYPTION_KEY": ""}):
            self.assertFalse(store_key.available())


class CronAndIsolationTests(unittest.TestCase):
    def setUp(self):
        p = patch.dict(os.environ, ENV)
        p.start()
        self.addCleanup(p.stop)

    def test_cron_requires_a_long_secret_compared_exactly(self):
        with patch.dict(os.environ, {"CRON_SECRET": ""}):
            self.assertFalse(store_key.cron_authorized("Bearer "))
        with patch.dict(os.environ, {"CRON_SECRET": "short"}):
            self.assertFalse(store_key.cron_authorized("Bearer short"))
        secret = "c" * 40
        with patch.dict(os.environ, {"CRON_SECRET": secret}):
            self.assertTrue(store_key.cron_authorized("Bearer " + secret))
            for bad in (None, "", secret, "Bearer " + secret[:-1], "bearer " + secret, "Bearer " + secret + " "):
                self.assertFalse(store_key.cron_authorized(bad), repr(bad))

    def test_flag_on_never_changes_how_loyverse_lab_or_demo_connect(self):
        """With IDRAK_STORE_API_KEYS=on, existing connection kinds keep their own adapters and
        never read store-key credentials; store-key routing needs config.store_api_key."""
        from app.services.pos import pipeline, demo, loyverse, lab as labmod
        org = "11111111-1111-1111-1111-111111111111"
        never = AsyncMock(side_effect=AssertionError("store-key credentials must not be read"))
        with patch.object(store_key, "load_credentials", never), \
                patch("app.services.pos.loyverse_oauth.access_token", AsyncMock(return_value="tok")), \
                patch("app.services.pos.pairing.load_credentials", AsyncMock(return_value={"shop_id": "shop-a", "org_id": org, "token": "lc.shop-a." + "t" * 43, "webhook_secret": "f" * 64})), \
                patch("app.services.pos.pairing.lab_origin", return_value=LAB):
            for flag in ("off", "on"):
                with patch.dict(os.environ, {"IDRAK_STORE_API_KEYS": flag}):
                    a = asyncio.run(pipeline._adapter_for({"provider_code": "demo", "account_ref": "demo", "config": {}}, org))
                    self.assertIsInstance(a, demo.DemoPOSAdapter)
                    a = asyncio.run(pipeline._adapter_for({"provider_code": "loyverse", "account_ref": "m1", "config": {}}, org))
                    self.assertIsInstance(a, loyverse.LoyverseAdapter)
                    a = asyncio.run(pipeline._adapter_for({"provider_code": "lab_web", "account_ref": "shop-a",
                                                           "config": {"paired_lab": True, "base_url": LAB}}, org))
                    self.assertIs(type(a), labmod.LabWebAdapter)
        self.assertTrue(pipeline._lab_shop({"paired_lab": True}) and pipeline._lab_shop({"store_api_key": True}))
        self.assertFalse(pipeline._lab_shop({}) or pipeline._lab_shop({"autosync": "webhook"}))

    def test_notification_paths_cannot_cross(self):
        """Lab approval-link signals only select paired connections; store-key signals only
        select store-key connections (checked in the SQL each handler uses)."""
        import inspect
        from app.services.pos import autosync
        self.assertIn("(config->>'paired_lab')::boolean", inspect.getsource(autosync.handle_lab_notify))
        self.assertIn("(config->>'store_api_key')::boolean", inspect.getsource(store_key.handle_notify))
        self.assertIn("(config->>'store_api_key')::boolean", inspect.getsource(store_key.catch_up_all))


class OrgAllowlistTests(unittest.TestCase):
    A, B = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"

    def setUp(self):
        p = patch.dict(os.environ, ENV)
        p.start()
        self.addCleanup(p.stop)

    def env(self, mode, orgs=""):
        return patch.dict(os.environ, {"IDRAK_STORE_API_KEYS": mode, "IDRAK_STORE_API_KEYS_ORGS": orgs})

    def test_on_opens_only_listed_organizations(self):
        with self.env("on", f" {self.A} "):
            self.assertTrue(store_key.available())
            self.assertTrue(store_key.available_for(self.A))
            self.assertFalse(store_key.available_for(self.B))

    def test_fails_closed(self):
        for mode, orgs in (("on", ""), ("on", "not-a-uuid"), ("on", f"{self.A},bad"), ("off", self.A), ("yes", self.A), ("", self.A)):
            with self.subTest((mode, orgs)), self.env(mode, orgs):
                self.assertFalse(store_key.available_for(self.A))
                self.assertFalse(store_key.available_for(self.B))
        with self.env("on", self.A), patch.dict(os.environ, {"IDRAK_CONNECT_ENCRYPTION_KEY": ""}):
            self.assertFalse(store_key.available_for(self.A))

    def test_all_mode_is_explicit(self):
        with self.env("all"):
            self.assertTrue(store_key.available_for(self.A) and store_key.available_for(self.B))

    def test_sync_paused_for_a_business_not_allowed(self):
        from app.services.pos import pipeline
        conn = {"provider_code": "lab_web", "account_ref": "shop-a", "config": {"store_api_key": True, "base_url": LAB}}
        never = AsyncMock(side_effect=AssertionError("credentials must not be read when paused"))
        with self.env("on", self.A), patch.object(store_key, "load_credentials", never):
            with self.assertRaises(adapter.SourceTemporaryError):
                asyncio.run(pipeline._adapter_for(conn, self.B))
