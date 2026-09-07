"""
Stage checks — predicates that actually run (application spec D-10, F-9).

**This module is the correction of Atlas's central defect.** Atlas's
`validate_artifacts.py` handles a stage's `validation_checks` like this:

    for check in validation_checks:
        messages.append(f"CHECK: {check}")

The strings are printed and never evaluated, and `passed` is computed purely
from file existence. Its own agent prose then says "all validation_checks must
pass before [C] is available" -- a guarantee nothing is in a position to give.

Here a check is a **named Python predicate**. A workflow that names a check with
no registered implementation fails the lint *before it can run*, so the failure
mode is a broken build rather than a green run that checked nothing. Métis can
afford this because the checks already exist as tested code -- this module
mostly points at them.

**A check returns a reason when it fails, never a bare False.** F-9 requires a
stage that fails to report what failed and the explicit action required; a
predicate that can only say "no" cannot satisfy that, and the caller ends up
inventing an explanation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from metis_mcp.mbt.model import APPROVED


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


OK = CheckResult(True)


def failed(reason: str) -> CheckResult:
    return CheckResult(False, reason)


Check = Callable[..., CheckResult]
_CHECKS: dict[str, Check] = {}


def check(name: str) -> Callable[[Check], Check]:
    def register(fn: Check) -> Check:
        _CHECKS[name] = fn
        return fn
    return register


def get(name: str) -> Check | None:
    return _CHECKS.get(name)


def registered() -> frozenset[str]:
    return frozenset(_CHECKS)


def run_all(names, context) -> CheckResult:
    """Run named checks in order, stopping at the first failure (F-9).

    An unregistered name is a hard failure rather than a skip. Skipping it is
    how a check becomes decorative -- the exact state Atlas's are in.
    """
    for name in names:
        fn = get(name)
        if fn is None:
            return failed(
                f"check {name!r} is not registered — a workflow may not name a "
                f"check nothing implements. Register it in workflow/checks.py or "
                f"remove it from the stage")
        result = fn(context)
        if not result.ok:
            return result
    return OK


# ---------------------------------------------------------------------------
# The checks. Each one points at machinery that already exists and is tested.
# ---------------------------------------------------------------------------

@check("model_is_wellformed")
def _wellformed(context) -> CheckResult:
    """M-18: any well-formedness failure blocks.

    Delegates to `require_valid`, which already assembles the message a blocked
    operator needs -- the findings themselves, not a count, because nobody can
    act on "3 problems". Re-deriving that here would give the workflow its own,
    quieter account of the same failure.
    """
    from metis_mcp.mbt.validation import ValidationFailed, require_valid

    if context.model is None:
        return failed("no model in scope — nothing to validate")
    try:
        require_valid(context.model, allow_unverifiable=context.allow_unverifiable,
                      inherited=context.inherited)
    except ValidationFailed as e:
        return failed(str(e))
    return OK


@check("model_is_approved")
def _approved(context) -> CheckResult:
    """G1: nothing is generated from an unreviewed model (§3.4, D-10)."""
    model = context.model
    if model is None:
        return failed("no model in scope")
    outstanding = model.unapproved_elements()
    if outstanding:
        return failed(
            f"{model.id} is not approved — {len(outstanding)} element(s) awaiting "
            f"review. Generating from an unreviewed model would produce "
            f"confidently wrong tests")
    return OK


@check("risk_is_accepted")
def _risk_accepted(context) -> CheckResult:
    """A risk acceptance names a person, and that is verified outside the handler.

    G1 declares `model_is_approved` and G2 has its own literal; this gate
    declared **no checks at all**, so the only thing standing between an
    unaccepted assessment and a passed stage was the handler's own `if`. Every
    other gate in this engine is guarded twice on purpose -- a handler decides
    what to report, a check decides whether the stage may pass -- and a gate with
    one of those is a gate whose guarantee rests on nobody editing the handler.

    Checks the identity rather than the literal. The literal is what the person
    typed this run and the handler has already compared it; the *name* is what
    the audit record keeps, and an acceptance with no name is the one thing
    `references/risk-governance.md` says the trail cannot be missing: "who / when
    / what / why -- without the last one the trail is useless", and without the
    first there is no trail at all.
    """
    answers = getattr(context, "risk_answers", None) or {}
    who = str(answers.get("accepted_by") or "").strip()
    if not who:
        return failed(
            "the assessment has not been accepted by a named person. Accepting "
            "takes ownership of every probability in it — Métis set none, and an "
            "acceptance nobody signed is not one")
    return OK


@check("design_is_accepted")
def _design_accepted(context) -> CheckResult:
    """A design acceptance names a person, verified outside the handler.

    The same double guard every gate in this engine has, and for the reason
    `risk_is_accepted` gives: a handler decides what to report, a check decides
    whether the stage may pass, and a gate with only the first rests its
    guarantee on nobody editing the handler.

    Checks the identity rather than the literal. The literal is what somebody
    typed this run and the handler has already compared it; the NAME is what
    survives into the document, and a design nobody signed is a set of proposals
    -- which is what Métis produced and is exactly what accepting is meant to
    change.
    """
    answers = getattr(context, "design_answers", None) or {}
    who = str(answers.get("accepted_by") or "").strip()
    if not who:
        return failed(
            "the design has not been accepted by a named person. Accepting it "
            "takes ownership of every decision in it — Métis proposed the rows "
            "and decided none of them")
    return OK


@check("intent_is_reviewed")
def _intent_reviewed(context) -> CheckResult:
    """Nothing is imported until the four readers have looked at it.

    **This is what makes intent a pre-processor rather than a post-mortem.**
    `intake` used to fetch, validate, land and only then assess risk, so the
    first moment anybody saw what was wrong with a claim was after it was a node
    in the graph. This check sits before `land`.

    It refuses on `not-ready` only, which is narrow on purpose. `not-ready`
    means the claim cannot be *represented* honestly -- a need with no
    specification would become a node nothing can ever be checked against (D-1).
    A claim nobody has costed, or whose environments are unlisted, is `ready`
    and lands with every one of those gaps recorded beside it: refusing those
    would mean Métis only ever accepted claims that were already finished, which
    is not what intake is for.
    """
    analysis = getattr(context, "analysis", None)
    if analysis is None:
        return failed(
            "no intent review ran, so nothing has looked at this claim. "
            "`analysis` is set by the `analysis` stage — a run that reached "
            "here without it has skipped the reading, not passed it")
    if analysis.get("status") == "not-ready":
        blocking = analysis.get("blocking") or []
        return failed(
            f"{len(blocking)} gap(s) mean this cannot be represented in the "
            f"graph as it stands: " + "; ".join(blocking[:3]))
    return OK


@check("landed_at_quarantine")
def _quarantine(context) -> CheckResult:
    """S-4: a source produces candidates, never approved facts."""
    model = context.model
    if model is None:
        return failed("no model in scope")
    approved = [sid for sid, s in model.states.items()
                if s.lifecycle_state == APPROVED]
    if approved and not context.expect_prior_approval:
        return failed(
            f"{len(approved)} element(s) landed already Approved. Authoring is not "
            f"approving (S-4) — a source that lands its own output as approved "
            f"has bypassed G1 entirely")
    return OK


@check("criteria_are_atomic")
def _criteria_atomic(context) -> CheckResult:
    """A criterion is atomic: one condition, one action, one validation.

    Blocking, unlike `check_ac_atomicity`'s advisory finding on a model, and the
    difference is real. There, the guard is a fact about the system and the
    criterion's shape is a consequence nobody chose. Here a person is *writing*
    the criteria, so a compound one is a correctable input -- and letting it
    through would mine several behaviours into one transition, which no later
    stage can take apart again.
    """
    from metis_mcp.model_sources.knowledge import validate as validate_knowledge

    knowledge = context.knowledge
    if knowledge is None:
        return failed("no knowledge file in scope — nothing to check")
    problems = validate_knowledge(knowledge)
    if problems:
        lines = "\n".join(f"    {p.describe()}" for p in problems)
        return failed(
            f"{len(problems)} problem(s) in the knowledge file; nothing is mined "
            f"until they are fixed:\n{lines}")
    return OK


@check("drafts_are_code_derived")
def _drafts_code_derived(context) -> CheckResult:
    """S-19: a criterion drafted from the code cannot arrive as intent.

    §4.1's circularity in its most direct form. A draft written *from* the
    behaviour it describes can only report agreement, so it must land at the
    weakest grade and stay there until a person edits or affirms it. A drafting
    stage that emitted anything else would manufacture the very thing S-19
    exists to protect.
    """
    from metis_mcp.ontology.labels import CODE_DERIVED

    wrong = [d.id for d in context.drafts if d.provenance != CODE_DERIVED]
    if wrong:
        return failed(
            f"{len(wrong)} draft(s) claim a provenance other than {CODE_DERIVED!r} "
            f"(first: {wrong[0]}). A criterion written from the code is "
            f"documentation; only a human edit or affirmation makes it intent (S-19)")
    return OK
