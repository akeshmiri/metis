"""
A person-authored claim as a landing plan (`metis requirement`).

**The narrowest source there is**, and deliberately so. Every other source reads
a document somebody else produced — a tracker item, a knowledge file, a Spec Kit
spec, a code property graph — and its job is mostly normalisation. This one
carries a single sentence a person just typed, so there is nothing to normalise
and everything to be careful about: it is the only path where the author, the
text and the write are the same act.

**Pure, like every other `plan_*`.** It decides what would be written and writes
nothing, so what this source does is assertable with no database — the split
`plan_landing`/`land` uses everywhere.

**The properties match `knowledge.py`'s Requirement exactly**, field for field.
Two sources producing the same label with different property sets is how a query
starts returning half an estate: `search_text` missing here would make an
authored requirement invisible to `search_knowledge`, and `valid_from` missing
would make it invisible to every read that requires a validity window.
"""
from __future__ import annotations

from datetime import datetime, timezone

from metis_mcp.model_sources.landing import LandingPlan, PlannedNode
from metis_mcp.retrieval import search_text_for

QUARANTINE = "Quarantine"


def episode_id_for(authored) -> str:
    """Content-derived (D-8), so re-landing the same claim is a no-op (TR-6)."""
    import hashlib

    digest = hashlib.sha256(authored.node_id.encode()).hexdigest()[:16]
    return f"ep-authored-{digest}"


def plan_claim(authored, *, author: str = "", project: str = "",
               recorded: str = "") -> LandingPlan:
    """One authored claim, as the nodes it would become. **Pure.**

    `authored.label` is `Requirement` or `Finding` and this does not second-guess
    it: `requirements.compose` already ran the EARS check, and deciding it twice
    in two places is how the two answers start to differ.
    """
    when = recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")
    episode = episode_id_for(authored)
    plan = LandingPlan(episode_id=episode, project=project)

    plan.nodes.append(PlannedNode("Episode", {
        "id": episode,
        "name": f"authored: {authored.logical_key}",
        "t_recorded": when,
        "source_connector": "authored",
        # Who typed it. Not an approval and not a review — N-10 says this is
        # precisely the identity that may NOT approve what it proposed, and the
        # audit needs to know which one that is.
        "job_id": author or "manual",
    }))

    properties = {
        "id": authored.node_id,
        "source_episode_id": episode,
        # The author's stable key, not the digested id: a reviewer reading
        # `REQ-3@580cd413` in a queue learns nothing the id does not say twice.
        "name": authored.logical_key,
        "text": authored.text,
        "search_text": search_text_for(authored.logical_key, authored.text),
        "revision": 1,
        # S-4. No source writes Approved, and an authoring verb is the last
        # place that rule could be allowed to bend.
        "lifecycle_state": QUARANTINE,
        # Bi-temporal validity. `valid_to` is empty while the claim still holds;
        # `landing.invalidate` closes it when a revision supersedes this one.
        "valid_from": when,
        "valid_to": "",
    }
    if authored.label == "Requirement":
        properties["ears_pattern"] = authored.ears_pattern or ""
        properties["statement"] = authored.text
    else:
        # A Finding says what a person should do about it. Pointing at
        # knowledge-capture is the same next step intake gives for free prose,
        # so both routes into the graph end in the same place.
        properties["detail"] = (
            "authored text that is not EARS-conformant. Rewrite it as "
            "`When <trigger>, the system shall <response>` and re-run "
            "`metis requirement`, or formalise it with knowledge-capture (S-13)")
        properties["severity"] = "advisory"

    plan.nodes.append(PlannedNode(authored.label, properties))
    return plan
