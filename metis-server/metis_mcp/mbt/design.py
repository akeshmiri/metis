"""
Test design: choosing a technique, and applying the two the engine lacked
(ISO/IEC/IEEE 29119-4; spec P-1a, M-9, GD-3).

**Step 5 of the journey, and it did not exist.** What Métis had were *coverage
criteria* — all-states, all-transitions, all-transition-pairs, guard-coverage,
boundary-coverage — and those are **path selection**: which walks to take through
a machine. Test design is the prior question: given this behaviour, which
technique actually finds its defects?

Two techniques were missing, and both are computable from what the graph now
holds rather than from anything new:

  * **Decision table** — a `(state, trigger)` group is a table already. Its
    transitions are the outcomes and their guards are the conditions, so
    enumerating the condition combinations gives one rule per row. Guard
    coverage varies each condition true and false *independently*; a decision
    table asks which **combinations** are reachable and what each produces,
    which is where a missing rule hides.
  * **Pairwise** — 245 `Parameter` nodes with `required` and `constraints`, and
    1,581 `Field`s behind them. Most defects involving several inputs are
    triggered by a *pair*, so covering all pairs finds them at a fraction of the
    exhaustive product.

**M-9 governs every output here.** A technique states a *condition on the data*
— "this parameter is absent", "this field violates `@NotNull`" — and never
solves it. Nothing in this module constructs a value, and `test_design.py`
asserts that no output names anything outside the model's own vocabulary.

**The model is the input, and the only input.** Test design consumes the graph;
it does not read a specification and cannot write one. Authority runs one way —
spec and AC author intent, the model carries it, design reads it — because a
test artefact that could rewrite the intent it came from is §4.1's circularity
arriving by a longer route.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from metis_mcp.behavior_model import _conjuncts, _parse_guard
from metis_mcp.mbt.model import Model

# Techniques this module can select, named for what ISO 29119-4 calls them.
DECISION_TABLE = "decision-table"
PAIRWISE = "pairwise"
BOUNDARY_VALUE = "boundary-value"
EQUIVALENCE_PARTITION = "equivalence-partition"

# 2**n rows. A real `(state, trigger)` group has two or three conditions; the cap
# only stops a pathological group being enumerated into uselessness, and when it
# trips the group is REPORTED rather than silently reduced (P-3b).
MAX_TABLE_CONDITIONS = 6


@dataclass(frozen=True)
class Rule:
    """One row of a decision table: a condition combination and its outcome."""

    conditions: tuple[tuple[str, bool], ...]
    transition_id: str | None
    # Set where no transition covers this combination. Not necessarily a defect:
    # the conditions may be unable to hold together, which is not decidable from
    # the text (`t.isEmpty()` and `t.isPresent()` look independent).
    unreachable_note: str = ""

    @property
    def is_covered(self) -> bool:
        return self.transition_id is not None

    def describe(self) -> str:
        return " and ".join(
            (atom if holds else f"NOT ({atom})") for atom, holds in self.conditions)


@dataclass
class DecisionTable:
    state: str
    trigger: str
    conditions: tuple[str, ...] = ()
    rules: list[Rule] = field(default_factory=list)
    reason_unavailable: str = ""

    @property
    def is_available(self) -> bool:
        return not self.reason_unavailable

    @property
    def uncovered(self) -> list[Rule]:
        return [r for r in self.rules if not r.is_covered]


def decision_table(model: Model, state: str, trigger: str) -> DecisionTable:
    """The `(state, trigger)` group as a table of conditions against outcomes.

    Fail-closed, and for the same reasons `_boolean_coverage_gap` is: an `OR`
    makes the guard a disjunction this does not reason about, and a numeric
    threshold belongs to boundary analysis rather than to a boolean table.
    Either one makes the table *unavailable* and says so — a partial table
    presented as complete is worse than none, because a missing row reads as a
    covered one.
    """
    table = DecisionTable(state=state, trigger=trigger)
    members = [t for t in model.transitions.values()
               if t.source == state and t.trigger == trigger]
    if len(members) < 2:
        table.reason_unavailable = (
            "only one transition on this (state, trigger) — a table of one row "
            "states nothing a single test does not")
        return table

    clauses = {t.id: _conjuncts(t.guard) for t in members}
    if any(c is None for c in clauses.values()):
        table.reason_unavailable = (
            "a guard contains OR — deciding a disjunction needs real boolean "
            "reasoning, and half a table is worse than none (M-17)")
        return table

    atoms = sorted({atom for c in clauses.values() if c for atom, _ in c})
    if not atoms:
        table.reason_unavailable = "no conditions to tabulate — every guard is empty"
        return table
    if any(_parse_guard(atom) is not None for atom in atoms):
        table.reason_unavailable = (
            "a condition is a numeric threshold — that is boundary analysis, and "
            "treating it as a boolean invents rows that cannot occur")
        return table
    if len(atoms) > MAX_TABLE_CONDITIONS:
        table.reason_unavailable = (
            f"{len(atoms)} conditions is {2 ** len(atoms)} rows — reported rather "
            f"than generated (P-3b)")
        return table

    table.conditions = tuple(atoms)
    index = {atom: i for i, atom in enumerate(atoms)}

    for row in range(1 << len(atoms)):
        assignment = tuple((atom, bool(row >> index[atom] & 1)) for atom in atoms)
        truth = dict(assignment)
        covering = next(
            (t.id for t in members
             if clauses[t.id] is not None
             and all(truth[atom] is not negated for atom, negated in clauses[t.id])),
            None)
        table.rules.append(Rule(
            conditions=assignment, transition_id=covering,
            unreachable_note="" if covering else (
                "no transition covers this combination — either a real input "
                "there matches nothing, or these conditions cannot hold "
                "together, which is not decidable from the text alone")))
    return table


# ---------------------------------------------------------------------------
# Pairwise
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Factor:
    """One input that can vary, and the ways it can (M-9: conditions, not values)."""

    name: str
    levels: tuple[str, ...]


def factors_for(transition) -> list[Factor]:
    """What can vary about this transition's inputs.

    Each parameter varies two ways it is honest to state without inventing data:
    an optional one is **supplied or omitted**; a required one is **valid or
    violating its declared constraint**. Both are conditions on the data, which
    M-9 permits; a concrete value is not, and none is produced.

    A parameter with no declared constraint and no optionality has nothing to
    vary that this can name, so it contributes no factor rather than a guessed
    one.
    """
    out: list[Factor] = []
    for parameter in getattr(transition, "inputs", ()) or ():
        name = (parameter or {}).get("name") or ""
        if not name:
            continue
        required = bool((parameter or {}).get("required", True))
        constraints = tuple((parameter or {}).get("constraints") or ())
        if not required:
            out.append(Factor(name, ("supplied", "omitted")))
        elif constraints:
            out.append(Factor(name, ("satisfies " + constraints[0], "violates " + constraints[0])))
        else:
            out.append(Factor(name, ("supplied", "omitted")))
    return out


def all_pairs(factors: list[Factor]) -> list[dict[str, str]]:
    """Cover every pair of levels across every pair of factors.

    Greedy, and deterministic: the same factors in the same order always yield
    the same set, because generation determinism (P-7) is not negotiable for
    something a test suite is built from.

    Fewer than two factors has no pair to cover, so it yields one case per level
    rather than an empty result — the caller asked for coverage of what varies,
    and one varying input still varies.
    """
    if not factors:
        return []
    if len(factors) == 1:
        return [{factors[0].name: level} for level in factors[0].levels]

    # Every pair that must appear in some case, in a fixed order so the result
    # is reproducible (P-7).
    required: list[tuple[str, str, str, str]] = []
    for i, a in enumerate(factors):
        for b in factors[i + 1:]:
            for la in a.levels:
                for lb in b.levels:
                    required.append((a.name, la, b.name, lb))
    outstanding = list(required)

    by_name = {f.name: f for f in factors}
    cases: list[dict[str, str]] = []

    while outstanding:
        # **Seed from an uncovered pair.** Filling greedily from an empty case
        # was the first version and it silently never covered anything: with no
        # levels fixed yet every candidate scores zero, so the first factor took
        # `levels[0]` in every case and its second level never appeared at all.
        a_name, a_level, b_name, b_level = outstanding[0]
        case = {a_name: a_level, b_name: b_level}

        for factor in factors:
            if factor.name in case:
                continue
            # The level closing the most still-uncovered pairs against what this
            # case has already fixed. Ties break on declared order, never on set
            # iteration, which would vary between runs.
            best, best_score = factor.levels[0], -1
            for level in factor.levels:
                score = sum(
                    1 for name, chosen in case.items()
                    if (name, chosen, factor.name, level) in outstanding
                    or (factor.name, level, name, chosen) in outstanding)
                if score > best_score:
                    best, best_score = level, score
            case[factor.name] = best

        covered = {pair for pair in outstanding
                   if case.get(pair[0]) == pair[1] and case.get(pair[2]) == pair[3]}
        outstanding = [p for p in outstanding if p not in covered]
        cases.append(case)

        if not covered:
            # Cannot happen while the seed is itself an uncovered pair, and
            # asserted rather than assumed: a generator that stops making
            # progress must fail loudly, not loop.
            raise RuntimeError(
                f"pairwise made no progress on {by_name and len(outstanding)} "
                f"outstanding pair(s) — the seed did not cover itself")
    return cases
