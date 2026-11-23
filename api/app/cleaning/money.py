"""Amounts written in fils inside a column of dinars (1 JD = 1000 fils).

Jordanian exports mix the two in one column: "3.25" next to "3250", "0.95"
next to "١٢٥٠". Read as dinars, 3250 fils becomes 3,250 JD: a sandwich that
"costs" 1,350 JD, a meal "priced" at 8,250 JD, revenue a thousand times too high,
and margins that hide real losses. The file-wide "prices are in fils" setting
can't catch this; it is per value.

A value is read as fils only when the evidence says so, and the user still
reviews every conversion on the cleaning screen:

  * it is a whole number >= MIN_FILS (fils have no fractions; 85.5 is dinars),
  * divided by 1000 it lands near a reference: the same product's amount on
    other rows, or the expected line total (quantity x price), else the
    column's median,
  * and it is far above that reference as written (a fils value is ~1000x).

Cost and price in the same row are also checked against each other: a cost
twenty times the selling price is fils when /1000 makes it a sane cost. A value
that is still wildly out of scale is flagged for review, never changed.
"""
from __future__ import annotations

import re
import statistics

FILS_WORD = re.compile(r"(fils|فلس|فلوس)", re.I)
MIN_FILS = 100      # smaller whole numbers are plausible dinar amounts
JUMP = 20           # written value vs reference: fils sit ~1000x above their dinar peers
BAND = 3            # value/1000 must land within 3x of the product's own amount
MEDIAN_BAND = 30    # looser band when only the column median is known
OUTLIER = 100       # still this far above the median after fixing: flag for review


def _whole(v: float) -> bool:
    return float(v).is_integer()


def _dinar_like(v) -> bool:
    return v is not None and v > 0 and (v < MIN_FILS or not _whole(v))


def _median(vals: list[float]) -> float | None:
    vals = [v for v in vals if v is not None and v > 0]
    return statistics.median(vals) if vals else None


def _by_ref(v: float, ref: float | None) -> float | None:
    if v is None or v < MIN_FILS or not _whole(v) or not ref:
        return None
    cand = v / 1000
    return cand if v >= ref * JUMP and ref / BAND <= cand <= ref * BAND else None


def _by_median(v: float, med: float | None) -> float | None:
    if v is None or v < MIN_FILS or not _whole(v) or not med:
        return None
    cand = v / 1000
    return cand if v >= med * MEDIAN_BAND and med / MEDIAN_BAND <= cand <= med * MEDIAN_BAND else None


def _sane_pair(cost: float | None, price: float | None) -> bool:
    """Is this cost plausible for this selling price? Unknown sides pass."""
    if not cost or not price:
        return True
    return 0.02 <= cost / price <= 1.5


def detect(cols: dict[str, list[float | None]], products: list[str | None] | None = None,
           quantity: list[float | None] | None = None) -> tuple[dict[str, dict[int, float]], dict[str, set[int]]]:
    """({field: {row: dinars}}, {field: {rows to review}}) for parsed money columns.

    cols: field -> parsed values (dinars as written), one per row.
    products: a grouping key per row (normalized product name) or None.
    quantity: parsed quantities per row, for checking line totals.
    """
    fixes: dict[str, dict[int, float]] = {f: {} for f in cols}
    review: dict[str, set[int]] = {f: set() for f in cols}
    n = max((len(v) for v in cols.values()), default=0)
    med = {f: _median([v for v in vals if _dinar_like(v)]) or _median(vals) for f, vals in cols.items()}

    # The same product's amount on its other rows, from values that already look like dinars.
    ref: dict[str, dict[str, float]] = {}
    if products:
        for f, vals in cols.items():
            groups: dict[str, list[float]] = {}
            for ri, v in enumerate(vals):
                k = products[ri] if ri < len(products) else None
                if k and _dinar_like(v):
                    groups.setdefault(k, []).append(v)
            ref[f] = {k: statistics.median(vs) for k, vs in groups.items() if len(vs) >= 2}

    def first_pass(f: str, ri: int) -> float | None:
        v = cols[f][ri]
        k = products[ri] if products and ri < len(products) else None
        r = ref.get(f, {}).get(k) if k else None
        return _by_ref(v, r) if r else _by_median(v, med[f])

    for f in ("unit_price", "cost", "carton_price", "discount", "tax"):
        if f not in cols:
            continue
        for ri in range(n):
            got = first_pass(f, ri)
            if got is not None:
                fixes[f][ri] = got

    def now(f: str, ri: int) -> float | None:
        if f not in cols:
            return None
        return fixes[f].get(ri, cols[f][ri])

    # Cost vs price in the same row.
    if "cost" in cols and "unit_price" in cols:
        for ri in range(n):
            c0, p0 = cols["cost"][ri], cols["unit_price"][ri]
            fc, fp = ri in fixes["cost"], ri in fixes["unit_price"]
            # As written they already agree (200 JD cost, 260 JD price): converting one
            # side alone would break a pair that is fine. Both sides in fils convert together.
            if fc != fp and c0 and p0 and _sane_pair(c0, p0):
                fixes["cost" if fc else "unit_price"].pop(ri)
                continue
            # A conversion that makes the pair absurd is dropped.
            for f in ("cost", "unit_price"):
                if ri in fixes[f] and not _sane_pair(now("cost", ri), now("unit_price", ri)):
                    fixes[f].pop(ri)
            # A cost (or price) the median missed, when the pair proves it: 100 next to 0.35.
            cost, price = now("cost", ri), now("unit_price", ri)
            if _sane_pair(cost, price):
                continue
            for f in ("cost", "unit_price"):
                v = cols[f][ri]
                if ri in fixes[f] or v is None or v < MIN_FILS or not _whole(v):
                    continue
                trial = (v / 1000, price) if f == "cost" else (cost, v / 1000)
                if _sane_pair(*trial):
                    fixes[f][ri] = v / 1000
                    break

    # A line total is checked against quantity x (fixed) unit price.
    if "total" in cols:
        for ri in range(n):
            v = cols["total"][ri]
            q, p = (quantity[ri] if quantity and ri < len(quantity) else None), now("unit_price", ri)
            expected = q * p if q and p and q > 0 else None
            got = _by_ref(v, expected) if expected else _by_median(v, med["total"])
            if got is not None:
                fixes["total"][ri] = got

    for f, vals in cols.items():
        m = med[f]
        if not m:
            continue
        for ri, v in enumerate(vals):
            if v is not None and ri not in fixes[f] and v >= m * OUTLIER and v >= MIN_FILS:
                review[f].add(ri)
    return fixes, review
