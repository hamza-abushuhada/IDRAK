# IDRAK Connect: diagnosis and review plan

Checked 26 November 2026. Branch: `codex/fix-idrak-connect`, based on GitHub
`main` at `b69f1a1`. The workspace initially contained an empty Git repository;
the existing repository history was fetched, with no previous work removed.

## Confirmed production findings

- `https://api.idrak.online/health`: HTTP 200, database connectivity healthy.
- Unauthenticated `/integrations/connections`: HTTP 401, expected, with
  `Access-Control-Allow-Origin: https://idrak.online`.
- Public OpenAPI contains all eight Connect paths. The frontend's public bundles
  use `https://api.idrak.online`; the public Supabase URL matches the supplied env.
- Authorized local settings were read from `C:\Users\ayman\Downloads\env`.
  No credentials were copied into tracked files. Supabase URL/project reference
  match Vercel production settings. Database host/user/database match after
  resolving the local password placeholder; production CORS allows the frontend.
- PostgreSQL diagnostic sessions used `default_transaction_read_only=on`,
  explicit read-only transactions, disabled statement caching, and a 10-second
  statement timeout. `SHOW transaction_read_only` returned `on`.
- **No `pos_*` tables exist.** No Connect columns or identity indexes exist.
  `SELECT ... LIMIT 0` against both `pos_providers` and `pos_connections` failed
  with `UndefinedTableError`, SQLSTATE `42P01`. No customer rows were selected.
- Migration ledger contains `001_core.sql` through `006_ai_budget_counter.sql`,
  plus `007_mapping_learning.sql` and `008_upload_parts.sql`. It does **not**
  contain the four Connect migrations listed below.

The API code queries these missing tables after authentication. The frontend's
generic message is emitted when `fetch` rejects. An unhandled database exception
can become a 500 response outside the inner CORS middleware, which the browser
then exposes as a network failure. The missing schema is directly confirmed;
the exact failing browser request was not captured with an authenticated session.
No authenticated production requests were made because user/profile dependency
code can create a missing profile even during a GET.

## Access and logs

GitHub connector is authenticated as `aymanbassam`; repository permission
metadata reports pull and push access. No remote branch push or PR was created.
The shell's GitHub CLI was not used for authenticated writes.

The supplied Vercel token successfully read both `idrak-web` and `idrak-api`,
their custom domain configurations, environment comparisons, deployments and
build events. There is no connected Vercel MCP tool; read-only REST and the
installed Vercel CLI were used.

Build logs for the projects' reported production targets show successful builds
and deployment completion. The web build has existing lint warnings. Project
target metadata reports Git SHA `8537a38` (18 November), older than current main,
while the public API already exposes newer Connect routes. This metadata is
insufficient to identify the precise source of the served artifact. Reconcile
the intended release artifact and custom-domain assignment before publishing;
do not assume latest main is already deployed. The alias lookup endpoint returned
404 even though project domain configuration lists the correct custom domains.

Runtime log queries for the last 30 minutes succeeded for both projects but
returned zero records. A 24-hour query was rejected by Hobby-plan retention.
Thus no historical runtime traceback was available; the database read reproduced
the missing-table error independently. Raw diagnostic files are local and ignored.

## Required migrations

| File | Requirement and impact |
| --- | --- |
| `007_pos_connect.sql` | Creates five POS tables, provider catalog, canonical source references, indexes, RLS and grants/revokes. Required by both page reads. |
| `008_pos_identity_inventory.sql` | Adds account/provider identity, backfills source records, removes duplicate mapping rows and replaces identity uniqueness. Required by the connections query's `account_ref`. Does not remove duplicate financial sales. |
| `009_pos_channels_webhooks.sql` | Adds `sales.channel`, webhook delivery replay table and Lab provider catalog entries. Required for sync, webhooks and channel dashboard queries. |
| `010_pos_identity_by_entity.sql` | Deduplicates source mapping rows and changes the UNIQUE identity index from event type to entity. Required for the pipeline's `ON CONFLICT` target and sale/refund lifecycle identity. |

There are two different `007` files and two different `008` files. The migration
runner tracks **complete filenames**, so those numbers do not establish that
Connect was applied. It sorts filenames lexicographically and uses a transaction
per file. Do not rename applied migrations or manually insert ledger entries.
Prerequisites include core tables, `auth.users`, `gen_random_uuid()`, roles
`anon`/`authenticated`, and the existing security migration. The other 007/008
files also reference `basira_ai_reader` from migration 002.

Migrations 008 and 010 contain DELETE statements against the source mapping
table. Those tables are currently absent, so there is no existing POS mapping to
deduplicate; still review those statements on staging. None of the migrations
is executed by this repair. `api/db/check_connect_readonly.sql` is an optional
metadata-only diagnostic, not a migration.

## Local changes

- Missing-table/column/conflict-target errors return a bilingual HTTP 503
  `schema_not_ready` within normal exception handling, preserving CORS. Logs
  contain only method/path/SQLSTATE, no SQL text, parameters or credentials.
- Provider catalog and expanded connection details now show errors and retry
  controls instead of staying in a loading state forever. Other existing work
  and API response shapes are preserved.
- Added mocked HTTP regression tests for schema errors, CORS, empty connections,
  tenant filtering, authentication and sync permissions.
- Prepared an independent hosted Lab runner, container recipe, access protection,
  persistent-volume setup and isolated HTTP tests; see the Lab deployment guide.

These changes improve behavior and diagnostics; they cannot create the missing
production tables. Connect remains unavailable until an approved schema rollout.

## Safe execution plan (not executed)

1. Review this branch and identify the exact intended API/web release artifacts.
2. Prepare an isolated staging database with the existing schema. Apply the four
   Connect migrations there only after approval for migration execution; verify
   RLS, grants, ledger filenames and the entity-based identity index.
3. Exercise catalog, empty list, demo connect/sync, reconnect deduplication,
   refund/cancel lifecycle, signed webhook rejection/replay and tenant isolation
   using synthetic staging data. Never use the production env for these tests.
4. Before production approval, confirm a restorable backup and review the exact
   SQL and deduplication impact. Request explicit approval for the four named
   migrations, API/web deployment and any merge as separate concrete actions.
5. After approved migrations, deploy the reviewed release and verify the Connect
   GETs using an existing user/org. Test mutations on staging, not production.
   If rollout fails, retain additive schema and roll back code; do not drop
   tables or delete imported financial records as an automatic rollback.
6. Publish the Lab only as a separate service with its own secrets and volume,
   after choosing a host/domain and obtaining explicit deployment approval.

Two existing integration constraints remain: Lab connectors default to the API
server's `127.0.0.1:8765`, which is not a user's computer from Vercel; and the
in-process auto-sync loop is disabled on Vercel. A remote Lab connection and
serverless scheduling/authentication need a separately reviewed implementation.
The independent Lab demo does not enable these production integrations.

## Validation

- API unittest discovery: **234 passed**, including four new HTTP regression tests.
- Standalone Lab unittest discovery: **11 passed**, including hosted HTTP access,
  sale/refund delivery, deduplication coverage and storage reinitialization.
- Frontend TypeScript: passed. Production `next build`: passed (100 static pages).
- Targeted Connect ESLint: passed with no warnings. Full ESLint: **14 errors,
  17 warnings** in other existing files.
  Errors concern state updates in effects and i18n function mutation, outside
  this repair. No lint rules were disabled.
- `git diff --check`: passed.
- Docker image: built successfully with non-root user `lab`. Container health,
  sale delivery and persisted revenue after restart: passed. Temporary container
  and volume removed. Host loopback access was restricted, so HTTP smoke requests
  ran inside the container. Public HTTPS/reverse proxy validation remains pending.

No production database changes, migrations, deploys, merges, external messages,
or automatic sync runs were performed.
