"""
Gathering the half a decision page cannot hold — and refusing to invent it.

Four of the six decisions have no rendered surface because each is *about*
something the review context does not carry. `review_ui/resolve.py` goes and
gets it, and the property that makes it safe is the one asserted hardest here:

    a resolver reports what it could not reach, and never substitutes for it.

Filling a field with a plausible value to make a page render would put a
decision in front of somebody over evidence nobody gathered. That is worse than
the refusal it replaces.
"""
from __future__ import annotations

import pytest

from metis_mcp.reconciliation.matching import AcceptanceCriterion
from metis_mcp.review_ui import resolve


@pytest.fixture
def model():
    from mbt_fixtures import login_model

    return login_model()


def _criterion(cid="AC-1", text="When the password is wrong, the system shall "
                                "reject the login with 401"):
    return AcceptanceCriterion(id=cid, text=text)


# --- confirm a match ---------------------------------------------------------

def test_a_match_is_fillable_from_the_session_alone(model):
    """Why this is the one to render first: the model is already loaded and the
    pre-filter is pure, so nothing reaches outside the process."""
    provided, missing = resolve.for_confirm_match(
        model, "AC-1", model.transition_ids()[0], [_criterion()])

    assert missing == []
    assert provided["ac_text"]
    assert "why_proposed" in provided


def test_the_evidence_comes_from_the_real_matcher(model):
    """X-17: the pre-filter narrows without deciding, and a reviewer has to see
    that a match rests on a route and a status rather than on wording
    similarity. Describing that in prose would be this module's own account."""
    provided, _ = resolve.for_confirm_match(
        model, "AC-1", model.transition_ids()[0], [_criterion()])

    why = provided["why_proposed"]
    assert set(why) == {"evidence", "strength", "ambiguous", "note"}
    assert isinstance(why["evidence"], dict)


def test_confirming_a_pairing_the_matcher_never_proposed_says_it_is_an_override(model):
    """Real information, not a missing input. A reviewer may overrule the
    pre-filter; they must be told that is what they are doing."""
    provided, missing = resolve.for_confirm_match(
        model, "AC-1", model.transition_ids()[-1],
        [_criterion(text="something about an entirely unrelated subject")])

    assert missing == []
    assert "override" in provided["why_proposed"]["note"]


def test_a_criterion_that_is_not_in_scope_is_reported_not_invented(model):
    provided, missing = resolve.for_confirm_match(
        model, "AC-MISSING", model.transition_ids()[0], [_criterion()])

    assert "ac_text" in missing
    assert "ac_text" not in provided


def test_an_empty_criterion_is_missing_rather_than_blank(model):
    """Rendering it would ask somebody to confirm that a blank validates a
    transition."""
    provided, missing = resolve.for_confirm_match(
        model, "AC-1", model.transition_ids()[0], [_criterion(text="")])

    assert "ac_text" in missing
    assert "ac_text" not in provided


def test_a_transition_that_is_not_in_the_model_is_reported(model):
    _, missing = resolve.for_confirm_match(
        model, "AC-1", "no-such-transition", [_criterion()])

    assert "transition_tuple" in missing


# --- resolve a divergence ----------------------------------------------------

def test_both_claims_are_gathered_and_neither_is_marked_as_likely(model):
    """S-10 forbids a precedence rule: it would silently decide which of a
    defect and a stale requirement is right, which is the judgement the
    decision exists to take."""
    tid = model.transition_ids()[0]

    provided, missing = resolve.for_resolve_divergence(
        model, tid, [_criterion()], validating={tid: ["AC-1"]})

    assert missing == []
    assert provided["code_side"]["transition_id"] == tid
    assert provided["ac_side"]["criteria"][0]["id"] == "AC-1"
    flat = str(provided).lower()
    for word in ("recommended", "likely", "probably", "suggest"):
        assert word not in flat


def test_the_validates_edge_is_read_from_the_mapping_not_the_criterion(model):
    """An `AcceptanceCriterion` carries text and provenance; `VALIDATES` is a
    relationship. Looking for an attribute found none on every criterion and
    would have reported every divergence unfillable — a resolver failing
    silently in the direction of "no evidence"."""
    tid = model.transition_ids()[0]

    _, without = resolve.for_resolve_divergence(model, tid, [_criterion()])
    _, with_edge = resolve.for_resolve_divergence(
        model, tid, [_criterion()], validating={tid: ["AC-1"]})

    assert "ac_side" in without, "no mapping means the AC side is unreachable"
    assert with_edge == []


def test_a_divergence_names_what_stays_blocked_while_it_is_open(model):
    tid = model.transition_ids()[0]

    provided, _ = resolve.for_resolve_divergence(
        model, tid, [_criterion()], validating={tid: ["AC-1"]})

    assert provided["blocked_paths"] == [tid]


# --- decide a drift item -----------------------------------------------------

class _Item:
    case_id = "TC-1"
    diff = ("- was", "+ is")


def test_the_published_text_cannot_come_from_the_ledger():
    """`PublicationLedger` stores a content HASH per case — which is what makes
    a hand edit detectable — and never the text. Reading the tracker is the only
    way to show a reviewer what it currently holds."""
    class _Ledger:
        last_generated = {"TC-1": "the text Métis last generated"}

    provided, missing = resolve.for_decide_drift(_Item(), ledger=_Ledger())

    assert provided["last_generated"] == "the text Métis last generated"
    assert "published_content" in missing


def test_a_reader_supplies_the_published_text():
    class _Ledger:
        last_generated = {"TC-1": "generated"}

    provided, missing = resolve.for_decide_drift(
        _Item(), ledger=_Ledger(), published_reader=lambda case: "what the tracker holds")

    assert missing == []
    assert provided["published_content"] == "what the tracker holds"


def test_a_tracker_that_cannot_be_read_is_reported_with_the_failure_named():
    """A blank page and an unreachable tracker are different facts, and only one
    of them means the reviewer should go and look themselves."""
    def refuse(case):
        raise RuntimeError("403 Forbidden")

    provided, missing = resolve.for_decide_drift(
        _Item(), published_reader=refuse)

    assert "published_content" in missing
    assert "403 Forbidden" in provided["read_failed"]


# --- the property that makes all of it safe ----------------------------------

def test_no_resolver_ever_fills_a_field_it_reported_missing(model):
    """The single worst thing this module could do. A page drawn over a
    substituted value asks somebody to decide on evidence nobody gathered."""
    cases = [
        resolve.for_confirm_match(model, "AC-NONE", "no-transition", []),
        resolve.for_resolve_divergence(model, "no-transition", []),
        resolve.for_decide_drift(_Item()),
    ]

    for provided, missing in cases:
        assert missing, "this case is supposed to be short of something"
        for name in missing:
            assert name not in provided, name


def test_a_refusal_names_the_input_and_who_holds_it():
    """"Not available" tells a reader nothing they can act on."""
    sentence = resolve.describe("decide_drift", ["published_content"])

    assert "published_content" in sentence
    assert "test-management tool" in sentence


def test_every_declared_source_is_named_for_every_decision_that_has_one():
    for decision, sources in resolve.SOURCES.items():
        assert sources, decision
        for name, holder in sources.items():
            assert holder and holder != "unknown", (decision, name)
