"""
Cross-surface link derivation (`mbt/link_proposals`, spec M-5a).

Every case here was unassertable a day ago, because the logic lived in a heredoc
inside `rebuild_graph.sh`. It carried four defects simultaneously and the stage
had never once executed.

Free to run: the derivation is pure, so the graph rows are just dicts.
"""
from __future__ import annotations

from metis_mcp.mbt.link_proposals import api_ids_for, propose, ui_ids_for

# Shaped like the real rows. The id is the thing that matters: a landed UiAction
# id is `{model_id}::{hash}` and carries NO screen name.
UI_ROWS = [
    {"id": "records-ui::9983f5be80990421", "trigger": "open RecordListPage",
     "name": "open RecordListPage → RecordListPage opened"},
    {"id": "records-ui::7c488ba5f06ebcf7", "trigger": "the page request completes",
     "name": "the page request completes → RecordListPage page ready"},
    {"id": "records-ui::e68911a98b6ced48", "trigger": "open SummaryPage",
     "name": "open SummaryPage → SummaryPage opened"},
]

API_ROWS = [
    {"id": "records-api::a1", "trigger": "GET /record"},
    {"id": "records-api::a2", "trigger": "POST /record"},
    {"id": "records-api::a3", "trigger": "GET /record/{id}"},
]

CALL = {"screen": "RecordListPage", "endpoint": "/record/",
        "anchor": {"file": "src/RecordListPage.jsx", "line": 18}}


# ---------------------------------------------------------------------------
# The join key. This is the bug that guaranteed zero.
# ---------------------------------------------------------------------------

def test_a_screen_is_matched_on_name_and_never_on_id():
    """The regression, stated as the thing that was false.

    `"RecordListPage" in "records-ui::9983f5be80990421"` is not merely wrong, it
    can never be true — so the stage reported a confident 0 that read as "these
    surfaces share nothing".
    """
    for row in UI_ROWS:
        assert "RecordListPage" not in row["id"], (
            "the fixture no longer reproduces the condition: a landed id must "
            "be an opaque hash, or this test proves nothing")

    assert ui_ids_for(UI_ROWS, "RecordListPage") == [
        "records-ui::9983f5be80990421", "records-ui::7c488ba5f06ebcf7"]


def test_a_screen_nothing_names_matches_nothing():
    assert ui_ids_for(UI_ROWS, "CheckoutPage") == []


def test_an_empty_screen_does_not_match_everything():
    """`"" in anything` is True, so an absent screen would have linked the whole
    UI surface to one endpoint."""
    assert ui_ids_for(UI_ROWS, "") == []


# ---------------------------------------------------------------------------
# Endpoint matching
# ---------------------------------------------------------------------------

def test_a_trailing_slash_is_not_a_different_endpoint():
    """The pack reports `/record/`; the controller declares `/record`."""
    assert api_ids_for(API_ROWS, "/record/") == api_ids_for(API_ROWS, "/record")
    assert "records-api::a1" in api_ids_for(API_ROWS, "/record/")


def test_matching_is_by_path_suffix_not_by_the_whole_trigger():
    """A controller may be dual-mounted and a gateway may strip a prefix."""
    rows = [{"id": "x", "trigger": "GET /api/v2/record"}]
    assert api_ids_for(rows, "/record") == ["x"]


def test_an_empty_endpoint_matches_nothing():
    assert api_ids_for(API_ROWS, "") == []
    assert api_ids_for(API_ROWS, "/") == []


# ---------------------------------------------------------------------------
# What the proposal carries
# ---------------------------------------------------------------------------

def test_a_proposal_names_the_pack_that_proposed_it():
    """`proposed_by` is required and was omitted — the second TypeError."""
    proposal = propose(UI_ROWS, API_ROWS, [CALL], proposed_by="react-ui")
    assert proposal.links
    assert {l.proposed_by for l in proposal.links} == {"react-ui"}


def test_evidence_is_a_mapping_not_a_sentence():
    """It was an f-string, which the frozen dataclass would have rejected."""
    proposal = propose(UI_ROWS, API_ROWS, [CALL], proposed_by="react-ui")
    evidence = proposal.links[0].evidence
    assert isinstance(evidence, dict)
    assert evidence["screen"] == "RecordListPage"
    assert evidence["anchor"]["file"] == "src/RecordListPage.jsx"


def test_nothing_is_confirmed_by_deriving_it():
    """M-5g: a derived link is a proposal and credits nothing."""
    proposal = propose(UI_ROWS, API_ROWS, [CALL], proposed_by="react-ui")
    assert not any(l.is_confirmed for l in proposal.links)


# ---------------------------------------------------------------------------
# A miss must be reportable as a miss
# ---------------------------------------------------------------------------

def test_an_unmatched_screen_is_returned_not_folded_into_a_zero():
    call = {"screen": "NoSuchPage", "endpoint": "/record"}
    proposal = propose(UI_ROWS, API_ROWS, [call], proposed_by="react-ui")
    assert proposal.links == []
    assert proposal.unmatched_screens == ["NoSuchPage"]
    assert proposal.unmatched_endpoints == []


def test_an_unmatched_endpoint_is_distinguished_from_an_unmatched_screen():
    """Which side missed is the whole diagnostic. `/summary/detail` is the real
    case: the demo service is records-only, so that one legitimately links to
    nothing — and saying so is different from reporting zero."""
    call = {"screen": "SummaryPage", "endpoint": "/summary/detail"}
    proposal = propose(UI_ROWS, API_ROWS, [call], proposed_by="react-ui")
    assert proposal.links == []
    assert proposal.unmatched_screens == []
    assert proposal.unmatched_endpoints == ["/summary/detail"]


# ---------------------------------------------------------------------------
# Both edge types
# ---------------------------------------------------------------------------

def test_both_edge_types_come_from_one_derivation():
    """`triggers` was left empty, so `persist_triggers` wrote zero while the
    caller printed it as a TRIGGERS count."""
    proposal = propose(UI_ROWS, API_ROWS, [CALL], proposed_by="react-ui")
    link_set = proposal.link_set("records")

    assert link_set.journey == "records"
    assert link_set.links and link_set.triggers
    assert len(link_set.triggers) == len(proposal.links)


def test_the_link_set_carries_the_journey_it_was_asked_for():
    """`journey` is required and was omitted, so the stage raised TypeError."""
    proposal = propose(UI_ROWS, API_ROWS, [CALL], proposed_by="react-ui")
    assert proposal.link_set("records").journey == "records"


def test_many_to_one_is_normal():
    """M-5e: one endpoint reached from several screens is not a duplicate."""
    proposal = propose(UI_ROWS, API_ROWS, [CALL], proposed_by="react-ui")
    pairs = {(l.ui_transition_id, l.api_transition_id) for l in proposal.links}
    assert len(pairs) == len(proposal.links), "a pair was proposed twice"
    # Two RecordListPage transitions x the two triggers whose path ends
    # `/record` (`GET /record`, `POST /record`). `GET /record/{id}` does not,
    # which is the suffix rule doing its job rather than an omission.
    assert len(proposal.links) == 4
