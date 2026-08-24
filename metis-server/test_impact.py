"""
`impact` — what a change touches (the one v1 capability v2 lacked).

Free to run: `_rows` is stubbed, which is the single function that opens a
session. What is asserted is the shape of the answer and the three ways it could
lie, not the graph behind it.
"""
from __future__ import annotations

import pytest

from metis_mcp import impact as I

CONTROLLER = "src/main/java/com/example/records/RecordController.java"


def _row(**over):
    base = {"supplied": CONTROLLER, "matched_file": CONTROLLER,
            "commit": "405f75b", "evidence_label": "Endpoint", "line": 41,
            "transition": "records-api::t1", "trigger": "POST /record",
            "outcome_status": 201, "lifecycle_state": "Quarantine",
            "criteria": []}
    base.update(over)
    return base


@pytest.fixture
def graph(monkeypatch):
    def install(rows):
        monkeypatch.setattr(I, "_rows", lambda cypher, **kw: rows)
    return install


# ---------------------------------------------------------------------------
# It answers the question
# ---------------------------------------------------------------------------

def test_a_changed_file_yields_the_transitions_recovered_from_it(graph):
    graph([_row(), _row(transition="records-api::t2", outcome_status=409)])
    out = I.impact([CONTROLLER])
    assert out["ok"] is True
    assert [t["id"] for t in out["impacted_transitions"]] == [
        "records-api::t1", "records-api::t2"]


def test_each_transition_says_which_evidence_reached_it(graph):
    """`Endpoint` and `Method` are different claims about why a file matters,
    and a reviewer weighs them differently."""
    graph([_row(evidence_label="Endpoint"), _row(evidence_label="Method")])
    reached = I.impact([CONTROLLER])["impacted_transitions"][0]["reached_via"]
    assert reached == ["Endpoint", "Method"]


def test_the_criteria_that_validate_an_impacted_transition_come_back(graph):
    """v1's `impacted_requirements`. A `code_derived` criterion is carried with
    its provenance, because its agreeing with the code is evidence of coverage
    and never of correctness (§4.1)."""
    graph([_row(criteria=[{"id": "AC-4", "provenance": "code_derived"}])])
    out = I.impact([CONTROLLER])
    assert out["validating_criteria"] == ["AC-4"]
    assert out["impacted_transitions"][0]["criteria"][0]["provenance"] == \
        "code_derived"


# ---------------------------------------------------------------------------
# The three ways it could lie
# ---------------------------------------------------------------------------

def test_a_file_that_matched_nothing_is_named_not_counted_as_no_impact(graph):
    """**The one that matters before a merge.** "Nothing depends on this" and
    "I have never seen this file" are different answers, and reporting the
    second as the first is how a change ships believing it was checked."""
    graph([_row()])
    out = I.impact([CONTROLLER, "src/main/java/nowhere/Absent.java"])
    assert out["files_supplied"] == 2
    assert out["files_matched"] == 1
    assert out["files_unmatched"] == ["src/main/java/nowhere/Absent.java"]


def test_every_supplied_file_missing_is_still_ok_but_visibly_empty(graph):
    """Not an error — the graph genuinely has nothing. But `files_matched: 0`
    against `files_supplied: 2` is the fact, and it must be readable."""
    graph([])
    out = I.impact(["a.java", "b.java"])
    assert out["ok"] is True
    assert out["files_matched"] == 0 and len(out["files_unmatched"]) == 2
    assert out["impacted_transitions"] == []


def test_the_answer_carries_the_commits_it_matched_against(graph):
    """The graph holds what the last extraction ingested. A file changed since
    is invisible and no query reveals that, so the answer says what it is
    current as of instead of implying it is current."""
    graph([_row(commit="405f75b"), _row(commit="aa11bb2",
                                        transition="records-api::t2")])
    out = I.impact([CONTROLLER])
    assert out["graph_commits"] == ["405f75b", "aa11bb2"]
    assert "not in the graph" in out["as_of"]


def test_the_path_actually_matched_is_reported_alongside_what_was_supplied(graph):
    """Suffix matching is the only thing that works — an anchor holds the CPG's
    path and a caller passes a diff path — but a caller must be able to see
    which anchor their string hit, not trust that it hit the right one."""
    graph([_row(supplied="RecordController.java")])
    out = I.impact(["RecordController.java"])
    assert out["matched_paths"] == [CONTROLLER]
    assert "Nothing was rewritten" in out["matching"]


def test_no_files_is_refused_rather_than_answered_emptily(graph):
    graph([])
    out = I.impact([])
    assert out["ok"] is False and "git diff" in out["reason"]


def test_the_answer_states_that_it_is_coverage_and_not_correctness(graph):
    """C-11 holds here as everywhere: this says which recovered behaviour a
    change touches, and nothing about whether that behaviour works."""
    graph([_row()])
    assert "never correctness" in I.impact([CONTROLLER])["means"]


# ---------------------------------------------------------------------------
# The query itself
# ---------------------------------------------------------------------------

def test_the_traversal_is_bounded_and_excludes_the_call_graph():
    """A wildcard depth over every relationship would report a transition as
    impacted because something it reaches eventually `CALLS` something in the
    file — a much weaker claim wearing the same name."""
    assert "*1..3" in I.IMPACT_CYPHER
    assert "CALLS" not in I.IMPACT_CYPHER


def test_the_query_uses_the_specialisation_expression_not_a_bare_transition():
    """A classified transition carries `:ApiCall` INSTEAD of `:Transition`, so
    a bare `:Transition` matches nothing on a recovered estate."""
    assert "ApiCall" in I.IMPACT_CYPHER and "UiAction" in I.IMPACT_CYPHER
