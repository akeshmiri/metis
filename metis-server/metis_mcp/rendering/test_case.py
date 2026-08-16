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


@dataclass(frozen=True)
class DataRequirement:
    """One condition the test data must satisfy, and where it is needed.

    Grouped rather than repeated per step (T-9). `steps` uses 1-based setup step
    numbers, with 0 meaning the act step -- so a tester preparing a fixture sees
    one entry per distinct condition without losing where it bites.
    """

    condition: str
    steps: tuple[int, ...]

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
    """Content-derived from the path (T-10): model + setup + validated transition.

    The criterion is metadata, not identity -- the same walk generated under two
    criteria is one path and one case.
    """
    basis = "|".join((model_id, *path.setup_transition_ids, path.validated_transition_id))
    return "tc-" + hashlib.sha256(basis.encode()).hexdigest()[:12]


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
    order: list[str] = []
    where: dict[str, list[int]] = {}
    for index, tid in enumerate(path.setup_transition_ids, start=1):
        guard = model.transitions[tid].guard
        if not guard:
            continue
        if guard not in where:
            order.append(guard)
            where[guard] = []
        where[guard].append(index)
    if act_guard:
        if act_guard not in where:
            order.append(act_guard)
            where[act_guard] = []
        where[act_guard].append(0)
    return tuple(DataRequirement(condition=g, steps=tuple(where[g])) for g in order)


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
        expected_result=f"{target_state.name}",
        is_assertion=True,
    )

    objective = (objectives or {}).get(
        validated.id,
        f"Verify that {humanise(validated.trigger).lower()} from "
        f"{source_state.name} results in {target_state.name}.",
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
    if case.data_requirements:
        lines.append("")
        lines.append("  Test data requirements:")
        for requirement in case.data_requirements:
            lines.append(f"    - {requirement.condition}  ({requirement.where})")
    return "\n".join(lines)
