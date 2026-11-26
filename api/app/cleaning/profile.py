"""Column fingerprinting: what a column's VALUES look like, whatever its header says.

The header matcher in fields.py only reads column names, so it only knows names
someone already wrote into the synonym list, and it trusts a wrong guess
blindly. The values are a second witness: a column of "+962 79 …" is phone
numbers whatever it is called, and a "date" column full of "19:26" is a time.

refine_with_values() uses that evidence three ways:
  1. Confidence: a header guess is scored by how well its values fit the field.
     A weak fit lowers confidence and marks the column for the user to confirm.
  2. Correction: when the values clearly belong to another distinctive kind
     (phone, time, email, payment, city, barcode, gender), the column moves to
     that field and is marked for review.
  3. Discovery: an unrecognised header whose values are clearly one of those
     kinds gets that field, always marked for review (never trusted alone).

Price vs cost vs total cannot be told apart from values alone; those still come
from the header (or from the AI step for columns left unmapped).
"""
from __future__ import annotations

import re
from collections import Counter

from .arabic import CITY_LOOKUP, JORDAN_CITIES, PAYMENT_LOOKUP, clean_text, is_null, match_key, to_western_digits
from .fields import FIELDS
from .parsers import map_city, map_payment, parse_date, parse_email, parse_number, parse_phone, parse_time

SAMPLE = 200
MIN_VALUES = 5           # fewer sampled values than this is too little to correct or discover
REVIEW_BELOW = 0.85      # confidence under this is shown to the user to confirm
MISMATCH_BELOW = 0.6     # value fit under this is reported as "values don't look like X"
SWITCH_BELOW = 0.4       # value fit under this lets a clear other kind take the column
CLEAR_KIND = 0.8         # a kind is "clear" when at least this share of values has it

_TIME_STRICT = re.compile(r"(\d{1,2}):\d{2}(:\d{2})?\s*(am|pm|ص|م)?")
_GENDER = {match_key(g) for g in ("male", "female", "ذكر", "انثى", "أنثى", "رجل", "امرأة", "سيدة")}

# Kinds that values alone can pin down -> (the field they become, the kind shown to the user).
DISCOVERABLE = {
    "phone": ("phone", "phone"),
    "email": ("email", "email"),
    "time": ("sale_time", "time"),
    "payment_exact": ("payment_method", "payment"),
    "city_exact": ("city", "city"),
    "gtin": ("barcode", "barcode"),
    "gender": ("gender", "gender"),
    # Only offered when the file already has invoice numbers (see refine_with_values):
    # a stray date column in a product catalog would otherwise make it look like sales.
    "date_strict": ("date", "date"),
}
_PURE_NUMBER = re.compile(r"[-+]?\d+(\.\d+)?")


def _gtin_ok(d: str) -> bool:
    """Check digit of an EAN-8 / UPC-A / EAN-13 / GTIN-14. Random ids pass ~10% of the time."""
    if len(d) not in (8, 12, 13, 14):
        return False
    body = [int(x) for x in d[:-1]][::-1]
    total = sum(x * (3 if i % 2 == 0 else 1) for i, x in enumerate(body))
    return (10 - total % 10) % 10 == int(d[-1])


def column_sample(rows: list[list], index: int) -> list:
    """Up to SAMPLE non-empty values, spread across the file rather than its first rows."""
    step = max(1, len(rows) // (SAMPLE * 2))
    out = []
    for r in rows[::step]:
        if index < len(r):
            v = r[index]
            if v is None or is_null(v):
                continue
            out.append(v)
            if len(out) >= SAMPLE:
                break
    return out


def profile(values: list) -> dict[str, float] | None:
    """Share of the values that look like each kind, plus the sample size "n"."""
    if not values:
        return None
    c: Counter[str] = Counter()
    for v in values:
        s = clean_text(v)
        low = to_western_digits(s).lower()
        key = match_key(s)
        if parse_number(v)[0] is not None:
            c["number"] += 1
        if low.endswith("%"):
            c["percent"] += 1
        if re.search(r"[^\W\d_]", s):
            c["text"] += 1
        phone, _ = parse_phone(v)
        # A bare 8-digit number parses as a landline but is usually an id or a
        # price; count it only for mobiles or when written like a phone.
        if phone and (phone.startswith("+9627") or low[:1] in ("+", "0")):
            c["phone"] += 1
        if parse_email(v)[0]:
            c["email"] += 1
        t = _TIME_STRICT.fullmatch(low)
        if t and int(t.group(1)) < 24:
            c["time"] += 1
        if parse_time(v)[0]:
            c["time_loose"] += 1
        if not t and parse_date(v)[0] is not None:
            c["date"] += 1
            # Excel serials (45707) and other bare numbers parse as dates too; fine
            # for checking a column already called a date, too weak to discover one.
            if not isinstance(v, (int, float)) and not _PURE_NUMBER.fullmatch(low):
                c["date_strict"] += 1
        if key in PAYMENT_LOOKUP:
            c["payment_exact"] += 1
        if map_payment(v)[0]:
            c["payment"] += 1
        if key in CITY_LOOKUP:
            c["city_exact"] += 1
        if map_city(v)[0] in JORDAN_CITIES:
            c["city"] += 1
        digits = re.sub(r"[\s-]", "", low)
        if re.fullmatch(r"\d{8,14}", digits):
            c["digits"] += 1
            if _gtin_ok(digits):
                c["gtin"] += 1
        if key in _GENDER:
            c["gender"] += 1
    n = len(values)
    out = {k: cnt / n for k, cnt in c.items()}
    out["n"] = n
    return out


def fit(kind: str, p: dict | None) -> float | None:
    """How well the values fit a field of this kind (0..1), or None when they can't tell."""
    if not p:
        return None

    def g(k: str) -> float:
        return p.get(k, 0.0)

    if kind == "date":
        return g("date")
    if kind == "time":
        return g("time_loose")
    if kind in ("phone", "email", "gender"):
        return g(kind)
    if kind == "money":
        return min(1.0, g("number") + g("percent"))  # "16%" is a valid tax / discount
    if kind == "quantity":
        return g("number")
    if kind == "payment":
        return g("payment")
    if kind == "city":
        return max(g("city"), 0.6 * g("text"))  # districts and villages aren't in the city list
    if kind == "barcode":
        return max(g("gtin"), g("digits"))
    if kind in ("person", "product", "branch", "category", "company", "area"):
        return g("text")
    return None  # ids and free text: any value fits, so the values can't confirm or refute


def _clear_kind(p: dict | None, allow_date: bool = False) -> tuple[str, str, float] | None:
    """(field, shown kind, share) for the strongest distinctive kind, if one is clear."""
    if not p or p.get("n", 0) < MIN_VALUES:
        return None
    keys = [k for k in DISCOVERABLE if allow_date or k != "date_strict"]
    best = max(((k, p.get(k, 0.0)) for k in keys), key=lambda kv: kv[1])
    if best[1] < CLEAR_KIND:
        return None
    field, shown = DISCOVERABLE[best[0]]
    return field, shown, best[1]


def refine_with_values(headers: list[str], rows: list[list], mapping: dict[str, dict]) -> dict[str, dict]:
    """Return a copy of an auto_map() result with value evidence folded in.

    Each entry gains "review" (bool) and "evidence" (None, or
    {"type": "mismatch" | "discovered", "kind": str, "share": float}).
    """
    used = {m["field"] for m in mapping.values() if m.get("field")}
    profiles = [profile(column_sample(rows, i)) for i in range(len(headers))]
    out = {h: {**mapping[h], "review": False, "evidence": None} for h in headers}

    def take(m: dict, field: str, shown: str, share: float) -> None:
        used.add(field)
        m.update(field=field, confidence=round(0.5 + 0.3 * share, 2), source="values", review=True,
                 evidence={"type": "discovered", "kind": shown, "share": round(share, 2)})

    def date_allowed() -> bool:
        # Only a transaction log (it has invoice numbers) with no date column yet
        # may get its date from the values.
        return "invoice_number" in used and "date" not in used

    # Pass 1: check, and if clearly wrong correct, every column the header mapped.
    for i, h in enumerate(headers):
        m, p = out[h], profiles[i]
        field = m.get("field")
        if not field:
            continue
        # "Code" / "كود" is a known SKU name, but when its values are real barcodes
        # (they pass the check digit) it is the barcode, which products match on first.
        if (field == "sku" and p and p.get("n", 0) >= MIN_VALUES and p.get("gtin", 0) >= CLEAR_KIND
                and "barcode" not in used):
            used.discard("sku")
            take(m, "barcode", "barcode", p["gtin"])
            continue
        kind = FIELDS[field][0]
        share = fit(kind, p)
        if share is None:
            m["review"] = m["confidence"] < REVIEW_BELOW
            continue
        alt = _clear_kind(p, date_allowed())
        if share < SWITCH_BELOW and alt and alt[0] != field and alt[0] not in used:
            used.discard(field)
            take(m, *alt)
            continue
        conf = round(m["confidence"] * (0.55 + 0.45 * share), 2)
        m.update(confidence=conf, review=conf < REVIEW_BELOW)
        if share < MISMATCH_BELOW:
            m["evidence"] = {"type": "mismatch", "kind": kind, "share": round(share, 2)}

    # Pass 2: discover fields for columns no header matched. Runs after pass 1 so a
    # field freed by a correction (a "date" header full of times) can be found here.
    for i, h in enumerate(headers):
        m = out[h]
        if m.get("field"):
            continue
        alt = _clear_kind(profiles[i], date_allowed())
        if alt and alt[0] not in used:
            take(m, *alt)

    # Pass 3: a "unit price" that is really the line's total.
    col = {m["field"]: i for i, m in enumerate(out[h] for h in headers) if m.get("field")}
    if "total" not in col and {"unit_price", "quantity"} <= col.keys() and ({"product", "category"} & col.keys()):
        item = col.get("product", col.get("category"))
        share = line_total_share(rows, col["unit_price"], col["quantity"], item)
        if share is not None and share >= CLEAR_KIND:
            m = out[headers[col["unit_price"]]]
            # Under review, so the AI step never moves it back by its name.
            m.update(field="total", confidence=0.8, source="values", review=True,
                     evidence={"type": "line_total", "kind": "money", "share": round(share, 2)})
    return out


LINE_TOTAL_ROWS = 5000


def line_total_share(rows: list[list], price_i: int, qty_i: int, item_i: int) -> float | None:
    """Share of items whose "unit price" grows with the quantity, as a line total does.

    For each item sold at two or more quantities: price / quantity the same at every
    quantity while the price itself differs is a line total (5 x 300.08 = 1500.40);
    the same price at every quantity is a unit price. None when fewer than 3 items
    can tell (one quantity each, or prices that change for other reasons).
    """
    step = max(1, len(rows) // LINE_TOTAL_ROWS)
    seen: dict[str, dict[float, list[float]]] = {}
    for r in rows[::step]:
        if max(price_i, qty_i, item_i) >= len(r):
            continue
        q, p = parse_number(r[qty_i])[0], parse_number(r[price_i])[0]
        key = match_key(str(r[item_i] or ""))
        if key and q and p and q > 0 and p > 0 and float(q).is_integer():
            seen.setdefault(key, {}).setdefault(q, []).append(p)
    total_like = unit_like = 0
    for by_qty in seen.values():
        if len(by_qty) < 2:
            continue
        med = {q: sorted(ps)[len(ps) // 2] for q, ps in by_qty.items()}
        per_unit = [p / q for q, p in med.items()]
        raw = list(med.values())
        if max(per_unit) - min(per_unit) <= 0.01 * max(per_unit) and max(raw) - min(raw) > 0.2 * max(raw):
            total_like += 1
        elif max(raw) - min(raw) <= 0.01 * max(raw):
            unit_like += 1
    judged = total_like + unit_like
    return total_like / judged if judged >= 3 else None
