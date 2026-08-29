"""
Equivalence partitioning and boundary value analysis (ISO/IEC/IEEE 29119-4).

`criteria._guard_coverage` varies each atomic condition true and false. For
`attempts >= 5` that is two cases, and neither of them is the case a tester
actually wants: the interesting values are 4, 5 and 6.

**The hard constraint is M-9: a guard is a test DATA REQUIREMENT, never a solved
value.** Métis must not invent a username, a password or a payload. It may state
that a test needs `attempts = 4`, because that is a *condition on the data*, not
the data. Everything this module emits is a condition; nothing here constructs a
fixture, and `test_techniques.py` asserts that no output ever names a value
outside the guard's own vocabulary.

**Deterministic, and reusing what already exists.** `behavior_model._parse_guard`
already extracts `(variable, operator, number)` -- it is the parser behind the
determinism check. Boundary analysis is the same parse read for a different
purpose, so the two cannot disagree about what a guard says.

**Fail-closed on anything it cannot parse (M-17).** `t.isEmpty()` has no
boundary. It yields a two-way equivalence partition -- the condition holds, or it
does not -- and **no boundary claim at all**. Inventing one would be inventing
data, which is exactly what M-9 forbids. On the pilot estate this is the dominant
case, so the honest yield of BVA there is small; it is worth having anyway
because the guards that *are* numeric are the ones where off-by-one lives.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from metis_mcp.behavior_model import _literal, _parse_guard, _strip_parens
from metis_mcp.mbt.model import IMPLEMENTED, Model

# How a partition was derived, so a reader can weigh it (the X-8 discipline
# applied to test data).
FROM_THRESHOLD = "numeric_threshold"
FROM_PREDICATE = "boolean_predicate"

# Boundary positions, in ISTQB's three-point form.
BELOW = "below"
AT = "at"
ABOVE = "above"


def _atoms(guard: str) -> list[str]:
    """Split a conjunction into its atomic conditions. No interpretation."""
    if not guard or not guard.strip():
        return []
    parts = re.split(r"\s+AND\s+", guard.strip(), flags=re.IGNORECASE)
    # `_strip_parens` removes only BALANCED wrapping parens. A naive
    # `.strip("()")` also eats call syntax, turning `t.isEmpty()` into
    # `t.isEmpty` -- a condition a tester cannot act on and that no longer
    # matches the guard it came from.
    return [_strip_parens(p) for p in parts if p.strip()]


@dataclass(frozen=True)
class Partition:
    """One equivalence class of a variable's domain.

    `condition` is what the data must satisfy -- the thing a tester reads. It is
    never a value.
    """

    variable: str
    condition: str
    derived_from: str
    source_guard: str

    def describe(self) -> str:
        return f"{self.condition}  [{self.derived_from}, from {self.source_guard!r}]"


@dataclass(frozen=True)
class Boundary:
    """One boundary point, as a CONDITION on the data (spec M-9).

    `condition` reads `attempts = 4`. That is a requirement the fixture must
    satisfy, not a fixture. Métis states it; a person or a factory provides it.
    """

    variable: str
    position: str
    value: float
    condition: str
    source_guard: str

    @property
    def is_edge(self) -> bool:
        return self.position in (BELOW, ABOVE)

    def describe(self) -> str:
        return f"{self.condition}  [{self.position} the boundary of {self.source_guard!r}]"


@dataclass
class TechniqueResult:
    partitions: list[Partition] = field(default_factory=list)
    boundaries: list[Boundary] = field(default_factory=list)
    unanalysable: list[tuple[str, str]] = field(default_factory=list)

    @property
    def variables(self) -> set[str]:
        return {p.variable for p in self.partitions}


def _number(value: float) -> str:
    """`5.0` -> `5`; `0.5` stays `0.5`. Presentation only."""
    return str(int(value)) if float(value).is_integer() else str(value)


def analyse_guard(guard: str) -> TechniqueResult:
    """Partitions and boundaries for one guard expression."""
    result = TechniqueResult()
    for atom in _atoms(guard):
        parsed = _parse_guard(atom)
        if parsed is None:
            # A predicate is a two-way partition and nothing more. `t.isEmpty()`
            # has no boundary; claiming one would be inventing data (M-9), and
            # M-17 says an unparseable expression is reported, never assumed.
            #
            # Polarity is normalised through `_literal`, the same helper the
            # complementarity check uses, so `NOT account_locked` partitions into
            # `account_locked` / `NOT (account_locked)` rather than the unreadable
            # `NOT (NOT account_locked)`. Double negation is propositional
            # structure, not interpretation -- no meaning is being assigned.
            base, _negated = _literal(atom)
            result.partitions.append(Partition(
                variable=base, condition=base, derived_from=FROM_PREDICATE,
                source_guard=guard))
            result.partitions.append(Partition(
                variable=base, condition=f"NOT ({base})",
                derived_from=FROM_PREDICATE, source_guard=guard))
            result.unanalysable.append(
                (atom, "not a numeric threshold — partitioned two ways, no boundary"))
            continue

        variable, operator, number = parsed
        n = _number(number)

        # Equivalence partitioning: the domain either side of the threshold,
        # plus the threshold itself where the operator distinguishes it.
        if operator in (">=", ">"):
            result.partitions.append(Partition(
                variable, f"{variable} < {n}", FROM_THRESHOLD, guard))
            result.partitions.append(Partition(
                variable, f"{variable} {operator} {n}", FROM_THRESHOLD, guard))
        elif operator in ("<=", "<"):
            result.partitions.append(Partition(
                variable, f"{variable} {operator} {n}", FROM_THRESHOLD, guard))
            result.partitions.append(Partition(
                variable, f"{variable} {'>=' if operator == '<' else '>'} {n}",
                FROM_THRESHOLD, guard))
        else:  # ==
            result.partitions.append(Partition(
                variable, f"{variable} == {n}", FROM_THRESHOLD, guard))
            result.partitions.append(Partition(
                variable, f"{variable} != {n}", FROM_THRESHOLD, guard))

        # Boundary value analysis: the standard three-point set. Emitted as
        # conditions, so `attempts = 4` is a requirement on the data, never a
        # fixture (M-9).
        for position, offset in ((BELOW, -1), (AT, 0), (ABOVE, 1)):
            value = number + offset
            result.boundaries.append(Boundary(
                variable=variable, position=position, value=value,
                condition=f"{variable} = {_number(value)}", source_guard=guard))
    return result


def analyse_transition(model: Model, transition_id: str) -> TechniqueResult:
    """Partitions and boundaries for one transition's guard."""
    transition = model.transitions.get(transition_id)
    if transition is None or transition.implementation_status != IMPLEMENTED:
        return TechniqueResult()
    return analyse_guard(transition.guard)


def analyse_group(model: Model, state: str, trigger: str) -> TechniqueResult:
    """Analyse a whole `(state, trigger)` group together.

    A group is the right unit: `attempts < 5` and `attempts >= 5` are two guards
    describing **one** partitioning of `attempts`, and analysing them separately
    would report the same boundary twice and the same partition twice.
    """
    merged = TechniqueResult()
    seen_partitions: set[tuple[str, str]] = set()
    seen_boundaries: set[tuple[str, float]] = set()

    for tid in model.transition_ids():
        t = model.transitions[tid]
        if t.source != state or t.trigger != trigger:
            continue
        if t.implementation_status != IMPLEMENTED:
            continue
        one = analyse_guard(t.guard)
        for p in one.partitions:
            key = (p.variable, p.condition)
            if key not in seen_partitions:
                seen_partitions.add(key)
                merged.partitions.append(p)
        for b in one.boundaries:
            key = (b.variable, b.value)
            if key not in seen_boundaries:
                seen_boundaries.add(key)
                merged.boundaries.append(b)
        merged.unanalysable.extend(one.unanalysable)
    return merged


def format_techniques(result: TechniqueResult) -> str:
    lines = [f"Equivalence partitions ({len(result.partitions)}) and "
             f"boundaries ({len(result.boundaries)})", ""]
    for p in result.partitions:
        lines.append(f"  partition  {p.describe()}")
    for b in result.boundaries:
        lines.append(f"  boundary   {b.describe()}")
    if result.unanalysable:
        lines += ["", "  NO BOUNDARY DERIVED (M-17 fail-closed):"]
        for atom, why in result.unanalysable:
            lines.append(f"    {atom}: {why}")
    lines += ["",
              "  Every line above is a CONDITION the test data must satisfy, never",
              "  a value Métis invented. Solving these to a fixture is out of scope",
              "  (M-9, §12)."]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Declared constraints (GD-3)
# --------------------------------------------------------------------------
#
# `analyse_guard` reads a guard the code EVALUATES. These read a constraint the
# code DECLARES -- `@Size(max=64)` on a payload field -- and they are the reason
# 164 constrained fields stay test data rather than becoming 164 transitions: a
# technique turns each into cases (P-1a) without adding a model element.
#
# **What is honestly missing, said once here rather than implied.** A constraint
# arrives as bare annotation text (`code_analysis/synthesis.py:582` carries
# `rejection.constraints`), so the FIELD it constrains is not in it. This states
# `length = 65` and cannot state which field's length; `Transition.inputs` names
# the fields separately and a tester reads both. Inventing the pairing would be
# inventing data (M-9), so it is not attempted.

FROM_CONSTRAINT = "declared_constraint"

# The subject each annotation constrains. Naming it is what lets the emitted
# condition read `length = 65` rather than an unattributed number.
_SIZE_LIKE = {"Size": "length", "Length": "length"}
_VALUE_LIKE = {"Min": "value", "Max": "value", "DecimalMin": "value",
               "DecimalMax": "value", "Digits": "digits"}
# Presence assertions: a two-way partition and no boundary. `@NotNull` has no
# third point -- "one less than null" is not a value, and claiming a boundary
# here would be the invention M-9 forbids.
_PRESENCE = ("NotNull", "NotBlank", "NotEmpty", "Null")
# Shape assertions: satisfied or not, with no orderable domain to bound.
_SHAPE = ("Pattern", "Email", "URL", "Past", "Future", "PastOrPresent",
          "FutureOrPresent", "Positive", "Negative", "PositiveOrZero",
          "NegativeOrZero", "AssertTrue", "AssertFalse", "Valid")

_ANNOTATION = re.compile(r"@(\w+)\s*(?:\((.*)\))?\s*$", re.DOTALL)
_BOUND = re.compile(r"\b(min|max|value)\s*=\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
_BARE_NUMBER = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*$")


def _bounds_in(arguments: str) -> list[tuple[str, float]]:
    """`(min=3, max=40)` -> `[("min", 3.0), ("max", 40.0)]`; `(64)` -> `[("value", 64.0)]`."""
    found = [(name.lower(), float(number))
             for name, number in _BOUND.findall(arguments or "")]
    if found:
        return found
    bare = _BARE_NUMBER.match(arguments or "")
    return [("value", float(bare.group(1)))] if bare else []


def analyse_constraint(constraint: str) -> TechniqueResult:
    """Partitions and boundaries for one declared constraint.

    Fail-closed on anything unrecognised (M-17), exactly as `analyse_guard` is:
    an annotation this does not know yields a two-way partition and **no boundary
    claim**, and says so in `unanalysable`. Silence would let a criterion shrink
    its own requirements (P-3).
    """
    result = TechniqueResult()
    text = (constraint or "").strip()
    if not text:
        return result

    match = _ANNOTATION.match(text)
    if match is None:
        result.partitions.append(Partition(
            text, f"satisfies {text}", FROM_CONSTRAINT, text))
        result.partitions.append(Partition(
            text, f"violates {text}", FROM_CONSTRAINT, text))
        result.unanalysable.append((text, "not a recognisable annotation — "
                                          "partitioned two ways, no boundary"))
        return result

    name, arguments = match.group(1), match.group(2) or ""
    subject = _SIZE_LIKE.get(name) or _VALUE_LIKE.get(name) or name

    # Every constraint partitions two ways: the data satisfies it or violates it.
    # That is true of all of them, and it is the half a rejection case needs.
    result.partitions.append(Partition(
        subject, f"satisfies @{name}", FROM_CONSTRAINT, text))
    result.partitions.append(Partition(
        subject, f"violates @{name}", FROM_CONSTRAINT, text))

    if name in _PRESENCE:
        result.unanalysable.append(
            (text, "a presence assertion — no orderable domain, so no boundary"))
        return result
    if name in _SHAPE:
        result.unanalysable.append(
            (text, "a shape assertion — satisfied or not, with no boundary"))
        return result

    bounds = _bounds_in(arguments)
    if not bounds:
        result.unanalysable.append(
            (text, f"@{name} declares no numeric bound to analyse"))
        return result

    for _which, number in bounds:
        for position, offset in ((BELOW, -1), (AT, 0), (ABOVE, 1)):
            value = number + offset
            result.boundaries.append(Boundary(
                variable=subject, position=position, value=value,
                condition=f"{subject} = {_number(value)}", source_guard=text))
    return result


def analyse_constraints(constraints) -> TechniqueResult:
    """Every declared constraint on one transition, folded into one result."""
    combined = TechniqueResult()
    for constraint in constraints or ():
        one = analyse_constraint(constraint)
        combined.partitions.extend(one.partitions)
        combined.boundaries.extend(one.boundaries)
        combined.unanalysable.extend(one.unanalysable)
    return combined
