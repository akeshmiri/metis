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
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from metis_mcp.mbt.guard_language import describe_guard
from metis_mcp.mbt.model import QUARANTINE
from metis_mcp.mbt.naming import transition_display_name
from metis_mcp.model_sources.base import SourceResult
from metis_mcp.ontology import validate, validate_relationship
from metis_mcp.ontology.labels import NEED_REVIEW, NEEDS_REVIEW_STATES


# **Human facts. A write path may never assert these.**
#
# Machine facts are re-derived on every run — guards, triggers, anchors, inputs,
# outcomes, evidence — so a writer asserts them freely. These four are not
# reproducible by any amount of re-extraction: a reviewer decided them.
#
# They were in the unconditional `SET n += row`, which is why every re-ingest
# reset the whole estate to Quarantine and re-approving 206 transitions was the
# standing cost of keeping the graph current. They now go through
# `ON CREATE SET`, so a NEW node still starts at Quarantine (S-4) and an existing
# one keeps what a human gave it.
#
# `ON CREATE SET` alone is not sufficient and is not the whole mechanism: it
# would also keep an approval whose behaviour has since changed, which is the
# dangerous direction. `identity.carry_human_facts` supplies the revocation
# (I-17, I-18) before the plan is ever built.
HUMAN_FACTS = ("lifecycle_state", "name", "name_tier", "provenance")


# Which edge each kind of evidence gets. One place, so a transition cannot point
# at an `Endpoint` with one relationship type here and another somewhere else.
EVIDENCE_RELATIONSHIPS = {
    "Endpoint": "DERIVED_FROM",
    "DeclaredOutcome": "DERIVED_FROM",
    "ExceptionMapping": "DERIVED_FROM",
    "Parameter": "EXERCISES",
    "Field": "REQUIRES",
    "Class": "EXPECTS",
    "Check": "CONSTRAINED_BY",
}


# A classified transition is written as `:ApiCall` or `:UiAction` **instead of**
# `:Transition` (see `ontology.labels`), so anything planning an edge INTO a
# transition has to name the label the node actually carries.
#
# Shared rather than inlined because getting it wrong is silent: the ontology
# check walks the specialisation chain and passes, and then the write emits
# `MATCH (b:Transition {id: ...})` against a node labelled `:ApiCall` and merges
# nothing. `land` reports that as `unmatched`; it does not fail.
TRANSITION_LABELS = {"api": "ApiCall", "ui": "UiAction"}


def transition_label_for(surface: str) -> str:
    return TRANSITION_LABELS.get(surface, "Transition")


# The same rule one level up. `RestServer` and `WebServer` specialise
# `Component`, and a specialisation is written INSTEAD of its parent -- so
# without this they were declared, catalogued, and written by nothing, while
# `graph_loader` carried a comment asserting they were. A comment the code does
# not back is worse than no comment.
COMPONENT_LABELS = {"api": "RestServer", "ui": "WebServer"}


def component_label_for(surface: str) -> str:
    """`RestServer` / `WebServer`, or the generic parent when the surface is
    unknown -- which leaves `:Component` meaning "unclassified" and therefore
    findable, exactly as `:Transition` does."""
    return COMPONENT_LABELS.get(surface, "Component")


def namespaced_id(model_id: str, element_id: str) -> str:
    """`admin-api::ac::LoggedOut::Submit::Failed1` — the id a node is written with.

    Shared for the same reason `transition_label_for` is: an edge planned against
    the bare id passes every check and then merges nothing, because no node
    carries that id. `identity.keys.bare_id` is the inverse.
    """
    return f"{model_id}::{element_id}"


def graph_transition_id(model, transition_id: str) -> str:
    """The id a transition is WRITTEN with — its natural key, not its source's id.

    **This is what lets two intakes describe one behaviour once** (I-2, R12).
    A transition's id comes from whatever recovered it: the code intake mints a
    Java signature, the OpenAPI intake mints an operationId. Measured on the demo
    corpus, `POST /record` reaches the graph as

        code     com.example.records.RecordController.create:…ResponseEntity(…)::POST
        OpenAPI  createRecord::POST->PostRecord201

    — two nodes for one behaviour, and a model that then claims twice the
    behaviour the service has, with no edge between the halves and nothing
    reporting it.

    `identity.keys.transition_key` has defined the natural key all along —
    `(model, source state, trigger, target state)` — and no writer used it.
    Landing does now, so the same behaviour recovered twice MERGEs onto one node
    and a deviation is what is left over rather than what has to be hunted for.

    Every writer of a transition id must go through here. One that mints its own
    plans an edge against a node that does not exist, which `land` reports as
    unmatched rather than failing.
    """
    from metis_mcp.identity.keys import short, transition_key

    transition = model.transitions.get(transition_id)
    if transition is None:
        return ensure_namespaced(model.id, transition_id)
    return f"{model.id}::{short(transition_key(model.id, transition, model))}"


def ensure_namespaced(model_id: str, element_id: str) -> str:
    """`namespaced_id`, but idempotent — safe on an id that already carries it.

    Both forms are real and reach the same writers. A model read from a **file**
    has bare ids (`Ready`); the same model read from the **graph** comes back
    already namespaced (`archive-api::Ready`), because that is what landing
    wrote. `plan_persist` takes either, so applying `namespaced_id`
    unconditionally produced `archive-api::archive-api::Ready` and every
    edge matched nothing.

    The test is a prefix check, **not** `"::" in element_id`: a Web element id
    is `ui::ApiSpecDetailPage::/spec/::Ok200`, which contains `::` while being
    entirely un-namespaced. That containment test is what left
    `records-spec-ui`'s findings unattached.
    """
    prefix = f"{model_id}::"
    return element_id if element_id.startswith(prefix) else prefix + element_id


@dataclass(frozen=True)
class PlannedNode:
    label: str
    properties: dict
    # Kept for nodes that genuinely carry more than one label. Transitions do
    # not: a classified transition is written as `:ApiCall` or `:UiAction`
    # **instead of** `:Transition`, which leaves the generic label meaning
    # "unclassified" and therefore findable.
    also: tuple = ()


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


def _wording(transition):
    """The guard in business language, from the resource its trigger names."""
    from code_analysis.unfolding import resource_noun, resource_of

    _, _, path = (getattr(transition, "trigger", "") or "").partition(" ")
    return describe_guard(getattr(transition, "guard", ""),
                          resource_noun(resource_of(path)))


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

    def add_node(label: str, props: dict, also: tuple = ()) -> None:
        outcome = validate(label, props)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        # Each additional label is validated too: a specialisation narrows its
        # parent (an `ApiCall` may not carry `surface: ui`), and writing one
        # without checking would put a node in the graph that its own label
        # forbids.
        for extra in also:
            extra_outcome = validate(extra, props)
            if not extra_outcome.valid:
                plan.errors.extend(extra_outcome.errors)
                return
        plan.nodes.append(PlannedNode(label=label, properties=props, also=tuple(also)))

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
        return ensure_namespaced(model.id, state_id)

    # Web surface: the pages a state belongs to become their own nodes, so
    # "which pages does this component have, and what condition is each in" is a
    # query rather than a substring search inside a transition id. A Page is a
    # grouping node and never a link in the walk, so path generation is untouched.
    pages: dict[str, str] = {}
    for sid in model.state_ids():
        page = getattr(model.states[sid], "page", "")
        if page and page not in pages:
            page_id = f"{model.id}::page::{page}"
            pages[page] = page_id
            add_node("Page", {
                "id": page_id, "source_episode_id": episode_id, "name": page,
                "component": model.id, "surface": "ui",
            })

    for sid in model.state_ids():
        state = model.states[sid]
        add_node("State", {
            "id": graph_state_id(sid), "source_episode_id": episode_id, "name": state.name,
            "surface": state.surface, "is_initial": state.is_initial,
            "lifecycle_state": QUARANTINE, "functional_areas": [journey],
            "page": getattr(state, "page", ""),
            "condition": getattr(state, "condition", ""),
            "name_tier": getattr(state, "name_tier", ""),
        })
        page = getattr(state, "page", "")
        if page:
            add_edge("Page", pages[page], "SHOWS", "State", graph_state_id(sid))

    # The specific label where the surface is known, the generic one where it is
    # not. `MATCH (t:Transition)` is then a worklist rather than a synonym for
    # every transition in the graph.
    transition_label = transition_label_for(surface)

    for tid in model.transition_ids():
        transition = model.transitions[tid]
        add_node(transition_label, {
            "id": graph_transition_id(model, tid), "source_episode_id": episode_id,
            # D-8: `name` is display data, not identity. It used to be the id --
            # a Java signature with a return type in it -- so every review screen
            # and every report showed a reviewer the implementation instead of
            # the behaviour they were being asked to decide about.
            "name": transition_display_name(transition, model.states),
            "trigger": transition.trigger,
            "guard_expression": transition.guard,
            "implementation_status": transition.implementation_status,
            "surface": surface,
            "extraction_method": result.extraction_method,
            "lifecycle_state": QUARANTINE, "functional_areas": [journey],
            "guard_anchor": transition.guard_anchor,
            "source_state_unresolved": transition.source_state_unresolved,
            "outcome_status": transition.outcome_status,
            # See labels.py: structure cannot be a Neo4j property, so the detail
            # is JSON and the two facts worth filtering on are their own columns.
            "inputs_json": json.dumps(list(transition.inputs), sort_keys=True),
            "security_json": json.dumps(list(transition.security), sort_keys=True),
            "input_count": len(transition.inputs),
            "requires_body": any(
                (p or {}).get("location") == "body" for p in transition.inputs),
            "outcome_source": getattr(transition, "outcome_source", "") or "constructed",
            "guard_claim": getattr(transition, "guard_claim", ""),
            # GD-3's variants. A list of strings IS a legal Neo4j property, so
            # unlike `inputs` these need no JSON envelope -- and a reviewer
            # reading the rejection sees the constraints it is about.
            "data_requirements": list(getattr(transition, "data_requirements", ()) or ()),
            # The expected response. Empty `response_body` means NO body (a 204,
            # or a `ResponseEntity<Void>`), which is a fact a test can assert --
            # not a recovery failure.
            "response_body": getattr(transition, "response_body", ""),
            "media_types": list(getattr(transition, "media_types", ()) or ()),
            # X-8. The guard in business language, and which tier said it --
            # `verbatim` means nothing has translated it yet, which is the
            # worklist a reviewer or an acceptance criterion works through.
            # Computed here where a source did not supply it. Synthesis words
            # its own guards; a hand-authored model landed from a file does not,
            # and 17 login-example transitions therefore carried no tier at all
            # -- which makes "show me everything still in implementation
            # language" quietly answer for part of the graph.
            "guard_wording": (getattr(transition, "guard_wording", "")
                              or _wording(transition).text),
            "guard_tier": (getattr(transition, "guard_tier", "")
                           or _wording(transition).tier),
            "name_tier": getattr(transition, "name_tier", ""),
        })
        add_edge("State", graph_state_id(transition.source), "WHEN",
                 transition_label, graph_transition_id(model, tid))
        add_edge(transition_label, graph_transition_id(model, tid), "THEN", "State",
                 graph_state_id(transition.target))

        # D-14: provenance is an edge. Each pair is `(label, evidence node id)`
        # computed by synthesis while the raw facts were still in hand; the
        # relationship type follows from the label, so this cannot drift from
        # the catalogue without `validate_relationship` refusing it.
        for label, node_id in getattr(transition, "evidence", ()) or ():
            rel = EVIDENCE_RELATIONSHIPS.get(label)
            if rel:
                add_edge(transition_label, graph_transition_id(model, tid), rel,
                         label, node_id)

    return plan


@dataclass
class LandingResult:
    episode_id: str = ""
    nodes_written: int = 0
    edges_written: int = 0
    refused: str | None = None
    # Edges whose plan was legal but whose endpoints were not both present when
    # the statement ran. See `land` -- this is the difference between what was
    # planned and what the database actually holds.
    unmatched: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.refused is None


def _with_marker(node: PlannedNode, props: dict) -> tuple:
    """`node.also`, plus `:NeedReview` when this node still owes a decision.

    **Applied here rather than in each planner, and that is the whole point.**
    Eight planners produce nodes -- behaviour, documentation, glossary, intent,
    structure, intake, spec documents, features -- and every one of them lands
    at Quarantine (S-4). Marking them one by one would mean the ninth planner
    somebody writes is unmarked, and nothing would notice: the node would look
    settled while being unreviewed, which is the safest-looking way to get the
    dangerous answer.

    Driven off `lifecycle_state`, which stays authoritative. A node with no
    lifecycle at all -- an `Episode`, an `Endpoint` -- is a fact rather than a
    candidate, and facts are not reviewed.
    """
    state = props.get("lifecycle_state")
    if state in NEEDS_REVIEW_STATES:
        return tuple(dict.fromkeys((*node.also, NEED_REVIEW)))
    return node.also


def land(session, plan: LandingPlan) -> LandingResult:
    """Execute an already-legal plan. Refuses an illegal one outright.

    **One statement per group, not per row.** This used to run a `session.run`
    for every node and every edge, which is invisible at ~250 nodes and is not at
    the ~23,000 writes an evidence layer produces. Rows are grouped by label and
    by `(from, rel, to)` triple and written with `UNWIND`; the MERGE semantics
    and the id-keying are unchanged, so a plan lands identically either way.

    **Counts come back from the database, never from `len(rows)`.** This project
    has already shipped that bug twice -- `persist_invokes` reported "91 INVOKES"
    into a graph holding zero, because an edge statement opens with two `MATCH`es
    and merges nothing when either id is absent, while the counter incremented
    regardless. `RETURN count(*)` is what the database did; the difference is
    reported as `unmatched` rather than rounded away.
    """
    if not plan.is_legal:
        return LandingResult(refused=f"{len(plan.errors)} validation error(s): "
                                     f"{plan.errors[0]}")

    by_label: dict[tuple, list[dict]] = {}
    for node in plan.nodes:
        props = {k: v for k, v in node.properties.items() if v is not None}
        by_label.setdefault((node.label, _with_marker(node, props)), []).append(props)

    nodes_written = 0
    for (label, also), rows in by_label.items():
        # **After the ON CREATE clause, not before it.** `ON CREATE SET` has to
        # follow `MERGE` immediately, so appending the label here produced
        # `MERGE (...) SET n:X ON CREATE SET ...` — a syntax error. The `also`
        # path had never been exercised (no node carried a second label until
        # `:NeedReview`), so the bug shipped latent and surfaced the first time
        # something used it.
        extra = "".join(f" SET n:{extra_label}" for extra_label in also)
        # Split in Python, not in Cypher. The map-manipulation this needs in
        # Cypher is an APOC function, and this deployment is Community with no
        # APOC -- but the plainer reason is that two named maps read as what they
        # are, where a `[k IN keys(row) WHERE ...]` comprehension does not.
        split = [{"id": row["id"],
                  "human": {k: v for k, v in row.items() if k in HUMAN_FACTS},
                  "machine": {k: v for k, v in row.items() if k not in HUMAN_FACTS}}
                 for row in rows]
        result = session.run(
            f"UNWIND $rows AS row "
            f"MERGE (n:{label} {{id: row.id}}) "
            f"ON CREATE SET n += row.human "
            f"SET n += row.machine{extra} "
            f"RETURN count(n) AS written", rows=split)
        nodes_written += _count(result)

    by_edge: dict[tuple, list[dict]] = {}
    for edge in plan.edges:
        key = (edge.from_label, edge.rel_type, edge.to_label)
        by_edge.setdefault(key, []).append({"a": edge.from_id, "b": edge.to_id})

    edges_written = 0
    unmatched: list[tuple[str, str, str]] = []
    for (from_label, rel_type, to_label), rows in by_edge.items():
        result = session.run(
            f"UNWIND $rows AS row "
            f"MATCH (a:{from_label} {{id: row.a}}), (b:{to_label} {{id: row.b}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"RETURN count(r) AS written", rows=rows)
        written = _count(result)
        edges_written += written
        if written < len(rows):
            unmatched.append(
                (f"{from_label}-[:{rel_type}]->{to_label}",
                 f"{len(rows) - written} of {len(rows)}",
                 "one or both endpoints were absent when this ran — an evidence "
                 "layer must land before the model that derives from it"))

    return LandingResult(episode_id=plan.episode_id,
                         nodes_written=nodes_written, edges_written=edges_written,
                         unmatched=unmatched)


def _count(result) -> int:
    """The `written` column, tolerating a driver stub that returns nothing.

    A real driver always returns a `Result`; `None` only comes from a recording
    fake in a test, and crashing on one would make the writer untestable without
    a container. Zero is the honest answer there — the stub did not claim to
    write anything.
    """
    if result is None:
        return 0
    for row in result:
        return int(row["written"])
    return 0
