"""
The two gap reports (application spec F-4, F-5; DQ-024).

Reconciliation produces **three** outputs, not one:

    matched pairs                the coverage basis
    transitions with no AC       UNSPECIFIED BEHAVIOUR
    ACs with no transition       UNIMPLEMENTED OR UNMODELLED

**F-5 is the rule that matters: the two gap types are not symmetric and are never
merged into one number.** The first is a specification gap -- the system does
something nobody wrote a criterion for. The second is an implementation or
modelling gap -- somebody specified something the model does not contain. They
have different causes, different severities and different owners, and averaging
them into "87% reconciled" destroys all of that.

This module also makes DQ-024 falsifiable for the first time. While transitions
were hand-authored alongside their criteria, "implemented behaviour with no
acceptance criterion" always read zero, because the same person wrote both sides.
Against code-derived transitions it reads what is actually true.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from metis_mcp.mbt.model import IMPLEMENTED, Model
from metis_mcp.reconciliation.matching import (
    CODE_DERIVED, AcceptanceCriterion, ConfirmedMatch,
)

UNSPECIFIED_BEHAVIOUR = "unspecified_behaviour"
UNIMPLEMENTED_OR_UNMODELLED = "unimplemented_or_unmodelled"


@dataclass
class Gap:
    kind: str
    element_id: str
    detail: str


@dataclass
class Reconciliation:
    matched: list[ConfirmedMatch] = field(default_factory=list)
    unspecified_behaviour: list[Gap] = field(default_factory=list)
    unimplemented: list[Gap] = field(default_factory=list)

    @property
    def intent_matched(self) -> list[ConfirmedMatch]:
        """Matches backed by INTENT (spec S-19).

        A match against a criterion written from the code is documentation
        agreeing with itself. It is a real match -- the criterion does describe
        that transition -- but it is not evidence the behaviour is *right*.
        """
        return [m for m in self.matched if m.is_intent]

    @property
    def documentation_matched(self) -> list[ConfirmedMatch]:
        return [m for m in self.matched if not m.is_intent]

    @property
    def summary(self) -> dict[str, int]:
        return {
            "matched": len(self.matched),
            "matched_by_intent": len(self.intent_matched),
            "matched_by_documentation": len(self.documentation_matched),
            UNSPECIFIED_BEHAVIOUR: len(self.unspecified_behaviour),
            UNIMPLEMENTED_OR_UNMODELLED: len(self.unimplemented),
        }

    @property
    def supports_a_correctness_claim(self) -> bool:
        """S-19/TR-11: only intent-backed matches can (spec §4.1)."""
        return bool(self.intent_matched)


def reconcile(model: Model, criteria: list[AcceptanceCriterion],
              confirmed: list[ConfirmedMatch]) -> Reconciliation:
    """Both directions, reported separately (spec F-4).

    Only **confirmed** matches count (F-7). Pre-filter candidates are evidence a
    human has not yet ruled on, and counting them would inflate coverage with
    guesses.
    """
    result = Reconciliation(matched=list(confirmed))

    matched_transitions = {m.transition_id for m in confirmed}
    matched_acs = {m.ac_id for m in confirmed}

    for tid in model.transition_ids():
        transition = model.transitions[tid]
        if transition.implementation_status != IMPLEMENTED:
            # `planned` behaviour is not a gap -- it does not exist yet (P-11).
            continue
        if tid not in matched_transitions:
            result.unspecified_behaviour.append(Gap(
                kind=UNSPECIFIED_BEHAVIOUR, element_id=tid,
                detail=(f"{transition.source} --[{transition.trigger}]--> "
                        f"{transition.target}: real behaviour with no acceptance criterion"),
            ))

    for ac in criteria:
        if ac.id not in matched_acs:
            result.unimplemented.append(Gap(
                kind=UNIMPLEMENTED_OR_UNMODELLED, element_id=ac.id,
                detail=f"{ac.text[:90]}: no transition in this model corresponds",
            ))

    return result


def dq_024(model: Model, confirmed: list[ConfirmedMatch]) -> dict:
    """Implemented transitions with at least one validating criterion.

    Reported with `falsifiable` stating whether the number can mean anything.
    **Two separate ways it can fail to mean anything**, and both are checked:

      1. the transitions are hand-authored, so the same person wrote both sides
         (REQ-DQ-001's original obligation);
      2. the criteria are **code-derived**, so the intent side was written FROM
         the behaviour it is measuring (S-19). This is the the pilot estate case: specs
         marked IMPLEMENTED, whose own plan says they document what was built.
         Counting those as validation reports a system agreeing with itself.

    `with_intent` is therefore reported alongside, and it is the only figure that
    can support a correctness claim.
    """
    implemented = [t for t in model.transitions.values()
                   if t.implementation_status == IMPLEMENTED]
    validated = {m.transition_id for m in confirmed}
    intent_validated = {m.transition_id for m in confirmed if m.is_intent}
    covered = [t for t in implemented if t.id in validated]
    intent_covered = [t for t in implemented if t.id in intent_validated]

    methods = {getattr(t, "extraction_method", "hand_authored") for t in implemented}
    hand_authored_only = methods == {"hand_authored"}
    documentation_only = bool(confirmed) and not intent_validated
    falsifiable = not hand_authored_only and not documentation_only

    qualifier = ""
    if hand_authored_only:
        qualifier = ("NOT falsifiable: every transition is hand_authored, so this "
                     "measures modelling discipline, not coverage of real "
                     "behaviour (REQ-DQ-001)")
    elif documentation_only:
        qualifier = ("NOT falsifiable: every validating criterion is code_derived, "
                     "so the intent side was written from the behaviour it "
                     "measures. This reports documentation agreeing with itself, "
                     "not correctness (S-19, §4.1)")

    return {
        "implemented": len(implemented),
        "with_acceptance_criterion": len(covered),
        "with_intent": len(intent_covered),
        "ratio": round(len(covered) / len(implemented), 3) if implemented else None,
        "intent_ratio": (round(len(intent_covered) / len(implemented), 3)
                         if implemented else None),
        "falsifiable": falsifiable,
        "qualifier": qualifier,
    }


def format_reconciliation(result: Reconciliation) -> str:
    """Never merges the two gap types into one figure (spec F-5)."""
    s = result.summary
    lines = [
        "Reconciliation",
        f"  matched (confirmed):        {s['matched']}",
        f"    of which INTENT-backed:   {s['matched_by_intent']}"
        f"   <- the only ones that can support a correctness claim (S-19)",
        f"    of which documentation:   {s['matched_by_documentation']}"
        f"   <- code-derived; agreement here is circular (§4.1)",
        "",
        f"  UNSPECIFIED BEHAVIOUR:      {s[UNSPECIFIED_BEHAVIOUR]}",
        "     the system does this; no acceptance criterion covers it",
    ]
    for gap in result.unspecified_behaviour[:8]:
        lines.append(f"       {gap.detail}")
    lines += [
        "",
        f"  UNIMPLEMENTED / UNMODELLED: {s[UNIMPLEMENTED_OR_UNMODELLED]}",
        "     specified, but no corresponding behaviour in this model",
    ]
    for gap in result.unimplemented[:8]:
        lines.append(f"       {gap.element_id}: {gap.detail}")
    lines += [
        "",
        "  These two are NOT one number. A specification gap and an implementation",
        "  gap have different causes and different owners (spec F-5).",
    ]
    if not result.supports_a_correctness_claim and result.matched:
        lines += [
            "",
            "  NO CORRECTNESS CLAIM IS SUPPORTED BY THIS RUN. Every confirmed match",
            "  is against a code_derived criterion, so both sides came from the same",
            "  code. That yields coverage, never correctness (S-19, S-3, TR-11).",
        ]
    return "\n".join(lines)
