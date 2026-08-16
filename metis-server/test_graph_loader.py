"""
Graph-loader and review-state-separation tests
(application spec §16.1, I-14, E-8).

Free to run: the mapper is pure, so no Neo4j is needed. Only the query text
itself needs a live database, and that is asserted structurally here.
"""
import json
import sys
import tempfile
from pathlib import Path

from metis_mcp.mbt import ALL_TRANSITIONS, generate
from metis_mcp.mbt.graph_loader import (
    INVOKES_CYPHER,
    STATES_CYPHER,
    TRANSITIONS_CYPHER,
    rows_to_model,
)
from metis_mcp.mbt.model import APPROVED, QUARANTINE
from metis_mcp.review import apply, export
from metis_mcp.review.state import (
    ReviewState,
    default_state_path,
    overlay,
    record,
    source_fingerprint,
)
from mbt_fixtures import STATES, TRANSITIONS, login_model, login_model_source


def _graph_rows(lifecycle=APPROVED):
    state_rows = [
        {"id": s, "name": s, "surface": "api", "is_initial": i, "lifecycle_state": lifecycle}
        for s, i in STATES
    ]
    transition_rows = [
        {"id": t[0], "source": t[1], "trigger": t[2], "target": t[3], "guard": t[4],
         "implementation_status": t[5], "lifecycle_state": lifecycle}
        for t in TRANSITIONS
    ]
    return state_rows, transition_rows


# --------------------------------------------------------------------------
# Pure mapper
# --------------------------------------------------------------------------

def test_rows_to_model_reproduces_the_fixture():
    state_rows, transition_rows = _graph_rows()
    report = rows_to_model("login-api", state_rows, transition_rows)
    assert report.model.id == "login-api"
    assert len(report.model.states) == 10
    assert len(report.model.transitions) == 17
    assert not report.skipped
    # The loaded model must generate exactly as the hand-built fixture does.
    assert (generate(report.model, ALL_TRANSITIONS).covered_transition_ids
            == generate(login_model(), ALL_TRANSITIONS).covered_transition_ids)


def test_mapper_skips_dangling_transitions_and_says_why():
    """A transition whose source was filtered out is a modelling problem.

    Silently shrinking the model would hide it, so it is reported.
    """
    state_rows, transition_rows = _graph_rows()
    state_rows = [r for r in state_rows if r["id"] != "AccountLocked"]
    report = rows_to_model("login-api", state_rows, transition_rows)
    skipped = dict(report.skipped)
    assert "t06" in skipped and "AccountLocked" in skipped["t06"]
    assert "t15" in skipped and "AccountLocked" in skipped["t15"]
    assert "t06" not in report.model.transitions


def test_mapper_skips_a_transition_with_no_trigger():
    state_rows, transition_rows = _graph_rows()
    for row in transition_rows:
        if row["id"] == "t03":
            row["trigger"] = None
    report = rows_to_model("login-api", state_rows, transition_rows)
    assert ("t03", "no trigger") in report.skipped


def test_mapper_is_order_independent():
    """Determinism must not depend on the driver preserving result order."""
    state_rows, transition_rows = _graph_rows()
    forward = rows_to_model("login-api", state_rows, transition_rows).model
    backward = rows_to_model("login-api", state_rows[::-1], transition_rows[::-1]).model
    assert generate(forward, ALL_TRANSITIONS).paths == generate(backward, ALL_TRANSITIONS).paths


def test_mapper_defaults_missing_lifecycle_to_quarantine():
    state_rows, transition_rows = _graph_rows(lifecycle=None)
    report = rows_to_model("login-api", state_rows, transition_rows)
    assert all(t.lifecycle_state == QUARANTINE for t in report.model.transitions.values())
    assert generate(report.model, ALL_TRANSITIONS).paths == []


def test_invokes_rows_are_loaded_for_cross_surface_credit():
    state_rows, transition_rows = _graph_rows()
    report = rows_to_model("login-api", state_rows, transition_rows,
                           [{"ui_transition": "u01", "api_transition": "t01"}])
    assert report.invokes == {"u01": "t01"}


# --------------------------------------------------------------------------
# Query shape (what needs a live database to verify fully)
# --------------------------------------------------------------------------

def test_queries_scope_by_journey_and_surface():
    """Spec M-1: a model is one <journey>-<surface> machine."""
    for cypher in (STATES_CYPHER, TRANSITIONS_CYPHER):
        assert "$journey" in cypher and "functional_areas" in cypher
        assert "$surface" in cypher
    assert "ORDER BY" in STATES_CYPHER and "ORDER BY" in TRANSITIONS_CYPHER


def test_transition_query_walks_when_then():
    assert "-[:WHEN]->" in TRANSITIONS_CYPHER and "-[:THEN]->" in TRANSITIONS_CYPHER
    assert "guard_expression" in TRANSITIONS_CYPHER


def test_invokes_query_is_cross_surface():
    assert "-[:INVOKES]->" in INVOKES_CYPHER
    assert "$surface" not in INVOKES_CYPHER, (
        "INVOKES spans two surfaces and must not be filtered to one"
    )


# --------------------------------------------------------------------------
# I-14 : source and review state are separate files
# --------------------------------------------------------------------------

def test_source_fingerprint_excludes_lifecycle():
    """The evidence a decision binds to is source substance, not the decision."""
    unapproved = login_model(approved=False)
    approved = login_model(approved=True)
    assert source_fingerprint(unapproved) == source_fingerprint(approved), (
        "approving an element must not change what a reviewer was shown"
    )


def test_source_fingerprint_moves_when_a_guard_changes():
    model = login_model()
    before = source_fingerprint(model)
    old = model.transitions["t06"]
    model.transitions["t06"] = type(old)(
        id=old.id, source=old.source, trigger=old.trigger, target=old.target,
        guard="NOT credentials_valid AND attempts >= 5",
        implementation_status=old.implementation_status,
        lifecycle_state=old.lifecycle_state,
    )
    assert source_fingerprint(model) != before


def test_reapplying_the_same_decision_file_is_no_longer_refused():
    """The defect the separation fixes: lifecycle was in the fingerprint, so
    applying a decision invalidated the file that made it."""
    model = login_model(approved=False)
    review = export(model)
    review.reviewer = "bob"
    for item in review.items:
        item.decision = "approve"

    first = apply(model, review)
    assert first.ok and len(first.applied) == 26

    second = apply(model, review)
    assert second.ok, f"a second apply must not be refused: {second.blocked_reason}"


def test_overlay_applies_human_facts_onto_a_fresh_source():
    source = login_model(approved=False)
    state = ReviewState()
    review = export(source)
    review.reviewer = "bob"
    for item in review.items:
        item.decision = "approve"
    result = apply(source, review)
    record(state, source, result.applied)

    # A fresh load of the source starts at Quarantine; the overlay restores it.
    fresh = login_model(approved=False)
    overlay_result = overlay(fresh, state)
    assert not overlay_result.stale
    assert overlay_result.applied == 26
    assert fresh.is_approved


def test_overlay_reports_stale_and_applies_nothing_when_source_moved():
    """Spec E-8: decisions are retained, not discarded -- but not applied."""
    source = login_model(approved=False)
    state = ReviewState()
    review = export(source)
    review.reviewer = "bob"
    for item in review.items:
        item.decision = "approve"
    record(state, source, apply(source, review).applied)

    moved = login_model(approved=False)
    old = moved.transitions["t06"]
    moved.transitions["t06"] = type(old)(
        id=old.id, source=old.source, trigger=old.trigger, target=old.target,
        guard="NOT credentials_valid AND attempts >= 5",
        implementation_status=old.implementation_status, lifecycle_state=old.lifecycle_state,
    )

    overlay_result = overlay(moved, state)
    assert overlay_result.stale
    assert overlay_result.applied == 0
    assert not moved.is_approved, "a stale overlay must not silently approve anything"
    assert len(state.states) + len(state.transitions) == 26, "decisions are retained"


def test_audit_is_append_only_across_review_rounds():
    """Spec N-15: a decision may be superseded, never edited away."""
    model = login_model(approved=False)
    state = ReviewState()

    first = export(model)
    first.reviewer = "bob"
    for item in first.items:
        item.decision = "approve"
    record(state, model, apply(model, first).applied)
    after_first = len(state.audit)

    second = export(model, include_approved=True)
    second.reviewer = "carol"
    for item in second.items:
        if item.id == "t06":
            item.decision = "reject"
            item.rationale = "guard is wrong"
        else:
            item.decision = "defer"
    record(state, model, apply(model, second).applied)

    assert len(state.audit) == after_first + 1
    assert state.transitions["t06"].lifecycle_state == "Rejected"
    # The earlier approval is still in the trail, not overwritten.
    assert any(a["element_id"] == "t06" and a["to_state"] == APPROVED for a in state.audit)
    assert any(a["element_id"] == "t06" and a["to_state"] == "Rejected" for a in state.audit)


def test_state_file_round_trips_and_has_a_default_path():
    state = ReviewState(model_id="login-api", source_fingerprint="abc123")
    restored = ReviewState.from_json(state.to_json())
    assert restored.model_id == "login-api"
    assert restored.source_fingerprint == "abc123"
    assert default_state_path("demo/login-api.json").name == "login-api.review.json"


def test_review_never_writes_the_model_source_file():
    """Spec I-14: re-extraction owns the source; review must not touch it."""
    with tempfile.TemporaryDirectory() as tmp:
        model_path = Path(tmp) / "login-api.json"
        model_path.write_text(json.dumps(login_model_source(), indent=2))
        before = model_path.read_text()

        from metis_mcp.mbt.cli import load_model
        model, _ = load_model(str(model_path))
        review = export(model)
        review.reviewer = "bob"
        for item in review.items:
            item.decision = "approve"
        result = apply(model, review)

        state_path = default_state_path(model_path)
        state = ReviewState.load(state_path)
        record(state, model, result.applied)
        state.save(state_path)

        assert model_path.read_text() == before, "the model source must be untouched"
        assert state_path.exists()

        reloaded, overlay_result = load_model(str(model_path))
        assert not overlay_result.stale
        assert reloaded.is_approved


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
