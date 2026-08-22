"""
The coverage ledger (application spec §6.8a, §6.8b).

Records *what is tested, where, and how* -- not merely whether a transition was
touched. Three rules shape this module:

  * **C-1/C-2** coverage has a mechanism: direct, or indirect via an `INVOKES`
    link from another surface. Indirect credit counts for all-transitions but
    **never** for guard coverage, because a UI path can only submit what the UI
    is capable of submitting.
  * **C-8** a transition covered only indirectly is reported as such, never as
    equivalently tested.
  * **C-10/C-11** the ledger records *coverage*, not outcome. It answers
    "is this behaviour tested?" and not "is it working?".

**P-16 -- a coverage figure without its version is not a measurement.** The
report must state the model version and commit it refers to, and for a long time
it did not: the ledger knew the model id and the criterion and nothing else, so
"how covered is release X" could not be answered by the thing whose whole job is
answering it. `ComponentRef` carries that half now, and a ledger built without
one **says so** rather than printing a figure that quietly omits what the rule
requires.

Deliberately database-free, like the rest of the engine. The `Component` and the
validating criteria are *passed in* by the caller, exactly as `test_case_ids`
already is -- this module never opens a session.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from metis_mcp.mbt.criteria import ALL_TRANSITIONS, GUARD_COVERAGE
from metis_mcp.mbt.model import Model
from metis_mcp.mbt.path_generation import GenerationResult

DIRECT = "direct"
INDIRECT = "indirect"
# A UI path **started** this call but observed no outcome (M-5a's `TRIGGERS`).
# Real information — the endpoint was exercised — and **not coverage**: firing a
# request proves neither which outcome occurred nor that anyone asserted it.
INITIATED = "initiated"
UNCOVERED = "uncovered"

# The mechanisms that count toward the covered figure. `INITIATED` is absent by
# design: crediting it would mark the 500 a page never handles as tested, which
# is precisely the gap M-5f exists to surface.
COVERING_MECHANISMS = frozenset({DIRECT, INDIRECT})

# Criteria for which indirect (cross-surface) credit is allowed at all.
# Guard coverage is deliberately absent -- see C-2.
_INDIRECT_CREDITABLE = {ALL_TRANSITIONS, "all-states"}


# What P-16 requires a coverage figure to name. A plain value object, not a
# graph handle: `Component` identity is `(component, commit)` (spec D-6), and both
# halves travel together or the figure is about an unnamed version.
@dataclass(frozen=True)
class ComponentRef:
    id: str
    component: str
    version: str
    commit_sha: str = ""

    def describe(self) -> str:
        commit = self.commit_sha or "no commit recorded"
        return f"{self.component} v{self.version} @ {commit}"


@dataclass(frozen=True)
class LedgerRow:
    transition_id: str
    surface: str
    mechanism: str
    criterion: str
    test_case_id: str | None = None
    note: str = ""
    # Which acceptance criteria validate this transition (`AcceptanceCriterion
    # -[:VALIDATES]->`). The ledger is keyed by transition (C-9), so criterion
    # coverage for a version is a pivot over these rather than a second query.
    criterion_ids: tuple[str, ...] = ()


@dataclass
class Ledger:
    model_id: str
    criterion: str
    rows: list[LedgerRow] = field(default_factory=list)
    uncovered: list[tuple[str, str]] = field(default_factory=list)  # (transition id, reason)
    # P-16. `None` is a real state -- a file-based run with no commit given --
    # and it is reported as such, never silently dropped from the report.
    component: ComponentRef | None = None
    # Every AC validating a transition in scope, covered or not. Needed as its
    # own field because an AC on an UNCOVERED transition has no row to sit on,
    # and omitting it would make the criteria denominator shrink to the covered
    # ones -- a coverage figure that rises by ignoring what it missed.
    criteria_in_scope: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def rows_for(self, transition_id: str) -> list[LedgerRow]:
        return [r for r in self.rows if r.transition_id == transition_id]

    def mechanisms_for(self, transition_id: str) -> set[str]:
        return {r.mechanism for r in self.rows_for(transition_id)}

    def indirect_only(self) -> list[str]:
        """Transitions with indirect coverage and no direct coverage (C-8).

        Reported separately because their combinations were never exercised --
        they are not equivalently tested to a directly-covered transition.
        """
        out = []
        for tid in sorted({r.transition_id for r in self.rows}):
            mechanisms = self.mechanisms_for(tid)
            if INDIRECT in mechanisms and DIRECT not in mechanisms:
                out.append(tid)
        return out

    def initiated_only(self) -> list[str]:
        """Started by a UI path, and never observed by one.

        The honest reading of "the call was genuinely made": worth reporting,
        never counted. A transition here has had a request sent at it and has had
        no outcome asserted.
        """
        out = []
        for tid in sorted({r.transition_id for r in self.rows}):
            mechanisms = self.mechanisms_for(tid)
            if INITIATED in mechanisms and not (mechanisms & COVERING_MECHANISMS):
                out.append(tid)
        return out

    def covered_transitions(self) -> set[str]:
        """Only covering mechanisms. `initiated` is deliberately absent."""
        return {r.transition_id for r in self.rows
                if r.mechanism in COVERING_MECHANISMS}

    def criteria_covered(self) -> list[str]:
        """ACs validating at least one covered transition (C-7, execution-free).

        This is what "release coverage" means without an execution result: a
        criterion whose behaviour has a test case, whether or not that case has
        ever been run (C-10, C-11).
        """
        covered = self.covered_transitions()
        out: set[str] = set()
        for tid in covered:
            out.update(self.criteria_in_scope.get(tid, ()))
        return sorted(out)

    def criteria_uncovered(self) -> list[str]:
        """ACs in scope validating nothing covered.

        Computed against `criteria_in_scope`, not against the rows: an AC on an
        uncovered transition has no row, and deriving the denominator from rows
        would let the figure rise by ignoring what it missed.
        """
        covered = set(self.criteria_covered())
        every: set[str] = set()
        for ids in self.criteria_in_scope.values():
            every.update(ids)
        return sorted(every - covered)

    def summary(self) -> dict:
        # Only covering mechanisms count. Summing every row would let a trigger
        # raise the number, which is the one thing `initiated` exists to prevent.
        covered = self.covered_transitions()
        criteria_covered = self.criteria_covered()
        return {
            "model": self.model_id,
            "criterion": self.criterion,
            # P-16: the version and commit this figure refers to. `None` when the
            # run did not record one -- absent, not zero, and the report says so.
            "component": self.component.component if self.component else None,
            "version": self.component.version if self.component else None,
            "commit": (self.component.commit_sha or None) if self.component else None,
            "covered": len(covered),
            "uncovered": len(self.uncovered),
            "indirect_only": len(self.indirect_only()),
            # Reported beside the covered figure, never inside it.
            "initiated_not_covered": len(self.initiated_only()),
            "criteria_covered": len(criteria_covered),
            "criteria_uncovered": len(self.criteria_uncovered()),
        }


def build_ledger(model: Model, result: GenerationResult,
                 test_case_ids: dict[str, str] | None = None,
                 *,
                 component: ComponentRef | None = None,
                 validating_criteria: dict[str, list[str]] | None = None) -> Ledger:
    """One row per coverage claim, from a generation result.

    `test_case_ids` maps a path's target key to the rendered case id, so the
    ledger can answer "by which test case" (C-7). Absent, rows record the claim
    without naming an artefact.

    `component` is P-16's version and commit. `validating_criteria` maps a
    transition id to the ids of the acceptance criteria that `VALIDATES` it --
    the same shape as `test_case_ids`, and read from the graph by the caller so
    this module stays database-free.

    Both are keyword-only and both default to `None`, which is a reported state
    rather than a silent one: a ledger with no component says so in its report.
    """
    criteria = {tid: tuple(ids) for tid, ids in (validating_criteria or {}).items() if ids}
    ledger = Ledger(model_id=result.model_id, criterion=result.criterion,
                    component=component, criteria_in_scope=criteria)
    ids = test_case_ids or {}

    for path in result.paths:
        transition = model.transitions[path.validated_transition_id]
        ledger.rows.append(LedgerRow(
            transition_id=transition.id,
            surface=model.states[transition.source].surface,
            mechanism=DIRECT,
            criterion=result.criterion,
            test_case_id=ids.get(path.target_key),
            note=path.data_note or "",
            criterion_ids=criteria.get(transition.id, ()),
        ))

    for u in result.uncoverable:
        ledger.uncovered.append((u.validated_transition_id or u.target_key,
                                 f"{u.reason}: {u.detail}" if u.detail else u.reason))
    for tid, reason in result.excluded:
        ledger.uncovered.append((tid, reason))

    return ledger


def credit_initiated(ledger: Ledger, model: Model, triggers: dict[str, list[str]],
                     covered_elsewhere: set[str]) -> list[str]:
    """Record that a UI path **started** these API calls (M-5a's `TRIGGERS`).

    `triggers` is one-to-many — opening a page fires every panel's request — and
    is deliberately a different shape from `invokes`, which is one-to-one.

    Nothing here is credited as coverage. C-3's structural argument holds for
    `INVOKES` (a UI transition that rendered an outcome necessarily satisfied
    that outcome's guard) and **not** for `TRIGGERS`: at the moment the request
    leaves, no outcome has occurred, and a failing call frequently produces no UI
    transition at all.
    """
    initiated = []
    for ui_transition_id, api_ids in sorted(triggers.items()):
        if ui_transition_id not in covered_elsewhere:
            continue
        for api_transition_id in sorted(api_ids):
            if api_transition_id not in model.transitions:
                continue
            if ledger.mechanisms_for(api_transition_id) & COVERING_MECHANISMS:
                continue  # already covered; "was called" adds nothing
            transition = model.transitions[api_transition_id]
            ledger.rows.append(LedgerRow(
                transition_id=api_transition_id,
                surface=model.states[transition.source].surface,
                mechanism=INITIATED,
                criterion=ledger.criterion,
                criterion_ids=ledger.criteria_in_scope.get(api_transition_id, ()),
                note=(f"started by {ui_transition_id} — the call was made; this "
                      f"outcome was not observed"),
            ))
            initiated.append(api_transition_id)
    return initiated


def credit_indirect(ledger: Ledger, model: Model, invokes: dict[str, str],
                    covered_elsewhere: set[str]) -> list[str]:
    """Credit API transitions exercised indirectly by covering UI paths (C-2/C-3).

    `invokes` maps a UI transition id to the API transition it drives (M-5a).
    `covered_elsewhere` is the set of UI transition ids with direct coverage.

    Credit is **structural, not a judgement** (C-3): because a UI transition's
    inherited guard is a *reference* to the API transition's guard (M-5c), a UI
    path traversing it necessarily satisfies that API guard. No similarity
    heuristic is involved, or permitted.

    Returns the transition ids credited. Refuses entirely under guard coverage.
    """
    if ledger.criterion not in _INDIRECT_CREDITABLE:
        # C-2: never credit indirect coverage toward guard coverage. A UI path
        # cannot exercise combinations the UI is incapable of submitting.
        return []

    credited = []
    for ui_transition_id, api_transition_id in sorted(invokes.items()):
        if ui_transition_id not in covered_elsewhere:
            continue
        if api_transition_id not in model.transitions:
            continue
        if DIRECT in ledger.mechanisms_for(api_transition_id):
            continue  # already directly covered; indirect adds nothing
        transition = model.transitions[api_transition_id]
        ledger.rows.append(LedgerRow(
            transition_id=api_transition_id,
            surface=model.states[transition.source].surface,
            mechanism=INDIRECT,
            criterion=ledger.criterion,
            criterion_ids=ledger.criteria_in_scope.get(api_transition_id, ()),
            note=f"via INVOKES from {ui_transition_id}",
        ))
        credited.append(api_transition_id)
    return credited


def format_report(ledger: Ledger) -> str:
    """A coverage report always states its criterion and its version (P-4, P-16, C-11)."""
    s = ledger.summary()
    lines = [f"Coverage — {s['model']}"]
    if ledger.component is not None:
        lines.append(f"  version:        {ledger.component.describe()}")
    else:
        # P-16 asks for the version and commit every time. Printing the figure
        # without them and saying nothing would read as though the omission were
        # not there; a coverage number about an unnamed version is exactly the
        # kind of claim this whole module refuses to make quietly.
        lines.append("  version:        not recorded for this run (P-16) — this "
                     "figure names no version or commit")
    lines += [
        f"  criterion:      {s['criterion']}",
        f"  covered:        {s['covered']}",
        f"  uncovered:      {s['uncovered']}",
        f"  indirect only:  {s['indirect_only']}",
    ]
    if ledger.criteria_in_scope:
        lines.append(f"  criteria:       {s['criteria_covered']} covered, "
                     f"{s['criteria_uncovered']} not")
    if ledger.indirect_only():
        lines.append("")
        lines.append("  Covered only indirectly — combinations not exercised (C-8):")
        for tid in ledger.indirect_only():
            lines.append(f"    {tid}")
    if ledger.uncovered:
        lines.append("")
        lines.append("  Not covered:")
        for tid, reason in ledger.uncovered:
            lines.append(f"    {tid:<12} {reason}")
    lines.append("")
    lines.append("  This states what is TESTED, not what is WORKING (C-11).")
    return "\n".join(lines)
