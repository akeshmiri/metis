"""
UIF → the graph (application spec §3.2 stage 2; D-1, D-8, S-4, TR-6).

**The half that was missing.** Six extractors produce a Unified Intake Format
document with every field traced to the response it came from. Nothing carried
that into the graph: `metis_mcp/uif_intake.py` went with the v1 engine, and
`intake_processor.py --land` has refused ever since -- correctly, because
refusing is better than reporting a success that wrote nothing.

**Two provenance records, answering different questions.** This is the
distinction that made the design confusing until it was written down:

    Episode        which RUN produced this, and can I re-run it?
                   Content-derived, so re-extracting unchanged content is a
                   no-op. Minted afresh whenever the content changes.

    <Source>Item   which ARTEFACT in the world is this about?
                   `jira:PROJ-14`, a Confluence page, an OpenAPI document.
                   Survives its Requirement being rejected -- rejecting a claim
                   must never destroy the evidence it came from.

**What is deliberately NOT created here.**

`specifications.acceptance_criteria` arrives already labelled as acceptance
criteria, and this does **not** create `AcceptanceCriterion` nodes from that
claim. Trusting an upstream extractor's labelling is the shortcut the intake
skill explicitly refuses; the text goes through the same mining and review path
as any other intake, landing at `Quarantine` for a human.

A `Requirement` is created **only when the text is EARS-conformant.** A Jira
title is free prose, and `Requirement.ears_pattern` is a required property with
no empty form. Stuffing a placeholder there would produce exactly the "fluent,
well-formed, invented requirement" `ac_mining` refuses to guess at (S-13, TR-4).
Non-conformant intake lands as a `Finding` naming what has to happen next --
formalisation through `knowledge-capture`, where a person does the judgement.

Everything lands at `Quarantine` (S-4). Nothing here approves anything.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from metis_mcp.ears_checker import check_ears_conformance
from metis_mcp.identity.keys import business_entity_key
from metis_mcp.mbt.model import QUARANTINE
from metis_mcp.model_sources.landing import LandingPlan, PlannedEdge, PlannedNode
from metis_mcp.ontology.validation import validate as validate_node
from metis_mcp.ontology.validation import validate_relationship

UIF_VERSION_PREFIX = "1."

# `scope.source_system` -> (label, the id property that label requires).
# Taken from what the extractors actually emit, not from what they are called:
# `swagger_extractor.py` writes `source_system="swagger"` and the artefact is an
# OpenAPI document, and Zephyr Scale's extractor writes `"scale"`.
ANCHORS: dict[str, tuple[str, str]] = {
    "jira": ("JiraItem", "jira_key"),
    "confluence": ("ConfluenceItem", "page_id"),
    "swagger": ("OpenApiItem", "document_id"),
    "scale": ("ZephyrItem", "zephyr_key"),
    "code_repository": ("CodeItem", "repo_id"),
    "database": ("DatasourceItem", "datasource_id"),
}

NOT_EARS = "intake_not_ears"
OPEN_QUESTION = "intake_open_question"


class IntakeRefused(Exception):
    """The document could not be read at all -- shape, not content."""


def load(path) -> dict:
    """Read a UIF file, refusing a shape this cannot land.

    An unknown `uif_version` is refused rather than read optimistically: the
    format is a hard contract, and guessing at a version this code has never
    seen is how a field silently means something else.
    """
    import pathlib

    try:
        document = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError) as e:
        raise IntakeRefused(str(e)) from e

    version = str(document.get("uif_version", ""))
    if not version:
        raise IntakeRefused("no uif_version — this is not a UIF document")
    if not version.startswith(UIF_VERSION_PREFIX):
        raise IntakeRefused(
            f"uif_version {version!r} is not supported (this lands {UIF_VERSION_PREFIX}x)")
    if not document.get("scope", {}).get("source_system"):
        raise IntakeRefused("scope.source_system is missing — nothing says where "
                            "this came from, so no anchor can be chosen")
    if not document.get("scope", {}).get("primary_id"):
        raise IntakeRefused("scope.primary_id is missing — the artefact has no "
                            "identity in its own system")
    return document


def episode_id_for(document: dict) -> str:
    """Content-derived (D-8): re-extracting unchanged content is a no-op.

    Hashes the parts that carry meaning and **excludes the timestamps** --
    `scope.uif_generated_at` changes on every extraction run, so including it
    would mint a new Episode each time and make TR-6 unachievable.
    """
    scope = document.get("scope", {})
    payload = {
        "source_system": scope.get("source_system"),
        "primary_id": scope.get("primary_id"),
        "primary_type": scope.get("primary_type"),
        "metadata": document.get("metadata", {}),
        "facts": document.get("facts", {}),
        "specifications": document.get("specifications", {}),
        "data_model": document.get("data_model", []),
        "open_questions": document.get("open_questions", {}),
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return "ep-" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def anchor_for(document: dict) -> tuple[str, str]:
    """`(label, id_property)` for this document's source system."""
    system = document.get("scope", {}).get("source_system", "")
    if system not in ANCHORS:
        raise IntakeRefused(
            f"no anchor label for source_system {system!r}. Known: "
            f"{', '.join(sorted(ANCHORS))}. Adding one is an ontology change "
            f"under D-2, not an edit here.")
    return ANCHORS[system]


def _requirement_text(document: dict) -> str:
    metadata = document.get("metadata", {})
    return (metadata.get("description") or metadata.get("title") or "").strip()


def plan_intake(document: dict, *, job_id: str = "manual",
                proposed_by: str = "", t_recorded: str | None = None) -> LandingPlan:
    """Build the whole plan offline. No session, no writes.

    Everything is validated against the ontology before anything is written, so
    `is_legal` is a complete answer before the database is touched -- the same
    discipline `landing.plan_landing` and `graph_writer.plan_persist` keep.
    """
    scope = document.get("scope", {})
    metadata = document.get("metadata", {})
    episode_id = episode_id_for(document)
    recorded = t_recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")
    label, id_property = anchor_for(document)

    plan = LandingPlan(episode_id=episode_id)

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

    # ---- the ingestion record. Exempt from source_episode_id (BASELINE_EXEMPT).
    add_node("Episode", {
        "id": episode_id,
        "name": f"{scope.get('source_system')}: {scope.get('primary_id')}",
        "t_recorded": recorded,
        "source_connector": scope.get("source_system"),
        "job_id": job_id,
        # N-10 depends on reading this back: the identity that proposed an
        # element may not approve it.
        "proposed_by": proposed_by or "unknown",
        # The document itself, so a consumer never has to re-extract to see what
        # was actually received (F-12).
        "raw_content": json.dumps(document, sort_keys=True),
    })

    # ---- the artefact in the world
    primary_id = scope.get("primary_id")
    anchor_id = f"{scope.get('source_system')}:{primary_id}"
    anchor_props = {
        "id": anchor_id,
        "source_episode_id": episode_id,
        "name": metadata.get("title") or primary_id,
        id_property: primary_id,
    }
    if label == "JiraItem":
        # Its second required property, and the only anchor that has one.
        anchor_props["issue_type"] = scope.get("primary_type") or "unknown"
    anchor_ok = add_node(label, anchor_props)

    # ---- the requirement, only when the text is EARS-conformant
    text = _requirement_text(document)
    ears = check_ears_conformance(text) if text else None
    if ears is not None and ears.pattern:
        requirement_id = f"req-{hashlib.sha256(anchor_id.encode()).hexdigest()[:12]}"
        if add_node("Requirement", {
            "id": requirement_id,
            "source_episode_id": episode_id,
            "name": requirement_id,
            "text": text,
            "statement": text,
            "ears_pattern": ears.pattern,
            "revision": 1,
            "lifecycle_state": QUARANTINE,
        }) and anchor_ok:
            add_edge(label, anchor_id, "REPRESENTS", "Requirement", requirement_id)
    elif text:
        # The honest outcome, not a silent skip. A Jira title is free prose, and
        # inventing an EARS pattern for it would produce a well-formed statement
        # nobody wrote.
        _add_finding(plan, add_node, add_edge, episode_id, NOT_EARS, "advisory",
                     f"intake text is not EARS-conformant: {text[:200]}",
                     label, anchor_id,
                     "formalise it through knowledge-capture, where a person "
                     "does the judgement (S-13)")

    # ---- business nouns the source described
    for entry in document.get("data_model") or []:
        name = (entry.get("name") or entry.get("entity") or "").strip()
        description = (entry.get("description") or "").strip()
        if not name or not description:
            # D-13: a glossary entry whose name is its own only explanation
            # answers nothing. Better absent than empty.
            continue
        add_node("BusinessEntity", {
            # The shared natural key (I-2), not a second minting rule. Intake and
            # the glossary describe the same noun and neither is wrong about it;
            # two rules meant `api spec` landed twice with no canonical form.
            "id": business_entity_key(name),
            "source_episode_id": episode_id,
            "name": name,
            "description": description,
            "impact": list(entry.get("impact") or ()),
            "properties_json": json.dumps(entry.get("properties") or [],
                                          sort_keys=True),
            "lifecycle_state": QUARANTINE,
        })

    # ---- what the source itself flagged as unresolved
    questions = document.get("open_questions") or {}
    for kind in ("ambiguities", "conflicts", "missing_requirements"):
        for item in questions.get(kind) or []:
            detail = item if isinstance(item, str) else json.dumps(item, sort_keys=True)
            _add_finding(plan, add_node, add_edge, episode_id, OPEN_QUESTION,
                         "advisory", f"{kind}: {detail[:300]}", label, anchor_id,
                         "the source flagged this; it needs a person")

    return plan


def _add_finding(plan, add_node, add_edge, episode_id: str, finding_type: str,
                 severity: str, detail: str, about_label: str, about_id: str,
                 remedy: str) -> None:
    finding_id = "finding:" + hashlib.sha256(
        f"{finding_type}|{about_id}|{detail}".encode()).hexdigest()[:16]
    if add_node("Finding", {
        "id": finding_id,
        "source_episode_id": episode_id,
        "name": finding_type,
        "finding_type": finding_type,
        "severity": severity,
        "detail": detail,
        "remedy": remedy,
        "resolution": "open",
        "lifecycle_state": QUARANTINE,
    }):
        add_edge("Finding", finding_id, "ABOUT", about_label, about_id)


def describe(plan: LandingPlan, document: dict) -> str:
    """What this plan will do, for a person about to run it."""
    by_label: dict[str, int] = {}
    for node in plan.nodes:
        by_label[node.label] = by_label.get(node.label, 0) + 1

    scope = document.get("scope", {})
    lines = [
        f"UIF — {scope.get('source_system')}: {scope.get('primary_id')}",
        f"  episode:  {plan.episode_id}",
    ]
    for label in sorted(by_label):
        lines.append(f"  {label + ':':<18} {by_label[label]}")

    claimed = len((document.get("specifications") or {}).get("acceptance_criteria") or [])
    if claimed:
        lines.append("")
        lines.append(
            f"  {claimed} acceptance criteria are claimed by this document and "
            f"NONE is created:")
        lines.append("     an upstream extractor's labelling is not evidence. The "
                     "text goes through")
        lines.append("     mining and review like any other intake (S-4).")
    return "\n".join(lines)
