"""
The specification as Gherkin (application spec §18; SP-1, SP-7, §7.8).

**One Requirement is one Feature; one AcceptanceCriterion is one Scenario.** That
is Cucumber's own convention -- a Feature is a user-facing capability and a
Scenario is an example of it -- and it is only expressible now that `Requirement`
and `HAS_AC` exist. Before them a criterion had nothing above it to be a Feature.

**Not executable, and it says so.** R8 is that Métis emits test cases rather than
executable test code, and a `.feature` file with no step definitions behind it is
a specification that happens to be machine-readable. It is not a test suite, and
presenting it as one would claim a capability that does not exist.

**Every traceability fact rides in a tag** (§7.8), because a tag survives the
round trip and a comment does not. The tags are not decoration: `@inferred` is
how a criterion Métis derived stays distinguishable from one a person wrote, and
`@code_derived` is S-19's grade -- a criterion written from the code can report
agreement and never correctness, and a reader is owed that on the page.

Gherkin is written and parsed here by hand rather than through a library. The
same reasoning `ac_mining` records: the shapes are small and regular, a regex
fails by *missing* something and reporting it, and adding a dependency to parse
four keywords buys nothing this codebase does not already do.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

INDENT = "  "
STEP_INDENT = INDENT * 2

# What a Scenario's tags carry. Each is a fact a reader needs and a round trip
# must not lose.
TAG_AC = "ac"
TAG_REQUIREMENT = "requirement"
TAG_AREA = "area"
TAG_ENTITY = "entity"
TAG_TRANSITION = "transition"


def _slug(text: str) -> str:
    """A tag-safe token. Gherkin tags cannot contain whitespace."""
    return re.sub(r"[^A-Za-z0-9_.:-]+", "-", text.strip()).strip("-") or "unnamed"


# The clause boundaries of a Given/When/Then sentence, in the author's own words.
#
# **Why not `ac_mining._parse`'s groups.** That regex strips `the`, `user is` and
# `they` on purpose: the state it mines is `slug(given)`, and `LoggedOut` is the
# right id where `TheUserIsLoggedOut` is not. Rendering from those groups turned
# "Given the user has admin permission, when they archive a record" into "Given
# user has admin permission, when archive a record" -- a silent rewording of a
# sentence a person wrote, which is exactly what the spec round trip's
# `test_human_wording_survives_regeneration` exists to prevent.
#
# So: parse to CHECK, slice to RENDER.
_GWT_SPLIT = re.compile(
    r"^\s*given\s+(?P<given>.+?)"
    r"[,\s]+when\s+(?P<when>.+?)"
    r"(?:[,\s]+and\s+(?P<and_guard>.+?))?"
    r"[,\s]+then\s+(?P<then>.+?)\.?\s*$",
    re.IGNORECASE | re.DOTALL)


def verbatim_clauses(text: str) -> dict | None:
    """The four clauses exactly as written, or None if this is not GWT prose."""
    match = _GWT_SPLIT.match(" ".join(text.split()))
    if not match:
        return None
    return {k: (v or "").strip() for k, v in match.groupdict().items()}


@dataclass(frozen=True)
class Scenario:
    """One acceptance criterion, as an example of its Feature."""

    criterion_id: str
    title: str
    given: str
    when: str
    and_guard: str
    then: str
    tags: tuple[str, ...] = ()
    # Rendered as a comment beneath the step, never as a step: the recovered
    # condition is evidence (T-5), and a reader must not mistake it for an
    # instruction to perform.
    guard_verbatim: str = ""

    def render(self) -> list[str]:
        lines = []
        if self.tags:
            lines.append(INDENT + " ".join(f"@{t}" for t in self.tags))
        lines.append(f"{INDENT}Scenario: {self.title}")
        lines.append(f"{STEP_INDENT}Given {self.given}")
        lines.append(f"{STEP_INDENT}When {self.when}")
        if self.and_guard:
            lines.append(f"{STEP_INDENT}And {self.and_guard}")
        lines.append(f"{STEP_INDENT}Then {self.then}")
        if self.guard_verbatim and self.guard_verbatim != self.and_guard:
            lines.append(f"{STEP_INDENT}# condition as recovered: {self.guard_verbatim}")
        return lines


@dataclass
class Feature:
    """One requirement, with its criteria as scenarios."""

    requirement_id: str
    title: str
    narrative: str = ""
    tags: tuple[str, ...] = ()
    scenarios: list[Scenario] = field(default_factory=list)
    # The business nouns these scenarios touch, rendered as a comment block. A
    # glossary is context for a reader, not a step anything executes.
    glossary: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _wrap(text: str, width: int = 76, indent: str = INDENT) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) + len(indent) > width and current:
            lines.append(indent + current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(indent + current)
    return lines


def render_feature(feature: Feature) -> str:
    """A `.feature` file. Deterministic: same input, same bytes (TR-6/P-7)."""
    lines: list[str] = []
    if feature.tags:
        lines.append(" ".join(f"@{t}" for t in feature.tags))
    lines.append(f"Feature: {feature.title}")
    if feature.narrative:
        lines += _wrap(feature.narrative)
    lines.append("")

    if feature.glossary:
        lines.append(f"{INDENT}# Business nouns these scenarios act on:")
        for entry in feature.glossary:
            lines.append(f"{INDENT}#   {entry}")
        lines.append("")

    for note in feature.notes:
        for wrapped in _wrap(note):
            lines.append(f"{INDENT}# {wrapped.strip()}")
    if feature.notes:
        lines.append("")

    for scenario in feature.scenarios:
        lines += scenario.render()
        lines.append("")

    # A file with no scenarios is a real state -- a requirement nobody has
    # written a criterion for -- and it is said, not left as an empty file that
    # reads like a rendering failure.
    if not feature.scenarios:
        lines.append(f"{INDENT}# No acceptance criteria. This requirement is "
                     f"stated and unspecified:")
        lines.append(f"{INDENT}# nothing here can be tested until somebody "
                     f"writes one.")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_feature(requirement_id: str, requirement_text: str,
                  criteria: list, *,
                  area: str = "",
                  glossary=None,
                  entity_ids: dict | None = None,
                  transition_ids: dict | None = None) -> Feature:
    """A Feature from one Requirement and its criteria.

    `criteria` are `knowledge.KnowledgeEntry`-shaped: anything carrying `id`,
    `text`, `polarity`, `derived` and `provenance`. Kept structural rather than
    typed so `specgen.Rule` can feed this too without either module importing the
    other.
    """
    from metis_mcp.model_sources.ac_mining import _parse

    entity_ids = entity_ids or {}
    transition_ids = transition_ids or {}

    tags = [f"{TAG_REQUIREMENT}:{_slug(requirement_id)}"]
    if area:
        tags.append(f"{TAG_AREA}:{_slug(area)}")

    feature = Feature(
        requirement_id=requirement_id,
        title=_feature_title(requirement_text, requirement_id),
        narrative=requirement_text,
        tags=tuple(tags),
    )

    referenced: list[str] = []
    for criterion in criteria:
        parsed = _parse(criterion.text)
        if parsed is None:
            # S-13's discipline in a renderer: a criterion nothing can read is
            # reported, never reshaped into steps that look parsed.
            feature.notes.append(
                f"{criterion.id} could not be read as Given/When/Then or EARS "
                f"and has no scenario: {criterion.text}")
            continue

        scenario_tags = [f"{TAG_AC}:{_slug(criterion.id)}"]
        polarity = getattr(criterion, "polarity", "")
        if polarity:
            scenario_tags.append(polarity)
        derived = getattr(criterion, "derived", "")
        if derived == "inferred_complement":
            scenario_tags.append("inferred")
            # Without this the round trip loses what the complement is OF, and
            # `knowledge.validate` correctly refuses the result as ungrounded
            # (S-13). Caught by round-tripping a real file, not by review.
            complement_of = getattr(criterion, "complement_of", "")
            if complement_of:
                scenario_tags.append(f"complement_of:{_slug(complement_of)}")
        provenance = getattr(criterion, "provenance", None)
        if callable(provenance):
            provenance = provenance()
        if isinstance(provenance, str) and provenance:
            scenario_tags.append(provenance)
        for entity in entity_ids.get(criterion.id, ()):
            scenario_tags.append(f"{TAG_ENTITY}:{_slug(entity)}")
            referenced.append(entity)
        for transition in transition_ids.get(criterion.id, ()):
            scenario_tags.append(f"{TAG_TRANSITION}:{_slug(transition)}")

        # An EARS criterion has no `then` clause to slice, so its steps are
        # necessarily transformed; a Given/When/Then one is rendered as written.
        clauses = verbatim_clauses(criterion.text) or {
            "given": (parsed["given"] or "").strip(),
            "when": (parsed["when"] or "").strip(),
            "and_guard": (parsed.get("and_guard") or "").strip(),
            "then": (parsed["then"] or "").strip(),
        }
        feature.scenarios.append(Scenario(
            criterion_id=criterion.id,
            title=_title_from(criterion.text, criterion.id),
            given=clauses["given"], when=clauses["when"],
            and_guard=clauses.get("and_guard") or "",
            then=clauses["then"],
            tags=tuple(scenario_tags),
        ))

    if glossary is not None:
        for entity_id in dict.fromkeys(referenced):
            entity = glossary.entity(entity_id)
            if entity is not None:
                feature.glossary.extend(entity.glossary_block())

    if any("inferred" in s.tags for s in feature.scenarios):
        feature.notes.append(
            "Scenarios tagged @inferred were NOT stated by anyone. They are "
            "Métis's complements of the stated ones and land at Quarantine as "
            "code_derived — read them before approving (S-19).")

    return feature


def _feature_title(requirement_text: str, fallback: str) -> str:
    """The requirement's own words, trimmed to a heading.

    A requirement is EARS, not Given/When/Then, so the scenario titler cannot
    read one -- and falling back to the id printed `Feature: REQ-ADMIN-01`, which
    tells a stakeholder nothing (SP-1). Nothing is paraphrased here: this is the
    statement's own sentence, shortened.
    """
    text = " ".join((requirement_text or "").split()).rstrip(".")
    if not text:
        return fallback
    return text if len(text) <= 90 else text[:87].rstrip() + "..."


def _title_from(text: str, fallback: str) -> str:
    """A readable Scenario name: what happens, not which id (SP-1).

    Falls back to the id rather than inventing a summary. A generated title that
    paraphrases is a second wording of the same rule, and two wordings is how a
    reader stops being able to trace a sentence to the element it came from.
    """
    from metis_mcp.model_sources.ac_mining import _parse

    parsed = _parse(text)
    if parsed is None:
        return fallback
    when = (parsed["when"] or "").strip().removeprefix("they ").strip()
    then = (parsed["then"] or "").strip().removeprefix("they are ").strip()
    title = f"{when} → {then}" if when and then else fallback
    return title if len(title) <= 90 else title[:87] + "..."


# ---------------------------------------------------------------------------
# Reading a .feature back (the round trip)
# ---------------------------------------------------------------------------
#
# **A `.feature` file is a source, not only an output.** A business analyst edits
# scenarios in Gherkin because that is the language their team already uses, and
# a format that can only be written to is a report -- it cannot be the place the
# specification lives.
#
# Parsed by hand, deliberately. The subset written above is four keywords and a
# tag line, a regex fails by *missing* a construct and saying so, and adding a
# dependency to read `Given` would be the only third-party parser in a codebase
# that has repeatedly chosen deterministic code over it (TR-4).
#
# **The subset is stated, and anything outside it is reported rather than
# skipped.** `Scenario Outline`, `Examples`, `Background`, `Rule` and doc-strings
# are real Gherkin and are NOT read: a file using them would lose content
# silently, and silent loss is the failure mode this whole module is written
# against.

_TAG_LINE = re.compile(r"^\s*@\S+(\s+@\S+)*\s*$")
_FEATURE = re.compile(r"^\s*Feature:\s*(?P<title>.*)$")
_SCENARIO = re.compile(r"^\s*Scenario:\s*(?P<title>.*)$")
_STEP = re.compile(r"^\s*(?P<keyword>Given|When|Then|And|But)\s+(?P<text>.*)$",
                   re.IGNORECASE)
UNSUPPORTED = ("Scenario Outline:", "Examples:", "Background:", "Rule:", '"""')

PARSE_UNSUPPORTED = "unsupported_gherkin"
PARSE_NO_FEATURE = "no_feature"
PARSE_INCOMPLETE_SCENARIO = "incomplete_scenario"


@dataclass(frozen=True)
class ParseProblem:
    kind: str
    where: str
    detail: str

    def describe(self) -> str:
        return f"[{self.kind:<22}] {self.where}: {self.detail}"


@dataclass
class ParsedFeature:
    requirement_id: str = ""
    title: str = ""
    narrative: str = ""
    area: str = ""
    tags: tuple[str, ...] = ()
    scenarios: list[Scenario] = field(default_factory=list)
    problems: list[ParseProblem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.requirement_id) and not self.problems


def _tags_of(line: str) -> list[str]:
    return [t.lstrip("@") for t in line.split() if t.startswith("@")]


def _tag_value(tags, prefix: str) -> str:
    for tag in tags:
        if tag.startswith(f"{prefix}:"):
            return tag.split(":", 1)[1]
    return ""


def parse_feature(text: str) -> ParsedFeature:
    """Read a `.feature` back into a requirement and its criteria.

    Never partially succeeds quietly: an unsupported construct is a problem on
    the result, and the caller decides. A parser that skipped `Examples:` would
    drop every row of a table and report a clean read.
    """
    parsed = ParsedFeature()
    pending_tags: list[str] = []
    current: dict | None = None
    narrative: list[str] = []
    in_feature = False

    def close(where: str) -> None:
        nonlocal current
        if current is None:
            return
        missing = [k for k in ("given", "when", "then") if not current.get(k)]
        if missing:
            parsed.problems.append(ParseProblem(
                PARSE_INCOMPLETE_SCENARIO, current["id"] or current["title"],
                f"missing {', '.join(missing)} — a criterion needs a situation, "
                f"an action and an outcome (M-1)"))
        else:
            parsed.scenarios.append(Scenario(
                criterion_id=current["id"], title=current["title"],
                given=current["given"], when=current["when"],
                and_guard=current.get("and", ""), then=current["then"],
                tags=tuple(current["tags"])))
        current = None

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()

        if any(stripped.startswith(u) for u in UNSUPPORTED):
            parsed.problems.append(ParseProblem(
                PARSE_UNSUPPORTED, f"line {number}",
                f"{stripped.split(':')[0]!r} is real Gherkin and is not read by "
                f"this parser. Reading the file anyway would drop it silently"))
            continue

        if not stripped or stripped.startswith("#"):
            continue

        if _TAG_LINE.match(line):
            pending_tags = _tags_of(line)
            continue

        feature = _FEATURE.match(line)
        if feature:
            close("")
            in_feature = True
            parsed.title = feature.group("title").strip()
            parsed.tags = tuple(pending_tags)
            parsed.requirement_id = _tag_value(pending_tags, TAG_REQUIREMENT)
            parsed.area = _tag_value(pending_tags, TAG_AREA)
            pending_tags = []
            continue

        scenario = _SCENARIO.match(line)
        if scenario:
            close("")
            current = {"id": _tag_value(pending_tags, TAG_AC),
                       "title": scenario.group("title").strip(),
                       "tags": pending_tags}
            pending_tags = []
            continue

        step = _STEP.match(line)
        if step and current is not None:
            keyword = step.group("keyword").lower()
            value = step.group("text").strip()
            # `And` continues whichever clause preceded it. Only the And-after-When
            # form is written by the renderer, and that is the condition clause.
            if keyword in ("and", "but"):
                keyword = "and" if current.get("when") and not current.get("then") else "then"
            current[keyword] = value
            continue

        if in_feature and current is None:
            narrative.append(stripped)

    close("")
    parsed.narrative = " ".join(narrative).strip()

    if not in_feature:
        parsed.problems.append(ParseProblem(
            PARSE_NO_FEATURE, "file", "no `Feature:` line — nothing to read"))
    elif not parsed.requirement_id:
        parsed.problems.append(ParseProblem(
            PARSE_NO_FEATURE, parsed.title or "file",
            f"no `@{TAG_REQUIREMENT}:<id>` tag on the Feature. The requirement id "
            f"is what a criterion hangs off (HAS_AC); without it the scenarios "
            f"land with nothing above them"))

    return parsed


def to_knowledge(parsed: ParsedFeature, model_id: str, *, surface: str = "api",
                 statement: str = ""):
    """A `ParsedFeature` as a `knowledge.KnowledgeFile` — the same stage 1 shape.

    Gherkin and the JSON knowledge file are two authoring formats for one thing,
    so they converge here rather than each growing a private path to the graph.
    """
    from metis_mcp.model_sources.knowledge import (
        INFERRED_COMPLEMENT, KnowledgeEntry, KnowledgeFile, KnowledgeRequirement,
        NEGATIVE, POSITIVE, STATED,
    )

    entries = []
    for scenario in parsed.scenarios:
        middle = f", and {scenario.and_guard}" if scenario.and_guard else ""
        entries.append(KnowledgeEntry(
            id=scenario.criterion_id or scenario.title,
            text=f"Given {scenario.given}, when {scenario.when}{middle}, "
                 f"then {scenario.then}.",
            requirement_id=parsed.requirement_id,
            polarity=NEGATIVE if NEGATIVE in scenario.tags else POSITIVE,
            derived=INFERRED_COMPLEMENT if "inferred" in scenario.tags else STATED,
            source_statement=statement or parsed.narrative,
            complement_of=_tag_value(scenario.tags, "complement_of"),
        ))

    return KnowledgeFile(
        model_id=model_id,
        requirement=KnowledgeRequirement(id=parsed.requirement_id,
                                         text=parsed.narrative or parsed.title),
        surface=surface,
        statement=statement or parsed.narrative,
        entries=entries,
    )
