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
    assert ":INVOKES]->" in INVOKES_CYPHER
    assert "$surface" not in INVOKES_CYPHER, (
        "INVOKES spans two surfaces and must not be filtered to one"
    )


def test_only_confirmed_invokes_are_honoured():
    """M-5g / F-7: a proposal is visible, and behaves like nothing until decided.

    An `INVOKES` edge may be stored unconfirmed so a reviewer can see and decide
    it. Without this filter the stored proposal would lend its guard to a UI
    transition and credit cross-surface coverage — a machine guess raising a
    coverage number, which is exactly what "proposed, never asserted" forbids.
    """
    from metis_mcp.mbt.graph_loader import INHERITED_GUARDS_CYPHER

    for query in (INVOKES_CYPHER, INHERITED_GUARDS_CYPHER):
        assert "confirmed_by" in query, (
            "an unconfirmed proposal must not behave like a confirmed match")


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


# --------------------------------------------------------------------------
# Bi-temporal reads (ontology.labels.VALIDITY_LABELS)
#
# Free to run: the clauses are strings and the refusals are argument checks.
# The behaviour they produce was verified against a live Neo4j — invalidating
# one of three criteria removed it from the default read, left it in an as-at
# read before the cut, and did not delete it or disturb its lifecycle_state.
# --------------------------------------------------------------------------

def test_a_validity_carrying_node_must_have_a_window():
    """The tolerance is gone, and `backfill-validity` is what replaced it.

    Reads used to accept `valid_to IS NULL` as "still valid", which kept a graph
    readable across the release that introduced validity — and made a node whose
    window was never set indistinguishable from one deliberately left open. The
    migration ends that ambiguity, so the read can now require a window.
    """
    from metis_mcp.mbt.graph_loader import currently_valid, valid_at

    assert "IS NULL" not in currently_valid("n")
    assert "IS NULL" not in valid_at("n")
    assert currently_valid("n") == "(n.valid_to = '')"


def test_a_label_with_no_window_is_not_dropped_by_a_multi_label_read():
    """Search spans six labels and four carry validity. A bare `valid_to = ''`
    dropped `BusinessEntity` and `Lesson` entirely — measured: a search for a
    term in a landed lesson returned nothing at all.

    This is NOT the removed tolerance. That accepted a validity-carrying node
    with no window; this accepts only labels for which a window was never
    defined.
    """
    from metis_mcp.mbt.graph_loader import valid_where_it_applies
    from metis_mcp.ontology.labels import VALIDITY_LABELS

    clause = valid_where_it_applies("n")
    for label in VALIDITY_LABELS:
        assert f"l = '{label}'" in clause
    assert "labels(n)" in clause and "valid_to = ''" in clause




def test_the_as_at_window_is_half_open():
    """`valid_from <= at < valid_to`. A fact invalidated at T was true up TO T
    and not AT T; closing both ends would make it briefly true and superseded at
    once."""
    from metis_mcp.mbt.graph_loader import valid_at

    clause = valid_at("n")
    assert "n.valid_from <= $at" in clause
    assert "n.valid_to > $at" in clause


def test_the_two_requirement_reads_cannot_drift():
    """The as-at query is derived from the default one by substituting the
    clause, not by copying the body — so a change to what a requirement returns
    reaches both or neither."""
    from metis_mcp.mbt.graph_loader import (
        REQUIREMENT_AS_AT_CYPHER,
        REQUIREMENT_CYPHER,
        currently_valid,
        valid_at,
    )

    rebuilt = (REQUIREMENT_CYPHER
               .replace(currently_valid("r"), valid_at("r"))
               .replace(currently_valid("ac"), valid_at("ac")))
    assert rebuilt == REQUIREMENT_AS_AT_CYPHER

    # The criteria filter belongs on the OPTIONAL MATCH. In the outer WHERE it
    # would drop the whole requirement row when its only criterion is
    # superseded, turning "no current criteria" into "no such requirement".
    body = REQUIREMENT_CYPHER
    assert body.index("OPTIONAL MATCH (r)-[:HAS_AC]") < body.index(currently_valid("ac"))


def test_invalidation_refuses_an_empty_instant():
    """An empty `valid_to` is what "still valid" means, so accepting it as an
    invalidation would silently do the opposite of what was asked."""
    import pytest as _pytest

    from metis_mcp.model_sources.landing import invalidate

    with _pytest.raises(ValueError, match="stopped being true"):
        invalidate(None, ["AC-1"], valid_to="   ")


def test_invalidating_nothing_touches_nothing():
    """No session is opened for an empty id list — asserted by passing None as
    the session, which would raise if it were used."""
    from metis_mcp.model_sources.landing import invalidate

    assert invalidate(None, [], valid_to="2026-01-01T00:00:00+00:00") == {
        "closed": 0, "already_closed": 0, "missing": []}


# --------------------------------------------------------------------------
# Free-text search (Lucene, Community edition — no new dependency)
#
# Behaviour verified against a live Neo4j, and the numbers are why this was
# worth doing:
#
#   query "locking"  CONTAINS -> AC-LOCK, AC-OLD (superseded, unordered)
#                    fulltext -> AC-LOCK 0.506, BE-ACC 0.131 (ranked, current)
#   query "lock"     CONTAINS -> nothing
#                    fulltext -> AC-LOCK, BE-ACC   (stems to "locked")
# --------------------------------------------------------------------------

def test_a_user_query_is_escaped_rather_than_parsed_as_lucene():
    """Somebody typing `auth:token` is asking a question, not writing a query
    language. Unescaped, Lucene reads `auth:` as a field selector and raises a
    parse error that reads like the database is broken."""
    from metis_mcp.mbt.graph_loader import lucene_escape

    assert lucene_escape("auth:token") == r"auth\:token"
    assert lucene_escape("lock~") == r"lock\~"
    assert lucene_escape("a(b)c") == r"a\(b\)c"
    assert lucene_escape("plain words") == "plain words"


def test_the_search_index_uses_a_stemming_analyzer():
    """`english`, not the default `standard`.

    Measured: with the default, searching `lock` returned NOTHING for a
    criterion whose text says "the account is locked" — standard tokenises and
    lowercases but does not stem. That beats CONTAINS on ranking and loses to it
    on word forms, which is half the reason to want full text at all.
    """
    from metis_mcp.ontology.schema import constraints_cypher, statements

    index = [s for s in statements(constraints_cypher()) if "FULLTEXT" in s.upper()]
    assert len(index) == 1, "one index across every searchable label"
    assert "fulltext.analyzer" in index[0] and "'english'" in index[0]


def test_the_index_and_the_query_name_the_same_labels():
    """Two lists in two files is the drift the generated schema exists to
    prevent, so the index is generated from `labels.SEARCH_TARGETS` and the
    query filters on the same set."""
    from metis_mcp.mbt.graph_loader import SEARCH_CYPHER
    from metis_mcp.ontology.labels import SEARCH_TARGETS
    from metis_mcp.ontology.schema import constraints_cypher, statements

    index = [s for s in statements(constraints_cypher()) if "FULLTEXT" in s.upper()][0]
    for label in SEARCH_TARGETS:
        assert label in index, f"{label} is searchable and not in the index"
        assert f"n:{label}" in SEARCH_CYPHER, f"{label} is indexed and not queried"


def test_search_filters_superseded_facts_and_ranks_what_is_left():
    """Two properties in one query, both absent before: `CONTAINS` returned a
    superseded criterion and had no notion of order."""
    from metis_mcp.mbt.graph_loader import SEARCH_CYPHER, valid_where_it_applies

    assert valid_where_it_applies("n") in SEARCH_CYPHER
    assert "score" in SEARCH_CYPHER and "ORDER BY score DESC" in SEARCH_CYPHER


def test_an_absent_index_is_reported_and_not_silently_downgraded():
    """Falling back to `CONTAINS` would leave search working badly with no
    signal — worse answers and no reason to suspect them. An absent index means
    the generated schema has not been applied, which is one command to fix, so
    the message says which command."""
    from metis_mcp.mbt.graph_loader import SearchIndexMissing

    assert issubclass(SearchIndexMissing, RuntimeError)
