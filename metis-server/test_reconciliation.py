"""
Reconciliation tests (application spec §3.3, §5.7, F-4, F-5, X-15..X-18; R5).

Free to run: the pre-filter is deterministic and the judge is injected.
"""
import sys

from metis_mcp.mbt.model import IMPLEMENTED, PLANNED, Model, State, Transition
from metis_mcp.reconciliation import (
    CODE_DERIVED,
    HUMAN_CONFIRMED,
    INDEPENDENTLY_AUTHORED,
    UNIMPLEMENTED_OR_UNMODELLED,
    UNSPECIFIED_BEHAVIOUR,
    AcceptanceCriterion,
    JudgementUnavailable,
    confirm,
    dq_024,
    format_reconciliation,
    judge,
    prefilter,
    reconcile,
)

# The real code-derived shape from athena-git.
MODEL = Model(
    id="athena-git-api",
    states={
        "Ready": State(id="Ready", name="Ready", surface="api", is_initial=True),
        "Ok200": State(id="Ok200", name="Ok200", surface="api"),
        "NoContent204": State(id="NoContent204", name="NoContent204", surface="api"),
        "Created201": State(id="Created201", name="Created201", surface="api"),
    },
    transitions={
        "get-commit-ok": Transition(id="get-commit-ok", source="Ready",
                                    trigger="GET /commit", target="Ok200",
                                    guard="NOT (t.isEmpty())"),
        "get-commit-empty": Transition(id="get-commit-empty", source="Ready",
                                       trigger="GET /commit", target="NoContent204",
                                       guard="t.isEmpty()"),
        "post-commit": Transition(id="post-commit", source="Ready",
                                  trigger="POST /commit", target="Created201"),
        "planned-delete": Transition(id="planned-delete", source="Ready",
                                     trigger="DELETE /commit", target="NoContent204",
                                     implementation_status=PLANNED),
    },
)

ROUTES = {"get-commit-ok": "/commit", "get-commit-empty": "/commit",
          "post-commit": "/commit", "planned-delete": "/commit"}


def _ac(id, text, areas=()):
    return AcceptanceCriterion(id=id, text=text, functional_areas=tuple(areas))


# --------------------------------------------------------------------------
# X-15/X-16 : the pre-filter narrows on evidence, first
# --------------------------------------------------------------------------

def test_prefilter_finds_candidates_by_route_and_status():
    ac = _ac("ac1", "When GET /commit finds no matching commit, the service shall "
                    "return 204 with no body.")
    proposal = prefilter(ac, MODEL, ROUTES)
    assert proposal.candidates
    top = proposal.candidates[0]
    assert top.transition_id == "get-commit-empty", [c.transition_id for c in proposal.candidates]
    assert "path" in top.evidence and "status" in top.evidence


def test_prefilter_tokenises_snake_case_triggers():
    """A real bug, found by running `reconcile` against the login model rather
    than by these tests: `_WORD` included `_`, so `submit_valid_credentials` was
    one token and EV_TRIGGER_WORDS could never fire for a snake_case trigger.
    Every hand-authored model returned zero candidates, which reads identically
    to "this criterion describes nothing".

    This fixture uses space-separated HTTP triggers, which happen to tokenise
    correctly — which is exactly why it was missed.
    """
    model = Model(
        id="login-api",
        states={"LoggedOut": State(id="LoggedOut", name="LoggedOut", surface="api",
                                   is_initial=True),
                "LoggedIn": State(id="LoggedIn", name="LoggedIn", surface="api")},
        transitions={"t01": Transition(id="t01", source="LoggedOut",
                                       trigger="submit_valid_credentials",
                                       target="LoggedIn", guard="credentials_valid")},
    )
    model.reindex()

    ac = _ac("ac1", "When the user submits valid credentials, they shall be logged in.")
    proposal = prefilter(ac, model, {})
    assert proposal.candidates, "a snake_case trigger must be matchable"
    assert proposal.candidates[0].transition_id == "t01"
    assert "valid" in proposal.candidates[0].evidence["trigger_words"]


def test_prefilter_returns_no_candidates_when_nothing_refers_to_the_model():
    ac = _ac("ac9", "The nightly billing reconciliation shall complete within an hour.")
    proposal = prefilter(ac, MODEL, ROUTES)
    assert proposal.candidates == []
    assert "no candidates" in proposal.note


def test_prefilter_evidence_is_literal_never_inferred():
    ac = _ac("ac2", "POST /commit shall create the commit and return 201.")
    proposal = prefilter(ac, MODEL, ROUTES)
    top = proposal.candidates[0]
    assert top.transition_id == "post-commit"
    assert top.evidence["path"] == "/commit"
    assert top.evidence["status"] == "201"


def test_strength_is_a_count_not_a_probability():
    """A score invites a threshold, and a threshold invites deciding without a
    human — which X-17 prohibits."""
    ac = _ac("ac1", "GET /commit returns 204 when empty")
    proposal = prefilter(ac, MODEL, ROUTES)
    assert all(isinstance(c.strength, int) for c in proposal.candidates)


def test_ambiguity_is_reported_not_resolved():
    """Both GET /commit transitions match on route and verb alone."""
    ac = _ac("ac3", "The GET /commit endpoint shall behave correctly.")
    proposal = prefilter(ac, MODEL, ROUTES)
    assert len(proposal.candidates) >= 2
    assert proposal.is_ambiguous
    assert "human decides" in proposal.note


# --------------------------------------------------------------------------
# X-17 : the pre-filter is evidence, never a verdict
# --------------------------------------------------------------------------

def test_no_judge_raises_rather_than_falling_back_to_the_top_candidate():
    """Falling back would turn evidence into a verdict — X-17's prohibition."""
    ac = _ac("ac1", "GET /commit returns 204 when empty")
    proposal = prefilter(ac, MODEL, ROUTES)
    try:
        judge(proposal, ac, MODEL)
    except JudgementUnavailable as e:
        assert "must not be treated as a decision" in str(e)
        return
    raise AssertionError("stage 2 must not silently accept the pre-filter's top pick")


def test_an_injected_judge_is_used_when_supplied():
    ac = _ac("ac1", "GET /commit returns 204 when empty")
    proposal = prefilter(ac, MODEL, ROUTES)
    called = []

    def fake_judge(p, a, m):
        called.append(a.id)
        p.note = "judged"
        return p

    assert judge(proposal, ac, MODEL, fake_judge).note == "judged"
    assert called == ["ac1"]


def test_confirmation_records_who_made_it():
    ac = _ac("ac1", "GET /commit returns 204 when empty")
    proposal = prefilter(ac, MODEL, ROUTES)
    match = confirm(proposal, "get-commit-empty", confirmed_by="bob", rationale="clear")
    assert match.confirmed_by == "bob"
    assert match.evidence, "the evidence shown at confirmation is retained"
    try:
        confirm(proposal, "get-commit-empty", confirmed_by="  ")
    except ValueError:
        return
    raise AssertionError("a confirmation without an identity must be refused")


# --------------------------------------------------------------------------
# F-4/F-5 : two gap types, never merged
# --------------------------------------------------------------------------

def test_f4_reconcile_reports_both_directions():
    criteria = [
        _ac("ac1", "GET /commit returns 204 when empty"),
        _ac("ac-orphan", "The service shall support pagination on all list endpoints."),
    ]
    proposal = prefilter(criteria[0], MODEL, ROUTES)
    confirmed = [confirm(proposal, "get-commit-empty", "bob")]

    result = reconcile(MODEL, criteria, confirmed)
    assert result.summary["matched"] == 1
    # Two implemented transitions remain unspecified; the planned one is not a gap.
    assert result.summary[UNSPECIFIED_BEHAVIOUR] == 2
    assert result.summary[UNIMPLEMENTED_OR_UNMODELLED] == 1
    assert not any(g.element_id == "planned-delete" for g in result.unspecified_behaviour)


def test_f5_the_two_gap_types_are_never_merged():
    result = reconcile(MODEL, [_ac("ac-orphan", "unrelated")], [])
    text = format_reconciliation(result)
    assert "UNSPECIFIED BEHAVIOUR" in text
    assert "UNIMPLEMENTED / UNMODELLED" in text
    assert "NOT one number" in text
    # No combined percentage anywhere.
    assert "%" not in text


def test_only_confirmed_matches_count():
    """Pre-filter candidates are evidence a human has not ruled on (F-7)."""
    criteria = [_ac("ac1", "GET /commit returns 204 when empty")]
    assert prefilter(criteria[0], MODEL, ROUTES).candidates
    result = reconcile(MODEL, criteria, confirmed=[])
    assert result.summary["matched"] == 0
    assert result.summary[UNSPECIFIED_BEHAVIOUR] == 3


# --------------------------------------------------------------------------
# DQ-024 becomes falsifiable
# --------------------------------------------------------------------------

def test_dq024_is_not_falsifiable_for_hand_authored_transitions():
    report = dq_024(MODEL, confirmed=[])
    assert report["falsifiable"] is False
    assert "modelling discipline" in report["qualifier"]


def test_dq024_is_falsifiable_once_transitions_come_from_code():
    model = Model(id="m", states=dict(MODEL.states), transitions={})
    for tid, t in MODEL.transitions.items():
        clone = Transition(id=t.id, source=t.source, trigger=t.trigger, target=t.target,
                           guard=t.guard, implementation_status=t.implementation_status)
        object.__setattr__(clone, "extraction_method", "static_analysis")
        model.transitions[tid] = clone
    model.reindex()

    report = dq_024(model, confirmed=[])
    assert report["falsifiable"] is True
    assert report["qualifier"] == ""
    assert report["implemented"] == 3 and report["with_acceptance_criterion"] == 0
    assert report["ratio"] == 0.0, "no criteria confirmed — the honest answer is zero"


# --------------------------------------------------------------------------
# S-19 : a criterion derived from code is documentation, not intent
# --------------------------------------------------------------------------

def test_s19_a_criterion_defaults_to_the_weakest_grade():
    """Fail-closed, like S-4: an origin nobody recorded is not assumed to be
    intent."""
    ac = _ac("ac1", "anything")
    assert ac.provenance == CODE_DERIVED
    assert not ac.is_intent


def test_s19_only_human_confirmed_and_independent_are_intent():
    assert AcceptanceCriterion("a", "t", provenance=HUMAN_CONFIRMED).is_intent
    assert AcceptanceCriterion("a", "t", provenance=INDEPENDENTLY_AUTHORED).is_intent
    assert not AcceptanceCriterion("a", "t", provenance=CODE_DERIVED).is_intent


def test_s19_confirming_a_match_does_not_manufacture_intent():
    """A person agreeing that AC-4 describes this transition says nothing about
    whether AC-4 was written from the code. Separate facts (cf. X-12)."""
    ac = _ac("ac1", "GET /commit returns 204 when empty")
    proposal = prefilter(ac, MODEL, ROUTES)
    match = confirm(proposal, "get-commit-empty", "bob")
    assert match.provenance == CODE_DERIVED
    assert not match.is_intent


def test_s19_an_unknown_grade_is_refused():
    ac = _ac("ac1", "GET /commit returns 204 when empty")
    proposal = prefilter(ac, MODEL, ROUTES)
    try:
        confirm(proposal, "get-commit-empty", "bob", provenance="probably-fine")
    except ValueError as e:
        assert "unknown provenance" in str(e)
        return
    raise AssertionError("a made-up grade must not pass")


def test_s19_the_report_separates_intent_from_documentation():
    ac = _ac("ac1", "GET /commit returns 204 when empty")
    proposal = prefilter(ac, MODEL, ROUTES)
    doc = confirm(proposal, "get-commit-empty", "bob", provenance=CODE_DERIVED)
    intent = confirm(proposal, "get-commit-ok", "bob", provenance=HUMAN_CONFIRMED)

    result = reconcile(MODEL, [ac], [doc, intent])
    assert result.summary["matched"] == 2
    assert result.summary["matched_by_intent"] == 1
    assert result.summary["matched_by_documentation"] == 1
    assert result.supports_a_correctness_claim


def test_s19_an_all_documentation_run_supports_no_correctness_claim():
    """The athena case: specs marked IMPLEMENTED, documenting what was built."""
    ac = _ac("ac1", "GET /commit returns 204 when empty")
    proposal = prefilter(ac, MODEL, ROUTES)
    doc = confirm(proposal, "get-commit-empty", "bob", provenance=CODE_DERIVED)

    result = reconcile(MODEL, [ac], [doc])
    assert not result.supports_a_correctness_claim
    text = format_reconciliation(result)
    assert "NO CORRECTNESS CLAIM IS SUPPORTED" in text
    assert "both sides came from the same" in text


def test_s19_dq024_is_not_falsifiable_against_code_derived_criteria():
    model = Model(id="m", states=dict(MODEL.states), transitions={})
    for tid, t in MODEL.transitions.items():
        clone = Transition(id=t.id, source=t.source, trigger=t.trigger, target=t.target,
                           guard=t.guard, implementation_status=t.implementation_status)
        object.__setattr__(clone, "extraction_method", "static_analysis")
        model.transitions[tid] = clone
    model.reindex()

    ac = _ac("ac1", "GET /commit returns 204 when empty")
    proposal = prefilter(ac, model, ROUTES)
    doc = confirm(proposal, "get-commit-empty", "bob", provenance=CODE_DERIVED)

    report = dq_024(model, [doc])
    assert report["with_acceptance_criterion"] == 1
    assert report["with_intent"] == 0
    assert report["falsifiable"] is False
    assert "written from the behaviour it" in report["qualifier"]


def test_s19_dq024_becomes_falsifiable_once_a_criterion_is_intent():
    model = Model(id="m", states=dict(MODEL.states), transitions={})
    for tid, t in MODEL.transitions.items():
        clone = Transition(id=t.id, source=t.source, trigger=t.trigger, target=t.target,
                           guard=t.guard, implementation_status=t.implementation_status)
        object.__setattr__(clone, "extraction_method", "static_analysis")
        model.transitions[tid] = clone
    model.reindex()

    ac = _ac("ac1", "GET /commit returns 204 when empty")
    proposal = prefilter(ac, model, ROUTES)
    intent = confirm(proposal, "get-commit-empty", "bob", provenance=HUMAN_CONFIRMED)

    report = dq_024(model, [intent])
    assert report["with_intent"] == 1
    assert report["falsifiable"] is True
    assert report["qualifier"] == ""


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
