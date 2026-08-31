"""
The intent file: what somebody wants, and how they say it behaves (§4.1, §4.5).

**Two things are authored here and one deliberately is not.**

    Intent          a stated need, in ordinary language. "Users should be able
                    to archive a record."
    Specification   how that need behaves, stated so it can be checked.
    ---------------------------------------------------------------
    Feature         NOT authored. Métis derives it -- see `feature.py` -- and
                    reports what it could not derive rather than inventing a
                    grouping nobody chose.

**Why a file, checked in, reviewed in a pull request.** The same discipline
`knowledge.py` and `glossary.py` keep, for the same reason: a statement
everybody relies on should be diffable and arguable before it is a node. This
module is the deterministic gate on that file. Nothing here calls a model. It
reads, checks, and either produces a landing plan or reports exactly what is
wrong.

**Provenance is required on every specification, and there is no default.**
`Specification.provenance` is what keeps §4.1's comparison alive: the same node
is reached from intent (`SPECIFIED_BY`) and from code (`IMPLEMENTS`), and the
grade is what says which. A specification a person wrote is
`independently_authored`; one decoded from an endpoint is `code_derived`, and
only the first two count as intent. Letting this default would silently promote
extraction output to intent, which is the one claim this platform must never
make.

**An Intent with no Specification is refused, not landed.** A need nobody has
said the behaviour of is a wish, and landing it would put a node in the graph
that nothing can ever be checked against -- the dangling reference D-1 exists to
prevent.
"""
from __future__ import annotations


import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from metis_mcp.identity.keys import business_entity_key
from metis_mcp.mbt.model import QUARANTINE
from metis_mcp.ontology.labels import (
    CODE_DERIVED,
    HUMAN_CONFIRMED,
    INDEPENDENTLY_AUTHORED,
)
from metis_mcp.retrieval import search_text_for

FILE_VERSION = "metis.intent/1"

INTENT_GRADES = (HUMAN_CONFIRMED, INDEPENDENTLY_AUTHORED)

# Problem kinds. Each names what is wrong, so a reader fixes the file rather
# than guessing at the checker.
UNKNOWN_VERSION = "unknown_version"
NO_STATEMENT = "no_statement"
NO_SPECIFICATION = "no_specification"
DUPLICATE_ID = "duplicate_id"
BAD_PROVENANCE = "bad_provenance"
CODE_DERIVED_AUTHORED = "code_derived_authored"
UNKNOWN_INTENT = "unknown_intent"
VAGUE_STATEMENT = "vague_statement"
UNKNOWN_CONTRACT = "unknown_contract_kind"
MISSING_CONTRACT = "contract_file_missing"

# What a specification may point at. These are **published contracts**, not the
# code: an OpenAPI document states what the service promises, and a structure
# file states what a screen presents and where the data lives. `M-13` keeps that
# distinct from static analysis for a reason a reviewer feels immediately -- "the
# document says this" and "the code does this" are different claims, and the
# `declared_contract` extraction method exists to carry the difference.
#
# So a specification does NOT generate an endpoint from its own prose. It names
# the contract, and the contract is what is parsed. That is what keeps building
# Endpoint/Page/Action off a specification from being circular: the prose never
# invents an endpoint, it only says which document to read.
CONTRACT_OPENAPI = "openapi"
# `structure` was a second contract kind, building Page/UiElement/Action from an
# authored file. Removed with the UI structure layer.
CONTRACT_KINDS = (CONTRACT_OPENAPI,)

# Words that make a statement unfalsifiable. Not a style rule: a specification
# nobody can disagree with cannot be compared against code either, which makes
# it useless for the one thing §4.1 asks of it.
_VAGUE = ("appropriate", "properly", "correctly", "as expected", "efficiently",
          "user-friendly", "robust", "seamless", "intuitive", "reasonable")


class IntentFileRefused(Exception):
    """The file could not be read at all -- shape, not content."""


@dataclass(frozen=True)
class Problem:
    kind: str
    entry_id: str
    detail: str

    def describe(self) -> str:
        return f"[{self.kind:<22}] {self.entry_id}: {self.detail}"


@dataclass(frozen=True)
class Specification:
    """How a need behaves, stated so it can be checked."""

    id: str
    statement: str
    intent_id: str
    provenance: str = INDEPENDENTLY_AUTHORED
    # The business nouns this behaviour is about. Used by `feature.py` to group
    # specifications, and matched against the glossary's own keys (I-2).
    entities: tuple[str, ...] = ()
    # The published contracts this behaviour is stated in. Métis builds the
    # Endpoint, Page and Action layer from these -- see `spec_build.py` -- and
    # links each back with `IMPLEMENTS`, which is the code side of §4.1's
    # comparison.
    contracts: tuple[tuple[str, str], ...] = ()
    # An existing Requirement this specifies, when there is one. Optional: the
    # spec's §7.8 chain reaches a Requirement, and this is the edge that keeps
    # A-24 resolvable when intent arrives before a requirement does.
    requirement_id: str = ""

    @property
    def is_intent(self) -> bool:
        return self.provenance in INTENT_GRADES


@dataclass(frozen=True)
class Intent:
    """A stated need, before anybody has said how it behaves."""

    id: str
    statement: str


@dataclass
class IntentFile:
    intents: list[Intent] = field(default_factory=list)
    specifications: list[Specification] = field(default_factory=list)
    # Which area these belong to, when the author says. Optional.
    area: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "intent_version": FILE_VERSION,
            "area": self.area,
            "intents": [{"id": i.id, "statement": i.statement} for i in self.intents],
            "specifications": [
                {"id": s.id, "statement": s.statement, "intent": s.intent_id,
                 "provenance": s.provenance, "entities": list(s.entities),
                 "contracts": [{"kind": k, "path": p} for k, p in s.contracts],
                 "requirement": s.requirement_id}
                for s in self.specifications
            ],
        }, indent=2)


def load(path: str | Path) -> IntentFile:
    """Read an intent file, refusing a shape this cannot land."""
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise IntentFileRefused(str(e)) from e

    version = raw.get("intent_version", "")
    if version != FILE_VERSION:
        raise IntentFileRefused(
            f"intent_version {version!r} is not {FILE_VERSION!r} — refused rather "
            f"than read optimistically, because a field that has quietly changed "
            f"meaning is worse than a file that will not open")

    return IntentFile(
        area=raw.get("area", ""),
        intents=[Intent(id=i.get("id", ""), statement=(i.get("statement") or "").strip())
                 for i in raw.get("intents", [])],
        specifications=[
            Specification(
                id=s.get("id", ""),
                statement=(s.get("statement") or "").strip(),
                intent_id=s.get("intent", ""),
                provenance=s.get("provenance", INDEPENDENTLY_AUTHORED),
                entities=tuple(s.get("entities", ())),
                contracts=tuple(
                    (c.get("kind", ""), c.get("path", ""))
                    for c in s.get("contracts", ())),
                requirement_id=s.get("requirement", ""),
            )
            for s in raw.get("specifications", [])
        ],
    )


def validate(document: IntentFile) -> list[Problem]:
    """Every defect, named, in a deterministic order."""
    problems: list[Problem] = []

    seen: set[str] = set()
    for intent in document.intents:
        if not intent.id:
            problems.append(Problem(NO_STATEMENT, "<no id>", "an intent needs an id"))
            continue
        if intent.id in seen:
            problems.append(Problem(DUPLICATE_ID, intent.id, "two intents share this id"))
        seen.add(intent.id)
        if not intent.statement:
            problems.append(Problem(
                NO_STATEMENT, intent.id,
                "no statement. An intent with no words is a label, and nothing "
                "downstream can be checked against a label"))

    intent_ids = {i.id for i in document.intents}
    spec_seen: set[str] = set()
    specified: set[str] = set()

    for spec in document.specifications:
        if not spec.id:
            problems.append(Problem(NO_STATEMENT, "<no id>", "a specification needs an id"))
            continue
        if spec.id in spec_seen:
            problems.append(Problem(DUPLICATE_ID, spec.id, "two specifications share this id"))
        spec_seen.add(spec.id)

        if not spec.statement:
            problems.append(Problem(
                NO_STATEMENT, spec.id,
                "no statement. A specification is the sentence the code is "
                "compared against; there is nothing to compare to"))

        if spec.intent_id not in intent_ids:
            problems.append(Problem(
                UNKNOWN_INTENT, spec.id,
                f"intent {spec.intent_id!r} is not in this file. A specification "
                f"exists to say how a stated need behaves, so it cannot float free"))
        else:
            specified.add(spec.intent_id)

        if spec.provenance not in (CODE_DERIVED, *INTENT_GRADES):
            problems.append(Problem(
                BAD_PROVENANCE, spec.id,
                f"provenance {spec.provenance!r} is not one of "
                f"{CODE_DERIVED}, {HUMAN_CONFIRMED}, {INDEPENDENTLY_AUTHORED}"))
        elif spec.provenance == CODE_DERIVED:
            problems.append(Problem(
                CODE_DERIVED_AUTHORED, spec.id,
                "a specification written BY HAND cannot be `code_derived`. That "
                "grade means Métis decoded it from an endpoint, and claiming it "
                "here would make an authored sentence look like evidence about "
                "the code (§4.1)"))

        # Matched on the word STEM, with no trailing boundary: "appropriate"
        # has to catch "appropriately", which is the form people actually write.
        # A trailing `\b` matched the adjective and missed every adverb, so the
        # check passed on "handle archiving appropriately" — the exact sentence
        # it exists to reject.
        for kind, contract_path in spec.contracts:
            if kind not in CONTRACT_KINDS:
                problems.append(Problem(
                    UNKNOWN_CONTRACT, spec.id,
                    f"contract kind {kind!r} is not one of "
                    f"{', '.join(CONTRACT_KINDS)}"))
            elif not contract_path or not Path(contract_path).exists():
                problems.append(Problem(
                    MISSING_CONTRACT, spec.id,
                    f"{contract_path!r} does not exist. A specification that "
                    f"names a contract nobody can read is a claim about a "
                    f"document, not a link to one"))

        vague = [w for w in _VAGUE
                 if re.search(rf"\b{re.escape(w)}", spec.statement.lower())]
        if vague:
            problems.append(Problem(
                VAGUE_STATEMENT, spec.id,
                f"{', '.join(repr(v) for v in vague)} makes this unfalsifiable. A "
                f"sentence nobody can disagree with cannot be compared against "
                f"code either, which is the only job it has"))

    for intent in document.intents:
        if intent.id and intent.id not in specified:
            problems.append(Problem(
                NO_SPECIFICATION, intent.id,
                "no specification says how this behaves. A need nobody has "
                "specified is a wish, and landing it would put a node in the "
                "graph that nothing can ever be checked against"))

    return problems


def episode_id_for(document: IntentFile) -> str:
    """Content-derived (D-8): re-landing an unchanged file is a no-op."""
    parts = [f"A|{document.area}"]
    for i in sorted(document.intents, key=lambda x: x.id):
        parts.append(f"I|{i.id}|{i.statement}")
    for s in sorted(document.specifications, key=lambda x: x.id):
        parts.append(f"S|{s.id}|{s.statement}|{s.intent_id}|{s.provenance}|"
                     f"{','.join(sorted(s.entities))}|{s.requirement_id}|"
                     f"{','.join(f'{k}:{p}' for k, p in sorted(s.contracts))}")
    return "ep-" + hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def plan_intent(document: IntentFile, episode_id: str = "", job_id: str = "manual",
                proposed_by: str = "", t_recorded: str | None = None):
    """`Intent`, `Specification`, and the edges between them. Pure.

    No `Feature` is planned here, deliberately. A feature is a grouping, and
    grouping is a judgement Métis makes from evidence it has -- the glossary,
    the code, or a person -- not something an author restates by hand. See
    `feature.derive`.
    """
    from metis_mcp.model_sources.landing import LandingPlan, PlannedEdge, PlannedNode
    from metis_mcp.ontology.validation import validate as validate_node
    from metis_mcp.ontology.validation import validate_relationship

    owns_episode = not episode_id
    episode_id = episode_id or episode_id_for(document)
    recorded = t_recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")
    plan = LandingPlan(episode_id=episode_id)

    def add_node(label: str, props: dict) -> bool:
        outcome = validate_node(label, props)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return False
        plan.nodes.append(PlannedNode(label=label, properties=props))
        return True

    def add_edge(from_label: str, from_id: str, rel: str, to_label: str, to_id: str) -> None:
        outcome = validate_relationship(from_label, rel, to_label)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        plan.edges.append(PlannedEdge(from_label, from_id, rel, to_label, to_id))

    if owns_episode:
        add_node("Episode", {
            "id": episode_id,
            "name": f"intent: {len(document.intents)} need(s), "
                    f"{len(document.specifications)} specification(s)",
            "t_recorded": recorded,
            "source_connector": "intent",
            "job_id": job_id,
            "proposed_by": proposed_by or "unknown",
        })

    for intent in document.intents:
        add_node("Intent", {
            "id": intent.id, "source_episode_id": episode_id,
            "name": intent.id, "statement": intent.statement,
            "search_text": search_text_for(intent.id, intent.statement),
            "lifecycle_state": QUARANTINE,
            # Bi-temporal validity: `valid_from` is when this claim started
            # being true, `valid_to` is "" while it still is. Invalidation
            # sets `valid_to`; nothing is deleted (see landing.VALIDITY_FACTS).
            "valid_from": recorded, "valid_to": "",
        })

    for spec in document.specifications:
        if not add_node("Specification", {
            "id": spec.id, "source_episode_id": episode_id,
            "name": spec.id, "statement": spec.statement,
            "search_text": search_text_for(spec.id, spec.statement),
            "provenance": spec.provenance,
            # The nouns it is about, normalised through the shared natural key so
            # a specification and the glossary agree about what `api spec` is.
            "entities": [business_entity_key(e) for e in spec.entities],
            # Recorded so the graph says what this behaviour was built from,
            # without anybody re-reading the file to find out (F-12).
            "contracts_json": json.dumps(
                [{"kind": k, "path": p} for k, p in spec.contracts], sort_keys=True),
            "lifecycle_state": QUARANTINE,
            # Bi-temporal validity: `valid_from` is when this claim started
            # being true, `valid_to` is "" while it still is. Invalidation
            # sets `valid_to`; nothing is deleted (see landing.VALIDITY_FACTS).
            "valid_from": recorded, "valid_to": "",
        }):
            continue
        add_edge("Intent", spec.intent_id, "SPECIFIED_BY", "Specification", spec.id)
        if spec.requirement_id:
            add_edge("Specification", spec.id, "SPECIFIES",
                     "Requirement", spec.requirement_id)

    return plan


def format_problems(problems: list[Problem], document: IntentFile) -> str:
    if not problems:
        return (f"Intent file — {len(document.intents)} need(s), "
                f"{len(document.specifications)} specification(s), all checkable.")
    lines = [f"Intent file — {len(problems)} problem(s); nothing is landed until "
             f"they are fixed.", ""]
    lines += [f"  {p.describe()}" for p in problems]
    return "\n".join(lines)
