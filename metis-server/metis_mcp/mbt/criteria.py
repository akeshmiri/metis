"""
Coverage criteria (application spec §6.1, §6.2).

A criterion is a function from a model to a set of **coverage targets** -- the
things that must be validated. It never decides how many assertions a test makes:
spec P-1a requires every criterion to preserve one validation per test, so deeper
criteria produce *more targets*, never richer ones.

Each target names exactly one `validated_transition_id`. That is what makes
P-5 ("one validation per test") a property of the type system here rather than a
convention someone has to remember.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from metis_mcp.mbt.model import Model, Transition

ALL_STATES = "all-states"
ALL_TRANSITIONS = "all-transitions"
ALL_TRANSITION_PAIRS = "all-transition-pairs"
GUARD_COVERAGE = "guard-coverage"

# ISO/IEC/IEEE 29119-4 boundary value analysis + equivalence partitioning.
# Opt-in like guard coverage (P-2a): it multiplies cases on every journey, and
# most journeys do not need that depth.
BOUNDARY_COVERAGE = "boundary-coverage"
# Step 5's two techniques (ISO/IEC/IEEE 29119-4). The five above select PATHS
# through a machine; these select *what to vary* — the prior question, and the
# one nothing here asked. See `mbt/design.py`.
DECISION_TABLE = "decision-table"
PAIRWISE = "pairwise"

# The default. Spec P-2: the criterion whose coverage number is meaningful
# without qualification and whose cost is predictable.
DEFAULT_CRITERION = ALL_TRANSITIONS


@dataclass(frozen=True)
class CoverageTarget:
    """One thing that must be validated by exactly one test.

    `validated_transition_id` is the single assertion (spec P-5).
    `via_transition_id`, where set, constrains how setup must arrive -- this is
    how transition-pair coverage varies the *route* without adding a second
    assertion.
    `data_note` carries a guard-coverage condition as a data requirement; it is
    never a solved value (spec M-9).
    """

    kind: str
    key: str
    validated_transition_id: str
    via_transition_id: str | None = None
    data_note: str | None = None


@dataclass
class CriterionResult:
    name: str
    targets: list[CoverageTarget] = field(default_factory=list)
    unsatisfiable: list[tuple[str, str]] = field(default_factory=list)  # (key, reason)


# ---------------------------------------------------------------------------
# all-states
# ---------------------------------------------------------------------------

def _all_states(model: Model) -> CriterionResult:
    """One target per non-initial state: validate arrival at it.

    Initial states need no test -- a tester establishes them as a precondition,
    they are not something the system transitions into. Including them would
    claim coverage for behaviour that was never exercised.
    """
    result = CriterionResult(name=ALL_STATES)
    initial = set(model.initial_state_ids())
    for sid in model.state_ids():
        if sid in initial:
            continue
        arrivals = model.incoming(sid)
        if not arrivals:
            result.unsatisfiable.append((sid, "no generatable transition arrives at this state"))
            continue
        # Deterministic choice: the lowest-id arriving transition (spec P-7).
        result.targets.append(CoverageTarget(
            kind="state", key=sid, validated_transition_id=arrivals[0].id,
        ))
    return result


# ---------------------------------------------------------------------------
# all-transitions  (the default)
# ---------------------------------------------------------------------------

def _all_transitions(model: Model) -> CriterionResult:
    result = CriterionResult(name=ALL_TRANSITIONS)
    for t in model.generatable_transitions():
        result.targets.append(CoverageTarget(
            kind="transition", key=t.id, validated_transition_id=t.id,
        ))
    return result


# ---------------------------------------------------------------------------
# all-transition-pairs
# ---------------------------------------------------------------------------

def _all_transition_pairs(model: Model) -> CriterionResult:
    """One target per consecutive pair (t1 -> t2), validating t2 only.

    Spec P-1a: the pair criterion tests the *same* transition once per arrival
    path. It does not assert two things -- it asserts one thing, having arrived a
    particular way. `via_transition_id` carries that constraint into generation.
    """
    result = CriterionResult(name=ALL_TRANSITION_PAIRS)
    for t1 in model.generatable_transitions():
        followers = model.outgoing(t1.target)
        if not followers:
            # **A dropped target says why, like every other criterion here.**
            # This used to `continue`, and it was the only place in this module
            # that discarded a target without a reason. On a model whose states
            # are all terminal -- every recovered API model, where an outcome
            # state is the end of the call -- that produced NO targets and NO
            # unsatisfiable rows, and the report read `covered: 0, uncovered: 0`.
            # Full coverage of nothing and total absence of coverage render
            # identically, which is the silent success this project hunts for.
            result.unsatisfiable.append((
                t1.id,
                f"terminal: no generatable transition leaves {t1.target} — "
                f"there is no pair to cover"))
            continue
        for t2 in followers:
            result.targets.append(CoverageTarget(
                kind="transition-pair",
                key=f"{t1.id}->{t2.id}",
                validated_transition_id=t2.id,
                via_transition_id=t1.id,
            ))
    return result


# ---------------------------------------------------------------------------
# guard coverage
# ---------------------------------------------------------------------------

# Split on AND/&& only. OR is deliberately not decomposed: a disjunction's
# branches are not independently controllable from a single transition, and
# treating them as such would claim combinations that no test actually varies.
_CONJUNCT_RE = re.compile(r"\s+AND\s+|\s*&&\s*", re.IGNORECASE)


def atomic_conditions(guard: str) -> list[str]:
    """Split a guard into its top-level conjuncts, verbatim.

    Deliberately minimal (spec M-6 normalisation discipline): it does not
    simplify, reorder or interpret. A guard it cannot split is returned whole,
    which is the fail-safe direction -- one condition treated as atomic is a
    weaker claim than a wrong decomposition.
    """
    if not guard or not guard.strip():
        return []
    return [c.strip() for c in _CONJUNCT_RE.split(guard.strip()) if c.strip()]


def guard_conditions(t) -> list[tuple[str, str]]:
    """The conditions a transition's guard makes, and what else each requires.

    `(condition, note_suffix)` pairs, preferring the `Check` nodes reached by
    `DERIVED_FROM -> DeclaredOutcome -> GUARDED_BY` over splitting the guard
    string.

    **Why the checks win.** Both describe the same branch, but only one of them
    can be ordered. Checks evaluate in sequence and short-circuit, so a fixture
    aimed at the third condition never reaches it unless the first two already
    hold — that is a data requirement, and splitting `a AND b AND c` on `AND`
    cannot recover it. The checks also carry `file:line@commit`, so a target
    says which line it came from instead of asking a reviewer to go and find it.

    Falls back to `atomic_conditions` where no check was landed, which is most
    of the estate today: `GUARDED_BY` is written only where dimension recovery
    resolved the guarding checks, and a service whose outcomes carry none still
    gets exactly the coverage it got before.
    """
    if not t.checks:
        return [(c, "") for c in atomic_conditions(t.guard)]

    out: list[tuple[str, str]] = []
    for i, check in enumerate(t.checks):
        earlier = [c.expression for c in t.checks[:i]]
        suffix = ""
        if earlier:
            # M-9: a condition on the data, never a value for it.
            suffix = (f" — reachable only once {' and '.join(earlier)} "
                      f"already hold, which is the order they are evaluated in")
        if check.anchor:
            suffix += f" [{check.anchor}]"
        out.append((check.expression, suffix))
    return out


def _guard_coverage(model: Model) -> CriterionResult:
    """One target per (transition, atomic condition, polarity).

    The false-polarity target is only satisfiable where some *other* transition
    from the same source and trigger actually exercises it. Where nothing does,
    it is reported unsatisfiable rather than silently dropped (spec P-3) -- a
    criterion that quietly reduces its own requirements reports success it did
    not achieve.
    """
    result = CriterionResult(name=GUARD_COVERAGE)
    for t in model.generatable_transitions():
        conditions = guard_conditions(t)
        if not conditions:
            # An unguarded transition has nothing to vary; it is covered by
            # all-transitions and contributes no guard target. Not a gap.
            result.targets.append(CoverageTarget(
                kind="guard", key=f"{t.id}::<unguarded>",
                validated_transition_id=t.id, data_note="no guard",
            ))
            continue
        siblings = [s for s in model.outgoing(t.source)
                    if s.trigger == t.trigger and s.id != t.id]
        for cond, note in conditions:
            result.targets.append(CoverageTarget(
                kind="guard", key=f"{t.id}::{cond}::true",
                validated_transition_id=t.id,
                data_note=f"{cond} must hold{note}",
            ))
            if siblings:
                # Some sibling on the same (state, trigger) represents the
                # complementary case; validating it is how "false" is exercised.
                result.targets.append(CoverageTarget(
                    kind="guard", key=f"{t.id}::{cond}::false",
                    validated_transition_id=siblings[0].id,
                    data_note=f"{cond} must not hold{note}",
                ))
            else:
                result.unsatisfiable.append((
                    f"{t.id}::{cond}::false",
                    "no alternative transition on this (state, trigger) exercises "
                    "the complementary case",
                ))
    return result


def _boundary_coverage(model: Model) -> CriterionResult:
    """One target per boundary value, plus one per equivalence partition
    (ISO/IEC/IEEE 29119-4).

    Sits ALONGSIDE guard coverage rather than replacing it. Guard coverage asks
    "is each condition exercised both ways?"; this asks "are the values either
    side of the threshold exercised?" -- the question that finds an off-by-one,
    which no true/false pair ever will.

    **P-1a holds: this adds more TESTS, never more assertions per test.** Each
    boundary is its own target and therefore its own single-assertion path.

    **M-9 holds: `data_note` carries a CONDITION, never a value.** `attempts = 4`
    is a requirement the fixture must satisfy; solving it remains out of scope.

    A guard with no recoverable boundary contributes its partitions and is
    reported in `unsatisfiable` for the boundary it does not have (M-17) -- never
    silently skipped, which would let a criterion quietly shrink its own
    requirements (P-3).
    """
    from metis_mcp.mbt.techniques import analyse_constraints, analyse_guard

    result = CriterionResult(name=BOUNDARY_COVERAGE)
    for t in model.generatable_transitions():
        analysis = analyse_guard(t.guard)
        if not t.guard.strip():
            result.targets.append(CoverageTarget(
                kind="boundary", key=f"{t.id}::<unguarded>",
                validated_transition_id=t.id, data_note="no guard"))
            continue

        for boundary in analysis.boundaries:
            result.targets.append(CoverageTarget(
                kind="boundary", key=f"{t.id}::{boundary.condition}",
                validated_transition_id=t.id,
                data_note=f"{boundary.condition} ({boundary.position} the boundary)"))

        for partition in analysis.partitions:
            result.targets.append(CoverageTarget(
                kind="partition", key=f"{t.id}::partition::{partition.condition}",
                validated_transition_id=t.id,
                data_note=f"{partition.condition} (equivalence partition)"))

        # **GD-3's variants.** The declared constraints an input must violate to
        # reach a rejection — `@Size(max=64)` on a payload field. These are why
        # 164 constrained fields stay TEST DATA rather than becoming 164
        # transitions: the technique turns each into cases without adding a model
        # element (P-1a). The model carried them and `techniques` read only the
        # guard, so the constraints were landed, loaded, and consumed by nothing.
        #
        # A constraint arrives as bare annotation text, so it names no field —
        # `length = 65` is stated and which field's length is not. That is a
        # recovery limit, not something to guess at (M-9); `inputs` carries the
        # field names beside it.
        declared = analyse_constraints(getattr(t, "data_requirements", ()) or ())
        for boundary in declared.boundaries:
            result.targets.append(CoverageTarget(
                kind="boundary", key=f"{t.id}::constraint::{boundary.condition}",
                validated_transition_id=t.id,
                data_note=f"{boundary.condition} ({boundary.position} the boundary "
                          f"of {boundary.source_guard})"))
        for partition in declared.partitions:
            result.targets.append(CoverageTarget(
                kind="partition", key=f"{t.id}::constraint::{partition.condition}",
                validated_transition_id=t.id,
                data_note=f"{partition.condition} (declared constraint "
                          f"{partition.source_guard})"))

        for atom, why in analysis.unanalysable:
            result.unsatisfiable.append((f"{t.id}::{atom}::boundary", why))
    return result


def _decision_table(model: Model) -> CriterionResult:
    """One target per REACHABLE row of each `(state, trigger)` decision table.

    Guard coverage varies each condition true and false independently, which for
    three conditions is six cases and says nothing about their **combinations**.
    A decision table asks what each combination produces, and that is where a
    missing rule hides: `POST /environment` has three conditions, eight rows,
    and two combinations no transition covers.

    An uncovered row is `unsatisfiable`, never a target. It is not necessarily a
    defect — the conditions may be unable to hold together, which is not
    decidable from the text — so it is reported for a human rather than turned
    into a test that can never pass.
    """
    from metis_mcp.mbt.design import decision_table

    result = CriterionResult(name=DECISION_TABLE)
    generatable = {t.id for t in model.generatable_transitions()}
    groups = sorted({(t.source, t.trigger) for t in model.transitions.values()})

    for state, trigger in groups:
        table = decision_table(model, state, trigger)
        if not table.is_available:
            result.unsatisfiable.append(
                (f"{state}|{trigger}", table.reason_unavailable))
            continue
        for row, rule in enumerate(table.rules):
            key = f"{state}|{trigger}|row{row}"
            if not rule.is_covered:
                result.unsatisfiable.append((key, rule.unreachable_note))
                continue
            if rule.transition_id not in generatable:
                continue
            result.targets.append(CoverageTarget(
                kind=DECISION_TABLE, key=key,
                validated_transition_id=rule.transition_id,
                # M-9: the row is a CONDITION on the data, never a value.
                data_note=rule.describe()))
    return result


def _pairwise(model: Model) -> CriterionResult:
    """One target per pairwise case over a transition's varying inputs.

    Most defects involving several inputs are triggered by a *pair*, so covering
    every pair finds them at a fraction of the product: `GET /environment/all`
    has seven varying inputs — 128 exhaustive, **7 pairwise**.

    A transition whose inputs cannot be varied without inventing data yields
    nothing and says so (M-9). P-1a holds: each case is its own single-assertion
    path, so this adds tests and never assertions.
    """
    from metis_mcp.mbt.design import all_pairs, factors_for

    result = CriterionResult(name=PAIRWISE)
    for t in model.generatable_transitions():
        factors = factors_for(t)
        if not factors:
            result.unsatisfiable.append(
                (t.id, "no input varies in a way that can be stated without "
                       "inventing a value (M-9)"))
            continue
        for i, case in enumerate(all_pairs(factors)):
            result.targets.append(CoverageTarget(
                kind=PAIRWISE, key=f"{t.id}|pair{i}",
                validated_transition_id=t.id,
                data_note=", ".join(f"{k} {v}" for k, v in sorted(case.items()))))
    return result


_CRITERIA = {
    ALL_STATES: _all_states,
    ALL_TRANSITIONS: _all_transitions,
    ALL_TRANSITION_PAIRS: _all_transition_pairs,
    GUARD_COVERAGE: _guard_coverage,
    BOUNDARY_COVERAGE: _boundary_coverage,
    DECISION_TABLE: _decision_table,
    PAIRWISE: _pairwise,
}


def criterion_names() -> list[str]:
    return sorted(_CRITERIA)


ALREADY_COVERED = "already_covered_by"


def targets_for(model: Model, criterion: str = DEFAULT_CRITERION,
                grades: dict | None = None) -> CriterionResult:
    """Coverage targets, minus anything an existing test already covers.

    `grades` comes from `test_levels.grade_transitions`. Spec REQ-METIS-PG-01:
    generation never fires for a layer already covered -- on the pilot estate 84
    of 145 transitions are covered by integration tests that already pass, and
    generating for them produces review burden and a flattering coverage figure
    in exchange for nothing.

    A dropped target moves to `unsatisfiable` **with the test that covers it
    named**, never disappearing: P-12 forbids quietly lowering the denominator,
    and "already tested" is a different fact from "not covered" that a reader
    must be able to tell apart.

    This is deliberately NOT `Transition.exclusion_reason`. That property is
    derived from lifecycle and implementation status -- facts about the
    transition itself. Existing coverage is external knowledge that varies with
    which inventory you point at, so it belongs to the criterion run, not to the
    element.
    """
    if criterion not in _CRITERIA:
        raise ValueError(
            f"unknown criterion {criterion!r}; known: {', '.join(criterion_names())}"
        )
    result = _CRITERIA[criterion](model)
    if not grades:
        return result

    kept = []
    for target in result.targets:
        grade = grades.get(target.validated_transition_id)
        if grade is not None and not grade.should_generate:
            evidence = ", ".join(grade.evidence) or grade.detail
            result.unsatisfiable.append((target.key, f"{ALREADY_COVERED}: {evidence}"))
            continue
        kept.append(target)
    result.targets = kept
    return result
