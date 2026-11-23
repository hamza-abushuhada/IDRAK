"""The AI as referee for column mapping: a third witness after the header and the values.

fields.py reads each column's name and profile.py reads its values. The
columns they leave empty or aren't sure about ("review") go to the AI with their
header, a few sample values, the current guess and what the values look like.
Its answer can break a tie, but it never overrules a witness that is sure:

  * Empty column: the AI may fill it, but only with a field no other column
    holds. It is trusted (no review) at AI confidence >= TRUST_AT and only when
    the values don't contradict that field; otherwise the user confirms it.
  * Column under review: the AI never changes its field. Its verdict is kept on
    the column (agrees, or proposes another field or "don't use", with a short
    reason) for the mapping screen. The review clears only when the AI agrees at
    >= TRUST_AT and the value evidence is not a mismatch.
  * Columns that are sure are never sent and their fields are off limits: an
    exact header match the values agree with, the company's saved mapping (and
    its "don't use"), the user's own choice.
  * Fails open: no answer, a timeout, an error or a malformed answer leaves the
    mapping and its review flags exactly as they were.

The AI call itself is injected (`ask`), so this module needs no model or DB;
routers/data.py passes services.ai.map_columns, which also counts the cost
against the org's daily AI budget.
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable

from .fields import FIELDS
from .profile import MIN_VALUES, MISMATCH_BELOW, column_sample, fit, profile

TRUST_AT = 0.85   # AI confidence needed to trust its answer; same bar as profile.REVIEW_BELOW
SAMPLES = 6       # sample values sent per column
TIMEOUT = 6.0     # seconds; the upload waits on this call

Ask = Callable[[dict, dict], Awaitable[dict | None]]


def candidates(headers: list[str], mapping: dict[str, dict], skip: set[str] | frozenset = frozenset()) -> list[str]:
    """Columns to send: empty or under review, except the company's saved or the user's own choices."""
    out = []
    for h in headers:
        m = mapping.get(h) or {}
        if h in skip or m.get("source") in ("memory", "user"):
            continue
        if not m.get("field") or m.get("review"):
            out.append(h)
    return out


# Phones, ids and emails are personal or useless to the model: keep their shape, drop the middle.
_EMAIL = re.compile(r"([^\s@])[^\s@]*@([^\s@]+)")
_LONG_DIGITS = re.compile(r"\d(?:[\s-]?\d){6,}")
_DATE_LIKE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}(\s\d{1,2})?")  # 2025-12-26 (14:30) is a date, keep it


def _redact(v) -> str:
    s = str(v).strip()[:60]
    s = _EMAIL.sub(r"\1***@\2", s)

    def mask(m: re.Match) -> str:
        run = m.group(0)
        if _DATE_LIKE.fullmatch(run):
            return run
        digits = [i for i, ch in enumerate(run) if ch.isdigit()]
        hide = set(digits[3:-2])
        return "".join("x" if i in hide else ch for i, ch in enumerate(run))

    return _LONG_DIGITS.sub(mask, s)


def _value_check(m: dict) -> str | None:
    ev = m.get("evidence") or {}
    if not ev:
        return None
    pct = round(100 * float(ev.get("share") or 0))
    return (f"{pct}% of the values look like {ev.get('kind')}" if ev.get("type") == "discovered"
            else f"only {pct}% of the values look like {ev.get('kind')}")


def build_request(headers: list[str], rows: list[list], mapping: dict[str, dict], cands: list[str]) -> tuple[dict, dict]:
    """(judge, decided): what the AI is asked about, and the settled columns whose fields are taken."""
    judge = {}
    for h in cands:
        m = mapping.get(h) or {}
        judge[h] = {"samples": [_redact(v) for v in column_sample(rows, headers.index(h))[:SAMPLES]],
                    "current_guess": m.get("field"), "value_check": _value_check(m)}
    decided = {h: m["field"] for h, m in mapping.items() if h not in judge and (m or {}).get("field")}
    return judge, decided


def _parse(v) -> tuple[str | None, float, str] | None:
    """(field or None for "don't use", confidence 0..1, reason), or None when the answer is unusable."""
    if not isinstance(v, dict):
        return None
    f = v.get("field")
    if f is None or (isinstance(f, str) and f.strip().lower() in ("", "null", "none")):
        f = None
    elif not isinstance(f, str) or f not in FIELDS:
        return None  # outside FIELDS: ignore the whole verdict
    try:
        conf = float(v.get("confidence"))
    except (TypeError, ValueError):
        conf = 0.5
    if conf != conf:  # NaN
        conf = 0.5
    if 1 < conf <= 100:  # "90" meant 90%
        conf /= 100
    conf = min(1.0, max(0.0, conf))
    return f, round(conf, 2), str(v.get("reason") or "").strip()[:160]


def _values_fit(rows: list[list], index: int, field: str) -> float | None:
    p = profile(column_sample(rows, index))
    if not p or p.get("n", 0) < MIN_VALUES:
        return None
    return fit(FIELDS[field][0], p)


def apply_verdicts(headers: list[str], rows: list[list], mapping: dict[str, dict],
                   cands: list[str], verdicts: dict | None) -> dict[str, dict]:
    """A copy of mapping with the AI's verdicts folded in (see the module docstring)."""
    out = {h: dict(m) for h, m in mapping.items()}
    if not isinstance(verdicts, dict):
        return out
    holder = {m["field"]: h for h, m in out.items() if m.get("field")}
    for h in cands:
        parsed = _parse(verdicts.get(h))
        if parsed is None:
            continue
        field, conf, reason = parsed
        m = out[h]
        current = m.get("field")
        verdict = {"field": field, "confidence": conf, "reason": reason, "agrees": field == current}
        if field and field != current and holder.get(field, h) != h:
            verdict["taken_by"] = holder[field]

        if current:
            # Under review: record the verdict, never move the field.
            m["ai"] = verdict
            if verdict["agrees"] and conf >= TRUST_AT and (m.get("evidence") or {}).get("type") != "mismatch":
                m["review"] = False
            continue

        if field is None:
            continue  # empty and the AI agrees nothing fits: nothing to show
        if "taken_by" in verdict:
            m["ai"] = verdict  # shown as a suggestion; the field stays with its holder
            continue
        share = _values_fit(rows, headers.index(h), field)
        contradicted = share is not None and share < MISMATCH_BELOW
        m.update(field=field, confidence=conf, source="ai", reason=reason,
                 review=conf < TRUST_AT or contradicted,
                 evidence=({"type": "mismatch", "kind": FIELDS[field][0], "share": round(share, 2)}
                           if contradicted else None),
                 ai={**verdict, "agrees": True})
        holder[field] = h
    return out


async def arbitrate(headers: list[str], rows: list[list], mapping: dict[str, dict], ask: Ask,
                    skip: set[str] | frozenset = frozenset(), timeout: float = TIMEOUT) -> dict[str, dict]:
    """Ask the AI about the uncertain columns and fold its verdicts in. Fails open."""
    cands = candidates(headers, mapping, skip)
    if not cands:
        return mapping
    judge, decided = build_request(headers, rows, mapping, cands)
    try:
        verdicts = await asyncio.wait_for(ask(judge, decided), timeout=timeout)
    except Exception:
        return mapping
    try:
        return apply_verdicts(headers, rows, mapping, cands, verdicts)
    except Exception:
        return mapping
