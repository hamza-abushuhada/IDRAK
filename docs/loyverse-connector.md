# Loyverse POS connector

Status: built and tested locally against a contract stub with synthetic data. **Not yet tested against real Loyverse.** Hidden from users: the wizard offers Loyverse only when the server reports `loyverse_available`, which requires every setting below.

## What it does
- **OAuth 2.0 authorization code:**
  - signed request bound to org, user and `sha256(state)`, valid for 10 minutes;
  - exact registered `redirect_uri`;
  - code exchanged server-to-server with the client secret.
- **Scopes:** least privilege, `MERCHANT_READ STORES_READ RECEIPTS_READ`.
- **Tokens:**
  - stored encrypted (Fernet, `IDRAK_CONNECT_ENCRYPTION_KEY`) in `pos_oauth_credentials`;
  - never sent to the browser or logged;
  - refreshed under a per-account lock (refresh tokens may rotate).
- **One Loyverse account → one IDRAK organization.**
  - The account's currency must match the organization's.
  - Only active stores are authorized.
- **Receipts → sales:**
  - SALE becomes completed, REFUND becomes its own returned invoice, and `cancelled_at` voids the invoice.
  - Only ADDED taxes are added; INCLUDED taxes stay in prices.
  - The total must reconcile with `total_money − tip − surcharge`. Otherwise the receipt becomes a reviewable sync error and is not imported.
- **Sync:**
  - `updated_at_min`/`updated_at_max` windows with full cursor pagination (limit 250);
  - a 5-minute overlap on each run;
  - duplicates skipped by content hash;
  - 401/402/403 → "reconnect required"; 429/5xx → retried next run without advancing the cursor.
- **Webhooks:**
  - an app-owned `receipts.update` webhook is registered at connect;
  - every request is verified with `X-Loyverse-Signature` (HMAC-SHA1 of the raw body, client secret, constant-time comparison);
  - the payload is only a trigger, and receipts are always re-fetched from the API.
- **Disconnect:** deletes our webhook at Loyverse and wipes tokens. Sales are kept, and the binding to the organization stays.

## Server settings (all required; none are in the repository)
| Variable | Value |
|---|---|
| `LOYVERSE_ENABLED` | `on` (any other value disables Loyverse completely) |
| `LOYVERSE_CLIENT_ID` | from the Loyverse developer dashboard |
| `LOYVERSE_CLIENT_SECRET` | from the dashboard; also the webhook signing key |
| `LOYVERSE_REDIRECT_URI` | exactly one of the app's registered redirect URLs, e.g. `https://<web>/ar/app/integrations/loyverse/callback` |
| `LOYVERSE_WEBHOOK_URL` | `https://<api>/integrations/loyverse/webhook` |

Database: `api/db/migrations/012_loyverse_oauth.sql` (additive; apply separately).

## Not verified yet (check against real Loyverse)
- Whether creating an OAuth app or using the API requires approval or a paid plan. The API defines `402 PAYMENT_REQUIRED` for lapsed subscriptions.
- Which scope `POST /webhooks` requires with an OAuth token. The docs list no webhook scope.
- The exact `receipts.update` payload. The docs show a payload example only for `inventory_levels.update`; the connector therefore relies only on `merchant_id` and `type`.
- What Loyverse returns to the redirect URI when the owner denies access (assumed to be the standard `?error=access_denied&state=`).
- The access-token lifetime in practice (docs example: `expires_in: 43200`), and whether refresh tokens rotate.
