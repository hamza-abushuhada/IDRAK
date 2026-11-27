"""HTTP regressions; mocked DB only, no lifespan/background sync or credentials."""
import unittest
import os
from unittest.mock import AsyncMock, patch

from asyncpg import UndefinedTableError, UndefinedColumnError, InvalidColumnReferenceError
from fastapi.testclient import TestClient

from app import db
from app.auth import Ctx, User, org_ctx
from app.main import app
from app.config import settings
from app.routers.integrations import _config_for
from app.services.pos.pipeline import build_adapter


class ConnectReadTests(unittest.TestCase):
    def setUp(self):
        self.ctx = Ctx(User("user", "user@example.org", None, False), "org", "cashier")
        app.dependency_overrides[org_ctx] = lambda: self.ctx
        self.pool_patch = patch.object(db, "init_pool", new_callable=AsyncMock)
        self.pool_patch.start()
        self.origin = settings.cors_origins[0]
        # Build middleware afresh with the test origin. Do not enter lifespan.
        app.middleware_stack = None
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.pool_patch.stop()
        app.middleware_stack = None

    def test_schema_errors_are_readable_through_cors_without_sql_leak(self):
        for path in ("/integrations/providers", "/integrations/connections"):
            for error in (UndefinedTableError, UndefinedColumnError, InvalidColumnReferenceError):
                with self.subTest(path=path, error=error):
                    with patch.object(db, "fetch", new=AsyncMock(side_effect=error("private SQL"))):
                        response = self.client.get(path, headers={"Origin": self.origin})
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.headers["access-control-allow-origin"], self.origin)
                    self.assertEqual(response.json()["code"], "schema_not_ready")
                    self.assertIn("ar", response.json()["detail"])
                    self.assertNotIn("private SQL", response.text)

    def test_connections_query_is_tenant_scoped_and_empty_is_success(self):
        with patch.object(db, "fetch", new=AsyncMock(return_value=[])) as fetch:
            response = self.client.get("/integrations/connections")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        sql, org = fetch.call_args.args
        self.assertIn("c.org_id=$1", sql)
        self.assertEqual(org, self.ctx.org_id)

    def test_unauthenticated_read_still_rejected(self):
        app.dependency_overrides.clear()
        with patch.object(db, "fetch", new=AsyncMock()) as fetch:
            self.assertEqual(self.client.get("/integrations/connections").status_code, 401)
        fetch.assert_not_awaited()

    def test_cashier_cannot_start_sync(self):
        with patch.object(db, "fetchrow", new=AsyncMock()) as fetch:
            self.assertEqual(self.client.post("/integrations/connections/id/sync").status_code, 403)
        fetch.assert_not_awaited()

    def test_cashier_cannot_issue_or_redeem_pairing(self):
        from app.services.pos import pairing
        with patch.object(pairing, 'exchange_remote', new=AsyncMock()) as exchange:
            for path in ('/integrations/lab/pairing-intents', '/integrations/lab/pair', '/integrations/lab/authorize'):
                self.assertEqual(self.client.post(path, json={}).status_code, 403)
        exchange.assert_not_awaited()

    def test_remote_lab_configuration_requires_staging(self):
        env = {"IDRAK_LAB_BASE_URL": "https://isolated-lab.example.test",
               "IDRAK_LAB_ACCESS_PASSWORD": "temporary-password"}
        with patch.dict(os.environ, {**env, "IDRAK_ENVIRONMENT": "production"}):
            self.assertEqual(_config_for("lab_pos")["base_url"], "http://127.0.0.1:8765")
            adapter = build_adapter({"provider_code": "lab_pos", "config": {}}, "org")
            self.assertIsNone(adapter.authorization)
        with patch.dict(os.environ, {**env, "IDRAK_ENVIRONMENT": "staging"}):
            self.assertEqual(_config_for("lab_web")["base_url"], env["IDRAK_LAB_BASE_URL"])
            adapter = build_adapter({"provider_code": "lab_web", "config": {}}, "org")
            self.assertTrue(adapter.authorization.startswith("Basic "))


class ConnectGuardTests(unittest.TestCase):
    """Disconnected connections and unpaired Lab URLs must never reach a source."""
    def setUp(self):
        self.ctx = Ctx(User("user", "user@example.org", None, False), "org", "manager")
        app.dependency_overrides[org_ctx] = lambda: self.ctx
        self.pool_patch = patch.object(db, "init_pool", new_callable=AsyncMock)
        self.pool_patch.start()
        app.middleware_stack = None
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.pool_patch.stop()
        app.middleware_stack = None

    def test_lab_authorize_returns_fragment_only_url_and_pair_accepts_state(self):
        from cryptography.fernet import Fernet
        from app.services.pos import pairing
        keys = {'IDRAK_LAB_PAIRING_KEY': 'unit-test-pairing-only-' + 'a' * 40, 'IDRAK_CONNECT_ENCRYPTION_KEY': Fernet.generate_key().decode()}
        with patch.dict(os.environ, keys), patch.object(db, "fetchrow", new=AsyncMock(return_value={"name": "Org", "name_ar": "مؤسسة"})):
            r = self.client.post("/integrations/lab/authorize", json={"locale": "ar"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["cache-control"], "no-store")
        body = r.json()
        self.assertTrue(body["authorize_url"].startswith(pairing.LAB_ORIGIN + "/connect#request="))
        self.assertEqual(set(body), {"authorize_url", "intent", "state", "expires_at"})
        with patch.object(pairing, "redeem", new=AsyncMock(return_value={"shop_id": "s", "name": "", "connections": []})) as redeem:
            ok = self.client.post("/integrations/lab/pair", json={"code": "c" * 43, "intent": "i", "state": "s" * 43})
            bad = self.client.post("/integrations/lab/pair", json={"code": "c" * 43, "intent": "i", "state": "s", "shop_id": "x"})
        self.assertEqual((ok.status_code, bad.status_code), (200, 400))
        self.assertEqual(redeem.await_args.args[3], "s" * 43)

    def test_test_connection_refuses_disconnected(self):
        from app.services.pos import pipeline
        row = {"id": "c1", "org_id": "org", "provider_code": "lab_pos", "status": "disconnected",
               "config": {"base_url": "https://idrak-connect-lab.vercel.app"}, "account_ref": "default"}
        with patch.object(db, "fetchrow", new=AsyncMock(return_value=row)), \
                patch.object(pipeline, "test_connection", new=AsyncMock()) as probe:
            response = self.client.post("/integrations/connections/c1/test")
        self.assertEqual(response.status_code, 409)
        probe.assert_not_awaited()

    def test_lab_connection_never_created_or_reactivated_without_approval_on_hosted(self):
        for env in ({"VERCEL": "1", "IDRAK_ENVIRONMENT": "staging", "IDRAK_LAB_BASE_URL": "https://idrak-connect-lab.vercel.app"},
                    {"VERCEL": "1"}):
            for code in ("lab_pos", "lab_web"):
                with patch.dict(os.environ, env), \
                        patch.object(db, "fetchrow", new=AsyncMock(return_value={"code": code, "is_implemented": True})) as read, \
                        patch.object(db, "execute", new=AsyncMock()) as write, patch.object(db, "fetchval", new=AsyncMock()) as insert:
                    response = self.client.post("/integrations/connections", json={"provider_code": code})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(read.await_count, 1, "no lookup of an existing connection to reactivate")
                write.assert_not_awaited(); insert.assert_not_awaited()

    def test_demo_pos_still_connects_and_reconnects_on_hosted(self):
        from app.routers import integrations
        provider = {"code": "demo", "is_implemented": True, "name": "Demo POS"}
        existing = {"id": "d1", "status": "disconnected"}
        conn = {"id": "d1", "provider_code": "demo", "status": "connected", "config": {"channel": "in_store", "auto_sync": False}}
        with patch.dict(os.environ, {"VERCEL": "1"}), \
                patch.object(db, "fetchrow", new=AsyncMock(side_effect=[provider, existing, conn])), \
                patch.object(db, "execute", new=AsyncMock()) as write, patch.object(db, "audit", new=AsyncMock()), \
                patch.object(integrations.pipeline, "run_sync", new=AsyncMock(return_value={"imported": 0})), \
                patch.object(integrations, "_detail", new=AsyncMock(return_value=conn)):
            response = self.client.post("/integrations/connections", json={"provider_code": "demo"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["reconnected"])
        self.assertIn("status='connected'", write.await_args.args[0])

    def test_status_reports_lab_linking_only_when_configured(self):
        from cryptography.fernet import Fernet
        keys = {"IDRAK_LAB_PAIRING_KEY": "unit-test-pairing-only-" + "a" * 40, "IDRAK_CONNECT_ENCRYPTION_KEY": Fernet.generate_key().decode()}
        with patch.dict(os.environ, keys):
            self.assertTrue(self.client.get("/integrations/status").json()["lab_linking"])
        with patch.dict(os.environ, {**keys, "IDRAK_LAB_PAIRING_KEY": ""}):
            self.assertFalse(self.client.get("/integrations/status").json()["lab_linking"])
        with patch.dict(os.environ, {**keys, "IDRAK_LAB_ORIGIN": "https://not-allowed.example.org"}):
            self.assertFalse(self.client.get("/integrations/status").json()["lab_linking"])

    def test_unpaired_lab_connection_refused_on_serverless(self):
        provider = {"code": "lab_pos", "is_implemented": True}
        with patch.dict(os.environ, {"VERCEL": "1", "IDRAK_ENVIRONMENT": "staging", "IDRAK_LAB_BASE_URL": ""}), \
                patch.object(db, "fetchrow", new=AsyncMock(return_value=provider)), \
                patch.object(db, "execute", new=AsyncMock()) as write:
            response = self.client.post("/integrations/connections", json={"provider_code": "lab_pos"})
        self.assertEqual(response.status_code, 400)
        write.assert_not_awaited()


class ConnectUiApiTests(unittest.TestCase):
    """Status reflects the real scheduler; responses hide internals; rename is scoped."""
    def setUp(self):
        self.pool_patch = patch.object(db, "init_pool", new_callable=AsyncMock)
        self.pool_patch.start()
        app.middleware_stack = None
        self.client = TestClient(app, raise_server_exceptions=False)
        self.row = {"id": "c1", "provider_code": "lab_pos", "account_ref": "shop-abc", "display_name": "Paired Lab lab_pos",
                    "status": "connected", "cursor": {"after": 5},
                    "config": {"paired_lab": True, "channel": "in_store", "auto_sync": True, "base_url": "https://lab.example.org",
                               "sales_adjust_inventory": False},
                    "provider_name": "IDRAK Lab", "provider_name_ar": None, "provider_category": "cloud_api", "open_errors": 0}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.pool_patch.stop()
        app.middleware_stack = None

    def as_role(self, role):
        app.dependency_overrides[org_ctx] = lambda: Ctx(User("user", "user@example.org", None, False), "org", role)

    def test_status_reports_real_scheduler_state(self):
        self.as_role("cashier")
        from app.routers import integrations
        with patch.object(integrations.db, "SERVERLESS", True), patch.dict(os.environ, {"POS_AUTOSYNC": "1"}):
            self.assertFalse(self.client.get("/integrations/status").json()["auto_sync_active"])
        with patch.object(integrations.db, "SERVERLESS", False), patch.dict(os.environ, {"POS_AUTOSYNC": "0"}):
            self.assertFalse(self.client.get("/integrations/status").json()["auto_sync_active"])
        with patch.object(integrations.db, "SERVERLESS", False), patch.dict(os.environ, {"POS_AUTOSYNC": "1"}):
            self.assertTrue(self.client.get("/integrations/status").json()["auto_sync_active"])

    def test_list_hides_internals_and_account_ref_for_non_managers(self):
        for role, sees_ref in (("cashier", False), ("manager", True)):
            self.as_role(role)
            with patch.object(db, "fetch", new=AsyncMock(return_value=[dict(self.row)])):
                item = self.client.get("/integrations/connections").json()[0]
            self.assertNotIn("cursor", item)
            self.assertEqual(item["config"], {"paired_lab": True, "channel": "in_store", "auto_sync": True})
            self.assertNotIn("lab.example.org", str(item))
            self.assertEqual("account_ref" in item, sees_ref, role)
            self.assertEqual(len(item["group_key"]), 16)
            self.assertNotIn("shop-abc", item["group_key"])

    def test_rename_requires_manager_valid_name_and_own_org(self):
        self.as_role("cashier")
        self.assertEqual(self.client.patch("/integrations/connections/c1", json={"display_name": "Shop"}).status_code, 403)
        self.as_role("manager")
        for bad in ("", "   ", "x" * 61, "bad\x07name"):
            with patch.object(db, "fetchval", new=AsyncMock()) as write:
                self.assertEqual(self.client.patch("/integrations/connections/c1", json={"display_name": bad}).status_code, 400, repr(bad))
            write.assert_not_awaited()
        with patch.object(db, "fetchval", new=AsyncMock(return_value=None)):
            self.assertEqual(self.client.patch("/integrations/connections/other", json={"display_name": "Shop"}).status_code, 404)
        from app.routers import integrations
        with patch.object(db, "fetchval", new=AsyncMock(return_value="c1")) as write, patch.object(db, "audit", new=AsyncMock()), \
                patch.object(integrations, "_detail", new=AsyncMock(return_value=dict(self.row, display_name="محل وسط البلد"))):
            r = self.client.patch("/integrations/connections/c1", json={"display_name": "  محل   وسط البلد "})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(write.call_args.args[1:], ("c1", "org", "محل وسط البلد"))
        self.assertIn("org_id=$2", write.call_args.args[0])
        self.assertNotIn("base_url", r.text)
