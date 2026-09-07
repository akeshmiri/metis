"""
Review findings a linter cannot make (Atlas's `code-reviewer`, narrowed).

**Metis does not review code**, and the tests that matter most are the ones
asserting it does not pretend to: style and maintainability belong to the tools
a repository already runs. What is ported is the part only a behaviour model can
supply — which of the behaviour a diff touches is now unasserted — and the
severity grading that makes it actionable.
"""
from __future__ import annotations

from metis_mcp.change_review import (
    BLOCKING,
    CRITICAL,
    MAJOR,
    MINOR,
    ORDER,
    QUESTION,
    findings_for,
    summarise,
)


def _impact(transitions=(), unmatched=()):
    """The shape `metis_mcp.impact.impact` really returns.

    It used to be `{"transitions": [...]}` with `{"transition": id}` rows, and
    the producer has never emitted either key — so every test here passed
    against a payload that does not exist while `findings_for` looped over
    nothing. `test_the_fixture_matches_what_impact_really_returns` below is what
    stops that happening again.
    """
    return {"impacted_transitions": [dict(t) for t in transitions],
            "files_unmatched": list(unmatched)}


def _sev(findings):
    return [f["severity"] for f in findings]


# --------------------------------------------------------------------------
# The grading, each grade for its own reason
# --------------------------------------------------------------------------

def test_touched_behaviour_with_no_criterion_is_critical():
    """Merging changes something no criterion asserts (D-4)."""
    out = findings_for(_impact([{"id": "t1", "criteria": []}]))
    assert _sev(out) == [CRITICAL]
    assert "D-4" in out[0]["why"]


def test_positive_only_coverage_is_major():
    """The guard's complement has no case of its own, and a positive result does
    not cover a rejection."""
    out = findings_for(
        _impact([{"id": "t1", "criteria": ["ac"]}]),
        depth={"rows": [{"transition_id": "t1", "verdict": "positive-only"}]})
    assert _sev(out) == [MAJOR]


def test_code_derived_only_validation_is_minor():
    """S-19: a criterion written from the code it checks can only report
    agreement — coverage, never correctness."""
    out = findings_for(_impact([{"id": "t1", "criteria": ["ac"]}]),
                       provenance={"t1": ["code_derived"]})
    assert _sev(out) == [MINOR]


def test_intent_backed_validation_produces_no_finding():
    """The grader must not become a machine that always complains."""
    assert findings_for(
        _impact([{"id": "t1", "criteria": ["ac"]}]),
        provenance={"t1": ["independently_authored"]}) == []


def test_an_unmatched_file_is_a_question_never_no_impact():
    """**The refusal that matters.** An unmatched file is one the model does not
    cover — exactly when a reviewer should look harder, not less."""
    out = findings_for(_impact(unmatched=["src/Unknown.java"]))
    assert _sev(out) == [QUESTION]
    assert "different answers" in out[0]["why"]


# --------------------------------------------------------------------------
# Ordering, blocking, and the boundary
# --------------------------------------------------------------------------

def test_blockers_come_first():
    """Atlas's hard rule 1: lead with blockers, narrative after. A report that
    opens with a summary buries the thing somebody must act on."""
    out = findings_for(
        _impact([{"id": "a", "criteria": ["x"]},
                 {"id": "b", "criteria": []}],
                unmatched=["f.java"]),
        depth={"rows": [{"transition_id": "a", "verdict": "positive-only"}]})
    assert _sev(out) == sorted(_sev(out), key=ORDER.index)
    assert out[0]["severity"] == CRITICAL


def test_it_produces_the_list_open_merge_request_refuses_over():
    """The loop this closes: that parameter existed with no producer."""
    s = summarise(findings_for(_impact([{"id": "t", "criteria": []}])))
    assert s["blocking"] and "critical" in s["blocking"][0]
    assert s["verdict"] == "blockers present"


def test_only_critical_and_major_block():
    """A Minor is maintainability — it does not block a merge."""
    assert set(BLOCKING) == {CRITICAL, MAJOR}
    s = summarise(findings_for(_impact([{"id": "t", "criteria": ["a"]}]),
                               provenance={"t": ["code_derived"]}))
    assert s["blocking"] == []


def test_a_missing_input_removes_findings_rather_than_guessing():
    """No depth data means no `major` — not a downgraded guess. A verdict built
    on an input nobody supplied is the confident-wrong output to avoid."""
    out = findings_for(_impact([{"id": "t1", "criteria": ["ac"]}]))
    assert MAJOR not in _sev(out)


def test_it_states_what_it_did_not_review():
    """Metis has no language server and no lint config; a second opinion would
    be worse than the tools the repository already runs."""
    s = summarise([])
    assert "style" in s["not_reviewed"] and "maintainability" in s["not_reviewed"]


def test_a_clean_result_is_not_a_statement_that_the_change_is_good():
    s = summarise([])
    assert "not a code" in s["means"]
    assert "not a statement that the change is good" in s["means"]


def test_the_fixture_matches_what_impact_really_returns():
    """The guard on every test above.

    `findings_for` read `impact["transitions"]` and `row["transition"]` while
    `impact.impact()` emitted `impacted_transitions` and `id`. The loop never
    ran, so `change_review` could not produce a CRITICAL finding for any diff —
    and it is documented as producing "the blocking list `open_merge_request`
    refuses over". Ten tests passed throughout, because `_impact` above invented
    the shape they wanted.

    So assert the fixture's keys against the producer's own source rather than
    against memory. A rename on either side fails here.
    """
    import ast
    from pathlib import Path

    source = Path("metis_mcp/impact.py").read_text()
    returned = {k.value for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Dict)
                for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}

    for key in _impact():
        assert key in returned, (
            f"the fixture uses {key!r} and metis_mcp/impact.py never returns it")

    # And the per-transition key, which is the half that actually broke.
    assert "id" in returned and "criteria" in returned
    assert "transition" not in _impact([{"id": "t", "criteria": []}])[
        "impacted_transitions"][0]


def test_a_critical_finding_names_the_transition_it_is_about():
    """`tid` came from a key the payload does not have, so a finding built from
    a real payload would have carried an empty id and still looked fine."""
    out = findings_for(_impact([{"id": "records-api::abc", "criteria": []}]))
    assert out[0]["transition_id"] == "records-api::abc"


def test_provenance_is_read_from_the_criteria_when_not_supplied():
    """`change_review` never passes `provenance`, so MINOR was unreachable even
    after the loop was fixed. The grade is already on each criterion."""
    out = findings_for(_impact([{"id": "t1", "criteria": [
        {"id": "AC-1", "provenance": "code_derived"}]}]))
    assert _sev(out) == [MINOR]


def test_an_intent_backed_criterion_read_inline_produces_no_finding():
    """The complement of the test above: the inline read must not fire on a
    criterion that is independently authored, or MINOR becomes always-on."""
    out = findings_for(_impact([{"id": "t1", "criteria": [
        {"id": "AC-1", "provenance": "independently_authored"}]}]))
    assert out == []
