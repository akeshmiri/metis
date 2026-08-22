"""
The knowledge-centre file (application spec §4.5, §4.6; S-13, S-19).

**What this is for.** A person states a requirement in ordinary language --
*"if a user has admin permission then they should be able to archive a record"*
-- and something has to turn that into acceptance criteria the rest of the
pipeline can use. `ac_mining` deliberately will not: it parses Given/When/Then
and EARS and **blocks free prose** rather than guessing at it (S-13, TR-4), and
that refusal is correct. Guessing is what produces a fluent, well-formed,
invented requirement.

So the formalisation happens where judgement belongs -- in a skill session, with
a person reading the result -- and this module is the **deterministic gate on
its output**. Nothing here calls a model. It reads a file, checks it, and either
hands `ac_mining` criteria it can parse or reports exactly what is wrong.

    prose  --(skill: judgement)-->  knowledge file  --(this: check)-->  ac_mining

**Knowledge has two stages, and they are different things.**

    stage 1  DOCUMENTATION   a Requirement and its atomic AcceptanceCriteria.
                             Text. Reviewable, diffable, and true or false on
                             its own terms, before any database exists.
    stage 2  GRAPH           the same facts as nodes in Neo4j, plus the
                             behaviour mined from them, plus the traceability
                             between the two.

Stage 1 is this file. Stage 2 is `landing`, and until now it wrote **only** the
behaviour: `Requirement` had no writer anywhere in the codebase, `HAS_AC` was
never created, and 255 `AcceptanceCriterion` nodes sat in the live graph with
nothing above them. `graph_writer.TRACE_CASE_CYPHER` already reads both -- so
"which requirement does this test case satisfy" resolved to null every time it
was asked. `plan_documentation` below is stage 1's landing.

**Why a file at all.** It is reviewable before anything touches the graph,
diffable, and version-controllable -- the same reasoning N-7 already applies to
review decisions, and the same three-file discipline `review.state` uses. The
graph is generated *from* it, so a disagreement is settled in a text file rather
than in a database.

**Two rules this file exists to enforce.**

1. **A criterion is atomic**: one condition, one action, one validation. A
   criterion carrying three conditions is three criteria wearing one id, and a
   reviewer can only accept or reject the bundle.
2. **An inferred criterion says that it is inferred.** Asked to record "an admin
   can archive", the honest complement is "a non-admin cannot archive" -- and
   nobody said that. It is Metis's inference, it must name the entry it is the
   complement of, and it reaches the graph as a candidate at `Quarantine` with a
   provenance grade that is **not** `human_confirmed` until a person edits or
   affirms it (S-19). Presenting an inference as something the person stated is
   precisely the fabrication S-13 exists to prevent.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import re

from metis_mcp.behavior_model import split_conjuncts
from metis_mcp.ears_checker import check_ears_conformance
from metis_mcp.model_sources.ac_mining import Criterion, _parse
from metis_mcp.mbt.model import QUARANTINE
from metis_mcp.ontology.labels import CODE_DERIVED

FILE_VERSION = "metis.knowledge/1"

# What the criterion asserts. A negative criterion is a first-class requirement,
# not the absence of a positive one: "a non-admin cannot archive" is a rule the
# system must enforce, and it needs its own test.
POSITIVE = "positive"
NEGATIVE = "negative"
POLARITIES = (POSITIVE, NEGATIVE)

# Where the criterion came from. The distinction is the whole point of the file.
STATED = "stated"
INFERRED_COMPLEMENT = "inferred_complement"
DERIVATIONS = (STATED, INFERRED_COMPLEMENT)

# Problem kinds. Each names one defect; they are never merged into a count.
UNPARSEABLE = "unparseable"
NOT_ATOMIC = "not_atomic"
UNGROUNDED_COMPLEMENT = "ungrounded_complement"
MISSING_SOURCE = "missing_source_statement"
BAD_VALUE = "bad_value"
DUPLICATE_ID = "duplicate_id"
NOT_EARS = "requirement_not_ears"
MISSING_REQUIREMENT = "missing_requirement"
ORPHANED_CRITERION = "orphaned_criterion"


@dataclass(frozen=True)
class KnowledgeEntry:
    """One atomic acceptance criterion, and where it came from."""

    id: str
    text: str
    requirement_id: str = ""
    polarity: str = POSITIVE
    derived: str = STATED
    # The human sentence this was formalised from. Required on every entry,
    # including inferred ones: without it there is no way to check the
    # formalisation against what was actually said.
    source_statement: str = ""
    # Required when `derived == INFERRED_COMPLEMENT`, and meaningless otherwise.
    complement_of: str = ""

    @property
    def is_inferred(self) -> bool:
        return self.derived == INFERRED_COMPLEMENT

    @property
    def provenance(self) -> str:
        """S-19's grade. Delegates, so there is exactly one definition of it."""
        return provenance_for(self)

    def to_criterion(self) -> Criterion:
        return Criterion(id=self.id, text=self.text,
                         requirement_id=self.requirement_id or None)


@dataclass(frozen=True)
class KnowledgeRequirement:
    """Stage 1's other half: the statement itself, in EARS.

    A criterion is atomic by rule (S-20), which means no single criterion ever
    carries the whole requirement. Something has to hold the requirement, or the
    graph gets a scatter of conditions with nothing saying what they are
    conditions OF -- which is the state the live graph was actually in.
    """

    id: str
    text: str

    @property
    def ears(self):
        return check_ears_conformance(self.text)


@dataclass(frozen=True)
class Problem:
    kind: str
    entry_id: str
    detail: str

    def describe(self) -> str:
        return f"[{self.kind:<22}] {self.entry_id}: {self.detail}"


@dataclass
class KnowledgeFile:
    model_id: str
    requirement: KnowledgeRequirement | None = None
    surface: str = "api"
    # The original, unedited words. Kept because every entry claims to be a
    # formalisation of it, and a claim nobody can check against its source is
    # not evidence.
    statement: str = ""
    entries: list[KnowledgeEntry] = field(default_factory=list)
    initial_state: str = ""
    # Which business domain this requirement governs (D-13). Optional: a
    # requirement with no area is a real state, not an error.
    area: str = ""
    # The `Specification` these criteria formalise, when there is one.
    #
    # `Specification -[:HAS_AC]-> AcceptanceCriterion` is in the catalogue and
    # had no writer, so the intent path from a Feature to the Scenarios that
    # demonstrate it could never fire -- the criteria existed and nothing said
    # which specified behaviour they belonged to. Optional: criteria that
    # formalise a requirement directly are still a real state.
    specification_id: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "knowledge_version": FILE_VERSION,
            "model_id": self.model_id,
            "surface": self.surface,
            "statement": self.statement,
            "specification": self.specification_id,
            "initial_state": self.initial_state,
            "area": self.area,
            "requirement": asdict(self.requirement) if self.requirement else None,
            "entries": [asdict(e) for e in self.entries],
        }, indent=2) + "\n"


class KnowledgeFileRefused(Exception):
    """The file could not be read at all -- shape, not content."""


def load(path: str | Path) -> KnowledgeFile:
    """Read a knowledge file. Refuses an unknown version rather than guessing.

    A version this build does not know may mean anything; reading it optimistically
    is how a field silently changes meaning between two releases.
    """
    data = json.loads(Path(path).read_text())
    version = data.get("knowledge_version")
    if version != FILE_VERSION:
        raise KnowledgeFileRefused(
            f"unknown knowledge_version {version!r}; this build reads {FILE_VERSION!r}")
    if not data.get("model_id"):
        raise KnowledgeFileRefused("model_id is required — a criterion with no model "
                                   "cannot be compared against anything")
    requirement = data.get("requirement") or None
    return KnowledgeFile(
        model_id=data["model_id"],
        requirement=(KnowledgeRequirement(id=requirement["id"], text=requirement["text"])
                     if requirement else None),
        surface=data.get("surface", "api"),
        statement=data.get("statement", ""),
        initial_state=data.get("initial_state", ""),
        area=data.get("area", ""),
        specification_id=data.get("specification", ""),
        entries=[KnowledgeEntry(
            id=e["id"], text=e["text"],
            requirement_id=e.get("requirement_id", ""),
            polarity=e.get("polarity", POSITIVE),
            derived=e.get("derived", STATED),
            source_statement=e.get("source_statement", ""),
            complement_of=e.get("complement_of", ""),
        ) for e in data.get("entries", [])],
    )


def _is_single(fragment: str) -> bool:
    """Whether a clause states exactly one thing.

    Empty counts as single: a criterion with no condition is normal (three of the
    login model's seventeen transitions are unguarded), and rejecting it would
    demand a condition where none exists.

    `split_conjuncts` returns `None` on a disjunction, which is the right answer
    here for the same reason it is there: `a OR b` is two things, and deciding
    which one the criterion means needs boolean reasoning nobody has done (M-17).
    """
    text = fragment.strip()
    if not text:
        return True
    parts = split_conjuncts(text)
    return parts is not None and len(parts) == 1


# The When..Then segment, so a conjoined ACTION can be told from a condition.
_WHEN_THEN = re.compile(r"\bwhen\b(?P<segment>.*?)\bthen\b", re.IGNORECASE | re.DOTALL)
# ` and ` that is NOT introducing a comma-delimited condition clause.
_BARE_AND = re.compile(r"(?<!,)\s+and\s+", re.IGNORECASE)


def check_atomic(text: str) -> str | None:
    """`None` if the criterion is atomic, else which clause carries more than one.

    One condition, one action, one validation. The clauses come from
    `ac_mining`'s own parser, so "atomic" is checked against exactly the reading
    the miner will take -- not against a second, private idea of the shape.

    **One case the parser alone cannot decide, and how it is decided here.**
    In *"when they archive a record and delete a record, then ..."* the regex's
    optional `and` clause swallows "delete a record" as though it were a
    condition, so every per-clause check passes and two actions go through as
    one criterion. English does not distinguish those two readings; punctuation
    does, and it is the punctuation this project already writes -- a condition
    clause is introduced by `, and`, which is exactly what `ac_drafting` emits
    and what §18's Given/When/Then uses. So a bare ` and ` inside the When..Then
    segment is a second action, and is reported as one rather than guessed at.
    """
    parsed = _parse(text)
    if parsed is None:
        return None  # unparseable is a different problem, reported separately

    # Per-clause first: when it fires it names the exact clause at fault, which
    # the segment check below cannot -- that one knows only that the segment
    # holds two things, not which.
    for clause, value in (("action (When)", parsed.get("when")),
                          ("condition (And)", parsed.get("and_guard")),
                          ("validation (Then)", parsed.get("then"))):
        if not _is_single(value or ""):
            return (f"the {clause} states more than one thing: {(value or '').strip()!r}. "
                    f"A criterion is atomic — one condition, one action, one "
                    f"validation — so this is several criteria under one id")

    segment = _WHEN_THEN.search(" ".join(text.split()))
    if segment and _BARE_AND.search(segment.group("segment")):
        return (f"the action (When) states more than one thing: "
                f"{segment.group('segment').strip().rstrip(',')!r}. A condition "
                f"clause is written `, and ...`; an unpunctuated `and` here joins "
                f"two actions, and a criterion has one")
    return None


def validate(knowledge: KnowledgeFile) -> list[Problem]:
    """Every defect in the file, each named. Deterministic order.

    Reports all of them rather than the first: a person fixing a file wants the
    whole list, and returning one at a time turns a single edit into six rounds.
    """
    problems: list[Problem] = []
    known_ids = {e.id for e in knowledge.entries}
    seen: set[str] = set()

    # Stage 1 is a Requirement AND its criteria. A file of bare criteria is a
    # scatter of conditions with nothing saying what they are conditions of.
    requirement = knowledge.requirement
    if requirement is None:
        problems.append(Problem(
            MISSING_REQUIREMENT, knowledge.model_id,
            "no requirement: criteria are atomic (S-20), so none of them carries "
            "the whole statement. Without one the criteria land with nothing "
            "above them, which is the state that made `TRACE_CASE_CYPHER`'s "
            "requirement hop return null for every test case ever traced"))
    else:
        ears = requirement.ears
        if not ears.conformant:
            problems.append(Problem(
                NOT_EARS, requirement.id,
                f"not EARS-conformant: {ears.reason}. `Requirement.ears_pattern` "
                f"is a required property, and force-tagging one that does not "
                f"hold would put an unchecked claim behind a checked field"))

    for entry in knowledge.entries:
        if entry.id in seen:
            problems.append(Problem(DUPLICATE_ID, entry.id,
                                    "two entries share this id; they would MERGE onto "
                                    "one node and one would silently disappear"))
        seen.add(entry.id)

        if entry.polarity not in POLARITIES:
            problems.append(Problem(BAD_VALUE, entry.id,
                                    f"polarity {entry.polarity!r} is not one of {POLARITIES}"))
        if entry.derived not in DERIVATIONS:
            problems.append(Problem(BAD_VALUE, entry.id,
                                    f"derived {entry.derived!r} is not one of {DERIVATIONS}"))

        if not entry.source_statement.strip():
            problems.append(Problem(
                MISSING_SOURCE, entry.id,
                "no source_statement: nothing records what this was formalised "
                "from, so the formalisation cannot be checked against it"))

        if _parse(entry.text) is None:
            problems.append(Problem(
                UNPARSEABLE, entry.id,
                "not in Given/When/Then or EARS 'While …, when …, the … shall …' "
                "shape. ac_mining parses these two and blocks everything else "
                "(S-13); a criterion it cannot read reaches the graph as nothing"))
        else:
            detail = check_atomic(entry.text)
            if detail:
                problems.append(Problem(NOT_ATOMIC, entry.id, detail))

        if entry.is_inferred:
            if not entry.complement_of:
                problems.append(Problem(
                    UNGROUNDED_COMPLEMENT, entry.id,
                    "an inferred complement must name the entry it is the "
                    "complement of. Nobody stated this criterion; without its "
                    "origin it is indistinguishable from something that was"))
            elif entry.complement_of not in known_ids:
                problems.append(Problem(
                    UNGROUNDED_COMPLEMENT, entry.id,
                    f"complement_of {entry.complement_of!r} names no entry in "
                    f"this file"))
            elif entry.complement_of == entry.id:
                problems.append(Problem(
                    UNGROUNDED_COMPLEMENT, entry.id,
                    "an entry cannot be its own complement"))
        elif entry.complement_of:
            problems.append(Problem(
                BAD_VALUE, entry.id,
                f"complement_of is set on a {STATED!r} entry, which claims both "
                f"that a person wrote it and that Metis derived it"))

        # Every criterion belongs to exactly one Requirement (`HAS_AC`). A
        # criterion naming a different requirement than the file's own would land
        # an edge from a node this file never wrote.
        if requirement is not None and entry.requirement_id \
                and entry.requirement_id != requirement.id:
            problems.append(Problem(
                ORPHANED_CRITERION, entry.id,
                f"requirement_id {entry.requirement_id!r} is not this file's "
                f"requirement ({requirement.id!r}). One file is one requirement "
                f"and its conditions"))

    return problems


def to_criteria(knowledge: KnowledgeFile) -> list[Criterion]:
    """The criteria `ac_mining.mine` should be given.

    Call `validate` first. This does not re-check: silently dropping invalid
    entries here would make the mined model quietly smaller than the file, which
    is the failure mode of every filter that fixes things on the way past.
    """
    return [e.to_criterion() for e in knowledge.entries]


def plan_documentation(knowledge: KnowledgeFile, episode_id: str,
                       criterion_transitions: dict | None = None,
                       glossary=None) -> "LandingPlan":
    """Stage 2 for stage 1's facts: `Requirement`, `AcceptanceCriterion`, `HAS_AC`.

    Built as a `LandingPlan` and written by `landing.land`, so these nodes go
    through the **same** ontology gate and the same human-fact preservation as
    every state and transition. A second, private writer for the documentation
    layer is how two halves of one graph come to disagree about what `Approved`
    means.

    **`VALIDATES` is minted here, and only for a transition this criterion's own
    text produced.** `demo_data/land_spec_criteria.py` refuses to mint it, and is
    right to: there the criteria arrive beside an independently-extracted model,
    so pairing them is a judgement, and F-7 holds a judgement for confirmation.
    Here the transition does not pre-exist -- it was mined FROM this criterion,
    and S-14 records the exact text span it came from. There is no candidate set,
    no similarity score and nothing to guess: the edge restates a derivation that
    already happened. Withholding it would report the criterion's own behaviour
    as unspecified, which is a false gap rather than a cautious one.

    What is NOT claimed by that edge is correctness. Every criterion here lands
    `code_derived` (S-19), so reconciliation counts these as documentation, not
    intent, until a person edits or affirms one.
    """
    from metis_mcp.model_sources.landing import (
        LandingPlan, PlannedEdge, PlannedNode, ensure_namespaced, transition_label_for,
    )
    from metis_mcp.ontology.validation import validate, validate_relationship

    plan = LandingPlan(episode_id=episode_id)
    mapping = criterion_transitions or {}

    def add_node(label: str, props: dict) -> bool:
        outcome = validate(label, props)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return False
        plan.nodes.append(PlannedNode(label=label, properties=props))
        return True

    def add_edge(from_label: str, from_id: str, rel: str,
                 to_label: str, to_id: str) -> None:
        outcome = validate_relationship(from_label, rel, to_label)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        plan.edges.append(PlannedEdge(from_label, from_id, rel, to_label, to_id))

    requirement = knowledge.requirement
    if requirement is None:
        plan.errors.append(
            "no requirement in the knowledge file — call validate() first")
        return plan

    if knowledge.area:
        add_edge("Requirement", requirement.id, "BELONGS_TO",
                 "BusinessArea", knowledge.area)

    ears = requirement.ears
    add_node("Requirement", {
        "id": requirement.id, "source_episode_id": episode_id,
        "name": requirement.id, "text": requirement.text,
        # Never force-tagged: the checker decides, and a non-conformant statement
        # was already refused by `validate` before reaching here.
        "ears_pattern": ears.pattern or "",
        "revision": 1,
        "lifecycle_state": QUARANTINE,
        "statement": knowledge.statement,
    })

    for entry in knowledge.entries:
        if not add_node("AcceptanceCriterion", {
            "id": entry.id, "source_episode_id": episode_id,
            "name": entry.id, "text": entry.text,
            "revision": 1,
            "lifecycle_state": QUARANTINE,
            "provenance": provenance_for(entry),
            "polarity": entry.polarity,
            # The two facts that keep an inference from reading as a statement.
            "derived": entry.derived,
            "complement_of": entry.complement_of,
            "source_statement": entry.source_statement,
        }):
            continue
        add_edge("Requirement", requirement.id, "HAS_AC",
                 "AcceptanceCriterion", entry.id)
        # The same criterion, reached from the specified behaviour it formalises.
        # Both edges are real and neither replaces the other: a requirement is
        # what was asked for, a specification is how it behaves, and §7.8's
        # chain runs through the first while the Feature path runs through the
        # second.
        if knowledge.specification_id:
            add_edge("Specification", knowledge.specification_id, "HAS_AC",
                     "AcceptanceCriterion", entry.id)
        # D-13's REFERENCES edge — what makes impact answerable in either
        # direction: which criteria touch this noun, and which nouns does this
        # requirement depend on. A catalogued relationship nothing wrote would be
        # exactly the dangling reference D-1 exists to prevent.
        if glossary is not None:
            from metis_mcp.model_sources.glossary import entities_referenced_by
            for entity_id in entities_referenced_by(entry.text, glossary):
                add_edge("AcceptanceCriterion", entry.id, "REFERENCES",
                         "BusinessEntity", entity_id)

        for transition_id in mapping.get(entry.id, ()):
            # The concrete label, not `Transition`: a classified transition is
            # written as `:ApiCall` or `:UiAction` INSTEAD of its parent, and an
            # edge planned against the parent passes the ontology check and then
            # matches no node at all.
            add_edge("AcceptanceCriterion", entry.id, "VALIDATES",
                     transition_label_for(knowledge.surface),
                     # The id the node is WRITTEN with: landing namespaces every
                     # element by model, so the bare mined id matches nothing.
                     # Idempotent: a mapping built from ids read OUT of the
                     # graph already carries the namespace, and prefixing twice
                     # produced `m::m::t` — an id no node has, so every
                     # VALIDATES edge matched nothing. Same defect `plan_persist`
                     # had; the fix had not reached here.
                     ensure_namespaced(knowledge.model_id, transition_id))

    return plan


def provenance_for(entry: KnowledgeEntry) -> str:
    """The S-19 grade a criterion reaches the graph with.

    **Always the weakest one, and deliberately so.** A criterion Metis
    formalised -- and more so one it inferred -- is not intent until a person
    edits or affirms it. `decisions.promotion_for` is what grants
    `HUMAN_CONFIRMED`, and only on a real edit or an explicit affirmation; this
    function must never anticipate that decision.
    """
    return CODE_DERIVED


def format_problems(problems: list[Problem], knowledge: KnowledgeFile) -> str:
    if not problems:
        inferred = sum(1 for e in knowledge.entries if e.is_inferred)
        lines = [f"Knowledge file — {knowledge.model_id}",
                 f"  {len(knowledge.entries)} criteria, all atomic and parseable.",
                 f"  {len(knowledge.entries) - inferred} stated, {inferred} inferred."]
        if inferred:
            lines += ["",
                      "  The inferred criteria were NOT stated by anyone. They are "
                      "Metis's",
                      "  complements of the stated ones, and they land at Quarantine "
                      "as",
                      "  code_derived — read them before approving (S-19)."]
        return "\n".join(lines)

    lines = [f"Knowledge file — {knowledge.model_id}",
             f"  {len(problems)} problem(s); nothing is mined until they are fixed.",
             ""]
    lines += [f"  {p.describe()}" for p in problems]
    return "\n".join(lines)
