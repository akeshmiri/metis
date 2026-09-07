"""
Authoring a requirement (`metis requirement`), and the landing hole it exposed.
"""
from __future__ import annotations

import pytest

from metis_mcp.model_sources.authored_claim import plan_claim
from metis_mcp.requirements import AuthoringRefused, compose, describe


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


def test_an_ears_statement_becomes_a_requirement():
    a = compose("REQ-3", "When a record has been archived, "
                         "the system shall reject an update with 409")
    assert a.label == "Requirement"
    assert a.ears_pattern == "EventDriven"
    assert a.node_id.startswith("REQ-3@")


def test_free_prose_becomes_a_finding_with_the_same_wording_intake_uses():
    """S-13 through a second door. A person typing prose has chosen to write
    something; refusing them would be pedantry, and silently calling it a
    requirement would be the guess `ac_mining` exists to avoid."""
    a = compose("REQ-9", "Archive is broken again")
    assert a.label == "Finding"
    assert any("not EARS-conformant" in x for x in a.advisories)
    assert any("knowledge-capture" in x for x in a.advisories)


def test_the_quality_check_actually_runs():
    """**It did not, in the first version.**

    That version guessed the function name and wrapped the call in
    `except Exception: pass`, so it reported zero quality findings forever while
    looking like it checked — the silent-success shape this repository hunts.
    """
    a = compose("REQ-4", "The system shall be fast and reliable")
    assert a.label == "Requirement"          # structurally fine
    assert any("AC-VAGUE-TERM" in x for x in a.advisories), a.advisories


def test_quality_findings_never_block():
    """S-4: advisory means advisory. A vague requirement still lands."""
    assert compose("REQ-4", "The system shall be fast").label == "Requirement"


@pytest.mark.parametrize("key,text", [
    ("", "The system shall do something."),
    ("REQ-1", ""),
    ("REQ-1", "   "),
])
def test_an_empty_key_or_claim_is_refused(key, text):
    with pytest.raises(AuthoringRefused):
        compose(key, text)


def test_the_same_text_under_the_same_key_is_the_same_node():
    """TR-6: re-stating an unchanged claim must be a no-op, and that starts with
    the id being identical."""
    a = compose("REQ-3", "The system shall retain records for seven years.")
    b = compose("REQ-3", "The system shall retain records for seven years.")
    assert a.node_id == b.node_id


def test_changed_wording_under_the_same_key_is_a_new_node():
    """A claim that changes is a NEW node, not a modified one: *shall reject*
    and *shall refresh* are two claims (D-15)."""
    a = compose("REQ-3", "The system shall reject the update.")
    b = compose("REQ-3", "The system shall refresh the update.")
    assert a.logical_key == b.logical_key
    assert a.node_id != b.node_id


def test_describe_says_it_lands_unapproved():
    body = describe(compose("REQ-3", "The system shall do the thing."))
    assert "Quarantine" in body
    assert "N-10" in body


# ---------------------------------------------------------------------------
# The landing plan
# ---------------------------------------------------------------------------


def test_the_plan_lands_at_quarantine_and_names_its_author():
    plan = plan_claim(compose("REQ-3", "The system shall do the thing."),
                      author="alice")
    requirement = plan.by_label("Requirement")[0]
    assert requirement.properties["lifecycle_state"] == "Quarantine"
    assert plan.by_label("Episode")[0].properties["job_id"] == "alice"


def test_the_authored_requirement_carries_what_every_other_source_carries():
    """**Two sources writing the same label with different properties is how a
    query starts returning half an estate.** `search_text` missing here makes an
    authored requirement invisible to `search_knowledge`; `valid_from` missing
    makes it invisible to every read that requires a validity window.
    """
    plan = plan_claim(compose("REQ-3", "The system shall do the thing."))
    properties = plan.by_label("Requirement")[0].properties
    for required in ("id", "name", "text", "search_text", "revision",
                     "lifecycle_state", "valid_from", "valid_to",
                     "ears_pattern", "source_episode_id"):
        assert required in properties, required
    assert properties["valid_to"] == "", "a new claim is still true"


def test_a_finding_says_what_to_do_about_it():
    plan = plan_claim(compose("REQ-9", "Archive is broken again"))
    detail = plan.by_label("Finding")[0].properties["detail"]
    assert "knowledge-capture" in detail or "metis requirement" in detail


def test_re_landing_the_same_claim_reuses_the_episode():
    """D-8: the episode is content-derived, so an unchanged re-land is a no-op."""
    one = plan_claim(compose("REQ-3", "The system shall do the thing."))
    two = plan_claim(compose("REQ-3", "The system shall do the thing."))
    assert one.episode_id == two.episode_id


# ---------------------------------------------------------------------------
# The hole this exposed in landing
# ---------------------------------------------------------------------------


def test_reopen_clears_a_closed_window_and_leaves_an_open_one_alone():
    """**The bug, measured against a real graph before it was fixed.**

    `valid_to` is in `VALIDITY_FACTS`, so landing writes it ON CREATE only —
    correctly, because a routine re-extraction must never resurrect a superseded
    fact. But a claim whose text REVERTS to an earlier wording produces a
    `claim_id` that already exists with `valid_to` set: the MERGE matches the
    closed node and does not reopen it, while supersession closes the one that
    WAS current.

    State REQ-3 as 409, revise to 423, revise to 410, revise back to 409:
    three nodes, **all closed, zero current**, and the landing reported success
    and "now revision 4". The requirement was invisible to every
    validity-respecting read.
    """
    from metis_mcp.model_sources.landing import _reopen

    class _Session:
        def __init__(self):
            self.ran = []

        def run(self, cypher, **params):
            self.ran.append((cypher, params))
            return _Result()

    class _Result:
        # `_count` iterates rather than calling `.single()`, so the stub has to
        # be iterable. Getting this wrong made the test fail against correct
        # code, which is its own kind of wrong.
        def __iter__(self):
            return iter([{"written": 1}])

    session = _Session()
    assert _reopen(session, ["REQ-3@abc"]) == 1
    cypher, params = session.ran[0]
    assert params["ids"] == ["REQ-3@abc"]
    # Only a CLOSED window is reopened: this must be a no-op for the ordinary
    # case where the new revision was created a moment ago.
    assert "n.valid_to <> ''" in cypher
    assert "SET n.valid_to = ''" in cypher


def test_reopen_is_a_no_op_with_nothing_to_reopen():
    from metis_mcp.model_sources.landing import _reopen

    assert _reopen(None, []) == 0
    assert _reopen(None, None) == 0


def test_reopen_returns_the_column_count_expects():
    """It did not, and the write succeeded before the count raised — so the
    graph looked correct and the command exited with a traceback. A filtered
    grep over the output hid it; the raw output did not."""
    from metis_mcp.model_sources.landing import REOPEN_CYPHER

    assert "AS written" in REOPEN_CYPHER
