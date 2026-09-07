"""
Static SQL review (Atlas's `sql-optimizer`).

**Findings are candidates, not defects**, and the tests that matter are the ones
asserting this refuses to overclaim: it has no schema, no statistics and no plan,
so it cannot know whether an index exists. A report that read as authoritative
would be the confident-and-wrong output this codebase exists to avoid.
"""
from __future__ import annotations

import pytest

from metis_mcp.sql_analysis import OPTIMISATION_PATHS, review, validation_plan


def _patterns(sql):
    return {f["pattern"] for f in review(sql)["findings"]}


@pytest.mark.parametrize("sql,expected", [
    ("SELECT * FROM t WHERE id = 1", "select-star"),
    ("SELECT id FROM t WHERE UPPER(name) = 'X'", "function-on-column"),
    ("SELECT id FROM t WHERE name LIKE '%x'", "leading-wildcard"),
    ("SELECT id FROM t WHERE id NOT IN (SELECT x FROM y)", "not-in"),
    ("SELECT a, (SELECT max(b) FROM y) FROM t WHERE a = 1", "scalar-subquery"),
    ("SELECT a FROM t1, t2 WHERE t1.id = t2.id", "cross-join"),
    ("SELECT id FROM t WHERE ROWNUM < 10", "row-limit-dialect"),
    ("SELECT id FROM big_table", "unfiltered"),
])
def test_each_catalogued_pattern_is_detected(sql, expected):
    """All eight of Atlas's stage-03 patterns, each by its own statement."""
    assert expected in _patterns(sql), sql


def test_a_clean_statement_produces_no_findings():
    """**The property that makes the rest usable.** A checker that flags
    everything is one people learn to ignore, which is worse than no checker."""
    out = review("SELECT id, name FROM t WHERE id = $1 LIMIT 10")
    assert out["findings"] == []
    assert out["verdict"] == "no candidate found"


def test_a_column_named_like_a_function_is_not_flagged():
    """The false positive that would discredit the check: `updated_at` and
    `coalesce_mode` are column names, not calls."""
    assert "function-on-column" not in _patterns(
        "SELECT updated_at, coalesce_mode FROM t WHERE id = 1")


def test_it_reports_what_it_checked_not_only_what_it_found():
    """"Nothing matched" and "not checked" are different answers, and only one
    of them is reassuring."""
    out = review("SELECT id FROM t WHERE id = 1 LIMIT 1")
    assert len(out["checked"]) == 8


def test_it_never_calls_a_finding_a_defect():
    """No schema, no statistics, no plan — so a candidate is all it can offer."""
    out = review("SELECT * FROM t")
    assert "not defects" in out["means"]
    assert "cannot know whether" in out["means"]


def test_optimisation_paths_appear_only_when_something_was_found():
    """Offering six remedies for a clean query is noise."""
    assert review("SELECT id FROM t WHERE id = 1 LIMIT 1")["optimisation_paths"] == []
    assert review("SELECT * FROM t")["optimisation_paths"] == list(OPTIMISATION_PATHS)


# --------------------------------------------------------------------------
# The distinction Atlas's stage 05 does not draw
# --------------------------------------------------------------------------

def test_explain_and_explain_analyze_are_separated_by_what_they_do():
    """**`EXPLAIN ANALYZE` runs the query** — with its writes, its locks and its
    cost. Offering it beside `EXPLAIN` as one menu item is how somebody executes
    it on a production replica believing it is the first."""
    plan = validation_plan("postgresql")
    assert "nothing is executed" in plan["safe_to_read"]["does"]
    assert "RUNS" in plan["executes_the_query"]["does"]
    assert "observe" in plan["safe_to_read"]["tier"]
    assert "run" in plan["executes_the_query"]["tier"]


def test_the_plan_is_dialect_aware():
    assert "DBMS_XPLAN" in validation_plan("oracle")["executes_the_query"]["command"]


def test_an_empty_statement_is_refused_not_passed():
    assert review("")["ok"] is False


def test_this_module_needs_no_database_and_no_tier():
    """It reads text. Reading SQL is not touching the system that runs it —
    which is why it is on the read surface and `observers/sql` is not."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("metis_mcp/sql_analysis.py").read_text())
    imported = {a.name.split(".")[0] for n in ast.walk(tree)
                if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree)
                 if isinstance(n, ast.ImportFrom)}
    assert "psycopg2" not in imported
    assert not any(m.startswith("metis_mcp") and "execution" in m
                   for m in imported)


# ---------------------------------------------------------------------------
# Per-finding remedies
# ---------------------------------------------------------------------------


def test_every_check_has_a_remedy_naming_what_it_would_need():
    """**One menu for every finding tells a reader nothing about theirs.**

    `OPTIMISATION_PATHS` is six generic strings and the whole list came back
    whenever any pattern fired. A remedy is only useful attached to the finding
    it fixes, and only honest when it says what Métis would have to know to be
    sure — which, without the schema, is usually something it does not have.
    """
    from metis_mcp.sql_analysis import _CHECKS, REMEDIES

    for name, _, _, _ in _CHECKS:
        assert name in REMEDIES, f"{name} has no remedy"
        assert REMEDIES[name]["remedy"]
        assert REMEDIES[name]["needs"], f"{name} does not say what it needs"


def test_no_remedy_names_a_check_that_does_not_exist():
    """A remedy for a pattern nothing detects is dead prose that reads as
    coverage."""
    from metis_mcp.sql_analysis import _CHECKS, REMEDIES

    names = {n for n, _, _, _ in _CHECKS}
    assert not (set(REMEDIES) - names)


def test_nothing_claims_to_be_a_safe_automatic_rewrite():
    """**The one that matters.**

    `NOT IN` → `NOT EXISTS` is not equivalence-preserving when the subquery can
    yield NULL: the first returns no rows at all. A tool that applied it silently
    would emit a statement that runs, returns different rows, and looks reviewed.
    Without the schema none of these is safe, and the flag says so rather than
    the absence of one implying it.
    """
    from metis_mcp.sql_analysis import REMEDIES

    assert all(r["safe_rewrite"] is False for r in REMEDIES.values())


def test_a_finding_carries_its_remedy_through_review():
    from metis_mcp.sql_analysis import review

    findings = review("SELECT * FROM orders")["findings"]
    star = [f for f in findings if f["pattern"] == "select-star"][0]
    assert "columns" in star["remedy"]
    assert star["needs"]


# ---------------------------------------------------------------------------
# The confirmation ladder
# ---------------------------------------------------------------------------


def test_prose_is_not_a_statement_and_nothing_further_is_attempted():
    from metis_mcp.sql_analysis import confirm

    out = confirm("please give me all the orders")
    assert out["ok"] is False
    assert out["confirmed_to"] is None
    assert "recognised SQL keyword" in out["stopped_because"]


def test_an_escaped_quote_is_one_string_not_two_delimiters():
    """`'it''s'` is a single literal. A naive count reads it as unbalanced and
    refuses a perfectly good statement."""
    from metis_mcp.sql_analysis import shape_of

    assert shape_of("SELECT * FROM t WHERE a = 'it''s'")["ok"]
    assert not shape_of("SELECT * FROM t WHERE a = 'x")["ok"]


def test_unbalanced_parentheses_are_named_with_the_counts():
    from metis_mcp.sql_analysis import shape_of

    problems = shape_of("SELECT (a FROM t")["problems"]
    assert any("parentheses" in p for p in problems)


def test_the_shape_check_does_not_claim_to_be_a_parse():
    """Métis has no SQL parser and adding one would be a fifth runtime
    dependency for everybody who never reviews a query. Calling this a parse
    would be the overclaim — a statement can pass it and still be rejected."""
    from metis_mcp.sql_analysis import shape_of

    assert "not a parse" in shape_of("SELECT 1")["means"]


def test_with_execution_off_the_answer_is_read_not_confirmed():
    """**The whole point.** A statement that reads cleanly and a statement that
    ran are different claims, and `off` is the default."""
    import types

    from metis_mcp.sql_analysis import STATIC, confirm

    out = confirm("SELECT id FROM orders WHERE id = 1",
                  execute=types.SimpleNamespace(tier=lambda: "off"))
    assert out["confirmed_to"] == STATIC
    assert "nothing was run" in out["stopped_because"]
    assert "READ, not confirmed" in out["stopped_because"]


def test_a_tier_without_a_target_confirms_nothing_further():
    """A plan is a fact about ONE database — its schema, its statistics, its
    indexes. Confirming against an unnamed one would be confirming against
    nothing."""
    import types

    from metis_mcp.sql_analysis import STATIC, confirm

    out = confirm("SELECT 1", execute=types.SimpleNamespace(tier=lambda: "observe"))
    assert out["confirmed_to"] == STATIC
    assert "no target was named" in out["stopped_because"]


def test_the_rung_is_never_higher_than_what_actually_happened():
    """This module opens no connection and acquires none, so it cannot reach
    `planned` however permissive the tier — and must not say it did."""
    import types

    from metis_mcp.sql_analysis import PLANNED, EXECUTED, confirm

    for tier in ("observe", "run"):
        out = confirm("SELECT 1", target="somewhere",
                      execute=types.SimpleNamespace(tier=lambda t=tier: t))
        assert out["confirmed_to"] not in (PLANNED, EXECUTED)
        assert "observers.sql" in out["stopped_because"]


def test_stopping_is_reported_as_an_answer_rather_than_a_failure():
    import types

    from metis_mcp.sql_analysis import confirm

    out = confirm("SELECT 1", execute=types.SimpleNamespace(tier=lambda: "off"))
    assert out["ok"] is True, "a statement Métis declined to run has not failed"


def test_the_validation_plan_no_longer_says_execution_is_not_ingested():
    """It said "Metis ingests no execution result", which stopped being true
    when `execution_intake` landed six labels (§8.7, revised). The claim that
    survives is narrower: results attach to the TestCase and never write the
    coverage ledger."""
    from metis_mcp.sql_analysis import validation_plan

    note = validation_plan()["note"]
    assert "ingests no execution result" not in note
    assert "coverage ledger" in note
