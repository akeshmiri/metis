"""
Path generation (application spec §6.3).

The rule that shapes everything here is spec P-5: **a path has exactly one
validated transition.** Everything before it is setup, and setup is *not*
credited as coverage (P-5a). This is the opposite of a chaining strategy -- it
produces more tests with repeated setup, deliberately, because a chained test
cannot say which transition broke and a failure at step three invalidates
everything after it.

Consequences that follow directly:
  * The optimisation objective is the **shortest setup**, not the fewest paths
    (P-6a). There is no set-cover step.
  * Generation is one path per coverage target -- no greedy extension.
  * Determinism is structural: every iteration is over a sorted sequence, and
    BFS explores neighbours in id order (P-7).

Loops (P-9): a shortest setup is by construction simple -- BFS never revisits a
state -- so the "at most one revisit" rule is satisfied without special handling.
Self-loops are reachable as validated transitions because setup targets their
source state, not the edge itself.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from metis_mcp.mbt.criteria import CoverageTarget, DEFAULT_CRITERION, targets_for
from metis_mcp.mbt.model import Model

# Spec P-8a. The login model's longest required setup is 6 (measured); 10 is that
# with headroom, and stays within what a person executes reliably by hand.
DEFAULT_SETUP_CAP = 10

UNREACHABLE = "unreachable"
EXCEEDS_SETUP_CAP = "exceeds_setup_cap"
UNSATISFIABLE = "unsatisfiable"


@dataclass(frozen=True)
class Path:
    """One test's worth of model: setup, then a single validated transition."""

    validated_transition_id: str
    setup_transition_ids: tuple[str, ...]
    criterion: str
    target_key: str
    data_note: str | None = None

    @property
    def precondition_group(self) -> tuple[str, ...]:
        """Paths sharing this key share a precondition (spec P-14a).

        This is what makes "open the login page" one shared precondition across
        every test starting there, rather than repeated prose in each case.
        """
        return self.setup_transition_ids

    @property
    def setup_length(self) -> int:
        return len(self.setup_transition_ids)


@dataclass(frozen=True)
class Uncoverable:
    target_key: str
    validated_transition_id: str
    reason: str
    detail: str = ""


@dataclass
class GenerationResult:
    model_id: str
    criterion: str
    setup_cap: int
    paths: list[Path] = field(default_factory=list)
    uncoverable: list[Uncoverable] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)  # (transition id, reason)

    @property
    def covered_transition_ids(self) -> set[str]:
        """Only validated transitions count. Setup is arrangement (spec P-5a)."""
        return {p.validated_transition_id for p in self.paths}

    def precondition_groups(self) -> dict[tuple[str, ...], list[Path]]:
        groups: dict[tuple[str, ...], list[Path]] = {}
        for p in self.paths:
            groups.setdefault(p.precondition_group, []).append(p)
        return groups


def _shortest_setup(model: Model, goal_state: str,
                    via_transition_id: str | None = None) -> tuple[str, ...] | None:
    """BFS from any initial state to `goal_state`, returning transition ids.

    Neighbours are explored in id order so the result is byte-identical across
    runs (spec P-7). Returns an empty tuple when the goal is itself an initial
    state, and None when unreachable.

    `via_transition_id` constrains the final setup step, which is how
    transition-pair coverage varies the arrival route (criteria.py's
    `via_transition_id`).
    """
    initial = model.initial_state_ids()
    if not initial:
        return None

    if via_transition_id is not None:
        via = model.transitions.get(via_transition_id)
        if via is None or not via.is_generatable or via.target != goal_state:
            return None
        prefix = _shortest_setup(model, via.source)
        if prefix is None:
            return None
        return prefix + (via.id,)

    if goal_state in initial:
        return ()

    # (state, path-so-far). `seen` on states, not paths: a shortest path never
    # needs to revisit a state, which is also why P-9's loop rule needs no
    # special handling here.
    queue: deque[tuple[str, tuple[str, ...]]] = deque(
        (sid, ()) for sid in initial
    )
    seen = set(initial)
    while queue:
        state_id, so_far = queue.popleft()
        for t in model.outgoing(state_id):  # already id-ordered
            if t.target in seen:
                continue
            path = so_far + (t.id,)
            if t.target == goal_state:
                return path
            seen.add(t.target)
            queue.append((t.target, path))
    return None


def generate(model: Model, criterion: str = DEFAULT_CRITERION,
             setup_cap: int = DEFAULT_SETUP_CAP,
             grades: dict | None = None) -> GenerationResult:
    """Generate one path per coverage target (spec P-6).

    Never silently drops a target: anything not covered appears in `uncoverable`
    with a reason, and excluded transitions are reported separately by reason
    (spec P-11, P-12). Lowering the denominator quietly would inflate the
    coverage figure, which is the failure P-12 exists to prevent.
    """
    result = GenerationResult(model_id=model.id, criterion=criterion, setup_cap=setup_cap)

    for t in model.excluded_transitions():
        result.excluded.append((t.id, t.exclusion_reason or "excluded"))

    criterion_result = targets_for(model, criterion, grades)
    for key, reason in criterion_result.unsatisfiable:
        result.uncoverable.append(Uncoverable(
            target_key=key, validated_transition_id="", reason=UNSATISFIABLE, detail=reason,
        ))

    for target in criterion_result.targets:
        _generate_one(model, target, criterion, setup_cap, result)

    return result


def _generate_one(model: Model, target: CoverageTarget, criterion: str,
                  setup_cap: int, result: GenerationResult) -> None:
    validated = model.transitions.get(target.validated_transition_id)
    if validated is None or not validated.is_generatable:
        result.uncoverable.append(Uncoverable(
            target_key=target.key,
            validated_transition_id=target.validated_transition_id,
            reason=UNREACHABLE,
            detail="validated transition is absent or excluded",
        ))
        return

    setup = _shortest_setup(model, validated.source, target.via_transition_id)
    if setup is None:
        result.uncoverable.append(Uncoverable(
            target_key=target.key,
            validated_transition_id=validated.id,
            reason=UNREACHABLE,
            detail=f"no route from an initial state to {validated.source!r}",
        ))
        return

    if len(setup) > setup_cap:
        # Spec P-8a: report the required length, so raising the cap is an
        # informed decision rather than a guess.
        result.uncoverable.append(Uncoverable(
            target_key=target.key,
            validated_transition_id=validated.id,
            reason=EXCEEDS_SETUP_CAP,
            detail=f"requires {len(setup)} setup steps, cap is {setup_cap}",
        ))
        return

    result.paths.append(Path(
        validated_transition_id=validated.id,
        setup_transition_ids=setup,
        criterion=criterion,
        target_key=target.key,
        data_note=target.data_note,
    ))
