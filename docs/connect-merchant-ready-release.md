# IDRAK Connect: merchant-ready release (PR #43): production plan

Status: **verified on Staging; NOT yet applied to production.**

## What changes for users
| Area | Production behavior after release | Gated? |
|---|---|---|
| Connect a new system: POS | Loyverse "Available now" (logo); Foodics, Odoo POS, Shopify POS, Square POS, Lightspeed POS "Coming soon" (display only) | no |
| Demo POS | No longer offered for new links. Existing Demo connections, data and reconnect are unchanged | no |
| Remove system | New, with explicit confirmation; distinct from Disconnect; keeps all invoices, returns, history and audit; re-linking has no duplicates | no |
| Online store via API key | IDRAK Connect Lab store only | **`IDRAK_STORE_API_KEYS=on`** (off = hidden) |

## Steps (each needs the owner's go-ahead)
1. Back up and restore-verify Supabase production (`backup_verify.py supabase`) and the published Lab DB (`backup_verify.py lab`).
2. Apply the additive migrations:
   - `api/db/migrations/014_connect_remove_and_store_keys.sql` to Supabase. It adds the `removed_at` column, a trigger that clears it on reconnect, and two new tables. No existing row changes.
   - `tools/idrak-connect-lab/serverless_migration_api_keys.sql` to the published Lab DB. It adds one new table.
3. Merge PR #43, then deploy API and web with `deploy_idrak1.py` (skip-domain, then promote). Deploy the published Lab from a clean export.
4. Leave `IDRAK_STORE_API_KEYS` **unset** on production. Users see the catalog and Remove; API keys stay hidden.
5. To enable API keys later:
   - add `IDRAK_STORE_API_KEYS=on` (production API only), then redeploy;
   - the published Lab must have `IDRAK_CONNECT_NOTIFY_URL` set to the production notify address for automatic arrival. Without it, sync still works through catch-up and "Sync now".

## Rollback
- **App:** promote the previous deployments. Record their IDs at release time in `previous-deployments.json`.
- **API keys only:** remove the flag and redeploy, or roll back the API. Linked stores then stop syncing; their data stays.
- **Migrations:** these can stay. They are additive and unused by older code. The trigger only clears `removed_at`.
- **Data:** nothing is deleted or rewritten by this release, so no data restore is expected. Restore-verified backups from step 1 are the last resort.

## Not to be used for tests in production
- the real Loyverse connection of branch "central";
- real merchant connections or keys.
