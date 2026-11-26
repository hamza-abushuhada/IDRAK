# Independent Vercel + Neon Lab

This is the active deployment plan. `render.yaml` and `DEPLOYMENT.md` retain the
earlier container alternative; no Render service was deployed or paid for.

## Account boundary

- Deploy only `tools/idrak-connect-lab`, as project `idrak-connect-lab`, in the
  user's **second Vercel account**. Verify its user/team identity and Hobby plan
  before creation. Never use the IDRAK production Vercel token for this project.
- Use a new dedicated Neon project/database on a confirmed Free plan. Do not
  import production IDRAK data, Supabase settings, users, tokens or `.env`.
- No paid upgrade is authorized. Free-plan quotas may suspend service; do not
  automatically upgrade a plan or add payment information.

## Runtime and durable state

The existing simulator operations are reused with `postgres_backend.py`, while
the original SQLite localhost and container runners remain available. The ASGI
entry point is `app.py` / `serverless_app:app`. No long-running listener, writable
local filesystem, startup migration or background thread is required on Vercel.

Every source order/stock transaction takes a PostgreSQL transaction advisory
lock. Receiver transactions have a separate lock and event uniqueness. This
protects stock and duplicate handling across concurrent serverless instances.
Failed receiver delivery remains in `source_events` and can be retried. External
webhooks are never forwarded to IDRAK production; the standalone receiver is local
domain logic backed by its own PostgreSQL schema.

## Setup

1. Create the dedicated database only after account/Free-plan verification.
2. Use its **direct** connection for explicit schema setup:
   `python postgres_backend.py`. It reads only `IDRAK_LAB_DATABASE_URL` and
   requires `IDRAK_LAB_ISOLATED_DATABASE=yes`. It creates `idrak_lab_source` and
   `idrak_lab_receiver`, then seeds missing products without resetting stock.
3. Use a pooled Neon connection for runtime. Configure only the five variables
   listed in `serverless.env.example`, using separate random access/signing
   secrets. Runtime refuses common IDRAK production credential variables.
4. Set Vercel project root to `tools/idrak-connect-lab`, framework FastAPI. Its
   own `pyproject.toml` keeps dependencies separate from the IDRAK API.
5. Deploy the review branch to the second account. Verify health, authenticated
   sale/order/refund flow, and persistence after a second deployment.

URLs after publishing:

- POS: `https://<verified-lab-domain>/pos`
- Web Store: `https://<verified-lab-domain>/shop`
- Standalone receiver: `https://<verified-lab-domain>/simulator/`

The final domain must be read from the actual deployment, never inferred from
the requested project name. `/health` is public; data APIs require Basic auth.
Use HTTPS. The password is a shared synthetic-demo login, not a production IdP.

## Connect to IDRAK Staging only

The IDRAK staging API supports the protected feed using:
`IDRAK_ENVIRONMENT=staging`, `IDRAK_LAB_BASE_URL`, `IDRAK_LAB_ACCESS_USER`,
`IDRAK_LAB_ACCESS_PASSWORD`, and the matching `IDRAK_LAB_WEBHOOK_SECRET`.
Set these only on the staging process. The new base URL and Basic-auth handling
are ignored outside staging. Existing connections keep their stored URL, so use
a new isolated test organization/connection in staging. No production connection
is created by deployment of this Lab.

## Verification

- Existing SQLite/hosted tests: `python -I -m unittest discover -s tests`.
- PostgreSQL integration: create a new localhost database named
  `idrak_lab_test_*`, set `IDRAK_LAB_TEST_DATABASE_URL`, then run
  `python tests/verify_serverless_postgres.py`. The script refuses remote and
  non-test databases and checks concurrency, stock, refunds and fresh app load.

Cloud account identity, plan, deployment URLs and redeployment persistence must
be recorded from actual provider responses before claiming the hosted app live.

## Verified deployment (26 November 2026)

The verified second Vercel team is `aymanbassams-projects` (Hobby), project
`idrak-connect-lab`. The dedicated Neon project is `orange-scene-81907509`
in organization `org-delicate-base-27335364` (Free), PostgreSQL 17 at 0.25 CU.
The public URLs are `https://idrak-connect-lab.vercel.app/pos` and
`https://idrak-connect-lab.vercel.app/shop`.

Real HTTP smoke checks from Vercel verified authentication, POS/store workflows,
refunds, inventory and unchanged state after redeployment. Protected templates
are generated into `server_assets/` and explicitly bundled; Vercel's `public/`
CDN extraction alone does not retain those templates for runtime reads.

The live feed was pulled successfully by the separate synthetic IDRAK staging
API at `https://idrak-connect-staging-api.vercel.app`. No production IDRAK
connection, database write or deployment was performed.

## Multiple shops (Phase 1)

Every product, order, invoice number, event and receiver record belongs to a `shop_id`.
Pre-existing data belongs to the legacy shop `idrak-test-shop-001` (so existing cursors,
invoice numbers and the IDRAK `account_ref` are unchanged).

- **Operator** (the site Basic credential) creates shops: `POST /api/shops {"name": "..."}`
  returns `shop_id`, a one-time `token` (`<shop_id>.<secret>`; only a SHA-256 hash is stored)
  and the shop's `webhook_secret`. `POST /api/shops/rotate-token {"shop_id"}` replaces a token.
  Without `X-Lab-Shop` the operator acts on the legacy shop; with it, on that shop.
- **Shop token**: `Authorization: Bearer <token>` is accepted only on `/api/*` and
  `/simulator/api/*`, is pinned to its own shop (another `X-Lab-Shop` is 403) and never
  opens pages or `/api/shops*`. The shop is never read from a request body.
- Webhook signatures use a per-shop key derived from `IDRAK_LAB_WEBHOOK_SECRET`.
- Existing SQLite files are upgraded automatically in one transaction at startup. For the
  hosted PostgreSQL database run `python postgres_backend.py` (explicit, idempotent;
  applies `serverless_migration_shops.sql`). Back up first.
- Known limitation: `seq` (event cursor) is a global sequence, so gaps may appear in a shop's cursor.
