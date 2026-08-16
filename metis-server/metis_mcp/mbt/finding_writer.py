"""
Landing findings and model versions in the graph (application spec §8.2, §8.3;
D-5, D-6, F-3, F-12, GR-1).

**Why findings belong in the graph rather than in a terminal.** F-12 makes the
graph the interface to consumers: they query it, they never re-derive. A
divergence that exists only in a command's stdout has to be re-computed by
everyone who wants it, and cannot be linked to the element it concerns. §8.2
gives `Finding` a place in the ontology precisely so "which behaviour has no UI
path?" is a query (§16.2) rather than a rerun.

`graph_writer.plan_persist` already lands `ModelVersion` and `Run`, but only as
part of *generation* -- it needs paths and cases, which a model that fails
validation (M-18) will never have. An extracted-but-not-yet-generatable model
still deserves a version and a provenance record: that is the state most models
are in immediately after extraction, and losing the extraction run's identity
because generation was blocked would make the block itself unauditable.

Everything here is MERGE-based on content-derived ids (D-8), so re-running an
extraction is a no-op rather than a duplicate (TR-6).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from metis_mcp.mbt.graph_writer import model_version_id
from metis_mcp.mbt.model import Model

# `finding_type` values. Each names a rule, so a reader can go from a row in the
# graph to the sentence in the specification that produced it.
API_ONLY = "api_only"                      # M-5f
UNHANDLED_OUTCOME = "unhandled_outcome"    # M-5f
DANGLING_INVOKES = "dangling_invokes"      # M-5f
RESTATED_GUARD = "restated_guard"          # M-5c
VALIDATION = "validation"                  # §2.6 / M-18
UNGUARDED_OUTCOME = "unguarded_outcome"    # §5.8's recovery limit

OPEN = "open"


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


@dataclass
class FindingRecord:
    finding_type: str
    severity: str
    detail: str
    about_label: str
    about_id: str
    remedy: str = ""
    model_id: str = ""

    @property
    def id(self) -> str:
        return "finding:" + _id(self.finding_type, self.about_id, self.detail)


@dataclass
class LoadPlan:
    """Pure. Nothing reaches the database until `load` runs it."""

    statements: list[tuple[str, dict]] = field(default_factory=list)
    versions: int = 0
    findings: int = 0
    runs: int = 0


MODEL_VERSION_CYPHER = """
MERGE (mv:ModelVersion {id: $id})
ON CREATE SET mv.created_at = datetime()
SET mv.journey = $journey, mv.surface = $surface, mv.version = $version,
    mv.commit_sha = $commit, mv.source_episode_id = $episode,
    mv.name = $id, mv.lifecycle_state = 'Quarantine'
"""

CONTAINS_CYPHER = """
MATCH (mv:ModelVersion {id: $version_id})
MATCH (n {id: $element_id}) WHERE n:State OR n:Transition
MERGE (mv)-[:CONTAINS]->(n)
"""

RUN_CYPHER = """
MERGE (r:Run {id: $id})
ON CREATE SET r.created_at = datetime()
SET r.name = $id, r.scope = $scope, r.criterion = $criterion,
    r.commit_sha = $commit, r.source_episode_id = $episode,
    r.engine = $engine, r.lifecycle_state = 'Quarantine'
"""

FINDING_CYPHER = """
MERGE (f:Finding {id: $id})
ON CREATE SET f.created_at = datetime()
SET f.finding_type = $finding_type, f.severity = $severity, f.detail = $detail,
    f.remedy = $remedy, f.resolution = $resolution, f.name = $finding_type,
    f.source_episode_id = $episode, f.model_id = $model_id,
    f.lifecycle_state = 'Quarantine'
"""

ABOUT_CYPHER = """
MATCH (f:Finding {id: $finding_id})
MATCH (n {id: $about_id})
MERGE (f)-[:ABOUT]->(n)
"""


def plan_load(model: Model, *, journey: str, surface: str, version: int,
              commit: str, episode: str, findings: list[FindingRecord],
              run_id: str = "", engine: str = "",
              source_fingerprint: str = "") -> LoadPlan:
    """Build every statement, in a fixed order, without touching the database.

    Ordering is deterministic so two runs produce identical plans -- the same
    discipline P-7 applies to path generation, applied here so a diff of two
    loads is meaningful.

    The version id is **content-derived**, via `graph_writer.model_version_id`.
    An earlier version of this function minted `f"{model.id}@{version}"` -- a
    sequential number, which D-8 explicitly forbids -- and the result was TWO
    ModelVersion nodes per model: one from here and one from `plan_persist`,
    describing the same extraction under different ids. Sharing the id function
    is what makes re-running a no-op rather than a duplicate (TR-6).
    """
    plan = LoadPlan()
    version_id = model_version_id(model.id, commit or source_fingerprint or f"v{version}")

    plan.statements.append((MODEL_VERSION_CYPHER, {
        "id": version_id, "journey": journey, "surface": surface,
        "version": version, "commit": commit, "episode": episode}))
    plan.versions = 1

    # D-6: elements are SHARED across versions, never duplicated per version --
    # membership is an edge, so an unchanged transition belongs to both.
    for sid in model.state_ids():
        plan.statements.append((CONTAINS_CYPHER, {
            "version_id": version_id, "element_id": f"{model.id}::{sid}"}))
    for tid in model.transition_ids():
        plan.statements.append((CONTAINS_CYPHER, {
            "version_id": version_id, "element_id": f"{model.id}::{tid}"}))

    if run_id:
        plan.statements.append((RUN_CYPHER, {
            "id": run_id, "scope": model.id, "criterion": "extraction",
            "commit": commit, "episode": episode, "engine": engine}))
        plan.runs = 1

    for finding in sorted(findings, key=lambda f: (f.finding_type, f.about_id)):
        plan.statements.append((FINDING_CYPHER, {
            "id": finding.id, "finding_type": finding.finding_type,
            "severity": finding.severity, "detail": finding.detail,
            "remedy": finding.remedy, "resolution": OPEN,
            "episode": episode, "model_id": finding.model_id or model.id}))
        plan.statements.append((ABOUT_CYPHER, {
            "finding_id": finding.id, "about_id": finding.about_id}))
        plan.findings += 1

    return plan


def load(session, plan: LoadPlan) -> dict:
    """Run a plan. Every statement is MERGE-based, so a repeat is a no-op (TR-6)."""
    for cypher, params in plan.statements:
        session.run(cypher, **params)
    return {"versions": plan.versions, "findings": plan.findings, "runs": plan.runs,
            "statements": len(plan.statements)}
