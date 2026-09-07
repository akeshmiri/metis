"""
Two classifications a test design needs and coverage cannot give it.

Ported from Atlas's `test-designer` stages 04 and 05, which are the two stages
the Métis port had no equivalent for. Coverage answers *is this behaviour
tested?*; these answer *can it be automated at all?* and *is it worth driving
under load?* — different questions, and a design that skips them either
automates something it cannot assert or load-tests something nobody sized.

**Both classify from recovered evidence, and refuse where there is none.** That
is the ported discipline, not a Métis embellishment: Atlas's stage 04 says never
mark a scenario `automate` from the class name alone — verify the prerequisite
exists, with a concrete reference — and its stage 05 says mark
`performance-candidate` only where volume or SLA risk is stated or verifiable,
never invented.

So the honest failure mode here is a `no basis` verdict, and it is reported as
one rather than being rounded to the safe-sounding answer. Classifying every
transition `functional-only` because the model carries no volume facts would
read as "measured, and none qualify", which is a different and false claim.
"""
from __future__ import annotations

from metis_mcp.mbt.validation import validate

# Stage 04 verdicts.
AUTOMATE = "automate"
MANUAL_ONLY = "manual-only"
DEFER = "defer"

# Stage 05 verdicts.
PERFORMANCE_CANDIDATE = "performance-candidate"
FUNCTIONAL_ONLY = "functional-only"
NO_BASIS = "no-basis"

# Input names that make a call volume-sensitive. Derived from the contract, not
# guessed from a route: a paged endpoint is one whose parameters say it pages.
_PAGING = ("page", "size", "limit", "offset", "cursor", "per_page", "pagesize",
           "top", "skip", "count", "max")
# Types that carry many of a thing, so cost scales with the caller's input.
_BULK_HINTS = ("list", "array", "collection", "[]", "set<", "iterable")


def _has_anchor(transition) -> bool:
    """Whether any recovered evidence points at a source line (X-6).

    The concrete form of Atlas's "verify the prerequisite exists, with a
    concrete reference": an unanchored transition is one nobody can point at, so
    nothing about it may be called verified.
    """
    return bool(getattr(transition, "evidence", ()) or
                getattr(transition, "guard_anchor", ""))


def classify_viability(model, unverifiable_ids: set[str] | None = None) -> list[dict]:
    """`automate` / `manual-only` / `defer` per transition, each with its reason.

    The reason is not decoration. A verdict a reader cannot audit is a verdict
    they have to take on trust, and this one decides whether somebody spends a
    week automating something that cannot be asserted.
    """
    unverifiable = unverifiable_ids if unverifiable_ids is not None else set()
    out: list[dict] = []

    for tid in model.transition_ids():
        transition = model.transitions[tid]
        trigger = (transition.trigger or "").strip()
        method, _, route = trigger.partition(" ")
        is_api = bool(route) and method.isupper()

        if tid in unverifiable:
            verdict, why = DEFER, (
                "the guard could not be shown to hold or fail, so there is no "
                "oracle to assert against (M-17). Neither a pass nor a defect — "
                "a third outcome")
        elif getattr(transition, "source_state_unresolved", False):
            verdict, why = MANUAL_ONLY, (
                "the state this runs from could not be resolved, so the "
                "precondition cannot be established from nothing (P-8)")
        elif not _has_anchor(transition):
            verdict, why = MANUAL_ONLY, (
                "no recovered evidence points at a source line, so nothing "
                "about this is verified (X-6) — automating it would rest on a "
                "name")
        elif is_api and not transition.inputs and method not in ("GET", "DELETE"):
            verdict, why = DEFER, (
                f"{method} with no recovered inputs: the request body is "
                f"unknown, so a call cannot be built from the contract")
        elif not is_api:
            # A UI action needs an addressable element, and Métis never guesses
            # a selector -- rendering raises rather than inventing one.
            verdict, why = MANUAL_ONLY, (
                "a UI action needs an authored selector; none is recovered, and "
                "a guessed one produces a test that fails for an unrelated "
                "reason")
        else:
            verdict, why = AUTOMATE, (
                f"anchored, and the contract is recovered "
                f"({len(transition.inputs)} input(s), outcome "
                f"{transition.outcome_status or 'unstated'})")

        out.append({"transition_id": tid, "trigger": trigger,
                    "verdict": verdict, "why": why})
    return out


def _volume_signals(transition) -> list[str]:
    """Why this call's cost might scale — from its contract, never its name."""
    signals = []
    for item in transition.inputs or ():
        name = str(item.get("name", "")).lower()
        type_name = str(item.get("type_name", "")).lower()
        if any(p == name or name.endswith(p) for p in _PAGING):
            signals.append(f"paging parameter `{item.get('name')}`")
        if any(h in type_name for h in _BULK_HINTS):
            signals.append(f"collection input `{item.get('name')}`")
    return signals


def classify_performance(model, viability: list[dict] | None = None) -> dict:
    """`performance-candidate` / `functional-only`, or an honest `no-basis`.

    Only transitions already judged `automate` are considered: driving load at
    something that cannot be automated is not a plan.

    **When the model carries no volume facts at all, every row is `no-basis`.**
    That is the ported refusal — inventing an SLA threshold or a traffic estimate
    is exactly what Atlas's stage 05 forbids, and reporting `functional-only`
    everywhere would claim a measurement nobody made.
    """
    automatable = {v["transition_id"] for v in (viability or [])
                   if v["verdict"] == AUTOMATE} if viability is not None else None

    rows, any_signal = [], False
    for tid in model.transition_ids():
        if automatable is not None and tid not in automatable:
            continue
        transition = model.transitions[tid]
        signals = _volume_signals(transition)
        any_signal = any_signal or bool(signals)
        rows.append({
            "transition_id": tid,
            "trigger": (transition.trigger or "").strip(),
            "verdict": PERFORMANCE_CANDIDATE if signals else FUNCTIONAL_ONLY,
            "signals": signals,
        })

    if not any_signal:
        # Report the absence rather than the safe-sounding default.
        for row in rows:
            row["verdict"] = NO_BASIS
            row["signals"] = []

    return {
        "rows": rows,
        "basis": ("volume-relevant inputs recovered from the contract"
                  if any_signal else
                  "none — this model carries no paging or collection inputs, so "
                  "no transition can be shown volume-sensitive. Naming one "
                  "anyway would be an invented SLA (never do that); supply "
                  "traffic evidence to classify properly"),
        "means": ("a candidate is a call whose cost plausibly scales with "
                  "input, not a statement that it is slow — Métis ingests no "
                  "execution result (§8.7)"),
    }


# Coverage depth (Atlas test-designer stage 03's third status).
FULL = "full"
PARTIAL = "partial"
POSITIVE_ONLY = "positive-only"


def classify_depth(model) -> dict:
    """Whether a transition's conditions are covered, or only its happy path.

    **The gap this closes.** `coverage` is binary per transition: a case that
    walks the positive branch makes it covered, and Atlas's stage 03 says
    plainly that a positive scenario is NOT coverage for a prohibited, boundary
    or partition condition unless a test with that condition's own oracle
    exists. Métis had the criteria to tell the difference and nothing that
    asked.

    Computed by comparison, not by a second opinion: `all-transitions` yields
    one target per transition, `guard-coverage` yields one per guard branch, and
    `boundary-coverage` reports which partitions cannot be reached at all. A
    transition whose deeper targets do not all generate is `partial`.

    **This does not change what `coverage` means** (C-11, C-1). It is a second
    question asked of the same model — adequacy, not the ledger.
    """
    from metis_mcp.mbt.path_generation import generate

    def _by_transition(criterion):
        result = generate(model, criterion, 10)
        covered, uncoverable = {}, {}
        for path in result.paths:
            covered.setdefault(path.validated_transition_id, set()).add(
                path.target_key)
        for item in result.uncoverable:
            uncoverable.setdefault(item.validated_transition_id, []).append(
                {"target": item.target_key, "reason": item.reason})
        return covered, uncoverable

    shallow, _ = _by_transition("all-transitions")
    guard, guard_gaps = _by_transition("guard-coverage")
    _, boundary_gaps = _by_transition("boundary-coverage")

    rows = []
    for tid in model.transition_ids():
        transition = model.transitions[tid]
        if tid not in shallow:
            continue                     # not generated at all -- `coverage` says so
        branches = len(guard.get(tid, ()))
        gaps = guard_gaps.get(tid, []) + boundary_gaps.get(tid, [])

        if gaps:
            verdict, why = PARTIAL, (
                f"{len(gaps)} condition(s) cannot be reached, so a case exists "
                f"for the path and not for them")
        elif transition.guard and branches < 2:
            verdict, why = POSITIVE_ONLY, (
                "guarded, and only one branch generates — the complement has no "
                "case of its own, which a positive result does not cover")
        else:
            verdict, why = FULL, (
                f"{branches or 1} branch(es) generate, including the complement"
                if transition.guard else "unguarded — one path is the whole of it")

        rows.append({"transition_id": tid, "verdict": verdict, "why": why,
                     "branches": branches, "unreachable": gaps})

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return {
        "rows": rows,
        "counts": counts,
        "means": ("adequacy, not the ledger: `coverage` answers whether "
                  "behaviour is tested, this answers whether its conditions "
                  "are — and a positive case is not coverage for a prohibited "
                  "or boundary condition"),
    }


def design_report(model) -> dict:
    """Both classifications together, which is how a designer reads them."""
    findings = validate(model)
    unverifiable = {
        getattr(f, "element_id", "") or getattr(f, "element", "")
        for f in findings.unverifiable
    }
    viability = classify_viability(model, unverifiable)
    performance = classify_performance(model, viability)

    counts: dict[str, int] = {}
    for row in viability:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1

    return {
        "model_id": model.id,
        "viability": viability,
        "viability_counts": counts,
        "performance": performance,
        "depth": classify_depth(model),
        "means": ("can it be automated, and is it worth driving under load — "
                  "neither is a coverage figure (C-11)"),
    }
