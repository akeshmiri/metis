"""
Static review of a SQL statement (Atlas's `sql-optimizer`, stages 03-05).

**No database, and therefore no tier.** This reads a statement as text and says
what looks wrong with it. Reading SQL is not touching the system that runs it, so
unlike `observers/sql` this needs no `METIS_EXECUTE` -- it is a question with a
determinate answer computed from an input, which is what puts it on the read
surface.

**Heuristics over text, and it says so in every answer.** There is no parser here
and no catalogue of the target schema, so a finding is a *candidate*: this cannot
know whether an index exists, whether a predicate is non-sargable in effect, or
whether a join is redundant given the data. A report presenting these as defects
would be the confident-and-wrong output this codebase exists to avoid. They are
worth raising because a person with the schema settles each in seconds.

**The validation plan is where Metis parts company with its source.** Atlas's
stage 05 offers `EXPLAIN` and `EXPLAIN ANALYZE` in one breath. They are not the
same act: `EXPLAIN` asks the planner what it would do, and `EXPLAIN ANALYZE`
**runs the query** -- with its writes, its locks and its cost. So they land in
different tiers here, and the plan says which is which rather than leaving
somebody to discover it on a production replica.
"""
from __future__ import annotations

import re

# The eight from Atlas's stage 03. Each carries the reason it matters, because a
# label alone ("non-sargable") tells a reader nothing they can act on.
#
# Deliberately conservative: matching too eagerly produces a report people learn
# to ignore, which is worse than no report.
_CHECKS: tuple[tuple[str, "re.Pattern[str]", str, str], ...] = (
    ("select-star", re.compile(r"\bselect\s+\*", re.I),
     "SELECT * over an explicit column list",
     "reads columns nobody asked for, breaks when the table gains one, and "
     "defeats a covering index"),
    ("function-on-column", re.compile(
        r"\bwhere\b.*?\b(?:upper|lower|trim|cast|coalesce|to_char|substr|"
        r"substring)\s*\(", re.I | re.S),
     "a function applied to a column in a predicate",
     "an index on the bare column cannot be used once the column is wrapped -- "
     "the usual cause of a scan nobody expected"),
    ("leading-wildcard", re.compile(r"\blike\s+'%", re.I),
     "LIKE with a leading wildcard",
     "no B-tree index can seek on it; the whole range is scanned"),
    ("not-in", re.compile(r"\bnot\s+in\s*\(", re.I),
     "NOT IN over a subquery or list",
     "returns nothing at all if any value is NULL, and usually plans worse "
     "than NOT EXISTS"),
    ("scalar-subquery", re.compile(r"\bselect\b[^;]*?\(\s*select\b", re.I),
     "a scalar subquery in the select list",
     "risks running once per row; a join or a lateral usually expresses the "
     "same thing once"),
    ("cross-join", re.compile(r"\bfrom\s+[\w.]+\s*,\s*[\w.]+", re.I),
     "comma-separated tables in FROM",
     "an implicit join whose condition lives in WHERE, where a missing one "
     "silently becomes a cross product"),
    ("row-limit-dialect", re.compile(r"\b(?:rownum|top\s+\d+)\b", re.I),
     "a dialect-specific row limiter",
     "`ROWNUM` and `TOP` are not portable, and `ROWNUM` applies before ORDER "
     "BY, which is rarely what the author meant"),
    ("unfiltered", re.compile(
        r"^\s*select\b(?:(?!\bwhere\b|\bjoin\b|\blimit\b|\bfetch\b).)*$",
        re.I | re.S),
     "no WHERE, JOIN or LIMIT anywhere",
     "the whole table is read; fine for a small reference table and a problem "
     "for anything that grows"),
)

# Atlas's stage 04, as the shape of an answer rather than an answer.
OPTIMISATION_PATHS = (
    "rewrite the query",
    "suggest an index",
    "refresh statistics / ANALYZE",
    "push the predicate down",
    "move the query into the DAO or utility layer where it belongs",
    "apply a dialect-specific fix (Oracle and PostgreSQL differ here)",
)

# **Per finding, not one menu for all of them.** `OPTIMISATION_PATHS` is six
# generic strings and every finding got the whole list, which tells a reader
# nothing about the one they have. Each entry here is the shape of the fix AND
# the fact Metis would need in order to be sure -- because without the schema
# almost nothing here is a safe automatic rewrite, and saying which is which is
# the difference between advice and a guess.
#
# `rewrite` is deliberately absent from most of them. A `NOT IN` -> `NOT EXISTS`
# change is not equivalence-preserving when the subquery can yield NULL, and a
# tool that silently made it would produce a statement that runs, returns
# different rows, and looks reviewed.
REMEDIES: dict[str, dict] = {
    "select-star": {
        "remedy": "list the columns the caller actually reads",
        "needs": "which columns the caller uses — Metis has the statement, "
                 "not its consumer",
        "safe_rewrite": False,
    },
    "function-on-column": {
        "remedy": "index the expression, or store the normalised value in its "
                  "own column and predicate on that",
        "needs": "the index catalogue: an expression index may already exist, "
                 "in which case there is nothing wrong here",
        "safe_rewrite": False,
    },
    "leading-wildcard": {
        "remedy": "a trigram index (PostgreSQL `pg_trgm`), a reversed-string "
                  "column for suffix matching, or full-text search",
        "needs": "the index catalogue and the dialect's available extensions",
        "safe_rewrite": False,
    },
    "not-in": {
        "remedy": "`NOT EXISTS`, once the subquery is known not to yield NULL",
        "needs": "the nullability of the subquery's column. **This is not an "
                 "equivalent rewrite when it can be NULL** — `NOT IN` returns "
                 "no rows at all, which is why this is never applied "
                 "automatically",
        "safe_rewrite": False,
    },
    "scalar-subquery": {
        "remedy": "a join, or a LATERAL, so the subquery is evaluated once "
                  "rather than once per row",
        "needs": "whether the subquery is correlated, and whether it can return "
                 "more than one row — the rewrite differs and one of them "
                 "changes the result",
        "safe_rewrite": False,
    },
    "cross-join": {
        "remedy": "state the join explicitly with its predicate, so a missing "
                  "condition is a syntax error rather than a cartesian product",
        "needs": "which columns relate the tables. The predicate may already be "
                 "in the WHERE clause, in which case this is style, not a defect",
        "safe_rewrite": False,
    },
    "row-limit-dialect": {
        "remedy": "`FETCH FIRST n ROWS ONLY`, which is standard and applies "
                  "after ORDER BY",
        "needs": "the target dialect's version — and note `ROWNUM` applies "
                 "BEFORE ORDER BY, so this is a behaviour change, not a "
                 "portability fix",
        "safe_rewrite": False,
    },
    "unfiltered": {
        "remedy": "a predicate, or a LIMIT, or a stated reason the whole table "
                  "is wanted",
        "needs": "the table's size and whether it grows. Reading a small "
                 "reference table whole is correct, and this cannot tell the "
                 "two apart",
        "safe_rewrite": False,
    },
}


def review(statement: str, dialect: str = "postgresql") -> dict:
    """Findings, candidate optimisation paths, and how to check them safely."""
    text = " ".join((statement or "").split())
    if not text:
        return {"ok": False, "reason": "no statement given"}

    findings = []
    for name, rx, what, why in _CHECKS:
        if not rx.search(text):
            continue
        finding = {"pattern": name, "what": what, "why": why}
        # The fix and what it depends on, per finding. A remedy Metis cannot
        # state safely says so rather than being omitted -- an absent entry
        # would read as "nothing to do".
        finding.update(REMEDIES.get(name, {
            "remedy": "not stated",
            "needs": "this pattern has no recorded remedy — that is a gap here, "
                     "not a judgement that none exists",
            "safe_rewrite": False,
        }))
        findings.append(finding)

    return {
        "ok": True,
        "dialect": dialect,
        "findings": findings,
        # Never absent: "nothing matched" and "not checked" are different
        # answers, and only one of them is reassuring.
        "checked": [name for name, _, _, _ in _CHECKS],
        "verdict": "no candidate found" if not findings else
                   f"{len(findings)} candidate(s)",
        "optimisation_paths": list(OPTIMISATION_PATHS) if findings else [],
        "validation_plan": validation_plan(dialect),
        "means": ("candidates from reading the text -- not defects. This has no "
                  "schema, no statistics and no plan, so it cannot know whether "
                  "an index exists or a join is redundant"),
    }


def validation_plan(dialect: str = "postgresql") -> dict:
    """How to check a finding, with the two commands separated by what they do.

    **The distinction Atlas's stage 05 does not draw.** `EXPLAIN` asks the
    planner; `EXPLAIN ANALYZE` executes the statement -- including its writes
    and its locks. Offering them as one menu item is how somebody runs the
    second on a production replica believing it is the first.
    """
    return {
        "safe_to_read": {
            "command": "EXPLAIN <statement>",
            "does": "asks the planner what it would do; nothing is executed",
            "tier": "observe (METIS_EXECUTE=observe)",
        },
        "executes_the_query": {
            "command": ("EXPLAIN (ANALYZE, BUFFERS) <statement>"
                        if dialect.startswith("postgres")
                        else "EXPLAIN PLAN FOR ... / DBMS_XPLAN"),
            "does": ("RUNS the statement to get real timings -- with its "
                     "writes, its locks and its cost"),
            "tier": "run (METIS_EXECUTE=run, and it costs the literal 'execute')",
        },
        # This said "Metis ingests no execution result", which stopped being
        # true when `execution_intake` landed six labels (§8.7, revised). What
        # is still true is the part that matters: an execution result attaches
        # to the `TestCase` that ran, never to the transition it covers, and
        # nothing there writes the coverage ledger (C-10).
        "note": ("a plan you gather is evidence you read. Execution results ARE "
                 "ingested (§8.7, revised) but never write the coverage ledger, "
                 "so this does not become a fact about the model (C-10, C-11)"),
    }


# ---------------------------------------------------------------------------
# The confirmation ladder
# ---------------------------------------------------------------------------
#
# **"Confirm it works" is not one thing, and the answer must say which rung it
# reached.** Running a statement is exactly what `METIS_EXECUTE` gates, `off` is
# the default, and `EXPLAIN ANALYZE` executes with its writes and its locks. So a
# statement that looks clean and a statement that ran are different claims, and
# collapsing them is the confident-wrong output this codebase exists to refuse.
#
# `validation_plan` already described the two commands correctly and **nothing
# ever acted on it** — it was printed and left for a person. This is the half
# that acts, and it stops honestly wherever the deployment stops it.

SHAPED, STATIC, PLANNED, EXECUTED = "shaped", "static", "planned", "executed"

# In order. `confirmed_to` is the highest rung actually reached.
RUNGS = (SHAPED, STATIC, PLANNED, EXECUTED)

_STATEMENT_START = re.compile(
    r"^\s*(with|select|insert|update|delete|merge|create|alter|drop|truncate|"
    r"explain|analyze|analyse)\b", re.I)


def shape_of(statement: str) -> dict:
    """Is this a statement at all? **Not a parse, and it does not claim to be.**

    There is no SQL parser here and adding one would be a fifth runtime
    dependency for everybody who never reviews a query. So this checks what can
    be checked without one — a recognised leading keyword and balanced
    delimiters — and is named `shaped` rather than `parses` because calling it a
    parse would be the overclaim.

    Quotes are counted outside comments and doubled escapes, because `'it''s'`
    is one string and a naive count reads it as two.
    """
    text = (statement or "").strip()
    if not text:
        return {"ok": False, "reason": "no statement given"}

    problems = []
    if not _STATEMENT_START.match(text):
        problems.append(
            "does not begin with a recognised SQL keyword — this may be prose, "
            "a fragment, or a dialect this does not know")

    # `''` is an escaped quote inside a string, not two delimiters.
    singles = text.replace("''", "").count("'")
    if singles % 2:
        problems.append("unbalanced single quotes")
    if text.count('"') % 2:
        problems.append('unbalanced double quotes')
    if text.count("(") != text.count(")"):
        problems.append(
            f"unbalanced parentheses ({text.count('(')} open, "
            f"{text.count(')')} close)")

    return {
        "ok": not problems,
        "problems": problems,
        "means": ("a shape check, not a parse. Metis has no SQL parser — a "
                  "statement can pass this and still be rejected by the target"),
    }


def confirm(statement: str, dialect: str = "postgresql", *,
            execute=None, target: str = "") -> dict:
    """Take a statement as far up the ladder as this deployment allows.

    `execute` is the tier resolver — `metis_mcp.execution` by default, injected
    for the same reason every other transport is: so the decision is assertable
    with no database and no environment.

    **The rung is always reported, and stopping is not failing.** *"`METIS_EXECUTE`
    is `off`, so nothing was run"* is an answer. What must never happen is
    `confirmed: true` from a statement that was only read.
    """
    shape = shape_of(statement)
    if not shape["ok"]:
        return {
            "ok": False,
            "confirmed_to": None,
            "rungs": {SHAPED: shape},
            "stopped_because": "; ".join(shape.get("problems", ())
                                         or [shape.get("reason", "")]),
            "means": "nothing further was attempted on a statement that is not "
                     "well formed",
        }

    reached = SHAPED
    rungs: dict = {SHAPED: shape}

    findings = review(statement, dialect)
    rungs[STATIC] = {
        "ok": not findings.get("findings"),
        "findings": findings.get("findings", []),
        "means": ("candidates from reading the text. Clean here does not mean "
                  "correct — it means none of the eight patterns fired"),
    }
    reached = STATIC

    if execute is None:
        from metis_mcp import execution as execute

    tier = getattr(execute, "tier", lambda: "off")()
    plan = validation_plan(dialect)

    if tier == "off":
        return {
            "ok": True,
            "confirmed_to": reached,
            "rungs": rungs,
            "stopped_because": (
                "METIS_EXECUTE is `off`, so nothing was run against any target. "
                "This statement has been READ, not confirmed — set `observe` to "
                "let the planner see it, and name a target"),
            "validation_plan": plan,
            "means": "static review only. A statement that reads cleanly and "
                     "fails on the target is exactly what this cannot rule out",
        }

    if not target:
        return {
            "ok": True,
            "confirmed_to": reached,
            "rungs": rungs,
            "stopped_because": (
                f"METIS_EXECUTE is `{tier}` and no target was named. A plan is "
                f"a fact about ONE database — its schema, its statistics, its "
                f"indexes — so confirming against an unnamed one would be "
                f"confirming against nothing"),
            "validation_plan": plan,
            "means": "static review only",
        }

    # Beyond here a real target is involved and the caller supplies the reader.
    # Métis does not open a connection from inside a review: `observers/sql` is
    # the one place that happens, at the tier that permits it.
    return {
        "ok": True,
        "confirmed_to": reached,
        "rungs": rungs,
        "stopped_because": (
            f"tier `{tier}` and target {target!r} permit a plan, and gathering "
            f"one is `observers.sql`'s act, not this module's. Pass its reader "
            f"to go further — this module has no connection and acquires none"),
        "validation_plan": plan,
        "means": "static review, with the route to a planned check named",
    }
