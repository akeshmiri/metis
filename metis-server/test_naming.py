"""
X-7 tier 1: the acceptance criteria's own words (spec X-7..X-12, S-10).

`naming.py` had **no test file**, which is the same reason
`propose_from_criteria` and `conflicts` could sit with zero callers without
anybody noticing: nothing exercised them, so nothing reported that the tier-1
path stopped at transition names and never reached the states or the guards.

The rules under test are all about *restraint*. A name taken from a criterion is
a presentation decision, not evidence that the code and the intent agree (X-11);
two criteria naming one state differently is a real disagreement, not something
to average (S-10); and nothing is proposed from a criterion nobody confirmed
(X-9, X-18).
"""
from __future__ import annotations

import sys

from metis_mcp.mbt.model import APPROVED, Model, State, Transition
from metis_mcp.mbt.naming import (
    TIER_AC_VOCABULARY,
    TIER_CODE_CONVENTION,
    conflicts,
    format_proposals,
    guard_wording_from_criterion,
    propose_from_criteria,
    split_criterion,
    transition_display_name,
    transition_name_from_criterion,
)

CRITERION = ("When the caller requests a metric that does not exist, "
             "then 204 No Content is returned")

# A criterion whose Then carries real domain vocabulary, not just a status. The
# difference decides whether a STATE gets a tier-1 name at all — see
# `test_a_status_only_then_proposes_no_state_name`.
DOMAIN_CRITERION = ("When the caller requests a metric that does not exist, "
                    "then the caller is told the metric is unknown")


def _model() -> Model:
    m = Model(
        id="records-api",
        states={
            "Metric": State(id="Metric", name="Metric", surface="api",
                            is_initial=True, lifecycle_state=APPROVED),
            "MetricGetActionByIdNoContent204": State(
                id="MetricGetActionByIdNoContent204",
                name="MetricGetActionByIdNoContent204", surface="api",
                lifecycle_state=APPROVED),
        },
        transitions={
            "t1": Transition(id="t1", source="Metric", trigger="GET /metric/{id}",
                             target="MetricGetActionByIdNoContent204",
                             guard="request_accepted", lifecycle_state=APPROVED),
        })
    m.reindex()
    return m


# --------------------------------------------------------------------------
# Splitting a criterion — one definition, three consumers.
# --------------------------------------------------------------------------

def test_a_criterion_splits_into_its_when_and_then():
    when, then = split_criterion(CRITERION)
    assert "does not exist" in when
    assert "204" in then


def test_anything_not_in_when_then_shape_yields_nothing_rather_than_half():
    """Half a criterion is not evidence. A partial parse would put an arbitrary
    fragment of a sentence into a name."""
    assert split_criterion("The system shall return metrics") == ("", "")
    assert split_criterion("") == ("", "")


# --------------------------------------------------------------------------
# The guard — the position tier 1 never used to reach.
# --------------------------------------------------------------------------

def test_the_when_clause_becomes_the_guards_business_wording():
    """`guard_language` decodes conventions the code commits to and reaches "the
    request is rejected". Only a person reaches "a metric that does not exist"."""
    assert guard_wording_from_criterion(CRITERION) == (
        "the caller requests a metric that does not exist")
    assert guard_wording_from_criterion(DOMAIN_CRITERION) == (
        "the caller requests a metric that does not exist")


def test_a_criterion_with_no_when_supplies_no_guard_wording():
    assert guard_wording_from_criterion("The system shall be fast") == ""


# --------------------------------------------------------------------------
# Proposals, and the two things they must never do.
# --------------------------------------------------------------------------

def _confirmed(text: str = DOMAIN_CRITERION, cid: str = "ac-1"):
    when, then = split_criterion(text)
    return {"t1": (cid, when, then)}


def test_a_confirmed_criterion_proposes_names_for_the_edge_and_its_target():
    proposals = propose_from_criteria(_model(), _confirmed())
    kinds = {p.kind for p in proposals}
    assert kinds == {"transition", "state"}, (
        "the Then clause names the state the transition arrives at — this half "
        "was computed and never written anywhere")
    assert all(p.tier == TIER_AC_VOCABULARY for p in proposals)


def test_a_status_only_then_proposes_no_state_name():
    """"then 204 No Content is returned" carries no domain vocabulary: strip the
    status and the trailing "is returned" and nothing is left.

    Proposing an empty or stub name would be worse than the tier-2 name, which
    at least encodes the status accurately. Fail-closed, and it means a criterion
    only improves a state name when it actually says something about the state.
    """
    proposals = propose_from_criteria(_model(), _confirmed(CRITERION))
    assert [p.kind for p in proposals] == ["transition"]


def test_naming_from_a_criterion_is_never_evidence_of_agreement():
    """X-11/X-12. If it were, §4.4's comparison would rediscover its own naming
    step and report agreement everywhere — destroying the one thing that makes
    extracting from code worth doing."""
    proposals = propose_from_criteria(_model(), _confirmed())
    assert proposals
    assert not any(p.is_evidence_of_agreement for p in proposals)


def test_an_unconfirmed_criterion_proposes_nothing():
    """X-9/X-18: alignment is evidence-based. Wording similarity alone never
    proposes a name, so an empty confirmed set produces an empty result."""
    assert propose_from_criteria(_model(), {}) == []


def test_two_criteria_naming_one_state_differently_is_reported_not_averaged():
    """S-10. Picking one silently buries a real disagreement about what the
    state IS."""
    model = _model()
    model.transitions["t2"] = Transition(
        id="t2", source="Metric", trigger="GET /metric/{id}",
        target="MetricGetActionByIdNoContent204", guard="NOT (request_accepted)",
        lifecycle_state=APPROVED)
    model.reindex()

    confirmed = dict(_confirmed())
    confirmed["t2"] = ("ac-2", "the metric id is unknown",
                       "the caller is told no such metric was recorded")

    clashes = conflicts(propose_from_criteria(model, confirmed))
    assert "MetricGetActionByIdNoContent204" in clashes, (
        "two criteria describe this state in different words")
    assert len({p.proposed_name
                for p in clashes["MetricGetActionByIdNoContent204"]}) == 2


def test_the_report_says_proposed_and_says_it_is_not_agreement():
    text = format_proposals(propose_from_criteria(_model(), _confirmed()), _model())
    assert "PROPOSED, never applied" in text
    assert "X-11" in text


# --------------------------------------------------------------------------
# The display name, and the tier boundary.
# --------------------------------------------------------------------------

def test_a_confirmed_criterion_beats_the_codes_own_vocabulary():
    model = _model()
    tier_two = transition_display_name(model.transitions["t1"], model.states)
    tier_one = transition_display_name(model.transitions["t1"], model.states,
                                       criterion_text=CRITERION)
    assert "MetricGetActionByIdNoContent204" in tier_two
    assert tier_one != tier_two
    assert "204" in tier_one, "the status IS the outcome and must survive"


def test_a_degenerate_criterion_falls_back_rather_than_producing_a_stub():
    """Tier 2's readable shape beats a name that says nothing — the fallback is
    the cascade working, not failing."""
    assert transition_name_from_criterion("When a, then b") == ""
    assert TIER_CODE_CONVENTION != TIER_AC_VOCABULARY


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
        except Exception as e:                                    # noqa: BLE001
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
