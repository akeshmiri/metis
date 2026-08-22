"""
Reading GitHub Spec Kit feature specs (application spec §4.5, S-12, S-14; R5).

`ac_mining.py` turns acceptance criteria into a model. This turns a real
repository's `.specify/specs/<feature>/spec.md` files into those criteria, so the
intent side of §4.4's comparison comes from what the team actually wrote rather
than from anything invented here.

**Why this matters more than its size.** §4.1 is blunt that a model extracted from
code, used to generate tests, proves only that the code does what the code does.
Its worth comes from comparison against intent, and **S-3** says a deployment
running only code extraction gets coverage, not correctness. A repository
practising spec-driven development has already written the intent down; not
reading it would leave the whole R5 half of the system unproven against a source
that was sitting there.

**Two real shapes, and only one is behaviour.** Spec Kit files in the wild carry
both:

    Given/When/Then     a behavioural rule -- a transition (M-1)
    bullet narrative    "Verified by: an e2e test across seven route prefixes"

The second is a genuine acceptance criterion and is genuinely **not** a state
transition: readiness gates, architectural constraints, process obligations. They
are read and returned, marked `is_behavioural=False`, so a caller can report them
rather than silently dropping 35 of 58 criteria -- but they are never forced into
a transition shape they do not have (S-13).

**One Given, several When/Then.** The real files nest them:

    **Given** a `GET /metric/{id}` request
    **When** a metric with the given id exists
    **Then** the `MetricDto` is returned with `200 OK`

    **When** no metric exists with the given id
    **Then** `204 No Content` is returned

That is two rules sharing a precondition -- two transitions, not one. Each
When/Then pair becomes its own criterion, carrying the Given it inherits and a
sub-id (`AC-4.1`, `AC-4.2`) so it stays traceable to the block it came from.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from metis_mcp.model_sources.ac_mining import Criterion
from metis_mcp.specgen.specification import (
    wording_fingerprint as _wording_fingerprint,
)

# `### AC-4: Metric Point Query`
_AC_HEADING = re.compile(r"^###\s+(AC-[\w.\-]+)\s*:\s*(.+?)\s*$", re.M)
# `**Given** ...` / `**When** ...` / `**Then** ...` / `**And** ...`
_CLAUSE = re.compile(r"^\*\*(Given|When|Then|And)\*\*\s+(.+?)\s*$", re.M | re.I)
_CODE_REF = re.compile(r"\*\*Code reference\*\*\s*:\s*(.+?)\s*$", re.M)
_STATUS = re.compile(r"Status:\s*\*\*([A-Za-z ]+)\*\*")

# Inline code spans carry the load in these files (`GET /metric/{id}`,
# `201 Created`). Backticks are stripped so the text a matcher sees is the text a
# reader sees -- but nothing else is rewritten.
_TICKS = re.compile(r"`([^`]*)`")
# `<sub>`athena-metric-api::…::POST->MetricSaveRejected400`</sub>` — the
# transition a generated rule came from.
#
# **`specgen` has always written this and nothing ever read it.** So the document
# carried the exact criterion→transition binding while the graph held **zero**
# `VALIDATES` edges and reconciliation reported every transition unmatched. For a
# generated spec this needs no matching heuristic at all: the id is right there,
# which is a far stronger link than name similarity, and X-17 forbids treating
# similarity as sufficient evidence anyway.
#
# Absent on a hand-written spec, which is correct — athena's 66 criteria have no
# binding and must keep going through `reconciliation.prefilter`.
_TRANSITION_REF = re.compile(r"<sub>`([^`]+)`</sub>")
# `<sub>wording: d159ab82f85d</sub>` — the fingerprint `specgen` stamped over the
# four clauses when it wrote this block.
#
# Recomputing it from the clauses as they now read is what makes an edit
# visible. S-19: a criterion is documentation "until a person edits or affirms
# one", and this is how the edit is detected without the model — the landing
# path reads files, so it cannot re-derive what the generator would produce.
_WORDING_FINGERPRINT = re.compile(r"<sub>wording:\s*([0-9a-f]+)</sub>")


@dataclass(frozen=True)
class SpecCriterion:
    """One acceptance criterion, as written."""

    id: str
    title: str
    feature: str
    text: str
    is_behavioural: bool
    code_reference: str = ""
    given: str = ""
    when: str = ""
    then: str = ""
    source_file: str = ""
    # The transition this criterion was generated from, where the document says
    # so. Empty for a hand-authored criterion — an absent binding is a fact
    # about the source, not a gap to fill in by guessing.
    transition_id: str = ""
    # A person rewrote these clauses after they were generated (S-19).
    #
    # **Only ever True for a generated criterion**, because only a generated one
    # carries a fingerprint to compare against. A hand-written criterion was
    # authored by definition and is not "edited"; claiming otherwise would
    # promote athena's 66 retro-documentation criteria to intent on the strength
    # of them having no fingerprint, which is the opposite of evidence.
    edited_by_hand: bool = False

    def to_criterion(self) -> Criterion:
        """The shape `ac_mining.mine()` consumes."""
        return Criterion(id=self.id, text=self.text, requirement_id=self.feature)


@dataclass
class SpecFeature:
    name: str
    status: str = ""
    criteria: list[SpecCriterion] = field(default_factory=list)

    @property
    def behavioural(self) -> list[SpecCriterion]:
        return [c for c in self.criteria if c.is_behavioural]

    @property
    def narrative(self) -> list[SpecCriterion]:
        return [c for c in self.criteria if not c.is_behavioural]


def _clean(text: str) -> str:
    return _TICKS.sub(r"\1", text).replace("  ", " ").strip().rstrip(".")


def _blocks(text: str) -> list[tuple[str, str, str]]:
    """`(id, title, body)` for each `### AC-n:` heading."""
    out = []
    matches = list(_AC_HEADING.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1), m.group(2), text[m.end():end]))
    return out


def _rules(body: str) -> list[tuple[str, str, list[str]]]:
    """Split a block into `(given, when, ands+then)` rules.

    A new `When` starts a new rule and inherits the most recent `Given`; an `And`
    attaches to whatever it follows. Anything before the first `Given`/`When` is
    not a rule.
    """
    clauses = [(m.group(1).lower(), _clean(m.group(2))) for m in _CLAUSE.finditer(body)]
    rules: list[tuple[str, str, list[str]]] = []
    given = ""
    current_when: str | None = None
    extras: list[str] = []

    def flush():
        if current_when is not None:
            rules.append((given, current_when, list(extras)))

    for kind, value in clauses:
        if kind == "given":
            flush()
            current_when, extras = None, []
            given = value
        elif kind == "when":
            flush()
            current_when, extras = value, []
        elif kind in ("then", "and"):
            if current_when is None:
                # An `And` qualifying the Given, before any When.
                if kind == "and" and given:
                    given = f"{given} and {value}"
                continue
            extras.append(value)
    flush()
    return [r for r in rules if r[2]]


def parse_spec(path: str | Path, feature: str = "") -> SpecFeature:
    """Read one `spec.md`."""
    p = Path(path)
    text = p.read_text()
    name = feature or p.parent.name
    status_match = _STATUS.search(text)
    out = SpecFeature(name=name, status=status_match.group(1).strip() if status_match else "")

    for ac_id, title, body in _blocks(text):
        code_ref = ""
        ref = _CODE_REF.search(body)
        if ref:
            code_ref = _clean(ref.group(1))

        # The transition this block was generated from, if the document says so.
        # `specgen` stamps it; a hand-written spec has none, and that absence is
        # carried honestly rather than filled in.
        ref_match = _TRANSITION_REF.search(body)
        transition_id = ref_match.group(1) if ref_match else ""

        stamp = _WORDING_FINGERPRINT.search(body)
        stamped = stamp.group(1) if stamp else ""

        rules = _rules(body)
        if not rules:
            # A real criterion, and genuinely not a transition. Returned marked,
            # never discarded and never forced into a shape it does not have.
            out.criteria.append(SpecCriterion(
                id=ac_id, title=title, feature=name,
                text=_clean(title), is_behavioural=False,
                code_reference=code_ref, source_file=str(p),
                transition_id=transition_id))
            continue

        for i, (given, when, extras) in enumerate(rules, start=1):
            sub_id = ac_id if len(rules) == 1 else f"{ac_id}.{i}"
            then = extras[-1] if extras else ""
            middle = extras[:-1]
            # Recomputed from the clauses as they now read. A difference from
            # what was stamped means a person rewrote them; no stamp means this
            # block was never generated, so there is nothing to have edited.
            edited = bool(stamped) and stamped != _wording_fingerprint(
                given, when, " and ".join(middle), then)
            # Reassembled into the Given/When/Then sentence `ac_mining` parses.
            # `And` clauses between When and Then become guard conditions.
            when_text = when if not middle else f"{when} and " + " and ".join(middle)
            sentence = f"Given {given}, when {when_text}, then {then}."
            out.criteria.append(SpecCriterion(
                id=sub_id, title=title, feature=name, text=sentence,
                is_behavioural=True, code_reference=code_ref,
                given=given, when=when_text, then=then, source_file=str(p),
                transition_id=transition_id, edited_by_hand=edited))
    return out


def read_specs(root: str | Path) -> list[SpecFeature]:
    """Read every `<root>/<feature>/spec.md`, in a fixed order."""
    base = Path(root)
    if not base.exists():
        raise FileNotFoundError(
            f"{base} does not exist. Point this at a Spec Kit `specs` directory "
            f"(the one holding <feature>/spec.md).")
    return [parse_spec(d / "spec.md") for d in sorted(base.iterdir())
            if (d / "spec.md").exists()]


def format_specs(features: list[SpecFeature]) -> str:
    behavioural = sum(len(f.behavioural) for f in features)
    narrative = sum(len(f.narrative) for f in features)
    lines = [f"Spec Kit — {len(features)} feature(s), "
             f"{behavioural + narrative} acceptance criteria", ""]
    lines.append(f"  {'feature':<40}{'behavioural':>12}{'narrative':>11}  status")
    for f in features:
        lines.append(f"  {f.name:<40}{len(f.behavioural):>12}{len(f.narrative):>11}"
                     f"  {f.status or '—'}")
    lines += ["",
              f"  {behavioural} criteria are Given/When/Then and describe a transition.",
              f"  {narrative} are narrative -- readiness gates, architectural",
              "  constraints, process obligations. Those are real criteria and",
              "  genuinely not state transitions; they are reported, never forced",
              "  into a shape they do not have (S-13)."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# A spec document -> a Requirement (application spec §4.5; S-13, S-19, §4.1)
# ---------------------------------------------------------------------------

def requirement_from_spec(feature: "SpecFeature", statement: str,
                          requirement_id: str = "") -> "KnowledgeFile":
    """One spec feature and its EARS statement, as a `KnowledgeFile`.

    **Why it returns a KnowledgeFile rather than landing.** `knowledge.py` is
    the only writer of `Requirement` in this codebase, and that is worth
    keeping: a second writer is how two halves of one graph come to disagree
    about what `Approved` means. So this converts, and
    `knowledge.plan_documentation` lands -- through the same ontology gate, the
    same Quarantine default, and the same `validate()` that reports a
    non-conformant statement as `requirement_not_ears` rather than landing it.

    **Why the statement is an argument and not derived.** A feature is named
    "Archive a record"; `Requirement.ears_pattern` needs "When a user archives a
    record, the system shall hide it from search." Deriving one from the other
    is composition, not extraction, and composing a requirement nobody wrote is
    precisely what `ac_mining` refuses to do (S-13, TR-4). The sentence comes
    from a person -- in a skill session, where the judgement belongs -- and
    everything below it is mechanical.

    **The circularity, and why nothing here defuses it (§4.1).** A spec rendered
    from the code model, parsed back into a requirement, then used to check that
    code, proves only that the code does what the code does. This does not stop
    you doing that -- it makes it *visible*: every criterion lands at
    `provenance_for`'s weakest grade, `code_derived`, and only
    `review.decisions.promotion_for` grants anything stronger, on a real edit or
    an explicit affirmation. A grade is never upgraded here, and
    `SpecCriterion.edited_by_hand` is deliberately not read as consent: it says
    the wording changed, not that a person affirmed the claim.

    The `Requirement` itself carries no grade, and should not. Provenance lives
    on `AcceptanceCriterion`, where it is an indexed property precisely because
    "which criteria in this scope are still code_derived" is the filter that
    separates a coverage claim from a correctness one. Copying a derived value
    onto the parent would be one fact in two places.
    """
    from metis_mcp.model_sources.knowledge import (
        KnowledgeEntry, KnowledgeFile, KnowledgeRequirement,
    )

    feature_id = requirement_id or f"req-{_slug(feature.name)}"
    entries = [
        KnowledgeEntry(
            id=criterion.id,
            text=criterion.text,
            requirement_id=feature_id,
            # The statement each criterion claims to formalise. Without it there
            # is no way to check the formalisation against what was said.
            source_statement=statement,
        )
        for criterion in feature.behavioural
    ]

    return KnowledgeFile(
        model_id=feature.name,
        requirement=KnowledgeRequirement(id=feature_id, text=statement),
        statement=statement,
        entries=entries,
    )


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-") or "unnamed"
