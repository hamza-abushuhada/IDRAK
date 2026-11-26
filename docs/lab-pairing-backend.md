# Lab pairing backend (stacked on PR #27)

This change adds server endpoints only. It does not add buttons, pairing screens,
deployment settings, or changes to production databases. Existing Demo POS and
unpaired legacy Lab connections retain their existing behavior.

## Protocol

1. A signed-in IDRAK manager calls `POST /integrations/lab/pairing-intents`
   in their current organization (`X-Org-Id`). The existing `manage_integrations`
   permission is required. The returned signed intent binds a random nonce to
   that IDRAK user and organization for five minutes.
2. After signing in to their Lab shop, the owner posts `{"intent":"..."}` to
   `/api/pairing-codes`. This requires a shop principal, not the shared operator
   credential. The response contains a random 256-bit code and expiry. Only its
   hash is stored. A new code supersedes outstanding codes for that shop.
3. The same IDRAK user posts `{"code":"...","intent":"..."}` to
   `/integrations/lab/pair` in the same organization. Additional fields, including
   `base_url`, are rejected. The backend validates the intent and permission
   before making a request to the Lab.
4. IDRAK contacts only `https://idrak-connect-lab.vercel.app/service/pairing/exchange`.
   The body is authenticated with a server-to-server HMAC and a 60-second request
   timestamp window. Redirects and environment proxies are disabled. The Lab
   validates the signed intent, code, expiry and binding, and consumes the code
   atomically while permanently binding the shop to one organization.
5. The Lab returns a separate read-only integration token and shop webhook key to
   the backend only. The integration token can read only `/api/pos/events` and
   `/api/web/events` for its own enabled shop; it cannot open pages, read catalog
   or receiver APIs, make sales, administer shops or issue pairing codes.
6. IDRAK encrypts the credentials with Fernet in `pos_lab_bindings`, verifies the
   embedded organization/shop on decryption, and creates or resumes `lab_pos`
   and `lab_web` connections in one database transaction. Its response contains
   only shop and connection identifiers. Config, audits and connection detail
   responses contain no credentials, code or intent.

A stolen code cannot be redeemed by another user or organization, even if its
signed intent is also stolen. The intent must be obtained before code issuance;
the eventual UI must preserve this order. This is intentional proof of the
destination organization, rather than an unbound short numeric code.

Both databases enforce a unique shop binding. Disconnecting or purging a
connection does not release that binding. Re-pairing to the same organization
rotates the integration token and resumes existing connection IDs and cursors.
Automatic transfer to another organization is deliberately unavailable.

## Configuration and migrations (prepared, not applied remotely)

- Set a separate random `IDRAK_LAB_PAIRING_KEY` (at least 32 characters) in both
  server environments. It must differ from the Lab webhook secret.
- Set `IDRAK_CONNECT_ENCRYPTION_KEY` in the IDRAK backend to a Fernet key generated
  offline using `Fernet.generate_key()`. Keep it outside the database and source
  control, and distinct from the pairing key. Losing it requires re-pairing;
  changing it requires re-encryption or re-pairing. Missing keys fail closed.
- The Lab refuses to pair unless its `IDRAK_LAB_WEBHOOK_SECRET` is deployment
  specific (at least 32 characters, never the localhost demo default), because
  each shop's webhook key handed to IDRAK is derived from it. The hosted and
  serverless entry points already refuse to start without it.
- **Lab origin.** Production leaves `IDRAK_LAB_ORIGIN` (API) and
  `NEXT_PUBLIC_LAB_URL` (web) unset, so both use the published Lab. An isolated
  staging stack points at its own Lab by setting `IDRAK_LAB_ORIGIN` /
  `NEXT_PUBLIC_LAB_URL` and listing that exact origin in
  `IDRAK_LAB_ALLOWED_ORIGINS` / `NEXT_PUBLIC_LAB_ALLOWED_ORIGINS` (comma
  separated, no wildcards). Origins must be bare `https://host` names: no
  credentials, path, query, port other than 443, IP literals or local/reserved
  hostnames. Any invalid value fails closed (pairing returns 503, the web link
  is hidden); nothing falls back to another Lab. Paired connections store the
  origin they were paired with. If the configured origin later changes, sync
  stops and the shop must be paired again, so credentials only ever go to the
  Lab that issued them. Staging must use its own pairing key and must not be a
  Preview of the production projects, which share production variables.
- IDRAK's new additive migration is `api/db/migrations/011_lab_pairing.sql`.
  **007–010 are already applied in production; do not reapply them based on old
  reports.** No migration runner was used against a published database.
- The separate Lab migration is
  `tools/idrak-connect-lab/serverless_migration_pairing.sql`. Lab's explicit
  `postgres_backend.initialize()` includes it after its existing migrations.
  Nothing runs automatically on requests or cold starts. SQLite development
  adds the new empty tables during its existing local initialization.
- Both migrations create only new tables/indexes, preserve existing rows and
  are idempotent. API binding tables use RLS and revoke public/browser-role
  privileges; Lab tables revoke PUBLIC privileges.

The two services do not share a database transaction. If the Lab consumes a code
but the response is lost or IDRAK cannot save it, obtain a new intent/code for
the **same** organization and retry. The permanent binding remains; a retry
rotates the read-only token and restores the connection. Codes cannot be replayed
to recover plaintext credentials. No automatic unlink/transfer is implemented.
Changes to shared operator or browser-session credentials do not rotate these
separate integration tokens; re-pair to rotate the integration token. Disabling
a shop rejects its integration token immediately.

## Sync and webhooks

Paired adapters always use the fixed HTTPS origin, reject redirects, use only
the shop integration bearer token, and verify every pulled payload's account,
channel and source system before normalization. They fail closed if credentials
are absent, corrupted or belong to another organization/shop.

Existing webhook endpoints verify the per-shop HMAC before accepting a payload,
then check the same shop/channel/source identity. Polling and webhook processing
serialize paired writes within each organization with an advisory transaction lock; existing
source-record identity/version checks and webhook delivery uniqueness prevent
duplicate sales and product creation, including under concurrent sync. Paired
inventory uses a shared `lab_inventory` source identity across POS/web, scoped by
organization/shop/SKU, so global source-sequence ordering prevents stale channel
updates from overwriting newer stock. Each paired shop has a distinct default
inventory branch. Legacy source identities and branches remain unchanged.
This change prepares receiving
webhooks; the self-contained Lab still delivers its automatic demo webhooks to
its own receiver. No external webhook destination is added to the Lab.

## Local verification

- Lab: `python -m unittest discover -s tools/idrak-connect-lab/tests -p 'test_*.py'`.
- API: run `python -m unittest discover -s app -t . -p 'test_*.py'` from `api/`.
- Complete pairing integration: set `IDRAK_PAIRING_TEST_DATABASE_URL` and
  `IDRAK_LAB_TEST_DATABASE_URL` to two different **empty localhost** PostgreSQL
  databases named `idrak_lab_test_*`, then run
  `python api/tests/verify_lab_pairing_local.py`. This test rejects remote hosts,
  query-string DSN overrides and non-test database names. It installs a disposable
  local baseline, not a production migration plan. It substitutes verified JWT
  identity only; actual organization membership, permissions, IDRAK transactions,
  Lab sessions, code exchange and both PostgreSQL stores are exercised.

The integration test routes HTTP through in-process ASGI transports, so it does
not contact the fixed hosted URL or verify its deployed availability/TLS. Tests
cover two shops/organizations, wrong membership/role/user, stolen/expired/replayed
codes, atomic redemption, independent binding conflict checks, encrypted storage,
restricted polling, cross-shop payload rejection, concurrent idempotency, signed
webhooks, re-pairing/cursor preservation, migration replay and legacy data retention.
