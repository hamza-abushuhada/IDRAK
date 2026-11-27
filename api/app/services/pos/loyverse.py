"""Loyverse POS connector (receipts -> IDRAK sales). Mapping is pure; HTTP is injectable.

Built from the official Loyverse API v1.0 reference (developer.loyverse.com/docs):
- base https://api.loyverse.com/v1.0, Bearer access token, all times UTC;
- GET /merchant/ (currency {code, decimal_places}), GET /stores, GET /receipts
  (filters updated_at_min/updated_at_max/store_id, limit 1..250, response cursor
  until absent), receipt_type SALE|REFUND, refund_for, cancelled_at,
  total_money (incl. discounts, taxes, surcharges, tips), total_tax,
  total_discount, total_taxes[{type INCLUDED|ADDED, money_amount}], tip,
  surcharge, line_items[{quantity, price, gross_total_money, total_money,
  total_discount, cost, item_name, variant_name, sku}], payments[{type, money_amount}];
- rate limit 300 requests / 300 s per account (429 RATE_LIMITED);
- webhooks created by an OAuth app carry X-Loyverse-Signature = lowercase hex
  HMAC-SHA1(client secret, raw body).

Accounting decisions (explicit, tested):
- invoice number = receipt_number (unique per Loyverse account); identity is
  (org, 'loyverse', merchant_id, receipt_number) so accounts never collide;
- line unit price = gross_total_money / quantity (keeps modifiers), line
  discount = line total_discount; receipt-level discounts are already inside
  the line discounts, so the sale-level discount stays 0 (never counted twice);
- tax added to the total = only ADDED taxes; INCLUDED taxes are already in the
  prices. The result must reconcile with Loyverse's total_money once tip and
  surcharge are accounted for, otherwise the receipt is NOT imported and is
  reported for review (no silent mismatch);
- REFUND receipts become their own 'returned' invoice; a cancelled receipt
  becomes 'void' (an already imported invoice is voided, never deleted);
- occurred_at = receipt_date (the real sale time), version = updated_at;
- only receipts from stores the owner authorized are imported.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from decimal import Decimal

import httpx

try:
    from . import adapter, model
except ImportError:  # pragma: no cover
    import adapter, model  # type: ignore

API_BASE = 'https://api.loyverse.com/v1.0'
PAGE_LIMIT = 250
MAX_PAGES_PER_WINDOW = 40          # 10,000 receipts per window before the window is narrowed
INITIAL_WINDOW = dt.timedelta(days=1)
TOLERANCE = Decimal('0.011')       # reconciliation tolerance (rounding)
# Every run re-reads the last few minutes: a receipt whose updated_at falls just
# before the previous run's end but became visible later (clock skew / indexing
# delay) is still picked up. Re-reads are skipped by content hash (no duplicates).
OVERLAP = dt.timedelta(minutes=5)


class SourceAuthError(adapter.SourceAuthError):
    pass


class SourceTemporaryError(adapter.SourceTemporaryError):
    pass


class ReconciliationError(model.InvalidEvent):
    pass


def verify_signature(client_secret: str, raw: bytes, header: str | None) -> bool:
    """X-Loyverse-Signature: lowercase hex HMAC-SHA1 of the raw body keyed with the client secret."""
    if not client_secret or not isinstance(header, str) or len(header) != 40:
        return False
    expected = hmac.new(client_secret.encode('utf-8'), raw, hashlib.sha1).hexdigest()
    return hmac.compare_digest(expected, header.strip().lower())


def _d(value) -> Decimal:
    if value is None:
        return Decimal('0')
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise model.InvalidEvent(f'bad monetary value: {value!r}')
    try:
        d = Decimal(str(value))
    except Exception:
        raise model.InvalidEvent(f'bad monetary value: {value!r}') from None
    if not d.is_finite():
        raise model.InvalidEvent(f'bad monetary value: {value!r}')
    return d


def _iso(value: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise model.InvalidEvent('receipt has no date')
    d = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None:   # Loyverse: all API times are UTC
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def _payment(payments: list) -> str:
    """Largest non-rounding payment decides the IDRAK payment method."""
    best, amount = None, Decimal('-1')
    for p in payments or []:
        t = str(p.get('type') or '').upper()
        if t == 'CASHROUNDING':
            continue
        a = abs(_d(p.get('money_amount')))
        if a > amount:
            best, amount = t, a
    if best is None:
        return 'cash'
    return 'cash' if best == 'CASH' else 'card'


def map_receipt(r: dict, stores: dict, allowed: set | None = None) -> 'model.Event | None':
    """One Loyverse receipt -> one model.Event, or None if it is outside the authorized stores."""
    if not isinstance(r, dict):
        raise model.InvalidEvent('receipt is not an object')
    number = r.get('receipt_number')
    if not isinstance(number, str) or not number:
        raise model.InvalidEvent('receipt has no receipt_number')
    store = r.get('store_id')
    if allowed is not None and store not in allowed:
        return None
    rtype = r.get('receipt_type')
    if rtype not in ('SALE', 'REFUND'):
        raise model.InvalidEvent(f'unknown receipt_type: {rtype!r}')
    when = _iso(r.get('receipt_date') or r.get('created_at'))
    version = r.get('updated_at') or r.get('created_at') or ''
    lines = []
    for li in r.get('line_items') or []:
        qty = _d(li.get('quantity'))
        if qty == 0:
            continue
        gross = _d(li.get('gross_total_money'))
        name = ' '.join(x for x in (li.get('item_name'), li.get('variant_name')) if x) or li.get('sku') or 'Item'
        lines.append(model.SaleLine(
            product=model.ProductRef(name=name, sku=li.get('sku') or None),
            quantity=abs(qty), unit_price=(gross / abs(qty)),
            unit_cost=_d(li.get('cost')), discount=_d(li.get('total_discount'))))
    added_tax = sum((_d(t.get('money_amount')) for t in (r.get('total_taxes') or []) if t.get('type') == 'ADDED'), Decimal('0'))
    status = 'returned' if rtype == 'REFUND' else 'completed'
    sale = model.Sale(external_id=number, invoice_number=number, occurred_at=when, lines=lines,
                      branch=(stores.get(store) or {}).get('name') if store else None,
                      payment_method=_payment(r.get('payments')), discount=Decimal('0'), tax=added_tax, status=status)
    if r.get('cancelled_at'):
        void = model.Sale(external_id=number, invoice_number=number, occurred_at=when, lines=lines or [
            model.SaleLine(product=model.ProductRef(name='Cancelled receipt'), quantity=Decimal('1'), unit_price=Decimal('0'))],
            branch=sale.branch, payment_method=sale.payment_method, status='void')
        return model.Event(type=model.EVENT_SALE_VOID, external_id=number, occurred_at=when, payload=void, version=version)
    expected = _d(r.get('total_money')) - _d(r.get('tip')) - _d(r.get('surcharge'))
    if abs(sale.total() - model.q3(expected)) > TOLERANCE:
        raise ReconciliationError(f'receipt {number}: lines {sale.total()} do not reconcile with Loyverse total {model.q3(expected)}')
    return model.Event(type=model.EVENT_REFUND if rtype == 'REFUND' else model.EVENT_SALE,
                       external_id=number, occurred_at=when, payload=sale, version=version)


class UnimportableReceipt(model.Event):
    """A receipt that could not be mapped safely. Fails validation on purpose so the
    pipeline records it in pos_sync_errors with the receipt number and the reason."""
    reason: Exception = None

    @classmethod
    def of(cls, r: dict, exc: Exception):
        number = str((r or {}).get('receipt_number') or 'unknown')[:64]
        sale = model.Sale(external_id=number, invoice_number=number, occurred_at=dt.datetime.now(dt.timezone.utc), lines=[])
        ev = cls(type=model.EVENT_SALE, external_id=number, occurred_at=sale.occurred_at, payload=sale)
        ev.reason = exc
        return ev

    def validate(self) -> None:
        raise model.InvalidEvent(str(self.reason)[:300])


class Client:
    """Minimal Loyverse API client. `transport` lets tests inject httpx.MockTransport."""

    def __init__(self, access_token: str, transport=None, base: str = API_BASE):
        self._http = httpx.Client(base_url=base, timeout=20, follow_redirects=False, trust_env=False, transport=transport,
                                  headers={'Authorization': 'Bearer ' + access_token, 'Accept': 'application/json'})

    def get(self, path: str, params: dict | None = None) -> dict:
        try:
            r = self._http.get(path, params=params)
        except httpx.HTTPError:
            raise SourceTemporaryError('Loyverse is unreachable') from None
        if r.status_code == 401:
            raise SourceAuthError('Loyverse access was revoked or has expired')
        if r.status_code == 402:
            raise SourceAuthError('The Loyverse subscription of this account has lapsed')
        if r.status_code == 403:
            raise SourceAuthError('Loyverse denied access (missing permission)')
        if r.status_code == 429 or r.status_code >= 500:
            raise SourceTemporaryError(f'Loyverse temporarily unavailable ({r.status_code})')
        if r.status_code != 200:
            raise SourceTemporaryError(f'Loyverse request failed ({r.status_code})')
        if len(r.content) > 20_000_000:
            raise SourceTemporaryError('Loyverse response too large')
        return r.json()

    def merchant(self) -> dict:
        return self.get('/merchant/')

    def stores(self) -> list[dict]:
        out, cursor = [], None
        for _ in range(20):
            data = self.get('/stores', {'limit': PAGE_LIMIT, **({'cursor': cursor} if cursor else {})})
            out += data.get('stores') or []
            cursor = data.get('cursor')
            if not cursor:
                return out
        raise SourceTemporaryError('too many store pages')

    def receipts(self, updated_min: str, updated_max: str) -> list[dict]:
        out, cursor = [], None
        for _ in range(MAX_PAGES_PER_WINDOW):
            params = {'updated_at_min': updated_min, 'updated_at_max': updated_max, 'limit': PAGE_LIMIT}
            if cursor:
                params['cursor'] = cursor
            data = self.get('/receipts', params)
            out += data.get('receipts') or []
            cursor = data.get('cursor')
            if not cursor:
                return out
        raise _WindowTooLarge()


class _WindowTooLarge(Exception):
    pass


def _fmt(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + f'{d.microsecond // 1000:03d}Z'


class LoyverseAdapter(adapter.POSAdapter):
    provider_code = 'loyverse'
    display_name = 'Loyverse POS'
    implemented = True
    capabilities = adapter.Capabilities(initial_import=True, incremental=True, refunds=True, webhook=True)

    def __init__(self, access_token: str, config: dict, transport=None, now=None):
        self.client = Client(access_token, transport=transport)
        self.config = config or {}
        self.stores = {s: {'name': n} for s, n in (self.config.get('store_names') or {}).items()}
        allowed = self.config.get('allowed_store_ids')
        self.allowed = set(allowed) if isinstance(allowed, list) else None
        self._now = now or (lambda: dt.datetime.now(dt.timezone.utc))

    def probe(self) -> list:
        """Light connection test: merchant + the 5 most recent receipts (mapped, not stored)."""
        self.client.merchant()
        data = self.client.get('/receipts', {'limit': 5})
        out = []
        for r in data.get('receipts') or []:
            try:
                ev = map_receipt(r, self.stores, self.allowed)
            except model.InvalidEvent as exc:
                ev = UnimportableReceipt.of(r, exc)
            if ev is not None:
                out.append(ev)
        return out

    def initial_events(self):
        return []  # history is pulled through fetch_changes from the cursor set at connect time

    def fetch_changes(self, ctx):
        """Receipts updated since the cursor, in bounded time windows (complete pagination per window)."""
        cur = ctx.cursor or {}
        origin = _iso(cur.get('updated_at_min') or self.config.get('import_since') or _fmt(self._now()))
        floor = _iso(self.config['import_since']) if self.config.get('import_since') else origin
        start = max(floor, origin - OVERLAP) if cur.get('updated_at_min') else origin
        now = self._now()
        events = []
        window = dt.timedelta(seconds=int(cur.get('window_seconds') or INITIAL_WINDOW.total_seconds()))
        for _ in range(30):   # bounded work per run; the cursor resumes next time
            if start >= now:
                break
            end = min(now, start + window)
            try:
                receipts = self.client.receipts(_fmt(start), _fmt(end))
            except _WindowTooLarge:
                if window <= dt.timedelta(minutes=5):
                    raise SourceTemporaryError('too many receipts in a 5-minute window')
                window = window / 4
                continue
            for r in sorted(receipts, key=lambda x: (x.get('updated_at') or '', x.get('receipt_number') or '')):
                try:
                    ev = map_receipt(r, self.stores, self.allowed)
                except model.InvalidEvent as exc:
                    # Surfaces as a reviewable sync error (pos_sync_errors), never silently dropped.
                    ev = UnimportableReceipt.of(r, exc)
                if ev is not None:
                    events.append(ev)
            start = end
            window = min(INITIAL_WINDOW, window * 2)   # widen back gradually after a busy period
        # The window end becomes the next minimum: receipts on the boundary are
        # fetched twice and skipped as duplicates by content hash (never lost).
        return events, {'updated_at_min': _fmt(start), 'window_seconds': int(window.total_seconds())}
