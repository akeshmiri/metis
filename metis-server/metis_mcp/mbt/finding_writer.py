"""
Landing findings and model versions in the graph (application spec §8.2, §8.3;
D-5, D-6, F-3, F-12, GR-1).

**Why findings belong in the graph rather than in a terminal.** F-12 makes the
graph the interface to consumers: they query it, they never re-derive. A
divergence that exists only in a command's stdout has to be re-computed by
everyone who wants it, and cannot be linked to the element it concerns. §8.2
gives `Finding` a place in the ontology precisely so "which behaviour has no UI
path?" is a query (§16.2) rather than a rerun.

`graph_writer.plan_persist` already lands `Component` and `Run`, but only as
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

from metis_mcp.mbt.graph_session import count_written
from metis_mcp.ontology.labels import label_expression
from metis_mcp.model_sources.landing import component_label_for, ensure_namespaced
from metis_mcp.mbt.graph_writer import component_id
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

    # `(kind, cypher, params)`. The kind is explicit because dispatch used to
    # compare `cypher is MODEL_VERSION_CYPHER` -- object identity -- and the
    # moment that statement was templated (to carry the Component
    # specialisation) every comparison silently stopped matching. A tuple of
    # strings cannot go stale that way.
    statements: list[tuple[str, str, dict]] = field(default_factory=list)
    versions: int = 0
    findings: int = 0
    runs: int = 0


MODEL_VERSION_CYPHER = """
MERGE (mv:$COMPONENT_LABEL {id: $id})
ON CREATE SET mv.created_at = datetime()
SET mv.journey = $journey, mv.surface = $surface, mv.version = $version,
    mv.commit_sha = $commit, mv.source_episode_id = $episode,
    mv.name = $id, mv.lifecycle_state = 'Quarantine'
"""

CONTAINS_CYPHER = f"""
MATCH (mv:{label_expression("Component")} {{id: $version_id}})
MATCH (n {{id: $element_id}}) WHERE n:State OR n:Transition OR n:ApiCall OR n:UiAction
MERGE (mv)-[:CONTAINS]->(n)
RETURN count(*) AS written
"""

# `Run` was staged out (§8.7): written here and by `plan_persist`, matched by
# no query. The run's identity survives in the Episode and in
# `.metis/runs/*.json`; what is gone is a node nothing asked about.

FINDING_CYPHER = """
MERGE (f:Finding {id: $id})
ON CREATE SET f.created_at = datetime()
SET f.finding_type = $finding_type, f.severity = $severity, f.detail = $detail,
    f.remedy = $remedy, f.resolution = $resolution, f.name = $finding_type,
    f.source_episode_id = $episode, f.model_id = $model_id,
    f.lifecycle_state = 'Quarantine'
"""

# `MATCH (n {id: $about_id})` with no label was the trap: a bare element id
# matches nothing, because landing namespaces every id as `{model_id}::{id}`.
# The caller now namespaces it (`plan_load`), and the count comes back so a miss
# is visible instead of being a statement that ran and did nothing.
ABOUT_CYPHER = """
MATCH (f:Finding {id: $finding_id})
MATCH (n {id: $about_id})
MERGE (f)-[:ABOUT]->(n)
RETURN count(*) AS written
"""


def plan_load(model: Model, *, journey: str, surface: str, version: int,
              commit: str, episode: str, findings: list[FindingRecord],
              run_id: str = "", engine: str = "",
              source_fingerprint: str = "") -> LoadPlan:
    """Build every statement, in a fixed order, without touching the database.

    Ordering is deterministic so two runs produce identical plans -- the same
    discipline P-7 applies to path generation, applied here so a diff of two
    loads is meaningful.

    The version id is **content-derived**, via `graph_writer.component_id`.
    An earlier version of this function minted `f"{model.id}@{version}"` -- a
    sequential number, which D-8 explicitly forbids -- and the result was TWO
    Component nodes per model: one from here and one from `plan_persist`,
    describing the same extraction under different ids. Sharing the id function
    is what makes re-running a no-op rather than a duplicate (TR-6).
    """
    plan = LoadPlan()
    version_id = component_id(model.id, commit or source_fingerprint or f"v{version}")

    # The same specialisation `plan_persist` writes. Two writers touching one
    # Component node have to agree about its label, or `MERGE` creates a second
    # node rather than updating the first.
    component_label = component_label_for(surface)
    plan.statements.append((
        "version",
        MODEL_VERSION_CYPHER.replace("$COMPONENT_LABEL", component_label), {
            "id": version_id, "journey": journey, "surface": surface,
            "version": version, "commit": commit, "episode": episode}))
    plan.versions = 1

    # D-6: elements are SHARED across versions, never duplicated per version --
    # membership is an edge, so an unchanged transition belongs to both.
    for sid in model.state_ids():
        plan.statements.append(("contains", CONTAINS_CYPHER, {
            "version_id": version_id, "element_id": f"{model.id}::{sid}"}))
    for tid in model.transition_ids():
        plan.statements.append(("contains", CONTAINS_CYPHER, {
            "version_id": version_id, "element_id": f"{model.id}::{tid}"}))


    for finding in sorted(findings, key=lambda f: (f.finding_type, f.about_id)):
        plan.statements.append(("finding", FINDING_CYPHER, {
            "id": finding.id, "finding_type": finding.finding_type,
            "severity": finding.severity, "detail": finding.detail,
            "remedy": finding.remedy, "resolution": OPEN,
            "episode": episode, "model_id": finding.model_id or model.id}))
        plan.statements.append(("about", ABOUT_CYPHER, {
            "finding_id": finding.id,
            # Landing namespaces every element id, so a bare one matches no
            # node and the ABOUT edge silently does not exist.
            #
            # The test is `startswith(model.id + "::")`, NOT `"::" in id`. A Web
            # element id is `ui::ApiSpecDetailPage::/spec/::Ok200` -- it already
            # contains `::` while being entirely un-namespaced, so the containment
            # test concluded it was done and left it bare. `athena-spec-ui` was
            # the model that exposed it: two ABOUT statements matched nothing and
            # `land` reported them rather than swallowing them.
            "about_id": ensure_namespaced(model.id, finding.about_id)}))
        plan.findings += 1

    return plan


def load(session, plan: LoadPlan) -> dict:
    """Run a plan. Every statement is MERGE-based, so a repeat is a no-op (TR-6).

    **The counts are read back, not returned from the plan.** They used to be
    `plan.versions` / `plan.findings` -- the size of what was *asked for*, which
    is identical whether the database did the work or not. Two of these
    statements begin with a `MATCH` that can find nothing (`CONTAINS` against an
    element that was never landed, `ABOUT` against an id that is not namespaced),
    and both are then a no-op that used to report as a write.
    """
    written = {"versions": 0, "findings": 0, "runs": 0, "contains": 0, "about": 0}
    unmatched: list[str] = []
    for kind, cypher, params in plan.statements:
        result = session.run(cypher, **params)
        if kind == "contains":
            if count_written(result):
                written["contains"] += 1
            else:
                unmatched.append(f"CONTAINS -> {params['element_id']}")
        elif kind == "about":
            if count_written(result):
                written["about"] += 1
            else:
                unmatched.append(f"ABOUT -> {params['about_id']}")
        elif kind == "version":
            written["versions"] += 1
        elif kind == "finding":
            written["findings"] += 1

    written["statements"] = len(plan.statements)
    # Named rather than absent (F-10). A finding whose ABOUT edge did not attach
    # is in the graph but unreachable from the element it concerns, which is the
    # one thing it exists to be reachable from.
    written["unmatched"] = unmatched
    return written


# ---------------------------------------------------------------------------
# Adapters -- the two producers of findings, into records this module can land
#
# Neither producer is changed. `validate` and `divergences` already return
# everything needed; what was missing was anything that carried their output
# into the graph, which is why §8.2 gave `Finding` a label and nothing ever
# wrote one.
# ---------------------------------------------------------------------------

def from_validation(result, model: Model) -> list[FindingRecord]:
    """Every validation finding, at the severity it was reported at.

    `unverifiable` is carried across unchanged. It is a third outcome (M-17) and
    folding it into either of the other two here would undo the one distinction
    validation exists to preserve.
    """
    records = []
    for finding in result.findings:
        for element_id in finding.element_ids or ("",):
            if not element_id:
                continue
            records.append(FindingRecord(
                finding_type=VALIDATION,
                severity=finding.severity,
                detail=f"{finding.check}: {finding.detail}",
                about_label="Transition",
                # Namespaced HERE, not at statement time. `FindingRecord.id`
                # hashes `about_id`, and a bare element id like "NoContent204"
                # is identical across every service -- so seven Athena models
                # produced ONE Finding node with seven ABOUT edges, carrying
                # whichever `model_id` landed last. Found by landing the real
                # estate; a single-model test cannot see it.
                about_id=f"{model.id}::{element_id}",
                remedy=finding.remedy,
                model_id=model.id,
            ))
    return records


def from_divergences(divergences: list, model: Model) -> list[FindingRecord]:
    """M-5f's cross-surface divergences.

    `Divergence.kind` already uses exactly this module's `finding_type` values --
    the two vocabularies were written against the same rule ids and never
    connected.
    """
    return [
        FindingRecord(
            finding_type=d.kind,
            severity="advisory",
            detail=d.detail,
            about_label="Transition",
            about_id=f"{model.id}::{d.element_id}",
            remedy=d.remedy,
            model_id=model.id,
        )
        for d in divergences
    ]
