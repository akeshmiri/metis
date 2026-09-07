"""
Ingesting what a running system did (the change to §8.7).

Six labels were staged out *with the condition that would bring them back*, and
this is that condition arriving. The tests that matter are not the happy path —
they are the ones asserting C-10 and C-11 survive the change, because those two
rules thread through the whole codebase and a quiet breach here would surface as
a coverage figure that had silently started meaning "working".
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from metis_mcp.execution_intake import (
    PROVENANCE,
    IntakeRefused,
    normalise,
    plan_execution_landing,
    summarise,
)

MODULE = pathlib.Path("metis_mcp/execution_intake.py")


def _results(*pairs):
    return [{"case_id": c, "outcome": o, "observed_at": "2026-09-02T10:00:00+00:00"}
            for c, o in pairs]


# --------------------------------------------------------------------------
# The two rules the whole change rests on
# --------------------------------------------------------------------------

def test_an_execution_attaches_to_a_case_never_to_a_transition():
    """**The load-bearing routing decision.** An execution is evidence about an
    artefact somebody ran. Edging it to the transition would make "this
    behaviour passed" expressible in one hop — the conflation §6.8a names as the
    reason these labels were staged out."""
    plan = plan_execution_landing(_results(("tc-1", "passed")))
    targets = {e["to_label"] for e in plan["edges"]}
    assert "Transition" not in targets
    assert targets <= {"TestCase", "TestExecution"}


def test_nothing_here_writes_to_the_coverage_ledger():
    """C-10, asserted over the source rather than trusted. A ledger row says a
    case COVERS a transition and never that it passed; if this module ever
    imported the ledger, that sentence would stop being true."""
    tree = ast.parse(MODULE.read_text())
    imported = {(n.module or "") for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom)}
    imported |= {a.name for n in ast.walk(tree)
                 if isinstance(n, ast.Import) for a in n.names}
    for forbidden in ("metis_mcp.mbt.coverage", "metis_mcp.mbt.graph_writer"):
        assert not any(m.startswith(forbidden) for m in imported), forbidden


def test_the_outcome_figure_says_it_is_not_coverage():
    """C-11: a reader handed one number cannot tell which question it answers,
    so the answer says which."""
    out = summarise([normalise({"case_id": "c", "outcome": "passed"})])
    assert "NOT coverage" in out["means"]
    assert "C-10" in out["means"] and "C-11" in out["means"]


def test_everything_is_labelled_as_observed():
    """The provenance that keeps a recovered fact and an observed one apart."""
    plan = plan_execution_landing(_results(("tc-1", "passed")), cycle="nightly")
    for node in plan["nodes"]:
        assert node["properties"]["provenance"] == PROVENANCE


def test_it_lands_at_quarantine_like_everything_else():
    """S-4. An observed result is still a claim: it says a run happened and
    reported an outcome, not that the outcome was correctly attributed."""
    plan = plan_execution_landing(_results(("tc-1", "failed")))
    assert all(n["properties"]["lifecycle_state"] == "Quarantine"
               for n in plan["nodes"])


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------

def test_an_unrecognised_outcome_is_refused_not_defaulted():
    """A runner that says `flaky` is telling you something, and flattening it to
    `not_run` loses the only interesting part."""
    with pytest.raises(IntakeRefused) as e:
        normalise({"case_id": "c", "outcome": "flaky"})
    assert "deliberately" in str(e.value)


def test_an_execution_with_no_case_is_refused():
    """Without a case there is nothing to attach it to — and attaching it to a
    transition is exactly what this must not do."""
    with pytest.raises(IntakeRefused):
        normalise({"outcome": "passed"})


def test_a_failure_detail_is_kept_verbatim_and_not_interpreted():
    """The runner's words. Rewriting them into a cause is analysis nobody did."""
    out = normalise({"case_id": "c", "outcome": "failed",
                     "detail": "expected 200, got 500"})
    assert out["detail"] == "expected 200, got 500"


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def test_a_pass_rate_over_no_runs_is_not_reported_as_zero():
    """A division nobody should see the result of."""
    out = summarise([normalise({"case_id": "c", "outcome": "skipped"})])
    assert out["passed_of_ran"] == "nothing ran"


def test_re_landing_the_same_observed_run_is_a_no_op():
    """Content-derived ids: a second ingest merges rather than creating a run
    somebody has to reconcile."""
    first = plan_execution_landing(_results(("tc-1", "passed")))
    second = plan_execution_landing(_results(("tc-1", "passed")))
    assert [n["id"] for n in first["nodes"]] == [n["id"] for n in second["nodes"]]


def test_a_cycle_groups_runs_without_owning_them():
    plan = plan_execution_landing(_results(("a", "passed"), ("b", "failed")),
                                  cycle="nightly")
    cycles = [n for n in plan["nodes"] if n["label"] == "TestCycle"]
    assert len(cycles) == 1
    assert sum(1 for e in plan["edges"] if e["rel_type"] == "CONTAINS") == 2
