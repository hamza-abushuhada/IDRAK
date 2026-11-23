"""Phase 3 of column mapping: learn from what companies confirm.

Two kinds of memory, both pure logic here (routers/data.py does the DB work):

1. Shared synonyms (across companies). When a user changes a column's field, or
   confirms a column Idrak marked for review, their org casts one vote:
   normalized header -> field ("" for "don't use"). A header becomes a shared
   synonym for every org once at least MIN_ORGS distinct orgs, and MIN_ORGS
   distinct users, voted for the same field, and that field holds at least
   AGREEMENT of the orgs that voted on the header. In auto_map it ranks below
   the org's own memory and the user's choice, above fuzzy matching, and never
   above an exact built-in synonym. The value check in profile.py still runs,
   so values that contradict it send the column to review.

   Privacy: a vote stores only the normalized header, the field, the org and the
   user who cast it, and only the API (service role) can read votes. What every
   org gets back is header -> field, promoted from counts. Headers that are pure
   numbers, very long, or look like personal data are never voted on or shared.

   Poisoning: one vote per org per header, however many files it uploads, and a
   header needs MIN_ORGS orgs and MIN_ORGS distinct users to spread.

2. File fingerprints (one org). A file's fingerprint is the sorted set of its
   normalized headers. Cleaning a file saves fingerprint -> the confirmed
   mapping (and the confirmed file type) for that org. The next file with the
   same fingerprint is mapped from it at once (source "memory", via "file"), with
   no AI call. Its values are still checked: a column whose values no longer fit
   its field, when they did before, goes back to review, and then the file type
   confirmation is not carried over.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

from .arabic import clean_text, to_western_digits
from .fields import ENTITIES, FIELDS, _EXACT, field_signature, header_key
from .profile import MIN_VALUES, MISMATCH_BELOW, column_sample, fit, profile

MIN_ORGS = 3          # distinct orgs (and distinct users) before a header is shared
AGREEMENT = 0.8       # share of the voting orgs the winning field must hold
MAX_KEY_CHARS = 40    # longer headers are sentences or notes, not names
MAX_KEY_WORDS = 6
FIT_DROP = 0.25       # a saved column's value fit must fall this much to count as "changed"

_DIGIT_RUN = re.compile(r"\d[\d\s().+-]{5,}\d")             # phone numbers, ids, dates written as digits
_GENERIC = re.compile(r"(column|col|unnamed|field|عمود)( \d+)*")  # io._headers names empty headers "Column 3"


def shareable_key(key: str) -> bool:
    """May this normalized header be counted and shared across orgs?"""
    if not key or len(key) < 2 or len(key) > MAX_KEY_CHARS or len(key.split()) > MAX_KEY_WORDS:
        return False
    if re.fullmatch(r"[\d ]+", key) or _GENERIC.fullmatch(key):
        return False
    return not re.search(r"\d{5,}", key.replace(" ", ""))


def shareable(header) -> str | None:
    """The key to vote under, or None when this header must never leave the org.

    Checked on the raw header too, because match_key drops "@" and "+".
    """
    raw = to_western_digits(clean_text(header))
    if "@" in raw or _DIGIT_RUN.search(raw):
        return None
    key = header_key(header)
    return key if shareable_key(key) else None


# ── 1. Shared synonyms ────────────────────────────────────────────────────────

def votes(headers: list[str], before: dict[str, dict], chosen: dict[str, str | None]) -> list[tuple[str, str]]:
    """(header key, field or "") for the columns the user really decided in this save.

    before: the upload's mapping as it was shown; chosen: what the user saved.
    A column counts when the user changed its field, or kept the field of a
    column Idrak had marked for review (the screen makes them confirm it).
    Columns accepted as shown are not votes: Idrak's own guesses (or the shared
    map itself) must not vote for themselves. Exact built-in synonyms are left
    to the built-in list.
    """
    out: dict[str, str] = {}
    clash: set[str] = set()
    for h, f in chosen.items():
        if h not in headers:
            continue
        f = f if f in FIELDS else ""
        prev = before.get(h) or {}
        if (prev.get("field") or "") == f and not prev.get("review"):
            continue
        key = shareable(h)
        if key is None or key in _EXACT:
            continue
        if out.get(key, f) != f:
            clash.add(key)  # two columns that read the same, mapped two ways: no vote
        out[key] = f
    return [(k, f) for k, f in out.items() if k not in clash]


def promote(counts: list[dict]) -> dict[str, str]:
    """header key -> field for the headers enough orgs agree on.

    counts: one row per (header_key, field) with "orgs" (distinct orgs that
    voted for it), "voters" (distinct users among them) and "total" (distinct
    orgs that voted on the header at all, for any field or "don't use").
    """
    best: dict[str, dict] = {}
    for r in counts:
        k = r.get("header_key")
        if not isinstance(k, str):
            continue
        if k not in best or (r.get("orgs") or 0) > (best[k].get("orgs") or 0):
            best[k] = r
    out = {}
    for k, r in best.items():
        field, orgs, voters, total = r.get("field"), r.get("orgs") or 0, r.get("voters") or 0, r.get("total") or 0
        if (field in FIELDS and shareable_key(k) and k not in _EXACT
                and orgs >= MIN_ORGS and voters >= MIN_ORGS and orgs >= AGREEMENT * total):
            out[k] = field
    return out


# ── 2. File fingerprints ──────────────────────────────────────────────────────

def fingerprint(headers: list[str]) -> str | None:
    """sha256 of the sorted normalized headers, or None when two columns read the same."""
    keys = [header_key(h) for h in headers]
    if not keys or len(set(keys)) != len(keys):
        return None
    return hashlib.sha256("\x1f".join(sorted(keys)).encode()).hexdigest()


def _fit_of(rows: list[list], index: int, field: str) -> float | None:
    p = profile(column_sample(rows, index))
    if not p or p.get("n", 0) < MIN_VALUES:
        return None  # too few values to say anything
    share = fit(FIELDS[field][0], p)
    return None if share is None else round(share, 2)


def _key_signature(headers: list[str], mapping: dict[str, dict]) -> list[list[str]]:
    return sorted([header_key(h), m["field"]] for h in headers if (m := mapping.get(h) or {}).get("field"))


def file_memory(headers: list[str], rows: list[list], mapping: dict, state: dict) -> tuple[str, dict] | None:
    """(fingerprint, what to save) for a file being cleaned, or None when it can't be remembered.

    mapping: uploads.mapping; state: entity_state() for it. Not remembered while
    a column is still under review (cleaned without being confirmed).
    """
    fp = fingerprint(headers)
    if fp is None:
        return None
    cols = {}
    for i, h in enumerate(headers):
        m = mapping.get(h) or {}
        if m.get("review"):
            return None
        f = m.get("field") if m.get("field") in FIELDS else None
        cols[header_key(h)] = {"field": f, "fit": _fit_of(rows, i, f) if f else None}
    entity = state.get("confirmed") if state.get("confirmed") in ENTITIES else None
    return fp, {"columns": cols, "entity": entity, "signature": _key_signature(headers, mapping) if entity else None}


def apply_file_memory(headers: list[str], rows: list[list], saved: dict | None) -> tuple[dict[str, dict], set[str]] | None:
    """The saved mapping for this file, value-checked, and its "don't use" columns.

    None (use the normal path) when the saved record doesn't fit this file or
    names a field Idrak no longer has.
    """
    cols = (saved or {}).get("columns")
    if not isinstance(cols, dict):
        return None
    out: dict[str, dict] = {}
    unused: set[str] = set()
    taken: set[str] = set()
    for i, h in enumerate(headers):
        entry = cols.get(header_key(h))
        if not isinstance(entry, dict):
            return None
        f = entry.get("field")
        if f is None:
            out[h] = {"field": None, "confidence": 1.0, "source": "memory", "via": "file", "review": False, "evidence": None}
            unused.add(h)
            continue
        if f not in FIELDS or f in taken:
            return None
        taken.add(f)
        now = _fit_of(rows, i, f)
        before = entry.get("fit")
        changed = (now is not None and now < MISMATCH_BELOW
                   and (not isinstance(before, (int, float)) or now <= before - FIT_DROP))
        out[h] = {"field": f, "confidence": round(0.55 + 0.45 * now, 2) if changed else 1.0,
                  "source": "memory", "via": "file", "review": changed,
                  "evidence": {"type": "mismatch", "kind": FIELDS[f][0], "share": now} if changed else None}
    return out, unused


def carried_entity(headers: list[str], mapping: dict[str, dict], saved: dict | None) -> dict | None:
    """The saved file type confirmation, as an uploads.mapping[ENTITY_KEY] entry, when it still holds.

    It holds when no column is under review and every column keeps the field it
    had when the type was confirmed (phase 2's field_signature rule).
    """
    saved = saved or {}
    entity = saved.get("entity")
    if entity not in ENTITIES or not saved.get("signature"):
        return None
    if any((mapping.get(h) or {}).get("review") for h in headers):
        return None
    if _key_signature(headers, mapping) != saved["signature"]:
        return None
    cols = {h: mapping.get(h) or {} for h in headers}
    return {"entity": entity, "fields": field_signature(cols), "by": saved.get("confirmed_by"),
            "at": dt.datetime.now(dt.timezone.utc).isoformat(), "via": "file"}
