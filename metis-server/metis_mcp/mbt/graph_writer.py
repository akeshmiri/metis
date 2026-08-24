"""
Persist generation results to the graph (application spec §8.4, §16.1 jobs 2 & 3).

Split into a **pure planner** and a **thin writer**, the same discipline as
requirement_landing.py and graph_loader.py:

    plan_persist(...)          pure; every node and edge validated offline
    persist(session, plan)     executes an already-legal plan

Why that split matters here specifically: under Community edition the application
gate is the *sole* guarantee that required properties exist (spec D-8a/D-8b).
Validating the whole plan before any write means an illegal node cannot reach the
database at all, rather than being caught by a constraint that does not exist.

What this makes answerable, which nothing else did (spec §16.2):

    which transitions does this test case cover?
    which transitions have no covering test?
    what changed between model version 2 and 3?

`Scenario -[:COVERS {sequence, is_validated}]-> Transition` is what carries it:
`is_validated` distinguishes the single assertion from its setup (spec P-5a), so
coverage credit can be computed in Cypher without re-deriving it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from metis_mcp.mbt.graph_session import count_written
from metis_mcp.model_sources.landing import (
    component_label_for,
    ensure_namespaced,
    transition_label_for,
)
from metis_mcp.mbt.model import Model
from metis_mcp.mbt.path_generation import GenerationResult
from metis_mcp.ontology import label_expression, validate, validate_relationship
from metis_mcp.rendering.test_case import TestCase

GENERATOR_VERSION = "mbt/1"


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
    properties: dict = field(default_factory=dict)


@dataclass
class PersistPlan:
    nodes: list[PlannedNode] = field(default_factory=list)
    edges: list[PlannedEdge] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_legal(self) -> bool:
        return not self.errors

    def by_label(self, label: str) -> list[PlannedNode]:
        return [n for n in self.nodes if n.label == label]


def _hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def component_id(model_id: str, source_fingerprint: str) -> str:
    """Content-derived (spec D-8): re-persisting an unchanged model is a no-op.

    Keyed on `(model, commit)` rather than on a structural fingerprint. A
    fingerprint sounds stronger and is not: it is computed over element ids, and
    landing namespaces those by model, so the SAME model fingerprinted from its
    source file and from the graph produced two different hashes -- and therefore
    two Component nodes for one extraction. `(model, commit)` is the same fact
    from either side, which is what a shared identity has to be.
    """
    return f"cmp-{_hash(model_id, source_fingerprint)}"


def path_id(model_version: str, validated: str, setup: tuple[str, ...]) -> str:
    return f"tp-{_hash(model_version, validated, *setup)}"


def plan_persist(model: Model, result: GenerationResult, cases: list[TestCase],
                 source_fingerprint: str, episode_id: str,
                 run_id: str, version: int = 1,
                 commit_sha: str | None = None) -> PersistPlan:
    """Build a fully-validated plan. No session, no writes.

    Every node is checked against its label contract and every edge against the
    relationship catalogue, so `is_legal` is a complete answer before anything
    touches the database.
    """
    plan = PersistPlan()
    mv_id = component_id(model.id, commit_sha or source_fingerprint)
    journey, _, surface = model.id.rpartition("-")

    def add_node(label: str, props: dict) -> None:
        outcome = validate(label, props)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        plan.nodes.append(PlannedNode(label=label, properties=props))

    def add_edge(from_label: str, from_id: str, rel: str, to_label: str,
                 to_id: str, props: dict | None = None) -> None:
        outcome = validate_relationship(from_label, rel, to_label)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        plan.edges.append(PlannedEdge(from_label, from_id, rel, to_label, to_id, props or {}))

    # `Run` was staged out: `plan_persist` and `finding_writer` wrote it and no
    # query ever matched it, so it had a writer and no reader (D-1). F-3's
    # reproducibility half rides on `Component` (version, commit) and on
    # `.metis/runs/*.json` (scope, criterion), which is what `workflow status`
    # actually reads. §8.7 records the trigger that would bring it back.

    # The specialisation where the surface is known (`RestServer` / `WebServer`),
    # the generic parent where it is not.
    component_label = component_label_for(surface or "api")
    add_node(component_label, {
        "id": mv_id, "source_episode_id": episode_id,
        "name": f"{model.id} v{version}",
        # The stable half of the identity. The node itself is one component AT
        # one commit (D-6), so without this you cannot ask for every version of
        # a component — the estate would read as N components today and 2N after
        # the next commit.
        "component": model.id,
        "journey": journey or model.id, "surface": surface or "api",
        "version": version, "commit_sha": commit_sha,
        "source_fingerprint": source_fingerprint,
    })

    # The pages this component presents (Web surface). Written here rather than at
    # landing because the Component node is created here -- a `HAS_PAGE` edge
    # declared in the catalogue and written by nothing would be exactly the
    # dangling reference D-1 exists to prevent.
    for sid in model.state_ids():
        page = getattr(model.states[sid], "page", "")
        if page:
            add_edge(component_label, mv_id, "HAS_PAGE", "Page", f"{model.id}::page::{page}")

    # Spec D-6: elements are shared across versions where unchanged, so a version
    # references them rather than duplicating them.
    #
    # **Two things have to match what `landing` actually wrote, and neither used
    # to.** Both fail silently: the plan is legal either way, because
    # `is_allowed` walks the specialisation chain and an id is just a string.
    #
    #   the LABEL  a classified transition carries `:ApiCall` or `:UiAction`
    #              INSTEAD of `:Transition`, so an edge planned against the
    #              parent matches no node at all.
    #   the ID     landing namespaces every element as `{model_id}::{id}`, so a
    #              bare `tid` matches nothing either.
    #
    # Found by re-landing the real Example estate: every CONTAINS and COVERS edge
    # for all thirteen models came back `unmatched`, which is only visible
    # because `persist` now reads its counts from the database.
    transition_label = transition_label_for(surface or "api")
    for sid in model.state_ids():
        add_edge(component_label, mv_id, "CONTAINS", "State",
                 ensure_namespaced(model.id, sid))
    for tid in model.transition_ids():
        add_edge(component_label, mv_id, "CONTAINS", transition_label,
                 ensure_namespaced(model.id, tid))

    cases_by_target = {c.target_key: c for c in cases}

    for path in result.paths:
        pid = path_id(mv_id, path.validated_transition_id, path.setup_transition_ids)
        add_node("Scenario", {
            "id": pid, "source_episode_id": episode_id,
            "name": f"{path.target_key}", "criterion": path.criterion,
            "generator_version": GENERATOR_VERSION,
            "setup_length": path.setup_length,
            "target_key": path.target_key,
        })
        add_edge("Scenario", pid, "GENERATED_FROM", component_label, mv_id)

        # Setup steps carry sequence 1..n and is_validated false; the single
        # assertion carries sequence 0 and is_validated true (spec P-5, P-5a).
        for index, tid in enumerate(path.setup_transition_ids, start=1):
            add_edge("Scenario", pid, "COVERS", transition_label,
                     ensure_namespaced(model.id, tid),
                     {"sequence": index, "is_validated": False})
        add_edge("Scenario", pid, "COVERS", transition_label,
                 ensure_namespaced(model.id, path.validated_transition_id),
                 {"sequence": 0, "is_validated": True})

        case = cases_by_target.get(path.target_key)
        if case is not None:
            # The steps a person executes, in order: preconditions first, then
            # the single asserting step (T-1a). Each keeps the transition it
            # came from, so a case still traces to the model element by element
            # rather than only as a whole.
            steps = [
                {"n": i, "transition_id": s.transition_id,
                 "description": s.description, "requires": s.guard_verbatim,
                 "expected_result": s.expected_result,
                 "is_assertion": s.is_assertion}
                for i, s in enumerate(case.precondition_steps, start=1)
            ]
            steps.append({
                "n": 0, "transition_id": case.act_step.transition_id,
                "description": case.act_step.description,
                "requires": case.act_step.guard_verbatim,
                "expected_result": case.act_step.expected_result,
                "is_assertion": True,
            })
            add_node("TestCase", {
                "id": case.id, "source_episode_id": episode_id, "name": case.name,
                "content_hash": _hash(case.name, case.objective,
                                      case.act_step.description,
                                      case.act_step.expected_result),
                "objective": case.objective, "criterion": case.criterion,
                "steps_json": json.dumps(steps, sort_keys=True),
                # Lifted out of the JSON because they are what a reader filters
                # on: what the case claims, and whether T-1a's one-assertion
                # rule holds without parsing anything.
                "expected_result": case.act_step.expected_result,
                "step_count": len(steps),
                "precondition_count": len(case.precondition_steps),
                "data_requirements_json": json.dumps(
                    [{"condition": d.condition, "steps": list(d.steps),
                      "kind": d.kind} for d in case.data_requirements],
                    sort_keys=True),
            })
            add_edge("Scenario", pid, "PRODUCES", "TestCase", case.id)

    return plan


@dataclass
class PersistResult:
    nodes_written: int = 0
    edges_written: int = 0
    refused: str | None = None
    # Edges whose plan was legal but whose endpoints were not both present when
    # the statement ran. The difference between what was planned and what the
    # database actually holds -- reported, never folded into the success.
    unmatched: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.refused is None


def persist(session, plan: PersistPlan) -> PersistResult:
    """Execute an already-legal plan. Refuses an illegal one outright.

    MERGE rather than CREATE throughout: ids are content-derived, so a repeat
    write must be a no-op and not a duplicate or a constraint violation. This is
    also what makes the write safe under transaction retry.

    **The counts come from the database, not from the loop.** They used to be
    `+= 1` after each `session.run`, which reports a number that cannot be wrong
    and therefore cannot be useful. The edge loop is where that bites: its
    `MATCH` finds nothing when an endpoint is absent -- which is exactly what a
    `:Transition` edge planned against a node carrying `:ApiCall` does -- and the
    `MERGE` then writes nothing while the result still said it had. `land` had
    the same defect and reports `unmatched` for it; this now matches.

    **One statement per group, not per row.** Grouping is what makes the count
    readable back in one round trip, and it replaces several hundred round trips
    per model with a handful.
    """
    if not plan.is_legal:
        return PersistResult(refused=f"{len(plan.errors)} validation error(s): "
                                     f"{plan.errors[0]}")

    by_label: dict[str, list[dict]] = {}
    for node in plan.nodes:
        props = {k: v for k, v in node.properties.items() if v is not None}
        by_label.setdefault(node.label, []).append(props)

    nodes_written = 0
    for label, rows in by_label.items():
        result = session.run(
            f"UNWIND $rows AS row "
            f"MERGE (n:{label} {{id: row.id}}) SET n += row "
            f"RETURN count(n) AS written", rows=rows)
        nodes_written += count_written(result)

    by_edge: dict[tuple, list[dict]] = {}
    for edge in plan.edges:
        key = (edge.from_label, edge.rel_type, edge.to_label)
        by_edge.setdefault(key, []).append(
            {"a": edge.from_id, "b": edge.to_id, "props": edge.properties or {}})

    edges_written = 0
    unmatched: list[tuple[str, str, str]] = []
    for (from_label, rel_type, to_label), rows in by_edge.items():
        result = session.run(
            f"UNWIND $rows AS row "
            f"MATCH (a:{from_label} {{id: row.a}}), (b:{to_label} {{id: row.b}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) SET r += row.props "
            f"RETURN count(r) AS written", rows=rows)
        written = count_written(result)
        edges_written += written
        if written < len(rows):
            unmatched.append(
                (f"{from_label}-[:{rel_type}]->{to_label}",
                 f"{len(rows) - written} of {len(rows)}",
                 "one or both endpoints were absent when this ran — check the "
                 "specialisation: a node classified :ApiCall or :UiAction does "
                 "not match a plan written against :Transition"))

    return PersistResult(nodes_written=nodes_written, edges_written=edges_written,
                         unmatched=unmatched)


# ---------------------------------------------------------------------------
# The queries the graph exists to answer (spec §16.2)
# ---------------------------------------------------------------------------

COVERED_TRANSITIONS_CYPHER = """
MATCH (p:Scenario)-[c:COVERS {is_validated: true}]->(t:Transition|ApiCall|UiAction)
WHERE $journey IN t.functional_areas AND t.surface = $surface
RETURN t.id AS transition, collect(DISTINCT p.id) AS paths
ORDER BY transition
"""

UNCOVERED_TRANSITIONS_CYPHER = """
MATCH (t:Transition|ApiCall|UiAction)
WHERE $journey IN t.functional_areas AND t.surface = $surface
  AND t.implementation_status = 'implemented'
  AND NOT (:Scenario)-[:COVERS {is_validated: true}]->(t)
RETURN t.id AS transition, t.lifecycle_state AS lifecycle
ORDER BY transition
"""

TRANSITIONS_WITHOUT_AC_CYPHER = """
MATCH (t:Transition|ApiCall|UiAction)
WHERE $journey IN t.functional_areas
  AND t.implementation_status = 'implemented'
  AND NOT (:AcceptanceCriterion)-[:VALIDATES]->(t)
RETURN t.id AS transition
ORDER BY transition
"""

VERSION_DIFF_CYPHER = f"""
MATCH (a:{label_expression("Component")} {{id: $version_a}})-[:CONTAINS]->(x)
WITH collect(x.id) AS in_a
MATCH (b:{label_expression("Component")} {{id: $version_b}})-[:CONTAINS]->(y)
WITH in_a, collect(y.id) AS in_b
RETURN [i IN in_a WHERE NOT i IN in_b] AS removed,
       [i IN in_b WHERE NOT i IN in_a] AS added
"""

TRACE_CASE_CYPHER = """
MATCH (tc:TestCase {id: $case_id})<-[:PRODUCES]-(p:Scenario)
      -[c:COVERS {is_validated: true}]->(t:Transition|ApiCall|UiAction)
OPTIONAL MATCH (ac:AcceptanceCriterion)-[:VALIDATES]->(t)
OPTIONAL MATCH (r:Requirement)-[:HAS_AC]->(ac)
OPTIONAL MATCH (ji:JiraItem)-[:REPRESENTS]->(r)
RETURN tc.id AS test_case, p.id AS path, t.id AS transition,
       ac.id AS acceptance_criterion, r.id AS requirement, ji.jira_key AS jira_key
"""
