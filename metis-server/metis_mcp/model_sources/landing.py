"""
Land a source's output in the graph (application spec S-4, D-8b, §16.1).

Closes the provenance gap: until now nothing wrote an `Episode` through a real
source path, so `source_episode_id` pointed at a hand-seeded node. Every element
landed here carries the id of the Episode that justifies it (spec P1).

Pure planner, thin writer -- and under Community edition that split is not a
stylistic preference. The application gate is the *sole* guarantee that required
properties exist (D-8a/D-8b), so a plan is validated in full before any statement
reaches the database.

Everything lands at **Quarantine**. Authoring is not approving (E-11): a model
produced by any source, including a human sitting at a keyboard, is a candidate
until someone else decides otherwise (N-10).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from metis_mcp.mbt.model import QUARANTINE
from metis_mcp.model_sources.base import SourceResult
from metis_mcp.ontology import validate, validate_relationship


@dataclass(frozen=True)
class PlannedNode:
    label: str
    properties: dict


@dataclass(frozen=True)
class PlannedEdge:
    from_label: str
    from_id: str
    rel_type: str
    to_label: str
    to_id: str


@dataclass
class LandingPlan:
    episode_id: str
    nodes: list[PlannedNode] = field(default_factory=list)
    edges: list[PlannedEdge] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def is_legal(self) -> bool:
        return not self.errors

    def by_label(self, label: str) -> list[PlannedNode]:
        return [n for n in self.nodes if n.label == label]


def episode_id_for(result: SourceResult, content_key: str) -> str:
    """Content-derived (spec D-8): re-landing identical output is a no-op."""
    basis = "|".join((result.source_connector, result.model.id, content_key))
    return "ep-" + hashlib.sha256(basis.encode()).hexdigest()[:16]


def _content_key(result: SourceResult) -> str:
    model = result.model
    parts = [model.id]
    for sid in model.state_ids():
        s = model.states[sid]
        parts.append(f"S|{s.id}|{s.name}|{s.surface}|{s.is_initial}")
    for tid in model.transition_ids():
        t = model.transitions[tid]
        parts.append(f"T|{t.id}|{t.source}|{t.trigger}|{t.target}|{t.guard}|"
                     f"{t.implementation_status}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def plan_landing(result: SourceResult, journey: str,
                 job_id: str = "manual", t_recorded: str | None = None) -> LandingPlan:
    """Build a fully-validated landing plan. No session, no writes."""
    content_key = _content_key(result)
    episode_id = episode_id_for(result, content_key)
    recorded = t_recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")

    plan = LandingPlan(episode_id=episode_id, skipped=list(result.skipped))

    def add_node(label: str, props: dict) -> None:
        outcome = validate(label, props)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        plan.nodes.append(PlannedNode(label=label, properties=props))

    def add_edge(from_label: str, from_id: str, rel: str, to_label: str, to_id: str) -> None:
        outcome = validate_relationship(from_label, rel, to_label)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        plan.edges.append(PlannedEdge(from_label, from_id, rel, to_label, to_id))

    # The Episode is exempt from source_episode_id -- it is the provenance record
    # and cannot point at one (spec D-8, BASELINE_EXEMPT).
    add_node("Episode", {
        "id": episode_id,
        "name": f"{result.source_connector}: {result.model.id}",
        "t_recorded": recorded,
        "source_connector": result.source_connector,
        "job_id": job_id,
        "content_key": content_key,
        "evidence": ", ".join(f"{k}={v}" for k, v in sorted(result.evidence.items())),
        # Spec N-10. Every element landed by this Episode was proposed by this
        # identity, so the separation-of-duties check has something to compare a
        # reviewer against. Carried as its own property, not parsed back out of
        # `evidence`: a gate that depends on splitting a joined string is a gate
        # that stops working the first time a value contains a comma.
        "proposed_by": result.proposed_by or "unknown",
    })

    model = result.model
    surface = model.id.rpartition("-")[2] or "api"

    def graph_state_id(state_id: str) -> str:
        """Namespace a state id by its model (spec I-2, D-8).

        A state's natural key is `(model, surface, observable_signature)` --
        `identity/keys.py` has said so all along, but this writer used the bare
        id. With one model landed that is invisible; with seven it is severe.
        Every synthesised API model calls its initial state `Ready`, so all seven
        MERGE-d onto ONE node: 145 transitions hung off it, and landing a UI model
        whose `Ready` is not initial silently flipped `is_initial` to false for
        every API model at once. Caught because validation then reported "no
        initial state" for all seven.
        """
        return f"{model.id}::{state_id}"

    for sid in model.state_ids():
        state = model.states[sid]
        add_node("State", {
            "id": graph_state_id(sid), "source_episode_id": episode_id, "name": state.name,
            "surface": state.surface, "is_initial": state.is_initial,
            "lifecycle_state": QUARANTINE, "functional_areas": [journey],
        })

    for tid in model.transition_ids():
        transition = model.transitions[tid]
        add_node("Transition", {
            "id": f"{model.id}::{tid}", "source_episode_id": episode_id, "name": tid,
            "trigger": transition.trigger,
            "guard_expression": transition.guard,
            "implementation_status": transition.implementation_status,
            "surface": surface,
            "extraction_method": result.extraction_method,
            "lifecycle_state": QUARANTINE, "functional_areas": [journey],
        })
        add_edge("State", graph_state_id(transition.source), "WHEN", "Transition",
                 f"{model.id}::{tid}")
        add_edge("Transition", f"{model.id}::{tid}", "THEN", "State",
                 graph_state_id(transition.target))

    return plan


@dataclass
class LandingResult:
    episode_id: str = ""
    nodes_written: int = 0
    edges_written: int = 0
    refused: str | None = None

    @property
    def ok(self) -> bool:
        return self.refused is None


def land(session, plan: LandingPlan) -> LandingResult:
    """Execute an already-legal plan. Refuses an illegal one outright."""
    if not plan.is_legal:
        return LandingResult(refused=f"{len(plan.errors)} validation error(s): "
                                     f"{plan.errors[0]}")

    for node in plan.nodes:
        props = {k: v for k, v in node.properties.items() if v is not None}
        session.run(f"MERGE (n:{node.label} {{id: $id}}) SET n += $props",
                    id=props["id"], props=props)

    for edge in plan.edges:
        session.run(
            f"MATCH (a:{edge.from_label} {{id: $a}}), (b:{edge.to_label} {{id: $b}}) "
            f"MERGE (a)-[:{edge.rel_type}]->(b)",
            a=edge.from_id, b=edge.to_id,
        )

    return LandingResult(episode_id=plan.episode_id,
                         nodes_written=len(plan.nodes), edges_written=len(plan.edges))
