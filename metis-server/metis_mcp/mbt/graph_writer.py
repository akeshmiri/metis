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

`TestPath -[:COVERS {sequence, is_validated}]-> Transition` is what carries it:
`is_validated` distinguishes the single assertion from its setup (spec P-5a), so
coverage credit can be computed in Cypher without re-deriving it.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from metis_mcp.mbt.model import Model
from metis_mcp.mbt.path_generation import GenerationResult
from metis_mcp.ontology import validate, validate_relationship
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


def model_version_id(model_id: str, source_fingerprint: str) -> str:
    """Content-derived (spec D-8): re-persisting an unchanged model is a no-op.

    Keyed on `(model, commit)` rather than on a structural fingerprint. A
    fingerprint sounds stronger and is not: it is computed over element ids, and
    landing namespaces those by model, so the SAME model fingerprinted from its
    source file and from the graph produced two different hashes -- and therefore
    two ModelVersion nodes for one extraction. `(model, commit)` is the same fact
    from either side, which is what a shared identity has to be.
    """
    return f"mv-{_hash(model_id, source_fingerprint)}"


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
    mv_id = model_version_id(model.id, commit_sha or source_fingerprint)
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

    add_node("Run", {
        "id": run_id, "source_episode_id": episode_id, "name": f"run {run_id}",
        "criterion": result.criterion, "setup_cap": result.setup_cap,
    })

    add_node("ModelVersion", {
        "id": mv_id, "source_episode_id": episode_id,
        "name": f"{model.id} v{version}",
        "journey": journey or model.id, "surface": surface or "api",
        "version": version, "commit_sha": commit_sha,
        "source_fingerprint": source_fingerprint,
    })

    # Spec D-6: elements are shared across versions where unchanged, so a version
    # references them rather than duplicating them.
    for sid in model.state_ids():
        add_edge("ModelVersion", mv_id, "CONTAINS", "State", sid)
    for tid in model.transition_ids():
        add_edge("ModelVersion", mv_id, "CONTAINS", "Transition", tid)

    cases_by_target = {c.target_key: c for c in cases}

    for path in result.paths:
        pid = path_id(mv_id, path.validated_transition_id, path.setup_transition_ids)
        add_node("TestPath", {
            "id": pid, "source_episode_id": episode_id,
            "name": f"{path.target_key}", "criterion": path.criterion,
            "generator_version": GENERATOR_VERSION,
            "setup_length": path.setup_length,
            "target_key": path.target_key,
        })
        add_edge("TestPath", pid, "GENERATED_FROM", "ModelVersion", mv_id)
        add_edge("Run", run_id, "PRODUCED", "TestPath", pid)

        # Setup steps carry sequence 1..n and is_validated false; the single
        # assertion carries sequence 0 and is_validated true (spec P-5, P-5a).
        for index, tid in enumerate(path.setup_transition_ids, start=1):
            add_edge("TestPath", pid, "COVERS", "Transition", tid,
                     {"sequence": index, "is_validated": False})
        add_edge("TestPath", pid, "COVERS", "Transition", path.validated_transition_id,
                 {"sequence": 0, "is_validated": True})

        case = cases_by_target.get(path.target_key)
        if case is not None:
            add_node("TestCase", {
                "id": case.id, "source_episode_id": episode_id, "name": case.name,
                "content_hash": _hash(case.name, case.objective,
                                      case.act_step.description,
                                      case.act_step.expected_result),
                "objective": case.objective, "criterion": case.criterion,
            })
            add_edge("TestPath", pid, "PRODUCES", "TestCase", case.id)

    return plan


@dataclass
class PersistResult:
    nodes_written: int = 0
    edges_written: int = 0
    refused: str | None = None

    @property
    def ok(self) -> bool:
        return self.refused is None


def persist(session, plan: PersistPlan) -> PersistResult:
    """Execute an already-legal plan. Refuses an illegal one outright.

    MERGE rather than CREATE throughout: ids are content-derived, so a repeat
    write must be a no-op and not a duplicate or a constraint violation. This is
    also what makes the write safe under transaction retry.
    """
    if not plan.is_legal:
        return PersistResult(refused=f"{len(plan.errors)} validation error(s): "
                                     f"{plan.errors[0]}")

    written_nodes = 0
    for node in plan.nodes:
        props = {k: v for k, v in node.properties.items() if v is not None}
        session.run(
            f"MERGE (n:{node.label} {{id: $id}}) SET n += $props",
            id=props["id"], props=props,
        )
        written_nodes += 1

    written_edges = 0
    for edge in plan.edges:
        session.run(
            f"MATCH (a:{edge.from_label} {{id: $from_id}}), "
            f"(b:{edge.to_label} {{id: $to_id}}) "
            f"MERGE (a)-[r:{edge.rel_type}]->(b) "
            f"{'SET r += $props' if edge.properties else ''}",
            from_id=edge.from_id, to_id=edge.to_id, props=edge.properties,
        )
        written_edges += 1

    return PersistResult(nodes_written=written_nodes, edges_written=written_edges)


# ---------------------------------------------------------------------------
# The queries the graph exists to answer (spec §16.2)
# ---------------------------------------------------------------------------

COVERED_TRANSITIONS_CYPHER = """
MATCH (p:TestPath)-[c:COVERS {is_validated: true}]->(t:Transition)
WHERE $journey IN t.functional_areas AND t.surface = $surface
RETURN t.id AS transition, collect(DISTINCT p.id) AS paths
ORDER BY transition
"""

UNCOVERED_TRANSITIONS_CYPHER = """
MATCH (t:Transition)
WHERE $journey IN t.functional_areas AND t.surface = $surface
  AND t.implementation_status = 'implemented'
  AND NOT (:TestPath)-[:COVERS {is_validated: true}]->(t)
RETURN t.id AS transition, t.lifecycle_state AS lifecycle
ORDER BY transition
"""

TRANSITIONS_WITHOUT_AC_CYPHER = """
MATCH (t:Transition)
WHERE $journey IN t.functional_areas
  AND t.implementation_status = 'implemented'
  AND NOT (:AcceptanceCriterion)-[:VALIDATES]->(t)
RETURN t.id AS transition
ORDER BY transition
"""

VERSION_DIFF_CYPHER = """
MATCH (a:ModelVersion {id: $version_a})-[:CONTAINS]->(x)
WITH collect(x.id) AS in_a
MATCH (b:ModelVersion {id: $version_b})-[:CONTAINS]->(y)
WITH in_a, collect(y.id) AS in_b
RETURN [i IN in_a WHERE NOT i IN in_b] AS removed,
       [i IN in_b WHERE NOT i IN in_a] AS added
"""

TRACE_CASE_CYPHER = """
MATCH (tc:TestCase {id: $case_id})<-[:PRODUCES]-(p:TestPath)
      -[c:COVERS {is_validated: true}]->(t:Transition)
OPTIONAL MATCH (ac:AcceptanceCriterion)-[:VALIDATES]->(t)
OPTIONAL MATCH (r:Requirement)-[:HAS_AC]->(ac)
OPTIONAL MATCH (ji:JiraItem)-[:REPRESENTS]->(r)
RETURN tc.id AS test_case, p.id AS path, t.id AS transition,
       ac.id AS acceptance_criterion, r.id AS requirement, ji.jira_key AS jira_key
"""
