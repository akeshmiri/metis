"""
The business glossary (application spec §4.6a; D-13).

**What this is for.** A criterion says *"when they archive a record"*. Two
questions follow immediately and neither had an answer: what is a record, and
what does archiving one actually change? Until now a business noun existed only
as words inside criterion prose, so nothing could be asked about it -- not what
it means, not what else touches it, not what a change to it would break.

Two levels, because the questions are different:

    BusinessArea     a domain -- Authentication, Records, Billing. Groups
                     entities and requirements. Answers "what else is in here".
    BusinessEntity   a noun -- User, Record, Session. Carries its properties and
                     the impact of acting on it. Answers "what am I touching".

**Deliberately not `Class`/`Field`.** Those are the evidence layer: what the code
declares. This is what the business means. The two disagree regularly, and that
disagreement is a finding (§4.1) -- collapsing them into one label to avoid the
mismatch would hide the divergence the platform exists to surface.

**A file, checked in, reviewed before it lands** -- the same discipline as
`knowledge.py`, and for the same reason: a definition everybody relies on should
be diffable and arguable in a pull request, not edited in a database.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field

from metis_mcp.identity.keys import business_entity_key
from pathlib import Path

FILE_VERSION = "metis.glossary/1"

UNKNOWN_AREA = "unknown_area"
DUPLICATE_ID = "duplicate_id"
MISSING_DESCRIPTION = "missing_description"
MISSING_IMPACT = "missing_impact"
BAD_PROPERTY = "bad_property"
ID_NOT_NATURAL_KEY = "id_not_natural_key"


@dataclass(frozen=True)
class EntityProperty:
    """One characteristic of a business noun.

    `meaning` is required and `values` is not: a property whose name is its own
    only explanation ("status: the status") is the kind of glossary entry that
    looks like documentation and answers nothing.
    """

    name: str
    meaning: str
    values: tuple[str, ...] = ()

    def describe(self) -> str:
        values = f" ({' | '.join(self.values)})" if self.values else ""
        return f"{self.name}{values} — {self.meaning}"


@dataclass(frozen=True)
class BusinessEntity:
    id: str
    name: str
    description: str
    area: str
    # **The half that makes this worth writing down.** A description says what a
    # noun is; `impact` says what changes when a criterion acts on it, which is
    # what an author or reviewer actually needs and what no schema records.
    impact: tuple[str, ...] = ()
    properties: tuple[EntityProperty, ...] = ()

    def glossary_block(self) -> list[str]:
        lines = [f"{self.name} — {self.description}"]
        for p in self.properties:
            lines.append(f"    {p.describe()}")
        for i in self.impact:
            lines.append(f"    impact: {i}")
        return lines


@dataclass(frozen=True)
class BusinessArea:
    id: str
    name: str
    description: str = ""


@dataclass(frozen=True)
class Problem:
    kind: str
    entry_id: str
    detail: str

    def describe(self) -> str:
        return f"[{self.kind:<20}] {self.entry_id}: {self.detail}"


@dataclass
class Glossary:
    areas: list[BusinessArea] = field(default_factory=list)
    entities: list[BusinessEntity] = field(default_factory=list)

    def entity(self, entity_id: str) -> BusinessEntity | None:
        return next((e for e in self.entities if e.id == entity_id), None)

    def entities_in(self, area_id: str) -> list[BusinessEntity]:
        return [e for e in self.entities if e.area == area_id]

    def to_json(self) -> str:
        return json.dumps({
            "glossary_version": FILE_VERSION,
            "areas": [asdict(a) for a in self.areas],
            "entities": [
                {**asdict(e), "properties": [asdict(p) for p in e.properties]}
                for e in self.entities
            ],
        }, indent=2) + "\n"


class GlossaryRefused(Exception):
    """The file could not be read at all — shape, not content."""


def load(path: str | Path) -> Glossary:
    data = json.loads(Path(path).read_text())
    version = data.get("glossary_version")
    if version != FILE_VERSION:
        raise GlossaryRefused(
            f"unknown glossary_version {version!r}; this build reads {FILE_VERSION!r}")
    return Glossary(
        areas=[BusinessArea(id=a["id"], name=a.get("name", a["id"]),
                            description=a.get("description", ""))
               for a in data.get("areas", [])],
        entities=[BusinessEntity(
            id=e["id"], name=e.get("name", e["id"]),
            description=e.get("description", ""), area=e.get("area", ""),
            impact=tuple(e.get("impact", ()) or ()),
            properties=tuple(EntityProperty(
                name=p["name"], meaning=p.get("meaning", ""),
                values=tuple(p.get("values", ()) or ()))
                for p in e.get("properties", []) or []),
        ) for e in data.get("entities", [])],
    )


def validate(glossary: Glossary) -> list[Problem]:
    """Every defect, named. Deterministic order."""
    problems: list[Problem] = []
    area_ids = {a.id for a in glossary.areas}

    seen: set[str] = set()
    for area in glossary.areas:
        if area.id in seen:
            problems.append(Problem(DUPLICATE_ID, area.id, "two areas share this id"))
        seen.add(area.id)

    seen = set()
    for entity in glossary.entities:
        if entity.id in seen:
            problems.append(Problem(DUPLICATE_ID, entity.id, "two entities share this id"))
        seen.add(entity.id)

        if not entity.description.strip():
            problems.append(Problem(
                MISSING_DESCRIPTION, entity.id,
                "no description: an entity nobody defined is a word, and the "
                "point of writing it down is that an author and a reviewer mean "
                "the same thing by it"))

        # I-2: the id must be the noun's natural key, because intake mints the
        # same key from a UIF's `data_model` name. Two minting rules meant
        # `api spec` landed twice -- once as the author's `apispec`, once as
        # intake's derived id -- and nothing said which was canonical. Caught
        # here, in the reviewable file, rather than as a duplicate in the graph.
        expected = business_entity_key(entity.name)
        if entity.id != expected:
            problems.append(Problem(
                ID_NOT_NATURAL_KEY, entity.id,
                f"id should be {expected!r}, the natural key of {entity.name!r}. "
                f"Intake derives that key from a UIF's data_model, so a different "
                f"id here lands the same noun twice with nothing marking either "
                f"as canonical (I-2)"))

        if not entity.impact:
            problems.append(Problem(
                MISSING_IMPACT, entity.id,
                "no impact recorded. A description says what this is; impact says "
                "what changes when a criterion acts on it — which is the half a "
                "schema cannot tell you and the half an author needs"))

        if entity.area and entity.area not in area_ids:
            problems.append(Problem(
                UNKNOWN_AREA, entity.id,
                f"area {entity.area!r} is not defined in this glossary"))

        for prop in entity.properties:
            if not prop.meaning.strip():
                problems.append(Problem(
                    BAD_PROPERTY, entity.id,
                    f"property {prop.name!r} has no meaning. A property whose "
                    f"name is its own only explanation documents nothing"))

    return problems


def entities_referenced_by(text: str, glossary: Glossary) -> list[str]:
    """The entity ids a criterion's own words mention. Literal, never a guess.

    Matched on the entity's `name` as a whole word, so `Record` does not match
    inside `Recording`. An entity the glossary does not define is simply not
    returned -- the omission is visible in the rendered Feature, where a missing
    noun is obvious, rather than being approximated by a similarity score. X-17
    is the same rule for criteria and transitions: name similarity is a candidate
    for review, never evidence.
    """
    lowered = text.lower()
    found = []
    for entity in glossary.entities:
        name = entity.name.strip().lower()
        if name and re.search(rf"\b{re.escape(name)}\b", lowered):
            found.append(entity.id)
    return found


def episode_id_for(glossary: Glossary) -> str:
    """Content-derived (D-8): re-landing an unchanged glossary is a no-op.

    Keyed on every area and entity, so editing one definition mints a new
    Episode and leaves the previous one intact as the record of what was
    believed before.
    """
    parts = []
    for area in sorted(glossary.areas, key=lambda a: a.id):
        parts.append(f"A|{area.id}|{area.name}|{area.description}")
    for entity in sorted(glossary.entities, key=lambda e: e.id):
        parts.append(f"E|{entity.id}|{entity.name}|{entity.description}|"
                     f"{entity.area}|{';'.join(entity.impact)}|"
                     + ";".join(p.describe() for p in entity.properties))
    return "ep-" + hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def plan_glossary(glossary: Glossary, episode_id: str = "",
                  job_id: str = "manual", t_recorded: str | None = None,
                  proposed_by: str = "") -> "LandingPlan":
    """Areas and entities as graph nodes, through the same ontology gate.

    **The Episode is planned here only when this glossary owns it.** Every node
    carries `source_episode_id` -- one of three baseline-required properties --
    and standing alone this used to plan entities pointing at an Episode nothing
    created, so the provenance they resolve through did not exist.

    But `workflow.handlers._knowledge_land` passes the *behaviour* plan's
    episode id, deliberately, so a knowledge run lands as one ingestion. There
    the Episode already exists and already carries that run's
    `source_connector`; MERGEing it again here would overwrite it with
    `"glossary"` and quietly relabel where the whole run came from. So an
    explicit `episode_id` means "somebody else owns this Episode" and none is
    planned.
    """
    from metis_mcp.model_sources.landing import LandingPlan, PlannedEdge, PlannedNode
    from metis_mcp.ontology.validation import validate as validate_node
    from metis_mcp.ontology.validation import validate_relationship

    owns_episode = not episode_id
    episode_id = episode_id or episode_id_for(glossary)
    recorded = t_recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")
    plan = LandingPlan(episode_id=episode_id)

    def add_node(label: str, props: dict) -> bool:
        outcome = validate_node(label, props)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return False
        plan.nodes.append(PlannedNode(label=label, properties=props))
        return True

    # Exempt from source_episode_id: it IS the provenance record (BASELINE_EXEMPT).
    if owns_episode:
        add_node("Episode", {
            "id": episode_id,
            "name": f"glossary: {len(glossary.areas)} area(s), "
                    f"{len(glossary.entities)} entities",
            "t_recorded": recorded,
            "source_connector": "glossary",
            "job_id": job_id,
            "proposed_by": proposed_by or "unknown",
        })

    for area in glossary.areas:
        add_node("BusinessArea", {
            "id": area.id, "source_episode_id": episode_id,
            "name": area.name, "description": area.description,
        })

    for entity in glossary.entities:
        ok = add_node("BusinessEntity", {
            "id": entity.id, "source_episode_id": episode_id,
            "name": entity.name, "description": entity.description,
            # JSON text, not nodes — D-13. The reader renders them all; nothing
            # queries one. Promote if that changes.
            "properties_json": json.dumps([asdict(p) for p in entity.properties],
                                          sort_keys=True),
            "impact": list(entity.impact),
        })
        if ok and entity.area:
            outcome = validate_relationship("BusinessEntity", "BELONGS_TO", "BusinessArea")
            if outcome.valid:
                plan.edges.append(PlannedEdge(
                    "BusinessEntity", entity.id, "BELONGS_TO",
                    "BusinessArea", entity.area))
            else:
                plan.errors.extend(outcome.errors)

    return plan


def format_problems(problems: list[Problem], glossary: Glossary) -> str:
    if not problems:
        return (f"Glossary — {len(glossary.areas)} area(s), "
                f"{len(glossary.entities)} entities, all defined.")
    lines = [f"Glossary — {len(problems)} problem(s); nothing is landed until "
             f"they are fixed.", ""]
    lines += [f"  {p.describe()}" for p in problems]
    return "\n".join(lines)
