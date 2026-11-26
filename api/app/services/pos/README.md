# IDRAK Connect — Universal Integration Layer

Vendor-independent architecture for connecting POS systems, e-commerce stores,
and custom sites/apps to IDRAK. Every source is normalized into the **same
canonical tables the manual import already writes** (`sales`, `sale_items`,
`products`, `inventory_levels`), so the dashboard, reports and insights need
**no** change and there is **no** separate "integrations dashboard". Each sale is
tagged with a **channel** (`in_store` / `online` / `other`) so one unified set of
reports can break revenue down by source with **no double counting**.

> **Status:** Foundation + three working reference connectors — **Demo**
> (synthetic), **IDRAK Lab POS** and **IDRAK Lab online store** (the local
> `idrak-connect-lab` test app). No *commercial* POS vendor is integrated. See
> **Implemented vs planned** below. Nothing here is committed/pushed/deployed.

---

## 1. Architecture

```
 Adapter (per source)          Pipeline (DB layer)               Canonical tables
 ────────────────────          ───────────────────               ────────────────
 DemoPOSAdapter        ──┐
 LabPOSAdapter          ─┤
 LabWebAdapter          ─┼─▶ normalize → decide(idempotency) ─▶  sales / sale_items
 CloudAdapter   (planned)│     per-event, one transaction        products / inventory_levels
 LocalAgentAdapter(plan.)│     record job + source + errors       (sales.channel)
 FileExportAdapter(plan.)┘             │
                                       ▼
          pos_sync_jobs · pos_source_records · pos_sync_errors · pos_webhook_deliveries
```

Two ingestion paths, same pipeline:
- **Pull** (`fetch_changes(cursor)`): adapter polls the source's incremental API.
  Runs on "Sync now" **and** automatically via the background auto-sync loop.
- **Push** (`run_webhook`): source POSTs a **signed** event; IDRAK verifies the
  HMAC, rejects replays, and applies it idempotently.

### Module map
| File | DB? | Role |
|------|-----|------|
| `model.py` | no | normalized event shapes, JOD precision, content hashing (incl. `InventoryMovement.absolute` for set-vs-delta stock) |
| `sync_logic.py` | no | idempotency / out-of-order decision (numeric-aware version compare), counts, reconcile |
| `adapter.py` | no | `POSAdapter` base + `Capabilities` |
| `demo.py` | no | synthetic reference connector |
| `lab.py` | no (pure map) | `LabPOSAdapter` / `LabWebAdapter`: map Lab events → canonical, verify webhook signature |
| `registry.py` | no | provider_code → implemented adapter class |
| `pipeline.py` | **yes** | resolvers + idempotent apply + orchestration + `run_sync` / `run_webhook` / `test_connection` |
| `../../routers/integrations.py` | yes | HTTP endpoints (authz, tenant scoping) |
| `../../main.py` | yes | background auto-sync loop (lifespan task) |

---

## 2. Identity & idempotency (the core correctness rule)

A source record's identity is **`(org_id, provider_code, account_ref, entity,
external_id)`** — deliberately **independent of `connection_id`**, and keyed on
**entity** (`sales` / `products` / `inventory_levels`) not event type:

- **Reconnect doesn't duplicate.** Disconnecting and reconnecting the same source
  reuses the existing connection (or adopts its records), and because identity
  ignores `connection_id`, no historical invoice is re-imported. *(This fixes the
  observed 49→96 bug.)*
- **A sale and its later refund/void are one record.** They share the `sales`
  entity + `external_id`, so a refund **updates** the invoice (status→returned)
  instead of inserting a second row.
- **Out-of-order is version-ordered.** `decide()` compares the source version;
  integer counters compare numerically (so `"12" > "8"`), ISO timestamps
  lexically. A stale (older) event is skipped; a duplicate (same content hash) is
  skipped; a newer one updates.

## 3. Channels & inventory

- **Channel**: `pos_connections.config.channel` → written to `sales.channel`.
  Demo & Lab-POS = `in_store`, Lab-web = `online`. Manual/imported sales stay
  `NULL` (shown as "direct"). The dashboard adds a `channels` breakdown that
  **sums to the existing total** — additive, never a parallel total.
- **Inventory**: `InventoryMovement` supports **delta** (add) and **absolute**
  (set `on_hand`). Sources that emit explicit stock (the Lab) set
  `config.sales_adjust_inventory=false`, so sale lines do **not** also move stock
  (no double count); their `inventory.updated` events are authoritative. The Demo
  connector has no explicit stock feed, so it seeds opening balances and lets
  sales/refunds move stock (reversed-then-reapplied on update — idempotent).

## 4. Connector categories

| Category | How data arrives | Auth | Status |
|----------|------------------|------|--------|
| `demo` | generated in-process | none | **implemented** |
| `lab_pos` / `lab_web` | local Lab incremental API + signed webhook | HMAC (local secret) | **implemented (test)** |
| `cloud_api` | vendor API poll + webhooks | OAuth/API key (secrets mgr) | planned |
| `local_agent` | on-prem agent pushes signed changes | signed submission | planned |
| `file_export` | scheduled CSV/Excel → existing import pipeline | per-upload | planned |

**Custom websites / apps** (e.g. a restaurant like Burgerizz) connect as a
`cloud_api`-style source: the site's developer POSTs signed order/payment/refund
events to `/integrations/webhooks/{provider}/{conn}`. A URL alone is **not**
enough — the site owner must add that outbound call (or expose a documented pull
API) with a shared signing secret. IDRAK never scrapes a site it was merely given
the address of.

## 5. Automatic sync & webhooks

- **Auto-sync loop** (`main.py`): every `POS_AUTOSYNC_INTERVAL` seconds (default
  15) it runs incremental sync for every `connected` connection whose
  `config.auto_sync` is true. On an unreachable source the pull fails *before* the
  cursor advances, so the next cycle retries (outage catch-up); bad individual
  events are logged to `pos_sync_errors`, not lost. Disable with `POS_AUTOSYNC=0`.
  "Sync now" remains as a manual fallback.
- **Signed webhook** (`/integrations/webhooks/{provider}/{conn}`): verifies the
  adapter's HMAC signature (401 on mismatch), dedupes by `event_id` via
  `pos_webhook_deliveries` (replay protection → `duplicate_skipped`), then applies
  through the same idempotent pipeline.
- **Connection test** (`POST /integrations/connections/{id}/test`): read-only —
  checks reachability/auth, transforms a sample, and reports webhook support.
  Surfaces as Connected / Syncing / Error / Disconnected / Needs-attention in the UI.

## 6. Database migrations

Apply with `python db/migrate.py` (idempotent). **Do not** run against a live DB
without review. Order:

- `007_pos_connect.sql` — providers, connections, jobs, source records, errors;
  `sales/products.pos_connection_id`.
- `008_pos_identity_inventory.sql` — `account_ref`; source identity independent of
  `connection_id` (+ de-dup of dirty data before the unique index).
- `009_pos_channels_webhooks.sql` — `sales.channel`; `pos_webhook_deliveries`;
  seeds `lab_pos` / `lab_web` providers.
- `010_pos_identity_by_entity.sql` — identity keyed on **entity** not event type
  (so sale↔refund share one record).

RLS enabled + `revoke ... from anon, authenticated` on all POS tables; tenant
isolation is enforced in application SQL via `org_id`.

## 7. Tests

**Unit (stdlib `unittest`, no DB/network/deps):**
```
python -I api/app/services/pos/test_pos.py    # 35 tests
python -I api/app/services/pos/test_lab.py    # 13 tests
```
Cover normalization/JOD precision, idempotency, numeric & ISO version ordering,
refunds, invalid-payload rejection, demo determinism, opening-balance inventory,
Lab event mapping (pending/completed/cancelled/refunded), absolute inventory,
payment mapping, webhook signature, pagination, reconciliation, and
tenant-isolation/authz by source inspection. **48 tests, all passing.**

**Integration / end-to-end (requires a local test DB + the Lab running):** the
dev-only scripts in `api/dev_local/` drive the real HTTP API against the Docker
test DB and prove: POS sale→IDRAK, online order→IDRAK, pending excluded,
COD-confirm, refund reverses + restores stock, absolute inventory,
disconnect/reconnect no-dup, signed webhook (accept/replay/401), automatic sync,
connection test, and unified channel analytics with no double count. **All
assertions pass.** These scripts are **not** committed (dev harness only).

## 8. Security considerations

- **Authorization**: reads require `view_dashboard`; connect/sync/disconnect/test
  require `manage_integrations` (manager+). The webhook endpoint is unauthenticated
  by JWT **by design** — it is authenticated by the per-connection HMAC signature.
- **Tenant isolation**: every canonical write is scoped by the connection's
  `org_id`; an adapter only ever receives its own `org_id`.
- **Secrets**: non-secret config lives in `pos_connections.config`; real secrets
  go in `credential_ref` (external store) and are never returned to the frontend.
  The Lab signing secret is read from `IDRAK_LAB_WEBHOOK_SECRET` (env), never DB.
- **Webhooks**: signature verification + `event_id` replay protection; no open
  unauthenticated ingestion. A connector without `verify_webhook` → `501`.

## 9. Known limitations / honest gaps

- Only **Demo** and the **Lab** connectors are implemented; `cloud_api` /
  `local_agent` / `file_export` are architecture only (shown "coming soon", not
  connectable).
- The Lab feed carries **no product cost**, so Lab sales show 0 cost / 100%
  margin until cost is set in IDRAK. (Demo data has realistic costs.)
- The dashboard KPI view **excludes the current day** (existing product behavior);
  same-day integrated sales appear immediately in the Sales list and in any
  dashboard range that includes today.
- Auto-sync advances the cursor on a successful pull even if some events failed to
  apply; failures are in `pos_sync_errors` for review but are **not** auto-retried
  (outage-level failures *are* retried, since the cursor isn't advanced then).
- The in-process auto-sync loop suits a single long-running server; on serverless
  (Vercel) use a cron hitting the sync path instead.
- No real secrets-manager wiring yet (`credential_ref` is a placeholder).

## 10. Before real-world deployment

1. Review this change set; run the unit tests + the dev integration scripts
   against a **separate** test DB.
2. Apply migrations `007`→`010` to the target DB and verify on staging first.
3. For a real vendor: implement its adapter + `verify_webhook`, wire a secrets
   manager for `credential_ref`, set its channel, and confirm whether it emits
   absolute stock (`sales_adjust_inventory=false`) or not.
4. Decide the production auto-sync mechanism (long-running loop vs cron).
5. Remove the dev-only harness (`api/dev_local/`, local `.env` files) from any
   commit. Then push/deploy via the normal IDRAK pipeline.
