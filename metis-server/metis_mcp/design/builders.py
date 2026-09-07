"""The rows of each design section, computed from what Métis recovered.

**Nothing here decides anything, and nothing here invents data.** Every row
states a *condition* -- on a guard, on a parameter, on an identity -- and never
a value that would satisfy it (M-9). Where a value would be needed the row says
what space it must come from (`<string, length 3..40, required>`), which is
X-6e's rule carried out of rendering and into design.

**Every builder is a pure function of a `DesignContext`.** No graph, no network,
no model call: the same context yields byte-identical rows, which is what lets
`metis design --check` be meaningful in CI and what stops a regenerated document
diffing against itself. Determinism is not incidental here -- P-7 makes path
generation byte-identical so a suite diffs cleanly, and a design whose row order
moved every run would undo that one document up.

**Row ids are content-derived, and that is what makes the merge work.**
`row_id` digests the stable parts of a row -- the behaviour it is about and the
condition it states -- so the same finding keeps the same id across runs and the
decision somebody recorded against it survives. An id that counted rows off
instead -- first row, second row -- would renumber the moment a transition was
added, silently moving every human decision onto the wrong row. That is the failure this shape exists to avoid, and it is
the same argument `identity.claim_id` makes one layer down.

**A builder returns rows; it never explains its own emptiness.** No rows can
mean *nothing here* or *nobody looked*, and only the ledger knows which -- so
`document.py` asks `inputs.unstatable()` and prints `absent_means` or
`empty_means` accordingly. A builder that returned its own excuse would be
guessing at a fact it does not hold.

**Reuse, not reimplementation.** `mbt/techniques.py` does partitions and
boundaries, `mbt/design.py` does decision tables and pairwise, `mbt/test_levels`
does the three-grade existing-coverage judgement, `viability.py` does
automatability and load candidacy, and `risk/prioritisation.py` does the order
and the warranted depth. This module joins them; where one of them refuses, the
refusal is carried through verbatim rather than being softened into a verdict.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from metis_mcp.mbt import design as engine
from metis_mcp.mbt import techniques
from metis_mcp.mbt.model import Model

#: How many hex characters of the digest go into a row id. Eight is the same
#: width `identity.claim_id` settled on, for the same reason: long enough that a
#: collision is not a practical concern, short enough to read in a table.
_DIGEST = 8


def row_id(section: str, *parts: str) -> str:
    """A stable id for one row, derived from what the row is about.

    Same behaviour and same condition is the same row, run after run, so the
    decision a person recorded against it is still theirs after a regeneration.
    """
    material = "␟".join(str(p or "") for p in parts)
    digest = hashlib.sha256(material.encode()).hexdigest()[:_DIGEST]
    return f"{section}-{digest}"


@dataclass
class DesignContext:
    """Everything a builder may read. Absent pieces are absent, never faked.

    Each field defaults to nothing rather than to an empty-but-plausible value,
    because the difference between *not gathered* and *gathered and empty* is
    the difference this whole document exists to preserve.
    """

    model: Model | None = None
    #: `get_requirement`'s row: text, criteria, lifecycle_state, anchors.
    requirement: dict | None = None
    #: `get_spec`'s specification rows.
    specifications: tuple[dict, ...] = ()
    #: `coverage_report`'s payload.
    coverage: dict | None = None
    #: `test_design`'s payload — viability, performance, depth, warranted depth.
    viability: dict | None = None
    #: transition id -> risk band, from `risk.product.technical_profile`.
    risk_bands: dict[str, str] = field(default_factory=dict)
    #: transition id -> rank, from `risk.prioritisation.order`.
    ranks: dict[str, int] = field(default_factory=dict)
    #: `test_levels.ExistingTest` rows, or the grade rows already computed.
    existing: dict[str, str] = field(default_factory=dict)
    #: Recovered UI -> API links, as dicts with `action`, `invokes`, `selector`.
    links: tuple[dict, ...] = ()
    #: The answers a person supplied to the asked half.
    answers: dict = field(default_factory=dict)
    #: Which declared inputs were actually gathered, by name.
    gathered: dict = field(default_factory=dict)

    def ordered_transition_ids(self) -> list[str]:
        """Transitions in the order the design works through them.

        **The same order the `prioritise` stage produces**, which is the point:
        a design and the batch generated from it that disagreed about what
        matters first would be two plans. `ranks` comes from
        `risk.prioritisation.order`; the id is the tie-break, so the order is
        total and stable (P-7).
        """
        if self.model is None:
            return []
        unranked = len(self.ranks) + 1
        return sorted(self.model.transition_ids(),
                      key=lambda tid: (self.ranks.get(tid, unranked), tid))

    def band(self, transition_id: str) -> str | None:
        return self.risk_bands.get(transition_id)


def _behaviour(model: Model, transition_id: str) -> str:
    """`(state, trigger) -> outcome`, in the model's own vocabulary."""
    transition = model.transitions[transition_id]
    return f"({transition.source}, {transition.trigger}) -> {transition.target}"


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------

def build_basis(context: DesignContext) -> list[dict]:
    """The claims this design demonstrates, with their provenance and state.

    **Claims are quoted, never paraphrased.** A reworded requirement is a
    different claim -- that is `identity.claim_id`'s whole premise -- so a design
    that summarised one would be designed against something nobody wrote.
    """
    from metis_mcp.ac_quality import assess as assess_quality
    from metis_mcp.ears_checker import check_ears_conformance

    rows: list[dict] = []
    requirement = context.requirement or {}
    text = requirement.get("text") or requirement.get("statement") or ""
    if text:
        conformance = check_ears_conformance(text)
        rows.append({
            "id": row_id("basis", requirement.get("id"), text),
            "claim": text,
            "kind": "Requirement",
            "provenance": requirement.get("provenance") or "",
            "lifecycle": requirement.get("lifecycle_state") or "",
            "quality": ("EARS-conformant" if conformance.conformant
                        else "not EARS-conformant — two readers may satisfy "
                             "this differently (S-13)"),
        })

    for criterion in requirement.get("criteria") or ():
        body = criterion.get("text") or ""
        if not body:
            continue
        findings = [f.describe() for f in assess_quality(body)]
        rows.append({
            "id": row_id("basis", criterion.get("id"), body),
            "claim": body,
            "kind": "AcceptanceCriterion",
            "provenance": criterion.get("provenance") or "",
            "lifecycle": criterion.get("lifecycle_state") or "",
            # Advisory and blocking nothing (S-4). Reported so a reader can
            # weigh what the criterion can actually assert.
            "quality": "; ".join(findings) if findings else "no quality finding",
        })

    for specification in context.specifications or ():
        statement = specification.get("statement") or specification.get("text") or ""
        if not statement:
            continue
        rows.append({
            "id": row_id("basis", specification.get("id"), statement),
            "claim": statement,
            "kind": "Specification",
            "provenance": specification.get("provenance") or "",
            "lifecycle": specification.get("lifecycle_state") or "",
            "quality": "",
        })
    return rows


# ---------------------------------------------------------------------------
# The machine
# ---------------------------------------------------------------------------

def build_machine(context: DesignContext) -> list[dict]:
    """The state machine in scope, as a mermaid state diagram.

    **The one section that is a picture, and the only one Métis draws.** The
    practice this comes from mandates a use-case diagram and a flow chart on
    every design, drawn by hand. Métis has the machine already — so it renders
    what it recovered and draws nothing it did not.

    **What it will not draw.** No actors: an actor is an `asked` input, and a
    diagram inventing one would put a person on the page nobody named. No
    inferred grouping, no implied ordering between unconnected states.

    **The cap is reported, never silently applied** (P-3b). Above
    `MAX_DIAGRAM_TRANSITIONS` a state diagram stops being readable, and a
    picture showing forty of fifty-six transitions with no note is worse than no
    picture — it looks complete. So the diagram is omitted whole and the row
    says how many there were.

    Returns one row carrying the rendered block, because the document's
    machinery is row-shaped and a special case here would be a second kind of
    section for one member.
    """
    model = context.model
    if model is None:
        return []

    transitions = context.ordered_transition_ids()
    if not transitions:
        return []

    from metis_mcp.design.sections import MAX_DIAGRAM_TRANSITIONS

    if len(transitions) > MAX_DIAGRAM_TRANSITIONS:
        return [{
            "id": row_id("machine", model.id),
            "diagram": "",
            "note": (f"{len(transitions)} transitions, above the "
                     f"{MAX_DIAGRAM_TRANSITIONS} a state diagram stays readable "
                     f"at. Not drawn — a diagram showing some of them with no "
                     f"note would look complete. Narrow the journey, or read "
                     f"the tables below, which carry every one."),
        }]

    # `_ordinal` keeps the drawing deterministic without putting a namespaced id
    # on the page: `athena-tms-api::079b43...` is unreadable and changes nothing
    # a reader can act on.
    seen: dict[str, str] = {}

    def node(state_id: str) -> str:
        if state_id not in seen:
            state = model.states.get(state_id)
            name = getattr(state, "name", "") or state_id
            seen[state_id] = name.rsplit("::", 1)[-1]
        return seen[state_id]

    lines = ["stateDiagram-v2"]
    initial = [s for s in sorted(model.states) if
               getattr(model.states[s], "is_initial", False)]
    for state_id in initial:
        lines.append(f"  [*] --> {_mermaid_id(node(state_id))}")

    for tid in transitions:
        transition = model.transitions[tid]
        label = transition.trigger or "?"
        if transition.guard:
            # The guard verbatim, truncated for the page only — the `technique`
            # and `dimensions` sections carry it whole, and this is a picture.
            guard = transition.guard
            if len(guard) > 48:
                guard = guard[:45] + "..."
            label = f"{label} [{guard}]"
        lines.append(
            f"  {_mermaid_id(node(transition.source))} --> "
            f"{_mermaid_id(node(transition.target))}: {_mermaid_label(label)}")

    return [{
        "id": row_id("machine", model.id),
        "diagram": "\n".join(lines),
        "note": (f"{len(model.states)} state(s), {len(transitions)} transition(s), "
                 f"in the order the rest of this design works through them."),
    }]


def _mermaid_id(name: str) -> str:
    """A state name as a mermaid identifier.

    Mermaid ids cannot carry spaces or punctuation, and a name that produced an
    invalid one would break the whole block rather than one line — which is why
    this substitutes rather than quoting and hoping.
    """
    import re as _re

    cleaned = _re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_")
    return cleaned or "unnamed"


def _mermaid_label(text: str) -> str:
    """A transition label, with the characters mermaid reads as syntax removed."""
    return (text.replace(":", " -").replace("\n", " ")
                .replace("<", "&lt;").replace(">", "&gt;"))


# ---------------------------------------------------------------------------
# Condition completeness
# ---------------------------------------------------------------------------

#: What each class is decided from, and — for the two Métis cannot draw — why
#: not. Kept beside the builder rather than inside it so the claim "this class
#: is undrawn" is a declaration a reader can check, not a branch they have to
#: find.
_UNDRAWN = {
    "dependency-failure": (
        "what happens when a required dependency stops answering is not in the "
        "source this was recovered from"),
    "non-goal": (
        "what is deliberately excluded is a decision somebody made, and it is "
        "recorded nowhere the extraction can reach"),
}


def build_conditions(context: DesignContext) -> list[dict]:
    """Every behaviour against the eight classes, each with an explicit decision.

    **The denominator, and the reason a design overstates itself without one.** A
    positive case says what the system does. It does not say what the system must
    reject, prevent, limit or leave alone — and counted as coverage for those, it
    excuses exactly the gaps somebody is paying for tests to find.

    `shared/knowledge/requirement-condition-coverage.md` has stated this rule for
    as long as it has existed, and nothing applied it: it was prose a model was
    asked to follow. The placement rule
    (`docs/academy/10-where-a-thing-belongs.md`) says a checkable rule is a tool,
    and six of the eight classes are computable from what Métis already recovered.

    **Every class gets a row, including the ones that do not apply.** That is the
    whole mechanism: a behaviour with no numeric threshold still needs a
    `boundary` row marked `not-applicable` *with a reason*. What it must not do is
    silently disappear.

    **Métis proposes; it never decides.** `proposed` is its reading and
    `decision` is a person's, and the two are separate columns because a class
    Métis could not reach reads `clarify` — which is neither "we will test it"
    nor "it does not apply".
    """
    from metis_mcp.mbt import techniques
    from metis_mcp.mbt.criteria import guard_conditions
    from metis_mcp.design.sections import CONDITION_CLASSES

    model = context.model
    if model is None:
        return []

    # A rejection sibling is what makes `prohibited` answerable: the complement
    # of a guard has a case only where the model carries the other branch.
    rejections: dict[tuple[str, str], list[str]] = {}
    for transition in model.transitions.values():
        status = transition.outcome_status or 0
        if status >= 400:
            rejections.setdefault(
                (transition.source, transition.trigger), []).append(transition.id)

    rows: list[dict] = []
    for tid in context.ordered_transition_ids():
        transition = model.transitions[tid]
        behaviour = _behaviour(model, tid)
        band = context.band(tid)
        analysis = techniques.analyse_guard(transition.guard or "")
        conditions = guard_conditions(transition)
        siblings = rejections.get((transition.source, transition.trigger), [])

        for condition_class in CONDITION_CLASSES:
            found, provenance, proposed, reason = _decide_class(
                condition_class, transition, analysis, conditions, siblings)
            rows.append({
                "id": row_id("cond", tid, condition_class),
                "subject": behaviour,
                "condition_class": condition_class,
                "found": found,
                "provenance": provenance,
                "proposed": proposed,
                "reason": reason,
                "risk_band": band,
            })
    return rows


def _decide_class(condition_class, transition, analysis, conditions, siblings):
    """`(found, provenance, proposed, reason)` for one class of one behaviour.

    Split out because eight branches inside a loop is where a class quietly
    stops being decided — and the one property this section has is that none of
    them can.
    """
    # Recovered from code, so it can only report that the code agrees with
    # itself (S-19). Never `independently_authored`, which is what intent is.
    recovered = "code_derived"

    if condition_class == "allowed":
        return (f"the transition itself: {transition.trigger} -> "
                f"{transition.target}", recovered, "test",
                "the behaviour is recovered and has an outcome")

    if condition_class == "prohibited":
        if siblings:
            return (f"{len(siblings)} rejecting sibling(s) on this "
                    f"(state, trigger)", recovered, "test",
                    "the complement is a recovered branch with its own outcome")
        if transition.guard:
            return ("", "", "clarify",
                    "the guard has conditions and no rejecting sibling was "
                    "recovered — what happens when it does not hold is unstated")
        return ("", "", "clarify",
                "no guard, so there is no complement to reject. Whether this "
                "behaviour can be refused at all is not a code fact")

    if condition_class == "partition":
        if analysis.partitions:
            return (f"{len(analysis.partitions)} partition(s) from the guard",
                    recovered, "test",
                    "the guard divides its inputs into classes that behave "
                    "differently")
        return ("", "", "not-applicable",
                "no guard condition partitions an input here")

    if condition_class == "boundary":
        if analysis.boundaries:
            return (f"{len(analysis.boundaries)} boundary condition(s)",
                    recovered, "test", "a numeric threshold has edges")
        if analysis.unanalysable:
            return ("", "", "not-applicable",
                    f"no numeric threshold: {analysis.unanalysable[0][1]}")
        return ("", "", "not-applicable",
                "no numeric constraint was recovered on this behaviour")

    if condition_class == "state-transition":
        return (f"{transition.source} -> {transition.target}", recovered, "test",
                "the machine states which state permits this and what it leaves "
                "behind")

    if condition_class == "authorization":
        if transition.security:
            return (f"{len(transition.security)} declared requirement(s)",
                    recovered, "test",
                    "a declarative check was recovered, so a caller without it "
                    "has a case")
        return ("", "", "clarify",
                "no declarative check was recovered. Declarative security is all "
                "extraction sees, so this is 'nobody looked', never 'open'")

    return ("", "", "clarify", _UNDRAWN[condition_class])


# ---------------------------------------------------------------------------
# Setup cost and data complexity
# ---------------------------------------------------------------------------

#: Verbs that leave something behind. Read from the recovered trigger, which is
#: the method the code answers on — not from a business word in a title.
_WRITING = ("POST", "PUT", "PATCH", "DELETE")
_READING = ("GET", "HEAD", "OPTIONS")


def _effect_of(trigger: str) -> str:
    """Whether reaching this changes anything, or `unknown`.

    **`unknown` rather than a default, and the login fixture is why.** A UI
    action's trigger is `submit_valid_credentials`, which is not an HTTP verb —
    so a rule that fell through to `read-only` would call a credential
    submission a read and hand it the cheapest cost band in the table. The
    effect is recovered from the verb or it is not recovered.
    """
    verb = (trigger or "").split(None, 1)[0].upper()
    if verb in _WRITING:
        return "state-changing"
    if verb in _READING:
        return "read-only"
    return "unknown"


def build_setup(context: DesignContext) -> list[dict]:
    """What reaching each behaviour costs, from the setup chain itself.

    **Computed, where the obvious version is guessed.** The practice this comes
    from classifies a slice by its business verb — `get` and `view` are cheap,
    `create` and `approve` are not. That is a stand-in for the real question,
    which is how much has to be true before the assertion can happen. Métis
    already answers it: `path_generation` walks the machine, and
    `Path.setup_transition_ids` IS the chain a test must establish.

    **The pattern is a person's choice and is left to them.** Whether existing
    data can be reused, or an isolated entity must be provisioned, depends on
    what the environment holds and who owns cleanup — and both are `asked`
    inputs. Métis computes the cost and states the two facts behind it; picking
    the pattern with that in hand is the part it must not do.
    """
    from metis_mcp.mbt.path_generation import shortest_setup

    model = context.model
    if model is None:
        return []

    rows: list[dict] = []
    for tid in context.ordered_transition_ids():
        transition = model.transitions[tid]
        # **Walked with `generatable_only=False`, deliberately.** `generate`
        # honours D-10 and excludes everything at `Quarantine`, which is correct
        # for generation and wrong here: a design is a pre-approval artefact —
        # the `test-design` workflow has no approval precondition precisely
        # because designing before approval is when it changes a decision. Going
        # through `generate` produced an empty section for every real model, and
        # its `empty_means` would have said "no path could be generated" while
        # hiding that the reason was approval rather than reachability.
        setup = shortest_setup(model, transition.source,
                               generatable_only=False)
        if setup is None:
            # **Genuinely unreachable**, which is a different fact from
            # unapproved and is the one worth omitting a row for: inventing a
            # cost would put a cheap-looking number on behaviour no test can get
            # to at all. `validate` is what reports it.
            continue
        effect = _effect_of(transition.trigger)
        depth = len(setup)
        complexity, basis = _cost_of(effect, depth)

        rows.append({
            "id": row_id("setup", tid),
            "behaviour": _behaviour(model, tid),
            "effect": effect,
            "setup_depth": depth,
            "preconditions": " → ".join(
                model.transitions[s].trigger for s in setup
                if s in model.transitions) or "none",
            "complexity": complexity,
            "basis": basis,
            "risk_band": context.band(tid),
        })
    return rows


def _cost_of(effect: str, depth: int) -> tuple[str, str]:
    """The cost band and the two facts behind it.

    Stated as a rule rather than a table lookup so a reader can disagree with
    the rule. Both inputs are recovered: the verb from the trigger, the depth
    from the path.
    """
    if effect == "unknown":
        # Depth alone, and the band says the other half is missing. Guessing the
        # effect here is what `_effect_of` refuses to do; guessing it one
        # function later would be the same guess in a different place.
        if depth <= 1:
            return "moderate", (
                f"{depth} setup step(s), and the effect is UNKNOWN — the trigger "
                f"carries no HTTP verb, so whether this writes was not recovered")
        return "escalate", (
            f"{depth} setup steps, and the effect is UNKNOWN. Cost is being read "
            f"from depth alone; confirm whether this writes before scheduling it")
    if effect == "read-only":
        if depth == 0:
            return "minimal", "read-only, and reachable with no setup"
        if depth == 1:
            return "minimal", "read-only, one setup step"
        return "moderate", f"read-only, but {depth} setup steps to reach"
    if depth <= 1:
        return "moderate", f"state-changing, {depth} setup step(s) — cleanup is owed"
    return ("escalate",
            f"state-changing after {depth} setup steps. Split it, stage it, or "
            f"make the cost visible — do not hide it in a precondition")


# ---------------------------------------------------------------------------
# Negative obligations
# ---------------------------------------------------------------------------

#: Which statuses satisfy each obligation. Ranges rather than one number,
#: because 401 and 403 are both a refusal and 400 and 422 are both a rejection —
#: and insisting on one of each pair would report an endpoint as unmet for
#: choosing the other.
_SATISFIED_BY = {
    "not-found": (404,),
    "authorization-denied": (401, 403),
    "validation-error": (400, 422),
}


def build_obligations(context: DesignContext) -> list[dict]:
    """What each endpoint's own shape obliges it to do, and whether it does.

    **The obligation is derived from a recovered fact, never from a name.** A
    path parameter obliges a not-found; a declared security requirement obliges
    a refusal; a body or a required query parameter obliges a rejection; an
    enumerated input obliges a case per constant. A route that merely *looks*
    like it should have one obliges nothing (X-6).

    **`unmet` is a question, not a defect.** The practice this comes from writes
    the negative scenario outright, with the status hardcoded — 400, 401/403,
    404. Métis knows what the endpoint was actually seen to produce, so it
    reports the recovered set and says no such outcome is in it. Whether the
    behaviour is unhandled or extraction did not see it is something only a
    person can settle, and declaring it a defect would be Métis asserting a
    conclusion from an absence.

    Grouped by trigger, because an obligation belongs to the endpoint rather
    than to one of its outcomes.
    """
    model = context.model
    if model is None:
        return []

    by_endpoint: dict[str, list] = {}
    for tid in context.ordered_transition_ids():
        transition = model.transitions[tid]
        by_endpoint.setdefault(transition.trigger, []).append(transition)

    rows: list[dict] = []
    for trigger, transitions in by_endpoint.items():
        statuses = {t.outcome_status for t in transitions if t.outcome_status}
        recovered = ", ".join(str(s) for s in sorted(statuses)) or "none"
        band = context.band(transitions[0].id)
        # One endpoint, one shape: the parameters and security are the same
        # across its outcomes, so the first carries them for all.
        first = transitions[0]
        inputs = first.inputs or ()

        for obligation, because in _obligations_of(first, inputs):
            if obligation == "enum-variation":
                # Not judged against a status: covering every constant is a data
                # obligation, and `build_data` is where the conditions live.
                rows.append({
                    "id": row_id("obl", trigger, obligation, because),
                    "endpoint": trigger, "obligation": obligation,
                    "because": because, "recovered": recovered,
                    "satisfied_by": "",
                    "status": "unmet",
                    "risk_band": band,
                })
                continue

            wanted = _SATISFIED_BY[obligation]
            carrier = next((t for t in transitions
                            if t.outcome_status in wanted), None)
            rows.append({
                "id": row_id("obl", trigger, obligation),
                "endpoint": trigger,
                "obligation": obligation,
                "because": because,
                "recovered": recovered,
                "satisfied_by": carrier.id if carrier else "",
                "status": "satisfied" if carrier else "unmet",
                "risk_band": band,
            })
    return rows


def _obligations_of(transition, inputs) -> list[tuple[str, str]]:
    """`(obligation, because)` for one endpoint, from what was recovered.

    Every entry names the fact that raised it. An obligation whose `because` a
    reader cannot check is one they have to take on trust, which is the same
    objection T-9a makes about an unanchored guard.
    """
    found: list[tuple[str, str]] = []

    path_params = [p for p in inputs if (p or {}).get("location") == "path"]
    if path_params:
        names = ", ".join(str((p or {}).get("name")) for p in path_params)
        found.append(("not-found",
                      f"takes a path parameter ({names}), so it can be asked "
                      f"for something that does not exist"))

    if transition.security:
        found.append(("authorization-denied",
                      f"{len(transition.security)} declared security "
                      f"requirement(s), so a caller can lack them"))

    rejectable = [p for p in inputs
                  if (p or {}).get("location") == "body"
                  or ((p or {}).get("location") == "query"
                      and (p or {}).get("required", False))]
    if rejectable:
        where = ", ".join(sorted({str((p or {}).get("location"))
                                  for p in rejectable}))
        found.append(("validation-error",
                      f"accepts input that can be malformed or omitted ({where})"))

    for parameter in inputs:
        values = (parameter or {}).get("enum_values") or ()
        if values:
            found.append(("enum-variation",
                          f"`{(parameter or {}).get('name')}` is enumerated over "
                          f"{len(values)} constant(s)"))
    return found


# ---------------------------------------------------------------------------
# Defect-proneness factors
# ---------------------------------------------------------------------------

#: What each factor asks the DESIGN to do. `technical_profile`'s docstring makes
#: the argument — "high branching is met with more test cases, high fan-in is met
#: with a contract nobody may break" — and then nothing acted on it, because only
#: the band was ever surfaced.
_RESPONSES = {
    "branching": "more cases: one per condition combination, not one per branch",
    "fan_in": "a contract nobody may break — changing this outcome reaches every "
              "caller that arrives here",
    "fan_out": "a decision table over the (state, trigger) group, which is where "
               "a missing rule hides",
    "unverifiable_guards": "no oracle: a sibling's guard cannot be asserted, so "
                           "cover it another way and say which",
    "code_complexity": "more paths through the handler than the guard shows — "
                       "read it before designing against it",
    "code_size": "the handler is large; confirm the behaviour is one behaviour "
                 "before writing one case for it",
    "repairs": "defect history, which is the strongest single signal here — this "
               "file has been repaired before",
}


def build_profile(context: DesignContext) -> list[dict]:
    """The factors behind the band, one row each, including the unmeasured ones.

    **A band says how much there is to get wrong and hides what.**
    `product.technical_profile` returns the individual factors deliberately, and
    says why in its own docstring — and until this section existed nothing read
    them: `test_design` surfaced the band, `prioritisation` ordered by it, and
    the response was always "test this more", which is the answer to none of them.

    **An unmeasured factor is a row, not a blank.** `not_measured` names what has
    no measurement, and a blank cell in a table of counts reads as zero — which
    would make an unmeasured handler look like a simple one. That is the exact
    reading `technical_profile` refuses when it leaves them out of `observed`.
    """
    from metis_mcp.risk import product

    model = context.model
    if model is None:
        return []

    unverifiable = product.unverifiable_ids(model)
    rows: list[dict] = []
    for tid in context.ordered_transition_ids():
        try:
            profile = product.technical_profile(model, tid, unverifiable)
        except KeyError:
            continue
        behaviour = _behaviour(model, tid)
        band = profile.get("band")

        for factor, observed in sorted((profile.get("observed") or {}).items()):
            rows.append({
                "id": row_id("prof", tid, factor),
                "behaviour": behaviour,
                "factor": factor,
                "observed": observed,
                "rating": (profile.get("factors") or {}).get(factor),
                "response": _RESPONSES.get(factor, ""),
                "risk_band": band,
            })

        for factor in profile.get("not_measured") or ():
            rows.append({
                "id": row_id("prof", tid, factor),
                "behaviour": behaviour,
                "factor": factor,
                # Spelled out rather than left blank: a blank in a column of
                # counts reads as zero, and zero here would read as "simple".
                "observed": "not measured",
                "rating": None,
                "response": _not_measured_means(factor, profile),
                "risk_band": band,
            })
    return rows


def _not_measured_means(factor: str, profile: dict) -> str:
    """What an absent measurement means, per factor.

    `repairs` is the one worth separating: a file counted and never repaired
    scores 1, and a file nobody counted has no score at all. `repairs_window` is
    what tells them apart, and it is empty exactly when nobody asked.
    """
    if factor == "repairs" and not profile.get("repairs_window"):
        return ("no window was given, so nothing was counted. This is not a "
                "file with no repairs — set `METIS_HISTORY_SINCE` and land the "
                "history to find out which it is")
    return (f"{factor} was not measured at extraction; it contributes nothing "
            f"to the band and must not be read as its best value")


# ---------------------------------------------------------------------------
# Techniques and coverage items
# ---------------------------------------------------------------------------

def build_technique(context: DesignContext) -> list[dict]:
    """Which technique each behaviour warrants, and how many items it yields.

    **A refusal is a row.** `decision_table` declines a guard containing an OR,
    and `analyse_guard` declines a predicate with no numeric boundary; both
    refusals appear here in the `unavailable` column rather than being dropped.
    A technique that could not be applied is a fact a designer needs -- silently
    omitting it makes the design look like it considered fewer options than it
    did.
    """
    model = context.model
    if model is None:
        return []

    rows: list[dict] = []
    seen_groups: set[tuple[str, str]] = set()

    for tid in context.ordered_transition_ids():
        transition = model.transitions[tid]
        behaviour = _behaviour(model, tid)
        band = context.band(tid)

        # Equivalence partitions and boundaries, from the guard itself.
        analysis = techniques.analyse_guard(transition.guard or "")
        for partition in analysis.partitions:
            rows.append({
                "id": row_id("tech", tid, techniques.__name__,
                             partition.condition),
                "behaviour": behaviour,
                "condition": partition.condition,
                "technique": "equivalence-partition",
                "items": 1,
                "unavailable": "",
                "risk_band": band,
            })
        for boundary in analysis.boundaries:
            rows.append({
                "id": row_id("tech", tid, "bva", boundary.condition),
                "behaviour": behaviour,
                "condition": boundary.condition,
                "technique": "boundary-value",
                "items": 1,
                "unavailable": "",
                "risk_band": band,
            })
        for atom, reason in analysis.unanalysable:
            rows.append({
                "id": row_id("tech", tid, "bva-refused", atom),
                "behaviour": behaviour,
                "condition": atom,
                "technique": "boundary-value",
                "items": 0,
                # Carried verbatim: `techniques.py` fails closed on anything it
                # cannot parse, and inventing a boundary is what M-9 forbids.
                "unavailable": reason,
                "risk_band": band,
            })

        # The decision table belongs to a `(state, trigger)` group, not to one
        # transition, so it is emitted once per group.
        group = (transition.source, transition.trigger)
        if group not in seen_groups:
            seen_groups.add(group)
            table = engine.decision_table(model, *group)
            if table.is_available:
                uncovered = len(table.uncovered)
                rows.append({
                    "id": row_id("tech", *group, "decision-table"),
                    "behaviour": f"({group[0]}, {group[1]})",
                    "condition": " / ".join(table.conditions),
                    "technique": "decision-table",
                    "items": len(table.rules),
                    "unavailable": (f"{uncovered} combination(s) reach no "
                                    f"transition" if uncovered else ""),
                    "risk_band": band,
                })
            else:
                rows.append({
                    "id": row_id("tech", *group, "decision-table"),
                    "behaviour": f"({group[0]}, {group[1]})",
                    "condition": "",
                    "technique": "decision-table",
                    "items": 0,
                    "unavailable": table.reason_unavailable,
                    "risk_band": band,
                })

        # Pairwise, over what the parameters can vary.
        factors = engine.factors_for(transition)
        if len(factors) >= 2:
            combinations = engine.all_pairs(factors)
            rows.append({
                "id": row_id("tech", tid, "pairwise"),
                "behaviour": behaviour,
                "condition": ", ".join(f.name for f in factors),
                "technique": "pairwise",
                "items": len(combinations),
                "unavailable": "",
                "risk_band": band,
            })
        elif factors:
            rows.append({
                "id": row_id("tech", tid, "pairwise"),
                "behaviour": behaviour,
                "condition": factors[0].name,
                "technique": "pairwise",
                "items": 0,
                "unavailable": "only one input varies — pairwise over a single "
                               "factor is equivalence partitioning under "
                               "another name",
                "risk_band": band,
            })

        # State-transition coverage always applies: it is what the model IS.
        rows.append({
            "id": row_id("tech", tid, "state-transition"),
            "behaviour": behaviour,
            "condition": transition.guard or "unguarded",
            "technique": "state-transition",
            "items": 1,
            "unavailable": "",
            "risk_band": band,
        })
    return rows


# ---------------------------------------------------------------------------
# Guard dimensions and the reduction
# ---------------------------------------------------------------------------

def build_dimensions(context: DesignContext) -> list[dict]:
    """The short-circuit chain per behaviour, and what covering it costs.

    **This is the section `mbt/dimensions.py` was written for and never had.**
    Four hundred lines implementing GD-1..GD-9 — the reduction that turns
    `3 auth x 2 authz x 10 payload = 60` cases into 13 — sat with no caller
    outside its own tests, because the checks it needs never reached a loaded
    model and, when they finally did, `GuardCheck` carried no `id` for it to
    read.

    **One row per dimension, and the chain-level reduction on every one of
    them.** A designer needs both: which condition sits where in the evaluation
    order, and what the whole chain costs. Splitting them across two tables would
    make the second unreadable without the first.

    **A refusal is a row.** Where precedence could not be recovered, GD-9 says
    the chain is neither assumed ordered nor assumed independent: `cost` reports
    the full product with `exploded=True`, and that reason is carried here
    verbatim rather than being softened into a number.
    """
    from metis_mcp.mbt.dimensions import build_chain, cost

    model = context.model
    if model is None:
        return []

    rows: list[dict] = []
    for tid in context.ordered_transition_ids():
        transition = model.transitions[tid]
        checks = getattr(transition, "checks", ()) or ()
        if not checks:
            # No row. A behaviour with no recovered check has no chain, and an
            # empty chain rendered as a row would read as "one dimension, none".
            continue

        chain = build_chain(tid, checks)
        chain_cost = cost(chain)
        behaviour = _behaviour(model, tid)
        band = context.band(tid)
        # `exploded` already means the bound does not apply, so the reduction
        # reads as the product against itself — which is the honest rendering of
        # "no reduction was available".
        reduction = f"{chain_cost.bounded_total} of {chain_cost.product_total}"

        for dimension in chain.ordered():
            rows.append({
                "id": row_id("dim", tid, dimension.id),
                "behaviour": behaviour,
                "condition": dimension.expression,
                # X-10c: an unclassified check keeps its position. `None` from
                # `classify` renders as blank, which is the recovered fact.
                "dimension_class": dimension.dimension_class or "",
                "order": dimension.order,
                "cases": chain_cost.per_dimension.get(dimension.id),
                "reduction": reduction,
                "anchor": dimension.anchor,
                "unavailable": chain_cost.reason,
                "risk_band": band,
            })
    return rows


# ---------------------------------------------------------------------------
# Test data conditions
# ---------------------------------------------------------------------------

def build_data(context: DesignContext) -> list[dict]:
    """What the data must satisfy, per input, as a condition.

    The `accepted_space` column is the X-6e form -- the space, never a value
    somebody could paste. `derivation` says how the condition was reached, so a
    reader can weigh a bound recovered from `@Size(max=64)` differently from one
    read out of a numeric guard.
    """
    from metis_mcp.rendering.test_case import input_condition

    model = context.model
    if model is None:
        return []

    rows: list[dict] = []
    for tid in context.ordered_transition_ids():
        transition = model.transitions[tid]
        band = context.band(tid)

        for parameter in transition.inputs or ():
            name = (parameter or {}).get("name") or ""
            if not name:
                continue
            constraints = tuple((parameter or {}).get("constraints") or ())
            analysis = techniques.analyse_constraints(constraints)
            conditions = [b.condition for b in analysis.boundaries] or \
                         [p.condition for p in analysis.partitions]
            rows.append({
                "id": row_id("data", tid, name),
                "input": f"{(parameter or {}).get('location', '?')}.{name}",
                "accepted_space": input_condition(parameter),
                "condition": "; ".join(conditions) if conditions else
                             ("required" if (parameter or {}).get("required", True)
                              else "may be omitted"),
                "derivation": "contract",
                "risk_band": band,
            })

        # `data_requirements` are GD-3's declared constraints a request must
        # violate to reach a rejection. They are conditions already; restating
        # them as anything else would be inventing.
        for requirement in transition.data_requirements or ():
            text = requirement if isinstance(requirement, str) else str(requirement)
            rows.append({
                "id": row_id("data", tid, "violate", text),
                "input": transition.trigger,
                "accepted_space": text,
                "condition": f"must violate: {text}",
                "derivation": "contract",
                "risk_band": band,
            })

        # Conditions the guard itself imposes, which the contract does not know.
        analysis = techniques.analyse_guard(transition.guard or "")
        for boundary in analysis.boundaries:
            rows.append({
                "id": row_id("data", tid, "guard", boundary.condition),
                "input": boundary.variable,
                "accepted_space": f"as constrained by `{boundary.source_guard}`",
                "condition": boundary.condition,
                "derivation": techniques.FROM_THRESHOLD,
                "risk_band": band,
            })
        for partition in analysis.partitions:
            if partition.derived_from != techniques.FROM_PREDICATE:
                continue
            rows.append({
                "id": row_id("data", tid, "guard-part", partition.condition),
                "input": partition.variable,
                "accepted_space": f"as constrained by `{partition.source_guard}`",
                "condition": partition.condition,
                "derivation": techniques.FROM_PREDICATE,
                "risk_band": band,
            })
    return rows


# ---------------------------------------------------------------------------
# Levels, existing coverage and viability
# ---------------------------------------------------------------------------

def build_levels(context: DesignContext) -> list[dict]:
    """Where each behaviour is asserted, what reaches it, and what it can bear.

    **`warranted` and `depth` are two different questions and both are shown.**
    `classify_depth` says what the model can support; `warranted_depth` says what
    the risk band justifies. Behaviour that warrants more than it can receive is
    the interesting case, and neither column finds it alone -- so the gap is
    carried into the uncertainty section rather than being averaged away here.
    """
    from metis_mcp.mbt.test_levels import UNCOVERED
    from metis_mcp.risk.prioritisation import warranted_depth

    model = context.model
    if model is None:
        return []

    viability = context.viability or {}
    verdicts = {row.get("transition_id"): row.get("verdict")
                for row in _rows_of(viability, "viability")}
    depths = {row.get("transition_id"): row.get("verdict")
              for row in _rows_of(viability, "depth")}

    rows: list[dict] = []
    for tid in context.ordered_transition_ids():
        band = context.band(tid)
        rows.append({
            "id": row_id("level", tid),
            "behaviour": _behaviour(model, tid),
            "level": _level_for(model, tid),
            # Absent is NOT covered-as-zero: a transition the grader never saw
            # is reported `uncovered` only because that is the grade's own
            # meaning, and the ledger records separately whether coverage was
            # measured at all.
            "existing": context.existing.get(tid, UNCOVERED),
            "viability": verdicts.get(tid, ""),
            "depth": depths.get(tid, ""),
            "warranted": warranted_depth(band).get("approach") or "",
            "risk_band": band,
        })
    return rows


def _rows_of(payload: dict, key: str) -> list[dict]:
    """The row list under `key`, tolerating the summarised form.

    `test_design(detail=False)` replaces its row lists with counts. Reading an
    int as a list would raise; reading it as empty would quietly lose every row.
    So the summarised form yields nothing and the caller's column renders blank,
    which is the honest outcome for a payload that was asked not to carry rows.
    """
    section = payload.get(key)
    if isinstance(section, dict):
        section = section.get("rows")
    return section if isinstance(section, list) else []


def _level_for(model: Model, transition_id: str) -> str:
    """The level this transition's assertion sits at.

    Derived from the surface the model carries, which is a first-class field --
    a lookup rather than a judgement, the same classification
    `metis-test-generate` makes when it routes to a specialist.
    """
    from metis_mcp.mbt.test_levels import API_FUNCTIONAL, WEB_FUNCTIONAL

    transition = model.transitions[transition_id]
    state = model.states.get(transition.source)
    surface = getattr(state, "surface", "api") or "api"
    return WEB_FUNCTIONAL if surface == "ui" else API_FUNCTIONAL


# ---------------------------------------------------------------------------
# Authorisation and authentication
# ---------------------------------------------------------------------------

def build_security(context: DesignContext) -> list[dict]:
    """What each call requires of a caller, and the refusal case beside it.

    **The negative condition is the column that matters.** A recovered
    authorisation check with no case for the identity that must be refused is
    asserted by nothing, and that is the ordinary state of an API test suite.
    Métis can state the complement as a condition; it cannot say whether the
    check is the right one, which is why `obligation` is a human column.
    """
    model = context.model
    if model is None:
        return []

    rows: list[dict] = []
    for tid in context.ordered_transition_ids():
        transition = model.transitions[tid]
        declared = transition.security or ()
        if not declared:
            continue
        for entry in declared:
            record = entry if isinstance(entry, dict) else {"name": str(entry)}
            scheme = record.get("scheme") or record.get("type") or ""
            authority = (record.get("role") or record.get("scope")
                         or record.get("name") or "")
            rows.append({
                "id": row_id("sec", tid, scheme, authority),
                "call": transition.trigger,
                "authentication": scheme or "declared, scheme unrecovered",
                "authority": authority,
                "negative_case": (f"a caller without `{authority}` is refused"
                                  if authority else
                                  "an unauthenticated caller is refused"),
                "risk_band": context.band(tid),
            })
    return rows


# ---------------------------------------------------------------------------
# Load and performance candidacy
# ---------------------------------------------------------------------------

def build_performance(context: DesignContext) -> list[dict]:
    """Which calls are worth driving under load, carrying `no-basis` intact.

    `viability.py` reports `no-basis` where the model holds no volume fact, and
    that verdict is copied here unchanged. Rounding it to `functional-only`
    would read as "measured, and none qualify", which is a claim nobody made.
    """
    model = context.model
    if model is None:
        return []

    rows = _rows_of(context.viability or {}, "performance")
    if not rows:
        return []

    out: list[dict] = []
    ranked = {tid: i for i, tid in enumerate(context.ordered_transition_ids())}
    for row in sorted(rows, key=lambda r: (ranked.get(r.get("transition_id"),
                                                      len(ranked)),
                                           str(r.get("transition_id")))):
        tid = row.get("transition_id")
        transition = model.transitions.get(tid)
        out.append({
            "id": row_id("perf", tid),
            "call": transition.trigger if transition else str(tid),
            "candidacy": row.get("verdict") or "",
            "basis": row.get("reason") or row.get("basis") or "",
            "risk_band": context.band(tid),
        })
    return out


# ---------------------------------------------------------------------------
# Contract and interface
# ---------------------------------------------------------------------------

def build_contract(context: DesignContext) -> list[dict]:
    """What each call declares against what was recovered from its code.

    A deviation is a test case *and* a question. It is never reported as a
    defect: the document may be stale or the code may be wrong, and deciding
    which is a person's judgement that no static comparison can make.
    """
    model = context.model
    if model is None:
        return []

    rows: list[dict] = []
    for tid in context.ordered_transition_ids():
        transition = model.transitions[tid]
        declared_status = transition.outcome_status
        body = transition.response_body
        # `outcome_source` separates a status constructed in code from one only
        # declared on an annotation. That difference IS the deviation question.
        recovered = (f"{declared_status or '?'}"
                     f"{' ' + body if body else ' (no body)'}")
        deviation = ""
        if transition.outcome_source and transition.outcome_source != "constructed":
            deviation = (f"the outcome is {transition.outcome_source}, not "
                         f"constructed in code — the document asserts it and "
                         f"nothing was seen to produce it")
        rows.append({
            "id": row_id("contract", tid),
            "call": transition.trigger,
            "declared": (f"{declared_status}" if declared_status else
                         "no status declared"),
            "recovered": recovered,
            "deviation": deviation,
            "risk_band": context.band(tid),
        })
    return rows


# ---------------------------------------------------------------------------
# Cross-surface journeys
# ---------------------------------------------------------------------------

def build_journey(context: DesignContext) -> list[dict]:
    """UI actions and the calls they invoke, with the guard M-5c lets them inherit.

    A selector is authored or it does not exist. An element with no authored
    selector renders as absent rather than as a guess (X-6e) -- guessing one
    produces a case that looks executable and is not.
    """
    if not context.links:
        return []

    rows: list[dict] = []
    for link in sorted(context.links, key=lambda link: (
            str(link.get("action") or ""), str(link.get("invokes") or ""))):
        action = link.get("action") or ""
        invokes = link.get("invokes") or ""
        rows.append({
            "id": row_id("journey", action, invokes),
            "action": action,
            "invokes": invokes,
            "inherited_guard": link.get("inherited_guard") or "",
            "selector": link.get("selector") or "no authored selector",
            "risk_band": context.risk_bands.get(invokes),
        })
    return rows


# ---------------------------------------------------------------------------
# Open questions and assumptions
# ---------------------------------------------------------------------------

def build_uncertainty(context: DesignContext) -> list[dict]:
    """Every input nobody supplied, and which section it silenced.

    **This section is the reason the rest can be trusted.** A design that lists
    what it covers and not what it could not consider is a design whose gaps read
    as decisions. Each row carries the exact question, so answering is possible
    without going and finding the ledger.
    """
    from metis_mcp.design import inputs as ledger

    result = ledger.completeness(gathered=context.gathered,
                                 answers=context.answers)
    silenced = ledger.unstatable(result["missing_required"])

    rows: list[dict] = []
    for missing in result["missing_inputs"]:
        name = missing["name"]
        declared = ledger.BY_NAME.get(name)
        affected = sorted(section for section, names in silenced.items()
                          if name in names)
        rows.append({
            "id": row_id("open", name),
            "question": (missing.get("question") or
                         (f"not gathered — `{missing.get('tool')}` supplies it"
                          if missing.get("tool") else "")),
            "decides": declared.why if declared else "",
            "absent_means": missing["absent_means"],
            "silences": ", ".join(affected) if affected else
                        "cross-cutting — it affects every section",
        })

    # The depth gap is an uncertainty of a different kind: nothing is missing,
    # and the design still cannot do what the risk band asks of it. It belongs
    # here because that is where a reader looks for what the design cannot say.
    rows += _depth_gap_rows(context)
    return rows


def _depth_gap_rows(context: DesignContext) -> list[dict]:
    """Behaviour that warrants deeper testing than the model can support.

    `prioritisation.depth_gaps` already computes this join; surfacing it as an
    open question is what turns it from a figure into something somebody owns.
    """
    from metis_mcp.risk.prioritisation import depth_gaps, warranted_depth

    viability = context.viability or {}
    achievable = {row.get("transition_id"): row.get("verdict")
                  for row in _rows_of(viability, "depth")}
    if not achievable or not context.risk_bands:
        return []

    warranted = {tid: warranted_depth(band).get("approach")
                 for tid, band in context.risk_bands.items()}
    rows: list[dict] = []
    for gap in depth_gaps(warranted, achievable):
        tid = gap.get("transition_id") or gap.get("id") or ""
        rows.append({
            "id": row_id("open", "depth", str(tid)),
            "question": (f"{tid} warrants deeper testing than the model can "
                         f"support. How will that be covered — manually, by "
                         f"changing the code, or by accepting the gap?"),
            "decides": "whether behaviour the band says matters is tested at all",
            "absent_means": ("THE GAP IS UNOWNED. It is not a coverage figure "
                             "and will not appear in one: the behaviour may be "
                             "fully covered at the depth it can reach"),
            "silences": "levels",
        })
    return rows


#: Builder name -> function. `sections.py` names one per section and this is
#: where the name resolves, so a section pointing at nothing fails a test rather
#: than rendering an empty table.
BUILDERS = {
    "build_basis": build_basis,
    "build_machine": build_machine,
    "build_conditions": build_conditions,
    "build_obligations": build_obligations,
    "build_profile": build_profile,
    "build_setup": build_setup,
    "build_technique": build_technique,
    "build_dimensions": build_dimensions,
    "build_data": build_data,
    "build_levels": build_levels,
    "build_security": build_security,
    "build_performance": build_performance,
    "build_contract": build_contract,
    "build_journey": build_journey,
    "build_uncertainty": build_uncertainty,
}


def builder_for(name: str):
    """The function a section names, or a KeyError naming what exists."""
    try:
        return BUILDERS[name]
    except KeyError:
        raise KeyError(
            f"no builder named {name!r}. Known: "
            f"{', '.join(sorted(BUILDERS))}") from None
