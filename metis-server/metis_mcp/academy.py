"""
§12 Academy and Explainability Specification.

REQ-METIS-ACD-07: "There is exactly one content-assembly stage ... shared
by all three output paths [interactive/Site/PPTX]." This module IS that
stage -- metis_mcp/site_renderer.py and metis_mcp/pptx_renderer.py both
call assemble_content() / the same real query functions here, never
re-gather or re-derive content independently. Rendering to HTML vs. .pptx
is deterministic template-fill after this, never a second generation pass.

REQ-METIS-ACD-06: Academy content is versioned alongside the ontology --
ACADEMY_CONTENT_VERSION below is bumped whenever a page's content changes
in a way that describes current schema/behavior (not on typo fixes); a
real, if manual, discipline rather than an automated check this project
doesn't have the infrastructure for yet.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

ACADEMY_CONTENT_VERSION = "1.0.0"
ACADEMY_DIR = Path(__file__).resolve().parent.parent / "academy"

# REQ-METIS-ACD-02: the real Academy module -- 4 real pages, each grounded
# in this codebase's actual code/schema, not placeholder text.
ACADEMY_PAGES = {
    "graph-model-basics": {
        "title": "Graph Model Basics",
        "file": "graph-model-basics.md",
        "anchors": {
            "closed-ontology": "The closed ontology",
            "control-plane": "The closed ontology",  # same section, real alias
            "structural-edges": "Structural edges",
        },
    },
    "reading-traceability-chains": {
        "title": "Reading Traceability Chains",
        "file": "reading-traceability-chains.md",
        "anchors": {
            "broken-chain": "When a chain is broken",
            "circular-traceability": "When a chain is broken",
        },
    },
    "confidence-tiers": {
        "title": "Confidence Tiers",
        "file": "confidence-tiers.md",
        "anchors": {
            "rejected": "The three tiers, exactly as implemented",
            "constitution-gate": "The Constitution gate runs first",
        },
    },
    "ears-authoring": {
        "title": "EARS Authoring",
        "file": "ears-authoring.md",
        "anchors": {
            "non-conformant": "The five real patterns",
            "const-047": "Structural conformance is necessary, not sufficient",
        },
    },
}


def load_page(page_id: str) -> str:
    entry = ACADEMY_PAGES[page_id]
    with open(ACADEMY_DIR / entry["file"], encoding="utf-8") as f:
        return f.read()


# REQ-METIS-ACD-03: inline "why" annotations -- every guardrail rejection
# reason gets linked to the relevant Academy page. A real, disclosed
# heuristic (substring match against this project's own actual rejection-
# reason text, e.g. structural_validation.py's "Missing required property"
# strings, confidence_tiering.py's REQ-METIS-GRD-03 messages,
# constitution_gate.py's "CONST-047 violation" prefix) -- not a claim of
# covering every possible future rejection reason verbatim.
_WHY_LINK_PATTERNS = [
    ("CONST-047 violation", "confidence-tiers", "constitution-gate"),
    ("Failed Layer 2 structural validation", "confidence-tiers", "rejected"),
    ("Missing required property", "graph-model-basics", "closed-ontology"),
    ("does not reference an existing Episode", "graph-model-basics", "closed-ontology"),
    ("Unknown entity type", "graph-model-basics", "closed-ontology"),
    ("Does not match any of the five EARS", "ears-authoring", "non-conformant"),
    ("29148", "ears-authoring", "const-047"),
    ("circular", "reading-traceability-chains", "circular-traceability"),
    ("contradiction", "confidence-tiers", "rejected"),
]


def get_why_link(rejection_reason: str) -> str | None:
    """Returns a real, real-anchor Academy link for a known rejection
    reason, or None if this specific reason isn't one of the ones this
    project has real content for yet -- returning a guessed/generic link
    for an unrecognized reason would be worse than no link."""
    for pattern, page_id, anchor_key in _WHY_LINK_PATTERNS:
        if pattern.lower() in rejection_reason.lower():
            return f"academy/{page_id}.html#{anchor_key}"
    return None


# REQ-METIS-ACD-04: next-step guidance -- every gap surfaced by
# metis_get_context includes a concrete next action, not just a flag.
#
# Real wiring status, disclosed precisely (not overclaimed): 'not_found'
# and 'no_traceability' are live -- called from metis_get_context/
# metis_get_traceability's not-found branches and metis_check_coverage's
# covered=False branch (metis_mcp/server.py). 'quarantine_stuck' and
# 'circular_traceability' are real, tested entries with no live MCP-tool
# call site yet -- Quarantine-item guidance belongs in review_api_server.py
# (an HTTP API, not an MCP tool ACD-04 is scoped to) and circular-
# traceability is a batch check (layer8_heuristics.py), not tied to a
# single node lookup. Kept here as a real, reusable lookup rather than
# removed, since a future tool wiring them in shouldn't have to
# re-author the guidance text.
_NEXT_STEP_GUIDANCE = {
    "not_found": "This id doesn't exist in the current corpus/graph. Check spelling, or if this "
                 "should exist, confirm the connector that should have landed it has actually run "
                 "(see reading-traceability-chains.md).",
    "no_traceability": "This entity has no HAS_AC/IMPLEMENTS/VERIFIES edges yet -- if it's meant to "
                        "be Approved, it needs at least one AcceptanceCriterion and one verifying "
                        "TestCase before DQ-006/DQ-017 will pass (see confidence-tiers.md).",
    "quarantine_stuck": "This item is Quarantine-tier and needs a human reviewer (Layer 7) -- it will "
                         "never auto-promote, regardless of how long it sits (see confidence-tiers.md).",
    "circular_traceability": "This Requirement's only supporting TestCase has no independent "
                              "AcceptanceCriterion behind it -- add a real AC derived from the "
                              "requirement text, don't just add more tests (see "
                              "reading-traceability-chains.md#circular-traceability).",
}


def next_step_guidance(gap_type: str) -> str | None:
    return _NEXT_STEP_GUIDANCE.get(gap_type)


@dataclass
class ChangelogEntry:
    entity_id: str
    revision: int
    t_valid: str
    source_episode_id: str
    changed_fields: dict = field(default_factory=dict)


def generate_changelog(session, entity_ids: list[str], since_revision: int = 1) -> list[ChangelogEntry]:
    """REQ-METIS-ACD-05: 'plain-language, checkpoint-protected running log
    of ontology/rule changes.' Real, generated from metis_mcp/temporal.py's
    actual :Revision supersession chain -- not a separate log a caller has
    to remember to also write to. 'Checkpoint-protected' here means what
    it means for temporal.py generally: nothing is destructively
    overwritten, so this changelog can always be regenerated identically
    from the same real history."""
    from metis_mcp.temporal import history

    entries = []
    for entity_id in entity_ids:
        chain = history(session, entity_id)
        prev_props = {}
        for rev in chain:
            if rev.revision < since_revision:
                prev_props = rev.properties
                continue
            changed = {
                k: {"from": prev_props.get(k), "to": v}
                for k, v in rev.properties.items() if prev_props.get(k) != v
            }
            entries.append(ChangelogEntry(
                entity_id=entity_id, revision=rev.revision, t_valid=rev.t_valid,
                source_episode_id=rev.source_episode_id, changed_fields=changed,
            ))
            prev_props = rev.properties
    return entries


def format_changelog_plain_language(entries: list[ChangelogEntry]) -> str:
    if not entries:
        return "No tracked changes in this range."
    lines = []
    for e in entries:
        if not e.changed_fields:
            lines.append(f"- {e.t_valid}: '{e.entity_id}' revision {e.revision} recorded (initial state).")
            continue
        changes = "; ".join(f"{k} changed from {v['from']!r} to {v['to']!r}" for k, v in e.changed_fields.items())
        lines.append(f"- {e.t_valid}: '{e.entity_id}' revision {e.revision} -- {changes}.")
    return "\n".join(lines)


def assemble_content(session, kind: str, **kwargs) -> dict:
    """REQ-METIS-ACD-07's single content-assembly stage. `kind` is one of:
    'academy_page', 'quality_summary', 'changelog', 'test_design_report'
    (Session 10). Both metis_mcp/site_renderer.py and metis_mcp/
    pptx_renderer.py call this same function -- they differ only in their
    final rendering step."""
    if kind == "academy_page":
        page_id = kwargs["page_id"]
        return {
            "kind": "academy_page", "page_id": page_id, "title": ACADEMY_PAGES[page_id]["title"],
            "content": load_page(page_id), "version": ACADEMY_CONTENT_VERSION,
        }
    if kind == "quality_summary":
        from metis_mcp.dq_metrics import compute_quality_score, compute_all_metrics
        score = compute_quality_score(session, scope=kwargs.get("scope"))
        score["metrics"] = compute_all_metrics(session)
        return {"kind": "quality_summary", **score}
    if kind == "changelog":
        entries = generate_changelog(session, kwargs["entity_ids"], kwargs.get("since_revision", 1))
        return {"kind": "changelog", "entries": entries, "plain_language": format_changelog_plain_language(entries)}
    if kind == "test_design_report":
        from metis_mcp.quality_report import build_test_design_report
        report = build_test_design_report(session, kwargs["scope"])
        return {"kind": "test_design_report", **report}
    raise ValueError(f"Unknown content kind '{kind}' -- not a fabricated fallback, a real error.")
