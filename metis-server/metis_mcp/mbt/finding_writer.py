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
import re
from dataclasses import dataclass, field

from metis_mcp.mbt.graph_session import count_written
from metis_mcp.ontology.labels import label_expression
from metis_mcp.model_sources.landing import (
    component_label_for, ensure_namespaced, graph_transition_id)
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


# `component` is REQUIRED on `Component` and was missing here, while
# `graph_writer` set it — two writers for one label, disagreeing. Under
# Community nothing complained, because property-existence constraints are an
# Enterprise feature; against Enterprise the whole stage failed with
# "Node(53) with label `RestServer` must have the property `component`".
#
# It is the stable half of the identity (D-6): the node is one component AT one
# commit, so without it you cannot ask for every version of a component, and the
# estate reads as N components today and 2N after the next commit.
MODEL_VERSION_CYPHER = """
MERGE (mv:$COMPONENT_LABEL {id: $id})
ON CREATE SET mv.created_at = datetime()
SET mv:NeedReview
SET mv.journey = $journey, mv.surface = $surface, mv.version = $version,
    mv.component = $component,
    mv.commit_sha = $commit, mv.source_episode_id = $episode,
    mv.name = $id, mv.lifecycle_state = 'Quarantine'
"""

# `RestServer -[:EXPOSES]-> Endpoint`, catalogued since the evidence layer landed
# and written by nothing: 0 of 12 on a real service, so "which entry points does
# this deployable serve" was unanswerable from a graph whose catalogue said
# otherwise.
#
# It is written HERE rather than in `land` because this is where the Component's
# content-derived id is computed. Planned earlier, the edge would point at a node
# that does not exist yet and `MERGE` would match nothing — the same ordering
# trap the derivation edges have.
EXPOSES_CYPHER = f"""
MATCH (mv:{label_expression("Component")} {{id: $version_id}})
MATCH (e:Endpoint {{id: $endpoint_id}})
MERGE (mv)-[:EXPOSES]->(e)
RETURN count(*) AS written
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

# `:NeedReview` alongside `lifecycle_state = 'Quarantine'`. This writer does not
# go through `landing.land`, which is where the marker is applied centrally, so
# it sets it itself — and `test_ontology` asserts the two can never disagree,
# which is what makes a second write path safe rather than a second answer.
FINDING_CYPHER = """
MERGE (f:Finding {id: $id})
ON CREATE SET f.created_at = datetime()
SET f:NeedReview
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


def _about_id(model: Model, about: str) -> str:
    """The graph id of whatever a finding concerns.

    A transition carries its natural key (I-2); a state carries its own id. One
    place, because composing it inline is how 24 `ABOUT` edges came to point at
    nodes that do not exist.
    """
    bare = about.split("::", 1)[-1] if about.startswith(f"{model.id}::") else about
    if bare in model.transitions:
        return graph_transition_id(model, bare)
    return ensure_namespaced(model.id, about)


def plan_load(model: Model, *, journey: str, surface: str, version: int,
              commit: str, episode: str, findings: list[FindingRecord],
              run_id: str = "", engine: str = "",
              source_fingerprint: str = "",
              endpoint_ids: tuple[str, ...] = ()) -> LoadPlan:
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
            "version": version, "component": model.id, "commit": commit,
            "episode": episode}))
    plan.versions = 1

    # D-6: elements are SHARED across versions, never duplicated per version --
    # membership is an edge, so an unchanged transition belongs to both.
    for sid in model.state_ids():
        plan.statements.append(("contains", CONTAINS_CYPHER, {
            "version_id": version_id, "element_id": f"{model.id}::{sid}"}))
    for tid in model.transition_ids():
        plan.statements.append(("contains", CONTAINS_CYPHER, {
            # **Not `f"{model.id}::{tid}"`.** A transition is written with its
            # NATURAL key since I-2, so a writer that composes the id from the
            # source's own `tid` addresses a node that does not exist. Caught by
            # this stage reporting "24 finding(s), 24 unattached" — the count it
            # reports is the only reason it was not silent.
            "version_id": version_id,
            "element_id": graph_transition_id(model, tid)}))

    # The entry points this deployable serves. Absent when the caller has no
    # structural report — the edge is simply not planned, rather than planned
    # against ids nobody recovered.
    for eid in endpoint_ids:
        plan.statements.append(("exposes", EXPOSES_CYPHER, {
            "version_id": version_id, "endpoint_id": eid}))


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
            # test concluded it was done and left it bare. `records-spec-ui` was
            # the model that exposed it: two ABOUT statements matched nothing and
            # `land` reported them rather than swallowing them.
            # Same rule: a finding about a transition has to name the id the
            # transition was written with, not the one its source used.
            "about_id": _about_id(model, finding.about_id)}))
        plan.findings += 1

    return plan


# What each statement kind writes, so `validate_plan` can check the properties
# against the ontology the way `landing.add_node` does. A kind absent here writes
# no node — `contains` and `about` are MATCH/MERGE over existing ones.
_WRITES_NODE = {"version": None, "finding": "Finding"}


def validate_plan(plan: LoadPlan) -> list[str]:
    """Required-property errors, before anything runs (§C1, D-8).

    **This is the guard Community edition does not have.** Property-existence
    constraints are Enterprise-only, and the community schema's own header says
    required-property enforcement "lives in metis_mcp/ontology/validation.py
    instead" — but only `landing.plan_landing` was calling it. This module writes
    `Component` and `Finding` through its own Cypher, and that is exactly where
    the missing `component` property lived: caught by an Enterprise constraint we
    were not supposed to be relying on, and by nothing else.

    Checked against the ontology rather than a hand-written list, so a new
    required property fails here rather than in somebody's database.
    """
    from metis_mcp.ontology import validate

    errors: list[str] = []
    for kind, cypher, params in plan.statements:
        if kind not in _WRITES_NODE:
            continue
        label = _WRITES_NODE[kind]
        if label is None:
            # The Component specialisation is chosen at plan time and appears in
            # the statement itself; read it back rather than re-deriving it.
            match = re.search(r"MERGE \(mv:(\w+)", cypher)
            label = match.group(1) if match else "Component"
        # `id` is the MERGE key and `name`/`lifecycle_state` are set in the
        # statement body; the ontology wants them present on the node, which
        # they are. What it cannot see is a property the statement forgot.
        props = dict(params)
        props.setdefault("id", params.get("id", ""))
        for prop in ("name", "lifecycle_state"):
            if f"mv.{prop}" in cypher or f"f.{prop}" in cypher:
                props.setdefault(prop, "set-in-statement")
        props.setdefault("source_episode_id", params.get("episode", ""))
        outcome = validate(label, props)
        if not outcome.valid:
            errors.extend(outcome.errors)
    return errors


def load(session, plan: LoadPlan) -> dict:
    """Run a plan. Every statement is MERGE-based, so a repeat is a no-op (TR-6).

    **The counts are read back, not returned from the plan.** They used to be
    `plan.versions` / `plan.findings` -- the size of what was *asked for*, which
    is identical whether the database did the work or not. Two of these
    statements begin with a `MATCH` that can find nothing (`CONTAINS` against an
    element that was never landed, `ABOUT` against an id that is not namespaced),
    and both are then a no-op that used to report as a write.
    """
    errors = validate_plan(plan)
    if errors:
        # Refused whole, not partly written. A half-landed finding set is worse
        # than none: the counts look plausible and the gap is invisible.
        raise ValueError(
            f"{len(errors)} ontology error(s) — nothing was written. "
            f"First: {errors[0]}")

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
                # is identical across every service -- so seven Example models
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
