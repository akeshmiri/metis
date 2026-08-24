"""
Test-case rendering (application spec §7).

A path becomes one human-executable test case with **exactly one validation**
(T-1a). Its structure is arrange-act-assert:

    Precondition  the setup path, rendered as arrangement       (no assertions)
    Step          the validated transition's trigger            (the Act)
    Expected      the validated transition's target state       (the Assert)

Two rules constrain everything here:

  * **T-2/T-3** every step maps to exactly one real transition, and the expected
    result to a real state. No narrative filler.
  * **T-6** rendered prose never introduces behaviour absent from the model.

Step wording resolves by the cascade in T-4. Tiers 1 (acceptance-criterion
wording) and 2 (generated prose) are implemented as far as available inputs
allow; tier 3 (verbatim) is always reachable. Which tier produced a step is
recorded, because a name's provenance determines how much weight it carries.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from metis_mcp.mbt.model import Model
from metis_mcp.mbt.path_generation import Path

TIER_ACCEPTANCE_CRITERION = "acceptance_criterion"
TIER_GENERATED_PROSE = "generated_prose"
TIER_VERBATIM = "verbatim"

_WORD_BOUNDARY = re.compile(r"[_\-.]+")


def humanise(identifier: str) -> str:
    """`submit_invalid_credentials` -> `Submit invalid credentials`.

    Deterministic and lossless in the sense that matters: it only re-spaces and
    capitalises. It does not paraphrase, so it cannot introduce behaviour (T-6).
    This is tier 2 of T-4's cascade, achieved without a model call -- the
    code-over-generation preference (spec TR-4) applies to prose too.
    """
    text = _WORD_BOUNDARY.sub(" ", identifier).strip()
    if not text:
        return identifier
    return text[0].upper() + text[1:]


# The two kinds of data requirement (spec T-8, §7.4).
GUARD = "guard"
INPUT = "input"


def input_condition(param: dict) -> str:
    """One parameter, as a CONDITION on the data (spec M-9, T-9c).

    `body.metricDto is a required RecordDto` states what the fixture must
    satisfy. It deliberately stops there: constructing a RecordDto is solving the
    condition, and solving conditions to concrete data is out of scope (§12).
    Anything that looks like a value here would be Métis inventing test data.
    """
    location = param.get("location", "?")
    name = param.get("name", "?")
    type_name = (param.get("type_name") or "").rsplit(".", 1)[-1]
    necessity = "required" if param.get("required", True) else "optional"
    line = f"{location}.{name} is {'a' if necessity == 'required' else 'an'} " \
           f"{necessity} {type_name}".replace("is a optional", "is an optional")
    constraints = [c for c in (param.get("constraints") or ()) if c]
    return f"{line} ({'; '.join(constraints)})" if constraints else line


@dataclass(frozen=True)
class DataRequirement:
    """One condition the test data must satisfy, and where it is needed.

    Grouped rather than repeated per step (T-9). `steps` uses 1-based setup step
    numbers, with 0 meaning the act step -- so a tester preparing a fixture sees
    one entry per distinct condition without losing where it bites.
    """

    condition: str
    steps: tuple[int, ...]
    # What kind of requirement this is. A guard says what must be *true of the
    # system*; an input says what the caller must *send*. Both are conditions on
    # the data and both belong here, but a tester preparing a fixture treats them
    # differently, and merging them into one undifferentiated list is how "you
    # must supply a body" reads as "the database must be in some state".
    kind: str = GUARD

    @property
    def where(self) -> str:
        if self.steps == (0,):
            return "the step under test"
        numbered = [s for s in self.steps if s]
        label = "setup step" if len(numbered) == 1 else "setup steps"
        parts = [f"{label} {', '.join(str(s) for s in numbered)}"] if numbered else []
        if 0 in self.steps:
            parts.append("the step under test")
        return " and ".join(parts)


@dataclass(frozen=True)
class Step:
    """One arrangement or act step. Always traceable to one transition."""

    transition_id: str
    description: str
    wording_tier: str
    guard_verbatim: str = ""
    expected_result: str = ""
    is_assertion: bool = False


@dataclass(frozen=True)
class TestCase:
    """One rendered case. Exactly one step carries `is_assertion` (T-1a)."""

    id: str
    name: str
    objective: str
    model_id: str
    criterion: str
    target_key: str
    precondition_steps: tuple[Step, ...]
    act_step: Step
    labels: tuple[str, ...] = ()
    data_requirements: tuple[DataRequirement, ...] = ()
    precondition_group: tuple[str, ...] = ()
    # Why the criterion chose this case ("the boundary", "no guard"). Carried
    # from `criteria.Path`, which has produced it all along.
    data_note: str = ""

    @property
    def assertion_count(self) -> int:
        """Must always be 1 (T-1a). Exposed so a test can assert it directly."""
        return sum(1 for s in (*self.precondition_steps, self.act_step) if s.is_assertion)


@dataclass
class RenderResult:
    cases: list[TestCase] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)  # (target key, reason)

    def by_target(self) -> dict[str, TestCase]:
        return {c.target_key: c for c in self.cases}


def _case_id(model_id: str, path: Path) -> str:
    """Content-derived from the path (T-10): model + setup + validated transition,
    **and the data requirement that distinguishes this case from its siblings.**

    The criterion stays metadata: the same walk under two criteria is one case,
    which is why the criterion name is deliberately not in the basis.

    `data_note` is different in kind. A technique that varies the DATA produces
    several cases over one walk -- pairwise on four optional inputs is six cases
    that traverse identical transitions and differ only in what they send. Keyed
    on the walk alone all six hashed to `tc-49a0d30271f2`: publishing them would
    write one and silently overwrite five, and `TestCase` merges on this id in
    the graph, so they would fuse there too. The same collision that fused
    `PageResponse` across seven modules, arriving through a different door.
    """
    basis = "|".join((model_id, *path.setup_transition_ids,
                      path.validated_transition_id, path.data_note or ""))
    return "tc-" + hashlib.sha256(basis.encode()).hexdigest()[:12]


def observable_result(transition, target_state) -> str:
    """What the tester checks — status and body, not the target's node name.

    `Expected result: MetricSaveRejected400` names a graph node. A tester checks
    a status code and a payload, and both are on the model (M-2/M-3): the
    business language built for the specification has to reach the artefact a QA
    engineer actually executes, or it only ever improved the document.
    """
    status = getattr(transition, "outcome_status", None)
    body = (getattr(transition, "response_body", "") or "").strip()
    name = getattr(target_state, "name", "") or ""
    if status is None:
        return name
    if body:
        return f"{status} with {body}"
    return f"{status} with no body"


def precondition_of(state) -> str:
    """What must be true to start, in the state's own words where it has them."""
    condition = (getattr(state, "condition", "") or "").strip()
    return condition or f"the system is in {getattr(state, 'name', '?')}"


def _describe(model: Model, transition_id: str,
              ac_wording: dict[str, str] | None) -> tuple[str, str]:
    """Resolve step wording by T-4's cascade. Returns (description, tier)."""
    transition = model.transitions[transition_id]
    if ac_wording and transition_id in ac_wording:
        return ac_wording[transition_id], TIER_ACCEPTANCE_CRITERION
    prose = humanise(transition.trigger)
    if prose and prose != transition.trigger:
        return prose, TIER_GENERATED_PROSE
    return transition.trigger, TIER_VERBATIM


def _group_requirements(model: Model, path: Path, act_guard: str) -> tuple[DataRequirement, ...]:
    """Collapse repeated conditions, retaining which steps need each.

    Order is first-appearance, so the list reads in the order a tester meets the
    conditions rather than in an arbitrary or alphabetical order.
    """
    order: list[tuple[str, str]] = []
    where: dict[tuple[str, str], list[int]] = {}

    def note(condition: str, kind: str, step: int) -> None:
        key = (condition, kind)
        if key not in where:
            order.append(key)
            where[key] = []
        where[key].append(step)

    def requirements_of(tid: str, step: int) -> None:
        transition = model.transitions[tid]
        if transition.guard:
            note(transition.guard, GUARD, step)
        # What the caller must SEND. Until the pack recovered parameters there
        # was nothing here at all, so a case for `POST /metric` printed no data
        # requirements whatsoever -- a test that could be read but not run.
        for param in transition.inputs or ():
            note(input_condition(param), INPUT, step)

    for index, tid in enumerate(path.setup_transition_ids, start=1):
        requirements_of(tid, index)
    requirements_of(path.validated_transition_id, 0)

    # `act_guard` is passed separately by the caller; it is already covered by
    # `requirements_of` above, so it is only used when the transition is absent.
    if act_guard and not any(k[0] == act_guard for k in order):
        note(act_guard, GUARD, 0)

    return tuple(DataRequirement(condition=c, steps=tuple(where[(c, k)]), kind=k)
                 for c, k in order)


def render_path(model: Model, path: Path,
                ac_wording: dict[str, str] | None = None,
                objectives: dict[str, str] | None = None) -> TestCase:
    validated = model.transitions[path.validated_transition_id]
    source_state = model.states[validated.source]
    target_state = model.states[validated.target]

    precondition_steps = []
    for tid in path.setup_transition_ids:
        description, tier = _describe(model, tid, ac_wording)
        setup_transition = model.transitions[tid]
        precondition_steps.append(Step(
            transition_id=tid,
            description=description,
            wording_tier=tier,
            guard_verbatim=setup_transition.guard,
            # Setup carries no assertions -- a failure here is *blocked*, not
            # failed (T-1a). Recording the resulting state is context, not a check.
            expected_result="",
            is_assertion=False,
        ))

    description, tier = _describe(model, validated.id, ac_wording)
    act_step = Step(
        transition_id=validated.id,
        description=description,
        wording_tier=tier,
        guard_verbatim=validated.guard,
        expected_result=observable_result(validated, target_state),
        is_assertion=True,
    )

    # Business language where the model carries it, the code's where it does not.
    # `guard_wording` is decoded from conventions the model already committed to,
    # or is a person's own words via a confirmed criterion.
    wording = (getattr(validated, "guard_wording", "") or "").strip()
    given = precondition_of(source_state)
    objective = (objectives or {}).get(
        validated.id,
        f"Verify that, given {given}, "
        f"{humanise(validated.trigger).lower()}"
        f"{f' when {wording}' if wording and wording != 'always' else ''} "
        f"returns {observable_result(validated, target_state)}.",
    )

    # T-8/T-9: guards are data *requirements*, aggregated so a tester can prepare
    # the fixture before executing rather than discovering them mid-run.
    #
    # Grouped by condition rather than listed per step. A five-step setup that
    # needs the same condition five times is one requirement to satisfy, not
    # five -- but which steps need it is retained, because dropping that would
    # lose real information about where a failure would surface.
    data_requirements = _group_requirements(model, path, validated.guard)

    return TestCase(
        id=_case_id(model.id, path),
        name=f"{source_state.name} → {target_state.name} on {validated.trigger}",
        objective=objective,
        model_id=model.id,
        criterion=path.criterion,
        target_key=path.target_key,
        precondition_steps=tuple(precondition_steps),
        act_step=act_step,
        labels=(model.id, path.criterion),
        data_requirements=data_requirements,
        data_note=path.data_note or "",
        precondition_group=path.precondition_group,
    )


def render(model: Model, paths: list[Path],
           ac_wording: dict[str, str] | None = None,
           objectives: dict[str, str] | None = None) -> RenderResult:
    """Render every path, failing loudly on anything untraceable (T-3, F-9)."""
    result = RenderResult()
    for path in paths:
        try:
            result.cases.append(render_path(model, path, ac_wording, objectives))
        except KeyError as e:
            result.failures.append((path.target_key, f"unresolvable model element {e}"))
    return result


def format_case(case: TestCase) -> str:
    """Human-readable form. The machine-readable companion is payload.py (T-9a)."""
    lines = [
        f"{case.id}  {case.name}",
        f"  Objective: {case.objective}",
        "",
        "  Precondition:",
    ]
    if case.precondition_steps:
        for n, step in enumerate(case.precondition_steps, 1):
            lines.append(f"    {n}. {step.description}")
            if step.guard_verbatim:
                lines.append(f"       requires: {step.guard_verbatim}")
    else:
        lines.append("    (none — starts from the initial state)")
    lines += [
        "",
        "  Step:",
        f"    {case.act_step.description}",
    ]
    if case.act_step.guard_verbatim:
        lines.append(f"      requires: {case.act_step.guard_verbatim}")
    lines += [
        "",
        f"  Expected result: {case.act_step.expected_result}",
    ]
    # Split by kind (T-9): "what you must send" and "what must already be true"
    # are prepared differently, and one undifferentiated list hides that.
    inputs = [r for r in case.data_requirements if r.kind == INPUT]
    guards = [r for r in case.data_requirements if r.kind != INPUT]
    if inputs:
        lines += ["", "  Request data required:"]
        for requirement in inputs:
            lines.append(f"    - {requirement.condition}  ({requirement.where})")
    if guards:
        lines += ["", "  Test data requirements:"]
        for requirement in guards:
            lines.append(f"    - {requirement.condition}  ({requirement.where})")
    if case.data_note:
        # Produced by `criteria.py` for every generated path and, until now, read
        # by nothing: the criterion that chose this case could say *why* it exists
        # ("the boundary", "no guard") and the tester never saw it.
        lines += ["", f"  Why this case: {case.data_note}"]
    return "\n".join(lines)
