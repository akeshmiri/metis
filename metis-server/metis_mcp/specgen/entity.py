"""
Business-entity specification (application spec §4.6a, §18; D-13).

**What this is for.** `specification.py` renders one *journey* — how a surface
behaves, as the interacting party experiences it. That is the right document for
"what happens when somebody logs in" and the wrong one for "what is a record,
and what breaks if I change it".

A business noun is the unit people actually reason about. It cuts across
journeys: `record` is touched by archive, restore and export, which live in
different flows and different surfaces. Until now the noun existed as a
`BusinessEntity` node with nothing rendering it, so the definition everybody
relied on could be queried and never read.

**Everything here is already in the graph.** Nothing is inferred:

    name, description, area          BusinessEntity, BELONGS_TO
    properties (name, meaning)       properties_json
    impact — what acting on it does  impact
    the criteria that touch it       AcceptanceCriterion-[:REFERENCES]->
    the requirements behind those    Requirement-[:HAS_AC]->
    the behaviour they validate      AcceptanceCriterion-[:VALIDATES]->

**The round trip stays closed.** Every rule carries the same stable
`AC-<id>:` heading `specification.py` emits and `spec_kit._AC_HEADING` reads
back, so an entity document a person has edited parses into the criteria it came
from. A document that renders to headings nothing can parse is a dead end, and
the journey specification learned that the expensive way — it parsed back to
*zero* criteria before the heading was stable.

**Provenance is rendered, not summarised away.** A criterion graded
`code_derived` was written from the code and can only ever report agreement with
it (§4.1). Showing an entity's criteria without their grades would present
coverage as correctness, which is the one claim this platform exists not to
make.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from metis_mcp.ontology.labels import (
    CODE_DERIVED,
    HUMAN_CONFIRMED,
    INDEPENDENTLY_AUTHORED,
)
from metis_mcp.specgen.specification import SPEC_VERSION, humanise

# Which grades count as intent. `code_derived` does not: it is the circularity
# §4.1 names, and the whole point of showing the grade is that a reader can tell
# the difference without being told.
INTENT_GRADES = (HUMAN_CONFIRMED, INDEPENDENTLY_AUTHORED)


@dataclass(frozen=True)
class EntityProperty:
    """One characteristic, as the glossary defined it."""

    name: str
    meaning: str
    values: tuple[str, ...] = ()

    def render(self) -> str:
        values = f" — one of {', '.join(f'`{v}`' for v in self.values)}" if self.values else ""
        return f"- **{self.name}** — {self.meaning}{values}"


@dataclass(frozen=True)
class EntityRule:
    """One acceptance criterion that touches this entity."""

    # The id the node actually carries. Used for `CITES`, and for nothing else.
    criterion_id: str
    text: str
    provenance: str
    lifecycle_state: str
    requirement_id: str = ""
    transition_ids: tuple[str, ...] = ()

    @property
    def heading_id(self) -> str:
        """The `AC-` form `spec_kit._AC_HEADING` can parse out of the markdown.

        **Display only.** It was briefly the same value as `criterion_id`, which
        meant a criterion whose real id is `records-spec-api-ac1` got cited as
        `AC-records-spec-api-ac1` -- an id no node carries, so every `CITES` edge
        matched nothing. Exactly the mistake `plan_spec_document` makes with
        `Rule.criterion_id`, repeated here.

        A document heading has to be parseable; an edge has to be true. They are
        different requirements and need different values.
        """
        return self.criterion_id if self.criterion_id.startswith("AC-") \
            else f"AC-{self.criterion_id}"

    @property
    def is_intent(self) -> bool:
        """False for `code_derived`: written from the code, so agreeing with the
        code proves nothing (§4.1)."""
        return self.provenance in INTENT_GRADES

    @property
    def title(self) -> str:
        """A readable label. The criterion's own words, trimmed — never the id,
        which tells a reader nothing (SP-1)."""
        first = self.text.strip().split("\n")[0].strip()
        return first[:97] + "…" if len(first) > 100 else first

    @property
    def heading(self) -> str:
        """`AC-<id>: <what it says>` — the form `spec_kit` reads back."""
        return f"{self.heading_id}: {self.title}"


@dataclass
class EntitySpec:
    """One business noun, fully described."""

    entity_id: str
    name: str
    description: str
    area: str = ""
    area_name: str = ""
    version: str = SPEC_VERSION
    generated_at: str = ""
    impact: tuple[str, ...] = ()
    properties: tuple[EntityProperty, ...] = ()
    rules: list[EntityRule] = field(default_factory=list)
    # F-10: what was left out is named rather than quietly absent.
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def intent_rules(self) -> list[EntityRule]:
        return [r for r in self.rules if r.is_intent]

    @property
    def code_derived_rules(self) -> list[EntityRule]:
        return [r for r in self.rules if r.provenance == CODE_DERIVED]

    @property
    def requirement_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(r.requirement_id for r in self.rules if r.requirement_id))

    @property
    def transition_ids(self) -> tuple[str, ...]:
        out: list[str] = []
        for rule in self.rules:
            out.extend(rule.transition_ids)
        return tuple(dict.fromkeys(out))

    @property
    def content_hash(self) -> str:
        """Content-derived (D-8), and deliberately **excludes** `generated_at`.

        Re-rendering an unchanged entity must be a no-op. Hashing the timestamp
        would make every regeneration a new document and defeat the MERGE that
        keeps this idempotent.
        """
        parts = [self.entity_id, self.name, self.description, self.area,
                 "|".join(self.impact)]
        for p in sorted(self.properties, key=lambda x: x.name):
            parts.append(f"P|{p.name}|{p.meaning}|{'/'.join(p.values)}")
        for r in sorted(self.rules, key=lambda x: x.criterion_id):
            parts.append(f"R|{r.criterion_id}|{r.text}|{r.provenance}|"
                         f"{r.lifecycle_state}|{'/'.join(r.transition_ids)}")
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]

    @property
    def document_id(self) -> str:
        return f"entdoc-{self.entity_id}"


def build(entity: dict, criteria: list[dict] | None = None,
          area_name: str = "", generated_at: str = "") -> EntitySpec:
    """Assemble one entity's specification from graph rows.

    `entity` and `criteria` are plain dicts as the loader returns them, so this
    stays pure and testable with no database — the same discipline the rest of
    the engine keeps.
    """
    raw_properties = entity.get("properties_json") or "[]"
    try:
        parsed = json.loads(raw_properties)
    except (TypeError, ValueError):
        parsed = []

    properties = tuple(
        EntityProperty(name=p.get("name", ""), meaning=p.get("meaning", ""),
                       values=tuple(p.get("values", ()) or ()))
        for p in parsed if p.get("name")
    )

    rules: list[EntityRule] = []
    skipped: list[tuple[str, str]] = []
    for row in criteria or []:
        cid = row.get("id") or ""
        if not cid:
            skipped.append(("<no id>", "criterion has no id — cannot be cited"))
            continue
        rules.append(EntityRule(
            # The real id, verbatim. Prefixing happens at render time only.
            criterion_id=cid,
            text=row.get("text") or "",
            provenance=row.get("provenance") or CODE_DERIVED,
            lifecycle_state=row.get("lifecycle_state") or "",
            requirement_id=row.get("requirement_id") or "",
            # `collect(DISTINCT t.id)` yields `[null]` when a criterion
            # validates nothing, and a null here renders as a citation to a
            # transition that does not exist. Stripped at this boundary because
            # `build` takes plain dicts from anywhere, not only the loader.
            transition_ids=tuple(
                t for t in (row.get("transition_ids") or ()) if t),
        ))

    return EntitySpec(
        entity_id=entity.get("id", ""),
        name=entity.get("name", ""),
        description=entity.get("description", ""),
        area=entity.get("area", ""),
        area_name=area_name or entity.get("area", ""),
        generated_at=generated_at,
        impact=tuple(entity.get("impact") or ()),
        properties=properties,
        rules=sorted(rules, key=lambda r: r.criterion_id),
        skipped=skipped,
    )


def render_markdown(spec: EntitySpec, coverage_summary: str = "") -> str:
    """The entity document.

    Deterministic: the same inputs and the same `generated_at` produce identical
    bytes, so a regeneration that changes nothing is byte-identical and the
    content hash proves it.
    """
    out: list[str] = [
        f"# {humanise(spec.name)} — business entity",
        "",
        "*Generated from the graph. Not authored — every statement below traces "
        "to a glossary entry or an acceptance criterion (SP-1, SP-2).*",
        "",
    ]

    if spec.area_name:
        out += [f"**Area:** {humanise(spec.area_name)}", ""]

    out += ["## What it is", "", spec.description or "_No description recorded._", ""]

    if spec.impact:
        out += ["## What changes when you act on it", "",
                "*The half a schema cannot record: a description says what this "
                "noun is, impact says what acting on it does.*", ""]
        out += [f"- {line}" for line in spec.impact]
        out.append("")

    out += ["## Properties", ""]
    if spec.properties:
        out += [p.render() for p in spec.properties]
    else:
        out.append("_None recorded._")
    out.append("")

    out += ["## Rules that touch it", ""]
    if not spec.rules:
        out += ["_No acceptance criterion references this entity yet._", ""]
    else:
        if spec.code_derived_rules:
            out += [
                f"> **⚠ {len(spec.code_derived_rules)} of {len(spec.rules)} rules are "
                f"`code_derived`.** They were written from the code, so their "
                f"agreeing with it is not evidence that the behaviour is correct "
                f"(§4.1) — only that it is covered. They are marked below.",
                "",
            ]
        for rule in spec.rules:
            out.append(f"### {rule.heading}")
            out.append("")
            out.append(rule.text.strip() or "_No text recorded._")
            out.append("")
            grade = "intent" if rule.is_intent else "**code-derived — coverage, not correctness**"
            out.append(f"- Provenance: {rule.provenance} ({grade})")
            if rule.lifecycle_state:
                out.append(f"- Lifecycle: {rule.lifecycle_state}")
            if rule.requirement_id:
                out.append(f"- Requirement: `{rule.requirement_id}`")
            if rule.transition_ids:
                out.append(f"- Validates: {', '.join(f'`{t}`' for t in rule.transition_ids)}")
            out.append("")

    out += ["## What is tested", "",
            coverage_summary or "No coverage has been computed for this entity.",
            "",
            "*This states what is **tested**, not what is **working** (C-10, C-11).*",
            ""]

    if spec.skipped:
        out += ["## Left out", "",
                "*Named rather than quietly absent (F-10).*", ""]
        out += [f"- `{what}` — {why}" for what, why in spec.skipped]
        out.append("")

    out += ["---", "",
            f"<!-- metis:entity-document id={spec.document_id} "
            f"entity={spec.entity_id} content_hash={spec.content_hash} -->"]
    return "\n".join(out)
