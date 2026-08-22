"""
Rendered documents, landed in the graph (application spec §18; D-8, F-12).

**Why the graph and not a file.** F-12 makes the graph the interface to
consumers: they query it, they never re-derive. A specification that exists only
as a `.md` beside the repo has to be re-rendered by everyone who wants it, is a
second copy of facts the graph already holds, and cannot carry an edge to the
behaviour it describes. Two copies of a specification is exactly what a single
point of truth exists to prevent.

So a document is a node. `body_markdown` is text rather than nodes, on
`Transition.inputs`' reasoning -- the reader renders the whole document and
nothing queries a paragraph -- and the structure that *is* worth querying is
carried as edges instead: `DESCRIBES` to the thing documented, `CITES` to every
criterion rendered inside it.

**Re-rendering an unchanged input writes nothing.** Ids are content-derived
(D-8) and `content_hash` deliberately excludes `generated_at`, so regeneration
is a `MERGE` onto the same node with the same values. A timestamp in the hash
would make every run a new document and defeat the idempotence.

Planner and writer are split, the same discipline as `landing` and
`graph_writer`: `plan_*` is pure and fully validated offline, `land` executes an
already-legal plan and reads its counts back from Cypher.
"""
from __future__ import annotations

from datetime import datetime, timezone

from metis_mcp.mbt.model import QUARANTINE
from metis_mcp.model_sources.landing import LandingPlan, PlannedEdge, PlannedNode
from metis_mcp.ontology.validation import validate as validate_node
from metis_mcp.ontology.validation import validate_relationship

SPEC_DOCUMENT = "SpecDocument"
ENTITY_DOCUMENT = "EntityDocument"


def _plan_document(*, label: str, document_id: str, title: str,
                   body_markdown: str, content_hash: str, episode_id: str,
                   describes_label: str, describes_id: str,
                   cites: tuple[str, ...] = (), rendered_at: str = "") -> LandingPlan:
    """One document, its subject, and the criteria it renders."""
    plan = LandingPlan(episode_id=episode_id)
    rendered = rendered_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

    def add_node(node_label: str, props: dict) -> bool:
        outcome = validate_node(node_label, props)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return False
        plan.nodes.append(PlannedNode(label=node_label, properties=props))
        return True

    def add_edge(from_label: str, from_id: str, rel: str,
                 to_label: str, to_id: str) -> None:
        outcome = validate_relationship(from_label, rel, to_label)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        plan.edges.append(PlannedEdge(from_label, from_id, rel, to_label, to_id))

    ok = add_node(label, {
        "id": document_id,
        "source_episode_id": episode_id,
        "name": title,
        "body_markdown": body_markdown,
        "content_hash": content_hash,
        "rendered_at": rendered,
        # S-4: a generated document is authored, never approved. Nothing here
        # decides that a specification is agreed -- G1 does, with a person.
        "lifecycle_state": QUARANTINE,
    })
    if not ok:
        return plan

    # The subject. Planned even when the target may be absent: `land` reports a
    # miss as `unmatched` rather than failing, which is the honest outcome --
    # a document whose subject has not landed is a real state, and silently
    # dropping the edge would make it invisible.
    add_edge(label, document_id, "DESCRIBES", describes_label, describes_id)

    for criterion_id in dict.fromkeys(cites):
        add_edge(label, document_id, "CITES", "AcceptanceCriterion", criterion_id)

    return plan


def plan_entity_document(spec, episode_id: str,
                         rendered_at: str = "") -> LandingPlan:
    """One `EntityDocument` for one `BusinessEntity`."""
    from metis_mcp.specgen.entity import render_markdown

    return _plan_document(
        label=ENTITY_DOCUMENT,
        document_id=spec.document_id,
        title=f"{spec.name} — business entity",
        body_markdown=render_markdown(spec),
        content_hash=spec.content_hash,
        episode_id=episode_id,
        describes_label="BusinessEntity",
        describes_id=spec.entity_id,
        cites=tuple(r.criterion_id for r in spec.rules),
        rendered_at=rendered_at,
    )


def plan_spec_document(spec, component_id: str, episode_id: str,
                       body_markdown: str, content_hash: str,
                       rendered_at: str = "") -> LandingPlan:
    """One `SpecDocument` for one `Component`.

    The journey specification is rendered by `specgen.specification`; this only
    lands what it produced, so the two stay one renderer and one writer rather
    than two half-renderers.
    """
    return _plan_document(
        label=SPEC_DOCUMENT,
        document_id=f"specdoc-{spec.model_id}",
        title=f"{spec.journey or spec.model_id} — behaviour specification",
        body_markdown=body_markdown,
        content_hash=content_hash,
        episode_id=episode_id,
        describes_label="Component",
        describes_id=component_id,
        # `rule.acceptance_criteria`, NOT `rule.criterion_id`. The latter is a
        # synthetic heading id derived from the transition's natural key so the
        # document round-trips through `spec_kit`; it names no node. Citing it
        # planned seventeen edges against ids nothing carries, and `land`
        # reported all seventeen as unmatched -- which is the honest outcome of
        # a wrong plan, not a missing one.
        #
        # `acceptance_criteria` is the real thing: the AC ids that VALIDATE the
        # transition this rule renders.
        cites=tuple(cid for r in spec.rules for cid in r.acceptance_criteria),
        rendered_at=rendered_at,
    )
