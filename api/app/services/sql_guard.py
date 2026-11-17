"""Validation for model-authored SQL before it reaches the database.

Extracted from services/assistant.py so it can be tested without a database,
a model, or any third-party package. Import it from assistant.py in place of
the inline FORBIDDEN / ALLOWED_TABLES checks.

Design note. The previous guard was a denylist of bare words. That shape loses
to any identifier the list did not anticipate: `\\bset\\b` cannot match inside
`set_config`, because `_` is a word character, so the one function able to
rewrite the tenant variable passed straight through. This module inverts the
default — a statement is rejected unless every table and every function it
names is on an allowlist. Unknown identifiers fail closed.

This is still defence in depth. The durable fix is to stop making `app.org_id`
writable from the statement the model controls; see bind_tenant_note() below.
"""

from __future__ import annotations

import re

# Only the read-only views the model is actually told about in SCHEMA_DOC.
# The previous ALLOWED_TABLES also admitted base tables (sales, customers,
# employees, purchases, ...), so the model's documented surface and its
# permitted surface disagreed. They now agree.
ALLOWED_TABLES = frozenset({
    "v_sales", "v_sale_lines", "v_inventory", "v_products", "v_purchases",
})

# Functions a reporting query legitimately needs. Anything absent is rejected,
# which is what stops set_config, current_setting, pg_sleep, lo_import,
# query_to_xml and every future equivalent without needing to name them.
ALLOWED_FUNCTIONS = frozenset({
    # aggregates
    "sum", "avg", "min", "max", "count", "round", "abs", "ceil", "floor",
    "greatest", "least", "stddev", "variance", "percentile_cont", "mode",
    # null handling / conditionals
    "coalesce", "nullif", "case", "cast", "nvl",
    # dates
    "date_trunc", "date_part", "extract", "age", "now", "to_char", "to_date",
    "make_date", "generate_series",
    # strings
    "lower", "upper", "trim", "btrim", "ltrim", "rtrim", "concat", "concat_ws",
    "substring", "substr", "length", "replace", "split_part", "position",
    "left", "right", "lpad", "rpad", "initcap",
    # numeric / window
    "row_number", "rank", "dense_rank", "lag", "lead", "ntile",
    "first_value", "last_value", "nth_value", "over", "partition",
    # types
    "numeric", "integer", "bigint", "text", "date", "timestamp", "interval",
    "boolean", "float", "decimal", "real", "char", "varchar",
})

_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)

# A table reference is the identifier after FROM or JOIN, plus any further
# identifiers in the same comma-separated list. The old regex captured only the
# first, so `from v_sales, auth.users` smuggled the second past the allowlist.
_FROM_CLAUSE = re.compile(r"\b(?:from|join)\s+(.+?)(?=\b(?:where|group|order|having|limit|offset|window|union|intersect|except|join|on|using|left|right|inner|outer|full|cross|lateral)\b|\)|$)", re.I | re.S)
_IDENTIFIER_HEAD = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_$]*(?:\.[a-zA-Z_][a-zA-Z0-9_$]*)*)")
_CTE_NAME = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(", re.I)
_FUNCTION_CALL = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_$]*)\s*\(")
_STATEMENT_START = re.compile(r"^\s*(select|with)\b", re.I)

# Reserved words that may legally appear before "(" without being a function.
_NON_FUNCTION_KEYWORDS = frozenset({
    "select", "from", "where", "and", "or", "not", "in", "exists", "all", "any",
    "values", "on", "using", "when", "then", "else", "end", "as", "by",
    "group", "order", "having", "limit", "offset", "union", "intersect",
    "except", "join", "inner", "left", "right", "full", "outer", "cross",
    "lateral", "with", "distinct", "filter", "within", "between", "like",
    "ilike", "is", "null", "true", "false", "asc", "desc", "nulls", "first",
    "last", "returning", "window", "partition", "over", "rows", "range",
    "preceding", "following", "unbounded", "current", "row",
})


class SqlRejected(Exception):
    """Raised when model-authored SQL fails validation. The message is safe to
    return to the model; it names the rule, never the schema."""


def _strip_noise(sql: str) -> str:
    """Remove string literals and comments so identifiers inside them cannot be
    mistaken for table or function references."""
    out = _BLOCK_COMMENT.sub(" ", sql)
    out = _LINE_COMMENT.sub(" ", out)
    return _STRING_LITERAL.sub("''", out)


def _table_refs(stripped: str) -> set[str]:
    refs: set[str] = set()
    for clause in _FROM_CLAUSE.findall(stripped):
        for item in clause.split(","):
            item = item.strip().lstrip("(").strip()
            if not item:
                continue
            m = _IDENTIFIER_HEAD.match(item)
            if m:
                refs.add(m.group(1).lower())
    return refs


def _function_refs(stripped: str) -> set[str]:
    return {
        name.lower() for name in _FUNCTION_CALL.findall(stripped)
        if name.lower() not in _NON_FUNCTION_KEYWORDS
    }


def validate(sql: str) -> str:
    """Return the normalised statement, or raise SqlRejected.

    Accepts a single read-only SELECT (or WITH ... SELECT) that references only
    allowlisted views and allowlisted functions.
    """
    if not sql or not sql.strip():
        raise SqlRejected("Empty query.")

    statement = sql.strip().rstrip(";").strip()
    stripped = _strip_noise(statement)

    if not _STATEMENT_START.match(stripped):
        raise SqlRejected("Only a single read-only SELECT is allowed.")

    # Reject anything that remains after a statement separator. Checking the
    # stripped text means a ';' inside a string literal no longer trips this.
    if ";" in stripped:
        raise SqlRejected("Only one statement is allowed.")

    cte_names = {c.lower() for c in _CTE_NAME.findall(stripped)}
    table_refs = _table_refs(stripped)

    unknown_tables = sorted(
        t for t in table_refs
        if t not in ALLOWED_TABLES and t not in cte_names
    )
    if unknown_tables:
        raise SqlRejected(f"Table(s) not available: {', '.join(unknown_tables)}")

    # The query must read from at least one allowlisted view. This rejects
    # function-only statements that have no FROM clause at all -- `select
    # current_user`, `select version()`, `select current_setting(...)` -- which
    # the function-call check alone misses for niladic keywords like
    # current_user that take no parentheses. The assistant exists to report on
    # business data, so a statement touching no view has no legitimate purpose.
    if not (table_refs & ALLOWED_TABLES):
        raise SqlRejected("Query must read from an available view.")

    unknown_functions = sorted(
        f for f in _function_refs(stripped)
        if f not in ALLOWED_FUNCTIONS and f not in cte_names
    )
    if unknown_functions:
        raise SqlRejected(f"Function(s) not available: {', '.join(unknown_functions)}")

    return statement


def bind_tenant_note() -> str:
    """Why this module is not, on its own, the whole fix.

    Tenant confinement for the assistant currently rests on the RLS policy in
    002_security.sql reading current_setting('app.org_id'), a value the server
    sets inside the same transaction that runs the model's SQL. While that is
    true, any gap in this validator is a cross-tenant read.

    The structural fix is to make the tenant unwritable from that statement:
    set app.org_id at connection checkout, under a role that holds no
    privilege to call set_config, so the model's SQL cannot reach it whatever
    it manages to express. This validator then becomes defence in depth rather
    than the boundary itself.
    """
    return bind_tenant_note.__doc__ or ""
