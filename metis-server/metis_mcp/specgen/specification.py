"""
Stakeholder specification generation (application spec §18; A-59..A-62).

Stakeholders should not have to read a model to understand a feature. §9's review
UI serves operators; this serves everyone else.

**SP-1 -- generated, then edited, and the split is explicit.** A journey
specification is a rendering of the model's *structure* -- which transitions
exist, their status, their evidence -- and that half is regenerated every run. Its
*language* is the other half: a person may rewrite any Given/When/Then into the
business's own words, and regeneration must not overwrite them.

`name_tier` and `guard_tier` are what make that safe without diffing prose. A
wording at tier `ac_vocabulary` came from a confirmed acceptance criterion and is
rendered verbatim; one at `code_convention` was decoded from code and is
regenerated. The tier IS the machine/human split, the same one
`identity.carry_human_facts` applies to the graph.

**SP-1a -- the document is re-readable.** Every rule carries a stable
`AC-<id>` heading matching `spec_kit._AC_HEADING`, and the transition id it came
from. Without the heading a generated spec parsed back to *zero* criteria, so the
loop -- code to model to spec to edited spec to model -- was open at its first
joint. The id is derived from the transition's natural key, never an ordinal:
The pilot estate's 16 positional `AC-4.1` sub-ids are the standing example of what an
ordinal costs, because inserting one rule shifts every id after it.

**SP-3 -- the model is already Given/When/Then.** `State -[:WHEN]-> Transition
-[:THEN]-> State` renders almost mechanically, which is why this module needs no
model call to produce readable output. Everything here is `humanise()` -- re-spacing
and capitalising an identifier -- reused from `rendering/test_case.py` so prose in
a specification and prose in a test case cannot drift apart.

**SP-4/SP-5 is the rule that matters most.** A generated document carries the
authority of a specification. Presenting a quarantined extraction as settled
behaviour would launder an unreviewed machine guess into an apparent decision.
Every rule therefore carries its lifecycle state, and anything not `Approved` is
visibly marked -- in the body text, not in a footnote.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from metis_mcp.mbt.model import (
    APPROVED,
    DEPRECATED,
    DISPUTED,
    IMPLEMENTED,
    PLANNED,
    QUARANTINE,
    REJECTED,
    Model,
)
import hashlib

from metis_mcp.identity import short, transition_key
from metis_mcp.mbt.validation import ValidationResult
from metis_mcp.rendering.test_case import humanise

# Wording a person authored, via a confirmed acceptance criterion. Rendered
# verbatim rather than regenerated -- see SP-1.
TIER_HUMAN_WORDING = "ac_vocabulary"


def wording_fingerprint(given: str, when: str, and_guard: str, then: str) -> str:
    """A hash over the four clauses, stamped into the document.

    **This is how an edit becomes visible without needing the model.** S-19 says
    a criterion is documentation "until a person edits or affirms one", so an
    edit has to be detectable -- and the landing path reads files, not the
    graph, so it cannot re-derive what the generator would have produced.

    Stamping the fingerprint makes the document self-describing: recompute it
    from the clauses as they now read, compare with what was stamped, and a
    difference means a human changed the words. Deterministic, and it needs
    nothing but the file.

    Over the clauses ALONE -- not the whole block. A lifecycle mark or a
    `Validated by:` line changes as the graph changes and is not a person
    rewriting the behaviour, so including them would report an edit on every
    regeneration.
    """
    basis = "|".join(part.strip() for part in (given, when, and_guard, then))
    return hashlib.sha256(basis.encode()).hexdigest()[:12]

SPEC_VERSION = "metis.journey-specification/1"

# SP-4: how each non-approved lifecycle state is marked in the body. `Approved`
# is deliberately unmarked -- marking everything would train readers to skip the
# marks, which is the failure this is meant to prevent.
_MARKS = {
    QUARANTINE: ("PROPOSED", "not yet approved — this is an unreviewed proposal"),
    DISPUTED: ("DISPUTED", "sources disagree; paths through it are blocked (S-8)"),
    REJECTED: ("REJECTED", "reviewed and declined — retained as evidence"),
    DEPRECATED: ("DEPRECATED", "superseded; retained as evidence (T-16)"),
}


@dataclass(frozen=True)
class Rule:
    """One transition, as Given/When/Then (spec SP-3)."""

    transition_id: str
    # `AC-<stable id>`. Derived from the transition's natural key so it survives
    # a rule being inserted above it, a guard being edited, and the document
    # being regenerated -- which is what lets a human edit this block and have
    # the edit still match its transition on the way back in.
    criterion_id: str
    given: str
    when: str
    and_guard: str
    # The condition as recovered, kept beside the sentence. T-5: the verbatim
    # form stays authoritative even where the prose reads cleanly.
    guard_verbatim: str
    then: str
    lifecycle_state: str
    implementation_status: str
    acceptance_criteria: tuple[str, ...] = ()

    @property
    def is_settled(self) -> bool:
        return self.lifecycle_state == APPROVED

    @property
    def wording_fingerprint(self) -> str:
        """Stamped into the block so a later edit to these clauses is visible."""
        return wording_fingerprint(self.given, self.when, self.and_guard, self.then)

    @property
    def title(self) -> str:
        """A readable label for this rule: what happens, not which id."""
        when = self.when.removeprefix("they ").strip()
        then = self.then.removeprefix("they are ").strip()
        return f"{when} → {then}"

    @property
    def heading(self) -> str:
        """`AC-<id>: <what happens>` — the form `spec_kit` can read back.

        The behaviour stays in the heading, because a stakeholder reads this and
        an element id printed as a section title tells them nothing (SP-1). The
        id is a prefix, not a replacement.
        """
        return f"{self.criterion_id}: {self.title}"

    @property
    def mark(self) -> str:
        if self.implementation_status == PLANNED:
            return "PLANNED — not built yet; correctly not a coverage gap (P-11)"
        marked = _MARKS.get(self.lifecycle_state)
        return f"{marked[0]} — {marked[1]}" if marked else ""


@dataclass(frozen=True)
class Situation:
    """One state, described as a situation a user can be in."""

    state_id: str
    name: str
    surface: str
    is_initial: bool
    lifecycle_state: str
    observable_as: str


@dataclass
class Specification:
    model_id: str
    journey: str
    version: str = SPEC_VERSION
    generated_at: str = ""
    model_version: str = ""
    commit: str = ""
    situations: list[Situation] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    coverage_note: str = ""
    override_note: str = ""
    unsettled: int = 0

    @property
    def is_fully_settled(self) -> bool:
        return self.unsettled == 0

    @property
    def content_hash(self) -> str:
        """Content-derived (D-8), and deliberately **excludes** `generated_at`.

        Landing this document must be idempotent: re-rendering an unchanged
        model has to MERGE onto the same node with the same values. Hashing the
        rendered body instead would fold the timestamp in and make every run a
        new document, which is the opposite of what D-8 asks for.
        """
        parts = [self.model_id, self.journey, self.model_version, self.commit]
        for s in sorted(self.situations, key=lambda x: x.state_id):
            parts.append(f"S|{s.state_id}|{s.name}|{s.surface}|{s.is_initial}|"
                         f"{s.lifecycle_state}|{s.observable_as}")
        for r in sorted(self.rules, key=lambda x: x.criterion_id):
            parts.append(f"R|{r.criterion_id}|{r.transition_id}|{r.given}|{r.when}|"
                         f"{r.and_guard}|{r.then}|{r.lifecycle_state}|"
                         f"{r.implementation_status}")
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


# A note against a tempting "improvement": `humanise` splits on `_`, `-` and `.`
# but leaves CamelCase alone, so `LoggedOut` renders verbatim rather than as
# "Logged out". That is deliberate. Softening it would make this document and the
# model use different words for one state, which is exactly what stops a reader
# tracing a sentence back to the element it came from (SP-2). A state whose name
# reads badly is a naming problem, fixed through X-7's cascade, not here.

def _observable_as(name: str, surface: str) -> str:
    """What the interacting party actually sees (spec M-2).

    Descriptive only. It never claims a state IS observable -- that is a modelling
    judgement (M-3) `validation.check_observability` can only partly check, and a
    document that asserted it would be overstating what anything verified.
    """
    if surface == "api":
        return f"the response condition {humanise(name)!r}"
    return f"the screen or message {humanise(name)!r}"


def criterion_id_for(model: Model, transition) -> str:
    """`AC-<stable short id>` from the transition's natural key.

    Never an ordinal. `spec_kit` mints `AC-4.1`, `AC-4.2` positionally for
    multi-rule blocks, and 16 of the pilot estate's 66 criteria sit on that: insert a rule
    and every id after it shifts, changing the node id and orphaning its
    approval. The natural key moves only when the behaviour itself does, which
    is exactly when a criterion *should* be treated as new.
    """
    return f"AC-{short(transition_key(model.id, transition, model))[:8]}"


def _given_clause(state) -> str:
    """What must be true to start — in business language where the model has it.

    `state.condition` is set by the M-6 unfolding pass ("no metric exists") and
    says what the situation IS. The state's name says only what it is *called*,
    and for a code-derived name that is `MetricGetActionByIdNoContent204`.
    """
    if state is None:
        return "the starting situation is not recorded"
    condition = (getattr(state, "condition", "") or "").strip()
    if condition:
        return condition
    return f"the user is {humanise(state.name)}"


def _then_clause(transition, target) -> str:
    """What the caller observes — status and body, not the target's node name.

    `they are MetricGetActionByIdNoContent204` is the code's vocabulary in the
    one position a stakeholder is most likely to read. The status and the
    response body are the observable result (M-2/M-3), and both are on the model.
    """
    status = getattr(transition, "outcome_status", None)
    body = (getattr(transition, "response_body", "") or "").strip()
    if status is None:
        return f"they are {humanise(target.name) if target else transition.target}"
    if body:
        return f"{body} is returned ({status})"
    # Empty body is a FACT, not missing information -- `ResponseEntity<Void>` and
    # a 204 both genuinely return nothing.
    return f"nothing is returned ({status}, no body)"


def _human_authored(transition) -> bool:
    """Whether this transition's wording came from a person (SP-1).

    `guard_tier` is `ac_vocabulary` only where a **confirmed** acceptance
    criterion supplied the words. Regenerating over those would silently revert
    someone's editing on the next run, which is the one failure that would make
    "generate once, then maintain the spec" unusable.
    """
    return getattr(transition, "guard_tier", "") == TIER_HUMAN_WORDING


def _and_clause(transition) -> str:
    """The precondition, in business language, with the raw guard kept as evidence.

    `guard_wording` is decoded from conventions the model already committed to
    ("the payload is invalid"), or is a person's own words where a confirmed
    criterion supplied them. The raw `guard` stays in the block below it: T-5
    says the verbatim condition is the authoritative statement, and this changes
    which one is the *sentence*, not which one is authoritative.
    """
    return (getattr(transition, "guard_wording", "") or "").strip()


def build(model: Model, *, journey: str = "",
          validation: ValidationResult | None = None,
          validated_transition_ids: set[str] | None = None,
          acceptance_criteria: dict[str, list[str]] | None = None,
          model_version: str = "", commit: str = "",
          override_density=None, generated_at: str | None = None) -> Specification:
    """Assemble the content once; §18.4's two outputs both render from this.

    `generated_at` is injectable so a dated export is reproducible in a test --
    otherwise the only thing that changes between two runs of the same model is a
    timestamp, and SP-7's "reproducible" claim could not be asserted.
    """
    spec = Specification(
        model_id=model.id,
        journey=journey or model.id.rsplit("-", 1)[0],
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model_version=model_version,
        commit=commit,
    )
    criteria = acceptance_criteria or {}
    validated = validated_transition_ids or set()

    for sid in model.state_ids():
        state = model.states[sid]
        spec.situations.append(Situation(
            state_id=sid, name=humanise(state.name), surface=state.surface,
            is_initial=state.is_initial, lifecycle_state=state.lifecycle_state,
            observable_as=_observable_as(state.name, state.surface),
        ))

    for tid in model.transition_ids():
        t = model.transitions[tid]
        source = model.states.get(t.source)
        target = model.states.get(t.target)
        rule = Rule(
            transition_id=tid,
            criterion_id=criterion_id_for(model, t),
            given=_given_clause(source),
            when=f"they {humanise(t.trigger).lower()}",
            and_guard=_and_clause(t) or t.guard,
            guard_verbatim=t.guard,
            then=_then_clause(t, target),
            lifecycle_state=t.lifecycle_state,
            implementation_status=t.implementation_status,
            acceptance_criteria=tuple(criteria.get(tid, ())),
        )
        spec.rules.append(rule)
        # A `planned` transition is not "unreviewed": there is nothing built to
        # review, `review export` correctly skips it (P-11), and it already
        # carries its own distinct PLANNED mark. Counting it as unapproved would
        # make a fully-reviewed model permanently report an outstanding decision.
        if not rule.is_settled and rule.implementation_status != PLANNED:
            spec.unsettled += 1

    # SP-2: open questions come from real findings, never from prose judgement.
    if validation:
        for finding in validation.blocking:
            spec.open_questions.append(f"[blocking] {finding.check}: {finding.detail}")
        for finding in validation.unverifiable:
            spec.open_questions.append(
                f"[unverifiable] {finding.check}: {finding.detail}")
    for tid in model.transition_ids():
        t = model.transitions[tid]
        if t.implementation_status == IMPLEMENTED and tid not in validated and criteria:
            spec.open_questions.append(
                f"[unspecified behaviour] {tid}: the system does this; "
                f"no acceptance criterion covers it")

    if override_density is not None and getattr(override_density, "caveat", ""):
        spec.override_note = override_density.caveat

    return spec


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _rule_block(rule: Rule) -> list[str]:
    lines = []
    if rule.mark:
        lines.append(f"> **⚠ {rule.mark}**")
        lines.append("")
    lines.append(f"**Given** {rule.given}")
    lines.append(f"**When** {rule.when}")
    if rule.and_guard:
        # Where no business wording exists the raw condition IS the clause, and
        # it stays in backticks — it is a code expression, and setting it as
        # prose would present `credentials_valid AND NOT account_locked` as
        # though a person had written it that way.
        if rule.and_guard == rule.guard_verbatim:
            lines.append(f"**And** the condition `{rule.and_guard}` holds")
        else:
            lines.append(f"**And** {rule.and_guard}")
    lines.append(f"**Then** {rule.then}")
    if rule.guard_verbatim and rule.guard_verbatim != rule.and_guard:
        # T-5: the recovered condition stays visible and authoritative. What
        # changed is which of the two is the *sentence* — a stakeholder reads
        # "the payload is invalid", and the reviewer checking it can still see
        # `NOT (payload_valid)` is what the code actually evaluates.
        lines.append("")
        lines.append(f"<sub>condition as recovered: `{rule.guard_verbatim}`</sub>")
    if rule.acceptance_criteria:
        lines.append("")
        lines.append("Validated by: " + ", ".join(rule.acceptance_criteria))
    lines.append("")
    lines.append(f"<sub>`{rule.transition_id}`</sub>")
    lines.append(f"<sub>wording: {rule.wording_fingerprint}</sub>")
    return lines


def render_markdown(spec: Specification, coverage_summary: str = "") -> str:
    """§18.2's contents, in order.

    Deterministic: the same model and the same `generated_at` produce identical
    bytes, so SP-7's reproducibility is a property of the output, not a claim.
    """
    out: list[str] = [
        f"# {humanise(spec.journey)} — behaviour specification",
        "",
        "*Generated from the model. Not authored — every statement below traces to "
        "a model element (SP-1, SP-2).*",
        "",
    ]

    if not spec.is_fully_settled:
        out += [
            f"> **⚠ {spec.unsettled} of {len(spec.rules)} rules are not approved.** "
            f"They are marked individually below. This document describes what the "
            f"model currently contains, which is not the same as what has been "
            f"agreed (SP-4).",
            "",
        ]

    out += ["## Purpose", "",
            f"How `{spec.model_id}` behaves, as the interacting party experiences it.",
            ""]

    out += ["## Situations a user can be in", ""]
    for s in spec.situations:
        start = " *(starting point)*" if s.is_initial else ""
        mark = ""
        if s.lifecycle_state != APPROVED:
            marked = _MARKS.get(s.lifecycle_state)
            mark = f" — **⚠ {marked[0]}**" if marked else ""
        out.append(f"- **{s.name}**{start} — observable as {s.observable_as}{mark}".rstrip())
    out.append("")

    out += ["## Behaviour rules", ""]
    for rule in spec.rules:
        # The heading is the BEHAVIOUR, not the element id. Using the id printed
        # `com.example.records.RecordController.one:
        # org.springframework.http.ResponseEntity(java.lang.Long)::GET->NoContent204`
        # as a section heading in a document meant for stakeholders (SP-1).
        # The id is kept, in small type, so every statement still traces to its
        # element (SP-2).
        out.append(f"### {rule.heading}")
        out.append("")
        out += _rule_block(rule)
        out.append("")

    out += ["## What is tested", ""]
    out.append(coverage_summary or "No coverage has been computed for this model.")
    out += ["",
            "*This states what is **tested**, not what is **working**. A rule may be "
            "fully covered and currently failing; the graph records coverage, not "
            "execution outcome (C-10, C-11).*",
            ""]

    out += ["## Open questions", ""]
    if spec.open_questions:
        out += [f"- {q}" for q in spec.open_questions]
    else:
        out.append("None recorded.")
    out.append("")

    out += ["## Provenance", "",
            f"- Model: `{spec.model_id}`",
            f"- Model version: {spec.model_version or 'not recorded'}",
            f"- Commit: {spec.commit or 'not recorded'}",
            f"- Generated: {spec.generated_at}"]
    if spec.override_note:
        out.append(f"- **Override density**: {spec.override_note}")
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------
# §18.4 : living page and dated export
# --------------------------------------------------------------------------

LIVING = "living"
EXPORT = "export"


@dataclass
class Document:
    kind: str
    body: str
    model_id: str
    model_version: str
    commit: str
    generated_at: str

    def staleness_against(self, current_version: str) -> str:
        """Spec SP-9: an export's staleness must be *retrievable*, not guessed."""
        if self.kind == LIVING:
            return ""
        if not self.model_version or not current_version:
            return "cannot be determined — the version was not recorded"
        if self.model_version == current_version:
            return ""
        return (f"generated from {self.model_version}; the model is now "
                f"{current_version}")


def living_page(spec: Specification, coverage_summary: str = "") -> Document:
    """Always current; regenerated on every model change (spec SP-6)."""
    return Document(kind=LIVING, body=render_markdown(spec, coverage_summary),
                    model_id=spec.model_id, model_version=spec.model_version,
                    commit=spec.commit, generated_at=spec.generated_at)


def dated_export(spec: Specification, coverage_summary: str = "") -> Document:
    """Frozen on generation, for sign-off and audit (spec SP-6, SP-7).

    Records its model version and commit so it is reproducible, and is **never
    silently updated** (SP-8) -- staleness is the whole point of an export. There
    is deliberately no `update()` here: the absence of the function is the
    enforcement.
    """
    body = render_markdown(spec, coverage_summary)
    header = (f"> **Dated export — frozen {spec.generated_at}.** Generated from "
              f"model version {spec.model_version or 'unrecorded'} at commit "
              f"{spec.commit or 'unrecorded'}. This document is never updated in "
              f"place; regenerate for current behaviour (SP-8).\n\n")
    return Document(kind=EXPORT, body=header + body, model_id=spec.model_id,
                    model_version=spec.model_version, commit=spec.commit,
                    generated_at=spec.generated_at)
