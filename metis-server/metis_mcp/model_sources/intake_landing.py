"""
UIF → the graph (application spec §3.2 stage 2; D-1, D-8, S-4, TR-6).

**The half that was missing.** Six extractors produce a Unified Intake Format
document with every field traced to the response it came from. Nothing carried
that into the graph: `metis_mcp/uif_intake.py` went with the v1 engine, and
the intake skill's `--land` refused ever since -- correctly, because refusing is
better than reporting a success that wrote nothing. That skill's extractors have
since been retired in favour of `code_analysis.tracker`, and this module is the
landing half they never had.

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
from dataclasses import dataclass
from datetime import datetime, timezone

from metis_mcp.ears_checker import check_ears_conformance
from metis_mcp.identity.keys import business_entity_key
from metis_mcp.mbt.model import QUARANTINE
from metis_mcp.model_sources.landing import LandingPlan, PlannedEdge, PlannedNode
from metis_mcp.ontology.validation import validate as validate_node
from metis_mcp.ontology.validation import validate_relationship
from metis_mcp.retrieval import search_text_for

UIF_VERSION_PREFIX = "1."

# `scope.source_system` -> (label, the id property that label requires).
# Taken from what a producer actually emits, not from what the source is called:
# the value for an OpenAPI document is `swagger`, and Zephyr Scale's is `scale`.
# Both predate this module and renaming either would detach every existing item
# from its anchor.
ANCHORS: dict[str, tuple[str, str]] = {
    "jira": ("JiraItem", "jira_key"),
    "confluence": ("ConfluenceItem", "page_id"),
    "swagger": ("OpenApiItem", "document_id"),
    "scale": ("ZephyrItem", "zephyr_key"),
    "code_repository": ("CodeItem", "repo_id"),
    # `database` -> `DatasourceItem` was the sixth. It went with the database
    # layer in the 2026-08-31 re-baseline: a Requirement traced to a schema as
    # its system of record is the trigger that would bring the anchor back.
}

NOT_EARS = "intake_not_ears"
OPEN_QUESTION = "intake_open_question"


class IntakeRefused(Exception):
    """The document could not be read at all -- shape, not content."""


@dataclass(frozen=True)
class Conformance:
    """Everything wrong with a UIF document, in one answer.

    `refusals` stop it landing; `advisories` do not, and both are returned
    together on purpose. `load` used to raise on the FIRST problem, so a
    document with three took three round-trips to learn about all of them —
    and two of its checks did not run at the door at all: an unknown
    `source_system` passed `load` and raised from `anchor_for` in the middle of
    planning, which is a stack trace where a sentence was wanted.
    """

    refusals: tuple[str, ...] = ()
    advisories: tuple[str, ...] = ()

    @property
    def conformant(self) -> bool:
        return not self.refusals

    def describe(self) -> str:
        parts = [f"refused: {r}" for r in self.refusals]
        parts += [f"advisory: {a}" for a in self.advisories]
        return "; ".join(parts) or "conformant"


def conformance(document: dict) -> Conformance:
    """Check a UIF document the whole way through before anything is planned.

    Advisories are not defects. A UIF whose text is free prose lands as a
    `Finding` pointing at `knowledge-capture` rather than as a `Requirement`
    (S-13) — that is correct behaviour and it is also the single most surprising
    thing this intake does, so it is said at the door instead of discovered by
    counting nodes afterwards.
    """
    from metis_mcp.ears_checker import check_ears_conformance

    refusals: list[str] = []
    advisories: list[str] = []

    version = str(document.get("uif_version", ""))
    if not version:
        refusals.append("no uif_version — this is not a UIF document")
    elif not version.startswith(UIF_VERSION_PREFIX):
        refusals.append(f"uif_version {version!r} is not supported "
                        f"(this lands {UIF_VERSION_PREFIX}x)")

    scope = document.get("scope") or {}
    system = scope.get("source_system")
    if not system:
        refusals.append("scope.source_system is missing — nothing says where "
                        "this came from, so no anchor can be chosen")
    elif system not in ANCHORS:
        # Was only reachable from `anchor_for`, mid-plan.
        refusals.append(
            f"no anchor label for source_system {system!r}. Known: "
            f"{', '.join(sorted(ANCHORS))}. Adding one is an ontology change "
            f"under D-2, not an edit here")
    if not scope.get("primary_id"):
        refusals.append("scope.primary_id is missing — the artefact has no "
                        "identity in its own system")

    text = _requirement_text(document)
    if not text:
        refusals.append("neither metadata.title nor metadata.description has "
                        "any text — there is nothing to land")
    elif not check_ears_conformance(text).conformant:
        advisories.append(
            "the text is not EARS-conformant, so this lands as a Finding "
            "pointing at knowledge-capture and NOT as a Requirement (S-13). "
            "`ears_pattern` has no empty form and guessing one is what "
            "ac_mining refuses to do")

    claimed = (document.get("acceptance_criteria")
               or (document.get("metadata") or {}).get("acceptance_criteria"))
    if claimed:
        advisories.append(
            f"{len(claimed)} claimed acceptance criteria are present and will "
            "NOT be trusted into AcceptanceCriterion nodes — a criterion "
            "asserted by the document that raised the requirement is not "
            "independent evidence of it")

    return Conformance(tuple(refusals), tuple(advisories))


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

    outcome = conformance(document)
    if not outcome.conformant:
        raise IntakeRefused("; ".join(outcome.refusals))
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
    """The text a Requirement would be created from.

    **Whichever field is EARS-conformant wins**, and description only breaks the
    tie. Found by the tracker intake: a Jira story's *summary* is where the
    requirement-shaped sentence lives — "When a record has been archived, the
    system shall reject an update with 409" — and its description is context
    prose. Preferring description unconditionally threw the conforming sentence
    away and landed the ticket as a `Finding`.

    This **selects**, it never rewrites. Nothing is reshaped to make it pass,
    which is the line `ac_mining` refuses to cross (S-13); the only change is
    which of two verbatim fields is read. It can therefore only turn a Finding
    into a Requirement where the text already conformed, and never the reverse.
    """
    from metis_mcp.ears_checker import check_ears_conformance

    metadata = document.get("metadata", {})
    description = (metadata.get("description") or "").strip()
    title = (metadata.get("title") or "").strip()

    if description and check_ears_conformance(description).conformant:
        return description
    if title and check_ears_conformance(title).conformant:
        return title
    return description or title


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
            "search_text": search_text_for(requirement_id, text),
            "ears_pattern": ears.pattern,
            "revision": 1,
            "lifecycle_state": QUARANTINE,
            # Bi-temporal validity: `valid_from` is when this claim started
            # being true, `valid_to` is "" while it still is. Invalidation
            # sets `valid_to`; nothing is deleted (see landing.VALIDITY_FACTS).
            "valid_from": recorded, "valid_to": "",
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
            "search_text": search_text_for(name, description),
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
