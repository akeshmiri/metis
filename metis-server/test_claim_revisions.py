"""
A requirement that changes produces a new revision, and does not overwrite one.

**The defect this file exists to prevent, stated exactly.** A `Requirement`'s id
was derived from its evidence anchor:

    requirement_id = f"req-{sha256(anchor_id)[:12]}"

so re-landing an edited Jira ticket resolved to the same node. `landing.split_row`
put `text`, `statement` and `revision` in the clause rewritten on every land, and
`lifecycle_state` in the `ON CREATE` clause that is never rewritten. The result,
measured rather than reasoned about:

    the requirement text was replaced in place, the previous wording gone;
    `revision` was rewritten to 1, so §8.4's versioning could never advance;
    an **Approved** requirement kept its approval while saying something else;
    and it never reappeared in `review queue`, because `NeedReview` tracks
    lifecycle and lifecycle had not moved.

Every one of those is a way for a requirements tool to lie about what somebody
agreed to, and none of them raised anything.

**The fix is identity, not a check.** `claim_id` splits a claim's id into a
stable logical key and a digest of its text, so a changed requirement is a
different node -- it lands at `Quarantine` because it is new (S-4), the previous
revision keeps the decision a human made (I-19), and `plan_supersession` closes
the old validity window through the `invalidate` that had been written, tested
and never called.

The graph-facing half runs against a recording fake rather than a live Neo4j:
the engine is database-free on purpose, and a test that needs a container is a
test that does not run.
"""
from __future__ import annotations

import pytest

from metis_mcp.identity.keys import claim_id, logical_key_of
from metis_mcp.model_sources.landing import (
    ON_CREATE_FACTS,
    LandingPlan,
    PlannedEdge,
    PlannedNode,
    plan_supersession,
    resolve_claim_edges,
    split_row,
)

TOKEN_V1 = "When the token expires the system shall reject the request"
TOKEN_V2 = "When the token expires the system shall refresh it silently"

KEY = "req-a1b2c3d4e5f6"


def _requirement(text: str, **overrides) -> PlannedNode:
    props = {
        "id": claim_id(KEY, text),
        "text": text,
        "statement": text,
        "ears_pattern": "event_driven",
        "revision": 1,                      # what every writer hardcodes
        "lifecycle_state": "Quarantine",
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": "",
    }
    props.update(overrides)
    return PlannedNode(label="Requirement", properties=props)


def _plan(*nodes: PlannedNode, edges=()) -> LandingPlan:
    return LandingPlan(episode_id="ep-1", nodes=list(nodes), edges=list(edges))


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def test_a_changed_requirement_is_a_different_node():
    """The whole fix in one assertion."""
    assert claim_id(KEY, TOKEN_V1) != claim_id(KEY, TOKEN_V2)
    assert logical_key_of(claim_id(KEY, TOKEN_V1)) == KEY
    assert logical_key_of(claim_id(KEY, TOKEN_V2)) == KEY


def test_reformatting_is_not_a_change():
    """TR-6: re-landing the same content must stay a no-op.

    Whitespace only. Case, punctuation and word order all carry meaning in a
    requirement -- `shall` and `shall not` differ by three characters -- so
    folding any of them would decide two different claims were one.
    """
    assert claim_id(KEY, TOKEN_V1) == claim_id(KEY, f"  {TOKEN_V1}  ")
    assert claim_id(KEY, TOKEN_V1) == claim_id(KEY, TOKEN_V1.replace(" ", "  "))
    assert claim_id(KEY, "the system shall lock") != claim_id(
        KEY, "the system shall not lock")


def test_a_legacy_id_reads_as_its_own_logical_key():
    """A graph landed before claim ids existed must be readable.

    Returning "" here would make every pre-existing requirement look like a new
    claim and land a duplicate beside it, which is a worse outcome than the bug
    being fixed.
    """
    assert logical_key_of("req-a1b2c3d4e5f6") == "req-a1b2c3d4e5f6"
    assert logical_key_of("") == ""


def test_a_claim_id_needs_something_to_be_a_revision_of():
    with pytest.raises(ValueError):
        claim_id("", TOKEN_V1)


# ---------------------------------------------------------------------------
# The fact partition — the half that made the overwrite silent
# ---------------------------------------------------------------------------

def test_revision_is_written_once_and_never_re_asserted():
    """It was a machine fact, so `SET n += row.machine` reset it to 1 on every land.

    Every claim writer hardcodes `"revision": 1` because a plan builder cannot
    know how many times a claim changed before -- that is a fact about the
    graph. While the property rode in the rewritten clause, §8.4's versioning
    could not advance no matter what else was fixed.
    """
    assert "revision" in ON_CREATE_FACTS
    split = split_row(_requirement(TOKEN_V1).properties)
    assert "revision" in split["on_create"]
    assert "revision" not in split["machine"]


def test_text_is_still_a_machine_fact():
    """The fix must not overshoot.

    Freezing `text` on create would make a re-land unable to correct a typo in
    the SAME claim, and would put the two halves of one node's content under
    different rules. Text stays re-assertable; what changed is that different
    text is a different node.
    """
    split = split_row(_requirement(TOKEN_V1).properties)
    assert "text" in split["machine"]
    assert "statement" in split["machine"]


# ---------------------------------------------------------------------------
# Supersession
# ---------------------------------------------------------------------------

def test_a_first_landing_supersedes_nothing():
    plan = _plan(_requirement(TOKEN_V1))
    result = plan_supersession(plan, current={})
    assert result.first_seen == [claim_id(KEY, TOKEN_V1)]
    assert result.supersedes == []
    assert result.to_close == []
    assert result.revisions == {claim_id(KEY, TOKEN_V1): 1}


def test_re_landing_identical_content_closes_nothing():
    """TR-6, and the reason it matters beyond tidiness.

    Closing a window here would move the instant a fact stopped being true to
    whenever somebody happened to re-run extraction.
    """
    v1 = claim_id(KEY, TOKEN_V1)
    plan = _plan(_requirement(TOKEN_V1))
    result = plan_supersession(plan, current={KEY: (v1, 1)})
    assert result.unchanged == [v1]
    assert result.supersedes == []
    assert result.to_close == []


def test_changed_text_supersedes_the_previous_revision():
    v1, v2 = claim_id(KEY, TOKEN_V1), claim_id(KEY, TOKEN_V2)
    plan = _plan(_requirement(TOKEN_V2))
    result = plan_supersession(plan, current={KEY: (v1, 1)})

    assert result.to_close == [v1]
    assert result.revisions == {v2: 2}
    (superseded,) = result.supersedes
    assert superseded.previous_id == v1
    assert superseded.new_id == v2
    assert superseded.logical_key == KEY
    assert superseded.label == "Requirement"


def test_revisions_accumulate():
    """A third edit is revision 3, not revision 2 again."""
    v3 = claim_id(KEY, "a third wording entirely")
    plan = _plan(_requirement("a third wording entirely"))
    result = plan_supersession(plan, current={KEY: (claim_id(KEY, TOKEN_V2), 2)})
    assert result.revisions == {v3: 3}


def test_supersession_takes_no_lifecycle_decision():
    """D-15: invalidation is not a review decision and must not disturb one.

    The new revision is unapproved because it is NEW, not because anything
    revoked it, and the old one keeps the approval a human gave it -- which is
    what I-19 means by retaining the prior decision in history. A `Supersede`
    carrying a lifecycle field would be the beginning of the opposite design.
    """
    from dataclasses import fields

    from metis_mcp.model_sources.landing import Supersede

    names = {f.name for f in fields(Supersede)}
    assert "lifecycle_state" not in names
    assert names == {"label", "logical_key", "previous_id", "new_id",
                     "previous_revision"}


def test_an_element_is_never_superseded():
    """Only the four validity-carrying labels are claims.

    A `Transition` whose guard changes is the SAME transition, modified -- its
    approval is revoked by `carry_human_facts`, and giving it a second,
    identity-based revocation path would mean two mechanisms disagreeing about
    what a behaviour change is.
    """
    plan = _plan(PlannedNode(label="Transition",
                             properties={"id": "m::t1", "guard": "x > 1"}))
    result = plan_supersession(plan, current={"m::t1": ("m::t1", 1)})
    assert result.supersedes == []
    assert result.first_seen == []
    assert result.revisions == {}


# ---------------------------------------------------------------------------
# Cross-plan edges
# ---------------------------------------------------------------------------

def test_an_edge_naming_a_logical_key_resolves_to_the_current_revision():
    """An authored file writes `REQ-3`; the live node is `REQ-3@<digest>`.

    Unresolved, this edge passes `validate_relationship` and then merges
    nothing -- the silent success that has shipped here twice.
    """
    live = claim_id("REQ-3", TOKEN_V2)
    plan = _plan(edges=[PlannedEdge("Specification", "SPEC-1", "SPECIFIES",
                                    "Requirement", "REQ-3")])
    unresolved = resolve_claim_edges(plan, current={"REQ-3": (live, 2)})
    assert unresolved == []
    assert plan.edges[0].to_id == live


def test_an_edge_to_a_claim_in_the_same_plan_is_left_alone():
    """The writer already minted it; re-resolving could point at an older one."""
    minted = claim_id("REQ-3", TOKEN_V1)
    plan = _plan(_requirement(TOKEN_V1, id=minted),
                 edges=[PlannedEdge("Specification", "SPEC-1", "SPECIFIES",
                                    "Requirement", minted)])
    unresolved = resolve_claim_edges(plan, current={"REQ-3": ("stale-id", 1)})
    assert unresolved == []
    assert plan.edges[0].to_id == minted


def test_an_unresolvable_claim_is_reported_and_left_as_written():
    """A claim that does not exist must read as absent, never be pointed at
    something plausible. Guessing here is what X-6e forbids everywhere else."""
    plan = _plan(edges=[PlannedEdge("Specification", "SPEC-1", "SPECIFIES",
                                    "Requirement", "REQ-NOBODY-LANDED")])
    unresolved = resolve_claim_edges(plan, current={})
    assert unresolved == ["REQ-NOBODY-LANDED"]
    assert plan.edges[0].to_id == "REQ-NOBODY-LANDED"


def test_an_edge_to_a_non_claim_label_is_untouched():
    plan = _plan(edges=[PlannedEdge("Requirement", "REQ-3", "BELONGS_TO",
                                    "BusinessArea", "billing")])
    assert resolve_claim_edges(plan, current={"billing": ("other", 1)}) == []
    assert plan.edges[0].to_id == "billing"


# ---------------------------------------------------------------------------
# End to end through `land()`
# ---------------------------------------------------------------------------
#
# A recording fake, not a container. `land` is the one place where the read, the
# revision stamp and the window close have to happen in the right ORDER, and the
# order is the part that a pure test of `plan_supersession` cannot check.


class FakeSession:
    """Answers `current_claims`, records everything else.

    Deliberately literal about the Cypher it recognises: a fake that answered
    every query with the same rows would let `land` read its supersession state
    from the wrong statement and still pass.
    """

    def __init__(self, claims: dict | None = None):
        # {logical_key: (node_id, revision)}
        self.claims = claims or {}
        self.written: list[dict] = []
        self.invalidated: list[str] = []
        # **Reopening is recorded separately from closing, and that separation
        # is the point.** Both statements start `SET n.valid_to`, so a fake that
        # matched on that alone counted a reopen as an invalidation — and the
        # test asserting "which window was closed" then failed against correct
        # code while being unable to notice a reopen that never happened.
        self.reopened: list[str] = []
        self.order: list[str] = []

    def run(self, cypher, **kwargs):
        if "RETURN wanted AS logical_key" in cypher:
            self.order.append("read")
            rows = []
            for key in kwargs["keys"]:
                if key in self.claims:
                    node_id, revision = self.claims[key]
                    rows.append({"logical_key": key, "id": node_id,
                                 "revision": revision})
            return rows
        if "SET n.valid_to = ''" in cypher:
            # Supersession reopening the window of the node it just made
            # current. Distinguished from closing by the value it sets.
            self.order.append("reopen")
            self.reopened.extend(kwargs["ids"])
            return _Count(len(kwargs["ids"]))
        if "SET n.valid_to" in cypher:
            self.order.append("invalidate")
            self.invalidated.extend(kwargs["ids"])
            return _Count(len(kwargs["ids"]))
        if "UNWIND $ids AS wanted MATCH (n {id: wanted})" in cypher:
            # `invalidate` asks which ids are present before closing, so it can
            # tell "nothing matched" from "everything was already closed".
            return [{"id": i} for i in kwargs["ids"]]
        if "MERGE (n:" in cypher:
            self.order.append("write")
            self.written.extend(kwargs["rows"])
            return _Count(len(kwargs["rows"]))
        if "MERGE (a)-[r:" in cypher:
            return _Count(len(kwargs["rows"]))
        return _Count(0)


class _Count:
    def __init__(self, n):
        self._rows = [{"written": n}]

    def __iter__(self):
        return iter(self._rows)


def _land(plan, session):
    from metis_mcp.model_sources.landing import land

    return land(session, plan)


def test_land_stamps_the_revision_from_the_graph_not_the_plan():
    """The plan says 1 -- every writer hardcodes it -- and the graph says 2."""
    session = FakeSession({KEY: (claim_id(KEY, TOKEN_V1), 1)})
    plan = _plan(_requirement(TOKEN_V2))
    assert plan.nodes[0].properties["revision"] == 1, "the writer's hardcoded 1"

    result = _land(plan, session)

    (row,) = [r for r in session.written if r["id"] == claim_id(KEY, TOKEN_V2)]
    assert row["on_create"]["revision"] == 2
    assert result.ok


def test_land_closes_the_previous_window_and_says_which():
    session = FakeSession({KEY: (claim_id(KEY, TOKEN_V1), 1)})
    result = _land(_plan(_requirement(TOKEN_V2)), session)

    assert session.invalidated == [claim_id(KEY, TOKEN_V1)]
    (superseded,) = result.superseded
    assert superseded["previous_id"] == claim_id(KEY, TOKEN_V1)
    assert superseded["new_id"] == claim_id(KEY, TOKEN_V2)
    assert superseded["revision"] == 2


def test_the_window_closes_at_the_new_claims_valid_from():
    """Not `now()`.

    The two instants must be the same or an as-at read between them finds either
    no valid claim or two, and both answers are wrong.
    """
    session = FakeSession({KEY: (claim_id(KEY, TOKEN_V1), 1)})
    plan = _plan(_requirement(TOKEN_V2, valid_from="2026-06-01T00:00:00Z"))
    result = _land(plan, session)
    assert result.superseded[0]["closed_at"] == "2026-06-01T00:00:00Z"


def test_the_new_claim_is_written_before_the_old_one_is_closed():
    """Order, which is the whole reason this is tested through `land`.

    Closing first leaves a window in which the old claim is superseded and the
    new one does not exist, so a read landing there sees no valid requirement at
    all. The worst case in this order is two open windows, which
    `current_claims` resolves deterministically and a re-run repairs.
    """
    session = FakeSession({KEY: (claim_id(KEY, TOKEN_V1), 1)})
    _land(_plan(_requirement(TOKEN_V2)), session)

    assert session.order.index("read") < session.order.index("write")
    assert session.order.index("write") < session.order.index("invalidate")


def test_an_unchanged_re_land_closes_nothing_and_writes_no_new_revision():
    v1 = claim_id(KEY, TOKEN_V1)
    session = FakeSession({KEY: (v1, 3)})
    result = _land(_plan(_requirement(TOKEN_V1)), session)

    assert session.invalidated == []
    assert result.superseded == []
    # The row is still written -- MERGE is how machine facts are re-asserted --
    # but `revision` rides in `on_create`, so an existing node keeps 3 rather
    # than being reset to the plan's hardcoded 1.
    (row,) = [r for r in session.written if r["id"] == v1]
    assert "revision" not in row["machine"]


def test_a_first_landing_closes_nothing():
    session = FakeSession({})
    result = _land(_plan(_requirement(TOKEN_V1)), session)
    assert session.invalidated == []
    assert result.superseded == []
    (row,) = session.written
    assert row["on_create"]["revision"] == 1
    assert row["on_create"]["lifecycle_state"] == "Quarantine"


# ---------------------------------------------------------------------------
# The intake path — the site the defect was actually found at
# ---------------------------------------------------------------------------
#
# `plan_supersession` cannot help if the writer still mints one id per anchor.
# These assert the root cause directly: the same Jira key with different text
# must produce different nodes, and the same text must not.


def _ticket(description: str) -> dict:
    return {
        "uif_version": "1.0",
        "scope": {"primary_id": "PROJ-14", "primary_type": "Story",
                  "source_system": "jira",
                  "uif_generated_at": "2026-08-21T10:00:00Z"},
        "metadata": {"title": "Archive a record", "description": description},
    }


def _requirement_node(document):
    from metis_mcp.model_sources import intake_landing

    plan = intake_landing.plan_intake(document)
    nodes = [n for n in plan.nodes if n.label == "Requirement"]
    return nodes[0] if nodes else None


HIDE = "When a user archives a record, the system shall hide it from search."
DELETE = "When a user archives a record, the system shall delete it permanently."


def test_editing_a_ticket_produces_a_different_requirement_node():
    """The original defect, at its source.

    The id was `req-<sha256(anchor)[:12]}` and nothing else, so both of these
    resolved to one node and the second silently overwrote the first -- keeping
    whatever approval a human had given the wording that no longer existed.
    """
    first = _requirement_node(_ticket(HIDE))
    second = _requirement_node(_ticket(DELETE))
    assert first is not None and second is not None

    assert first.properties["id"] != second.properties["id"], (
        "an edited ticket must land a new claim, not overwrite the approved one")
    assert logical_key_of(first.properties["id"]) == \
        logical_key_of(second.properties["id"]), (
        "both are revisions OF the same ticket, so the logical key must match")


def test_re_reading_an_unedited_ticket_is_a_no_op():
    """TR-6. Content-derived identity means a re-fetch writes nothing new."""
    assert _requirement_node(_ticket(HIDE)).properties["id"] == \
        _requirement_node(_ticket(HIDE)).properties["id"]


def test_the_anchor_is_shared_by_every_revision():
    """`REPRESENTS` from one `JiraItem` is what makes "every version of PROJ-14"
    a traversal -- and is why no `SUPERSEDES` edge was added (D-1)."""
    from metis_mcp.model_sources import intake_landing

    anchors = set()
    for description in (HIDE, DELETE):
        plan = intake_landing.plan_intake(_ticket(description))
        anchor = next(n for n in plan.nodes if n.label == "JiraItem")
        anchors.add(anchor.properties["id"])
        assert any(e.rel_type == "REPRESENTS" and e.to_label == "Requirement"
                   for e in plan.edges), "the anchor must reach its requirement"
    assert len(anchors) == 1, "the artefact is one artefact across revisions"


def test_land_reopens_the_window_on_the_node_it_just_made_current():
    """**The wiring, which two earlier tests failed to cover.**

    They exercised `_reopen` in isolation and both PASSED with the call site
    sabotaged — proving the function worked and not that landing used it, which
    is the same shape as the `expect_prior_approval` hole.

    What it guards: `valid_to` is written ON CREATE only, so a claim whose text
    REVERTS to an earlier wording produces a `claim_id` that already exists with
    its window closed. The MERGE matches that closed node; supersession closes
    the one that WAS current; the claim ends with every revision closed and none
    current, invisible to every validity-respecting read, and the landing reports
    success and a new revision number.
    """
    session = FakeSession({KEY: (claim_id(KEY, TOKEN_V1), 1)})
    _land(_plan(_requirement(TOKEN_V2)), session)

    assert session.invalidated == [claim_id(KEY, TOKEN_V1)], "the old window"
    assert session.reopened == [claim_id(KEY, TOKEN_V2)], (
        "landing closed the previous revision and did not reopen the new one; "
        "a reverted wording therefore leaves the claim with no current revision")


def test_the_close_happens_before_the_reopen():
    """Order matters: reopening first would leave two open windows for an
    instant, and closing without reopening is the bug above. Close, then open."""
    session = FakeSession({KEY: (claim_id(KEY, TOKEN_V1), 1)})
    _land(_plan(_requirement(TOKEN_V2)), session)

    assert "invalidate" in session.order and "reopen" in session.order
    assert session.order.index("invalidate") < session.order.index("reopen")


def test_a_first_seen_claim_reopens_nothing():
    """No supersession, no reopen. This must not become a landing that clears
    `valid_to` on every run — that would undo an invalidation by accident, which
    is exactly what `VALIDITY_FACTS` exists to prevent."""
    session = FakeSession({})
    _land(_plan(_requirement(TOKEN_V1)), session)

    assert session.invalidated == []
    assert session.reopened == []
