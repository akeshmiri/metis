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

Deliberately database-free, like the rest of the engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from metis_mcp.mbt.criteria import ALL_TRANSITIONS, GUARD_COVERAGE
from metis_mcp.mbt.model import Model
from metis_mcp.mbt.path_generation import GenerationResult

DIRECT = "direct"
INDIRECT = "indirect"
UNCOVERED = "uncovered"

# Criteria for which indirect (cross-surface) credit is allowed at all.
# Guard coverage is deliberately absent -- see C-2.
_INDIRECT_CREDITABLE = {ALL_TRANSITIONS, "all-states"}


@dataclass(frozen=True)
class LedgerRow:
    transition_id: str
    surface: str
    mechanism: str
    criterion: str
    test_case_id: str | None = None
    note: str = ""


@dataclass
class Ledger:
    model_id: str
    criterion: str
    rows: list[LedgerRow] = field(default_factory=list)
    uncovered: list[tuple[str, str]] = field(default_factory=list)  # (transition id, reason)

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

    def summary(self) -> dict:
        covered = {r.transition_id for r in self.rows}
        return {
            "model": self.model_id,
            "criterion": self.criterion,
            "covered": len(covered),
            "uncovered": len(self.uncovered),
            "indirect_only": len(self.indirect_only()),
        }


def build_ledger(model: Model, result: GenerationResult,
                 test_case_ids: dict[str, str] | None = None) -> Ledger:
    """One row per coverage claim, from a generation result.

    `test_case_ids` maps a path's target key to the rendered case id, so the
    ledger can answer "by which test case" (C-7). Absent, rows record the claim
    without naming an artefact.
    """
    ledger = Ledger(model_id=result.model_id, criterion=result.criterion)
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
        ))

    for u in result.uncoverable:
        ledger.uncovered.append((u.validated_transition_id or u.target_key,
                                 f"{u.reason}: {u.detail}" if u.detail else u.reason))
    for tid, reason in result.excluded:
        ledger.uncovered.append((tid, reason))

    return ledger


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
            note=f"via INVOKES from {ui_transition_id}",
        ))
        credited.append(api_transition_id)
    return credited


def format_report(ledger: Ledger) -> str:
    """A coverage report always states its criterion (P-4, C-11)."""
    s = ledger.summary()
    lines = [
        f"Coverage — {s['model']}",
        f"  criterion:      {s['criterion']}",
        f"  covered:        {s['covered']}",
        f"  uncovered:      {s['uncovered']}",
        f"  indirect only:  {s['indirect_only']}",
    ]
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
