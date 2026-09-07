"""
Read a live relational database (observe tier).

Ported from Atlas's `athena-analyzer`. What crossed is the capability to read a
live database; what did not is Atlas's warehouse schema, its view names, and its
project configuration — one of those views maps tracker accounts to real employee
names, which is the reason `scrub` exists here rather than being left to a
convention.

**Atlas's `sql-optimizer` did NOT cross, and this docstring used to say it had.**
Identifying anti-patterns and proposing optimisations is a separate capability
from reading, and it needs no database at all -- so it is `metis_mcp/sql_analysis.py`
on the READ surface, not a sibling of this module behind the execution tier. The claim
was wrong while it stood, and it was published into a skill's `knowledge/`, so it
was wrong in two places at once.

**Read-only is enforced on the statement, not requested of the caller.** The
precedent is `code_analysis/tracker.py`, whose `assert_read_only` checks every
URL against a closed allowlist of GETs before it is issued, so a reader that
grew a write fails in the test suite rather than in front of somebody's database.
A SQL string has no such structure, so the check is the statement's own shape:
one statement, a leading SELECT or WITH, and no write keyword anywhere at
statement level.

That is deliberately conservative and will refuse some legitimate reads. A
refused read is a message; an accepted `DELETE` is somebody's afternoon.
"""
from __future__ import annotations

import re

from metis_mcp.execution import authorise, record

# Statement-level keywords that write, drop, or grant. Matched on word
# boundaries so a column called `updated_at` or a table called `deleted_rows`
# does not trip the guard -- the false positive that makes people disable it.
_FORBIDDEN = (
    "insert", "update", "delete", "drop", "truncate", "alter", "create",
    "grant", "revoke", "merge", "call", "do", "copy", "vacuum", "refresh",
)
_FORBIDDEN_RE = re.compile(
    r"(?<![\w.])(" + "|".join(_FORBIDDEN) + r")(?![\w])", re.I)

# Person-shaped columns are dropped before anything is returned. A deny-list,
# enforced here rather than asked of each caller: the aggregate is what a quality
# report needs, and a name in a log line is a name whether or not the report
# meant to include it.
_PII_COLUMNS = ("email", "username", "user_name", "full_name", "display_name",
                "first_name", "last_name", "executor", "assignee_name",
                "reporter_name", "author_name", "phone")


class UnsafeStatement(Exception):
    """The statement is not provably a read. Nothing was sent to the database."""


def assert_read_only(statement: str) -> None:
    """Refuse anything not provably a single read.

    The analogue of `tracker.assert_read_only`, and the same reason for
    existing: the guarantee should be a property of the code, not of everyone
    who ever calls it.
    """
    text = " ".join(statement.strip().split())
    if not text:
        raise UnsafeStatement("empty statement")

    # One statement. A trailing semicolon is fine; a second statement is how a
    # read becomes a read AND a write.
    body = text.rstrip(";")
    if ";" in body:
        raise UnsafeStatement(
            "more than one statement. Send them one at a time — a batch is how "
            "a SELECT carries something else with it")

    if not re.match(r"^\s*(select|with)\b", body, re.I):
        raise UnsafeStatement(
            f"a read starts with SELECT or WITH; this starts "
            f"{body.split()[0]!r}")

    found = _FORBIDDEN_RE.search(body)
    if found:
        raise UnsafeStatement(
            f"{found.group(1).upper()} appears in the statement. This reader "
            f"only reads (X-7a's observe tier); nothing was sent")


def scrub(rows: list[dict]) -> list[dict]:
    """Drop person-shaped columns. Enforced, not conventional.

    Atlas's release-readiness names the concrete case: a warehouse view mapping
    tracker accounts to real employee names, embedded in a statistics view that
    a coverage report would otherwise select from wholesale.
    """
    return [{k: v for k, v in row.items()
             if not any(p in k.lower() for p in _PII_COLUMNS)}
            for row in rows]


def query(dsn: str, statement: str, *, actor: str = "",
          limit: int = 500) -> dict:
    """Run one read and return its rows, labelled as observed.

    `dsn` names the connection; the password within it comes from the
    environment the caller built it from, never from an argument this tool
    exposes (PLT-005).
    """
    assert_read_only(statement)
    contact = authorise("sql", _safe_target(dsn), actor=actor)

    import psycopg2                                   # the `execute` extra

    connection = psycopg2.connect(dsn)
    try:
        # A read-only transaction, so the guarantee holds even if the statement
        # guard above is ever wrong. Belt and braces, because the failure mode
        # is somebody's data.
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute(statement)
            columns = [c[0] for c in (cursor.description or ())]
            rows = [dict(zip(columns, r)) for r in cursor.fetchmany(limit)]
            truncated = cursor.fetchone() is not None
    finally:
        connection.close()

    rows = scrub(rows)
    record(contact, f"read {len(rows)} row(s)", {"truncated": truncated})
    return {
        "ok": True,
        "rows": rows,
        "row_count": len(rows),
        # Never summarised away: a truncated result read as complete is a wrong
        # answer that looks like a right one.
        "truncated": truncated,
        "provenance": "observed_from_running_system",
        "means": ("what the database contains right now, not what the code "
                  "says it should (§8.7)"),
    }


def _safe_target(dsn: str) -> str:
    """The DSN with any credential removed, for the audit record."""
    return re.sub(r"//[^@/]*@", "//<redacted>@", dsn)
