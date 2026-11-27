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
            for path in ('/integrations/lab/pairing-intents', '/integrations/lab/pair'):
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
