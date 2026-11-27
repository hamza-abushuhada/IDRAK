"""Online store by API key: address allow-list (SSRF), key format, probe checks,
error mapping, notification parsing and that the key never appears in messages."""
import asyncio
import json
import os
import time
import unittest
from unittest.mock import patch

import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.services.pos import adapter, store_key

LAB = "https://idrak-connect-lab-staging.vercel.app"
KEY = "lsk_0123456789ab_" + "A" * 43
STORE = "shop-abc123"
ENV = {"IDRAK_LAB_ORIGIN": LAB, "IDRAK_LAB_ALLOWED_ORIGINS": LAB, "IDRAK_STORE_API_KEYS": "on",
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
