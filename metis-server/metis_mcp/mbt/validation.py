"""
Model well-formedness (application spec §2.6, M-17, M-18; A-1..A-4).

Stage 3 of §3.2, and the one stage that **blocks on any failure**. Everything
downstream -- path generation, rendering, publication -- rests on the assumption
that this ran and passed. Until now it did not run at all in this chain: approval
was gated (G1) but well-formedness was not, so a model could be approved and
still be non-deterministic, and paths would generate from it regardless.

Four properties, from §2.6's own table:

    determinism          ambiguous -- one interaction matches two transitions
    guard completeness   an interaction matches NO transition; silent, no error
    reachability         a dead state, or a missing transition
    AC coverage          behaviour nothing validates is an unverified claim

**M-17 -- fail-closed.** A guard this checker cannot parse is reported
`unverifiable`, never assumed correct. That is a third outcome, not a pass: it
blocks by default, and an operator who accepts the risk does so through an
explicit flag that is recorded, never by the checker quietly deciding for them.
The precedent is N-11's self-approval override -- visible, not silent.

The interval arithmetic is **harvested, not rewritten**: `behavior_model.py`'s
`guards_conflict` and `_guard_coverage_gap` are pure functions over strings, and
§20.2 lists that module as reuse-as-is for exactly this reason. Reimplementing
them here would produce two subtly different notions of "overlap", which is how a
model passes one checker and fails the other.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from metis_mcp.behavior_model import _guard_coverage_gap, guards_conflict
from metis_mcp.mbt.model import IMPLEMENTED, Model

# Checks (spec §2.6).
DETERMINISM = "determinism"
GUARD_COMPLETENESS = "guard_completeness"
REACHABILITY = "reachability"
OBSERVABILITY = "observability"
AC_COVERAGE = "ac_coverage"

# Severities. `UNVERIFIABLE` is deliberately not a synonym for either of the
# others: "this is wrong" and "this cannot be shown to be right" are different
# facts, and collapsing them is what lets an unparseable guard read as a pass.
BLOCKING = "blocking"
UNVERIFIABLE = "unverifiable"
ADVISORY = "advisory"


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str
    element_ids: tuple[str, ...]
    detail: str
    remedy: str = ""

    def describe(self) -> str:
        ids = ", ".join(self.element_ids)
        line = f"[{self.severity:<12}] {self.check:<18} {ids}: {self.detail}"
        return f"{line}\n{' ' * 15}-> {self.remedy}" if self.remedy else line


@dataclass
class ValidationResult:
    model_id: str
    findings: list[Finding] = field(default_factory=list)
    checked: int = 0

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == BLOCKING]

    @property
    def unverifiable(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == UNVERIFIABLE]

    @property
    def advisory(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ADVISORY]

    def is_valid(self, allow_unverifiable: bool = False) -> bool:
        """Spec M-18. `allow_unverifiable` is the operator's explicit risk
        acceptance, not a default -- see this module's docstring."""
        if self.blocking:
            return False
        return allow_unverifiable or not self.unverifiable


def _implemented(model: Model):
    """Only `implemented` behaviour is validated.

    `planned` transitions are excluded because they do not exist yet (P-11):
    checking determinism against behaviour nobody has built would block
    generation on a conflict that cannot occur. Lifecycle is deliberately NOT
    filtered on -- validation is stage 3 and approval is G1, between stages 4
    and 5, so validating only approved elements would run the check after the
    decision it exists to inform.
    """
    return [t for t in model.transitions.values()
            if t.implementation_status == IMPLEMENTED]


def effective_guard(transition, inherited: dict[str, str] | None = None) -> str:
    """A transition's own guard, conjoined with any guard it INHERITS (spec M-5c).

    A UI transition that invokes an API transition carries **no copy** of that
    API guard -- M-5c makes it a reference, so the two cannot drift. The
    consequence for validation is that a UI model read in isolation looks
    ambiguous exactly where it is in fact determined by the API side: two
    transitions on one trigger, both apparently unguarded, whose real guards are
    `t.isEmpty()` and `NOT (t.isEmpty())` on the other surface.

    Passing `inherited` resolves that. Omitting it is not wrong -- it is a
    narrower question ("is this model well-formed on its own?") -- but the answer
    must not be mistaken for the wider one, which is why the finding says so.
    """
    local = (transition.guard or "").strip()
    borrowed = ((inherited or {}).get(transition.id) or "").strip()
    if local and borrowed:
        return f"{local} AND {borrowed}"
    return local or borrowed


def _groups(model: Model) -> dict[tuple[str, str], list]:
    """The `(state, trigger)` groups I-18 treats as the unit of revalidation."""
    groups: dict[tuple[str, str], list] = {}
    for t in sorted(_implemented(model), key=lambda x: x.id):
        groups.setdefault((t.source, t.trigger), []).append(t)
    return groups


# --------------------------------------------------------------------------
# Determinism (spec §2.6, A-1)
# --------------------------------------------------------------------------

def check_determinism(model: Model,
                      inherited: dict[str, str] | None = None) -> list[Finding]:
    """One interaction must not match two transitions.

    An unguarded transition is handled explicitly rather than handed to
    `guards_conflict`: an empty guard means *always*, which overlaps everything.
    Passing "" through the threshold parser would report it `unverifiable` --
    true but useless, when the conflict is certain and nameable.
    """
    findings = []
    for (state, trigger), members in _groups(model).items():
        if len(members) < 2:
            continue
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                ga, gb = effective_guard(a, inherited), effective_guard(b, inherited)
                if not ga or not gb:
                    unguarded = a.id if not ga else b.id
                    findings.append(Finding(
                        check=DETERMINISM, severity=BLOCKING,
                        element_ids=(a.id, b.id),
                        detail=(f"({state}, {trigger}): {unguarded} is unguarded, so it "
                                f"always matches — it is ambiguous with every sibling"
                                + ("" if inherited is not None else
                                   ". No INVOKES guards were supplied, so a guard "
                                   "inherited from another surface would not be seen "
                                   "(M-5c)")),
                        remedy="give it a guard, or merge the siblings into one transition",
                    ))
                    continue
                conflicts, reason = guards_conflict(ga, gb)
                if not conflicts:
                    continue
                # `guards_conflict` returns (conflicts, reason); certainty is
                # carried in the reason's wording. Sniffing one phrase missed the
                # identical-guard case entirely -- 62 pairs that are CERTAINLY
                # ambiguous were filed as merely unverifiable. Both certainty
                # markers are matched now.
                verifiable = ("overlapping satisfying ranges" in reason
                              or "SAME condition" in reason)
                findings.append(Finding(
                    check=DETERMINISM,
                    severity=BLOCKING if verifiable else UNVERIFIABLE,
                    element_ids=(a.id, b.id),
                    detail=f"({state}, {trigger}): {reason}",
                    remedy=("make the guards mutually exclusive" if verifiable else
                            "restate the guards as simple threshold comparisons, or "
                            "confirm exclusivity by review — this is not assumed (M-17)"),
                ))
    return findings


# --------------------------------------------------------------------------
# Guard completeness (spec §2.6, A-2)
# --------------------------------------------------------------------------

def check_guard_completeness(model: Model,
                             inherited: dict[str, str] | None = None) -> list[Finding]:
    """The guards on a `(state, trigger)` group must jointly cover the domain.

    Groups of one are skipped: a lone guard has nothing to be jointly exhaustive
    *with*, and "does this state handle this trigger at all" is a different
    question -- one this checker deliberately does not answer, because the strict
    reading ("every state must handle every trigger used anywhere") produces
    overwhelmingly more expected non-applicability than real findings.

    A group containing an unguarded transition is complete by construction: that
    transition fires for every input. It is still ambiguous, and `check_determinism`
    reports it there rather than here.
    """
    findings = []
    for (state, trigger), members in _groups(model).items():
        if len(members) < 2:
            continue
        guards = [effective_guard(t, inherited) for t in members]
        if any(not g.strip() for g in guards):
            continue
        reason = _guard_coverage_gap(guards)
        if reason is None:
            continue
        verifiable = "gap in guard coverage" in reason or "no guard covers" in reason
        findings.append(Finding(
            check=GUARD_COMPLETENESS,
            severity=BLOCKING if verifiable else UNVERIFIABLE,
            element_ids=tuple(t.id for t in members),
            detail=f"({state}, {trigger}): {reason}",
            remedy=("add a transition for the uncovered range, or widen an existing "
                    "guard" if verifiable else
                    "restate the guards as simple threshold comparisons, or confirm "
                    "joint coverage by review — this is not assumed (M-17)"),
        ))
    return findings


# --------------------------------------------------------------------------
# Reachability (spec §2.6)
# --------------------------------------------------------------------------

def check_reachability(model: Model) -> list[Finding]:
    """Every state must be reachable from an initial state.

    A terminal state is reported `advisory`, not blocking: a machine legitimately
    ends somewhere, and the login model's own `AccountLocked` would be terminal
    were it not for the admin-unlock edge. An *unreachable* state is blocking --
    it is either dead, or a transition is missing (§2.6).
    """
    initial = model.initial_state_ids()
    if not initial:
        return [Finding(
            check=REACHABILITY, severity=BLOCKING, element_ids=(model.id,),
            detail="no initial state — a tester cannot establish any precondition",
            remedy="mark the state a user starts from as initial (P-8)",
        )]

    outgoing: dict[str, list] = {}
    for t in _implemented(model):
        outgoing.setdefault(t.source, []).append(t)

    seen, frontier = set(initial), list(initial)
    while frontier:
        current = frontier.pop()
        for t in outgoing.get(current, []):
            if t.target not in seen:
                seen.add(t.target)
                frontier.append(t.target)

    findings = []
    for sid in model.state_ids():
        if sid not in seen:
            findings.append(Finding(
                check=REACHABILITY, severity=BLOCKING, element_ids=(sid,),
                detail=f"unreachable from {'/'.join(sorted(initial))} — a dead state, "
                       f"or a transition into it is missing",
                remedy="add the transition that reaches it, or remove the state",
            ))
        elif sid not in outgoing:
            findings.append(Finding(
                check=REACHABILITY, severity=ADVISORY, element_ids=(sid,),
                detail="terminal — no implemented transition leaves it",
                remedy="confirm the machine is meant to end here",
            ))
    return findings


# --------------------------------------------------------------------------
# Observability (spec M-3, A-4)
# --------------------------------------------------------------------------

def check_observability(model: Model) -> list[Finding]:
    """A state must be distinguishable through its own surface (M-3).

    What is mechanically checkable is the contrapositive: two states on one
    surface that present identically are not two observable situations. Whether a
    *single* state is genuinely observable is a modelling judgement no checker can
    make, and this does not pretend otherwise -- stated so the check is not read
    as more than it is.
    """
    findings = []
    by_signature: dict[tuple[str, str], list[str]] = {}
    for sid in model.state_ids():
        state = model.states[sid]
        by_signature.setdefault((state.surface, state.name.strip().lower()), []).append(sid)

    for (surface, name), ids in sorted(by_signature.items()):
        if not name:
            findings.append(Finding(
                check=OBSERVABILITY, severity=BLOCKING, element_ids=tuple(ids),
                detail="no name — a placeholder never persists (X-10)",
                remedy="resolve the name through the X-7 cascade, or by review",
            ))
        elif len(ids) > 1:
            findings.append(Finding(
                check=OBSERVABILITY, severity=BLOCKING, element_ids=tuple(sorted(ids)),
                detail=f"{len(ids)} states present identically on surface {surface!r} "
                       f"as {name!r} — they are not distinguishable through it (M-3)",
                remedy="merge them, or give each its own observable signature",
            ))
    return findings


# --------------------------------------------------------------------------
# AC coverage (spec §2.6's fourth property)
# --------------------------------------------------------------------------

def check_ac_coverage(model: Model, validated_transition_ids: set[str] | None = None
                      ) -> list[Finding]:
    """Behaviour nothing validates is an unverified claim.

    **Advisory, not blocking**, and the distinction is deliberate. The other three
    checks are properties of the model alone; this one depends on reconciliation,
    which is stage 4 and runs *after* validation (§3.2). Blocking here would make
    stage 3 depend on stage 4's output and deadlock the pipeline. F-4 already
    reports this gap as a first-class finding where it belongs.
    """
    validated = validated_transition_ids or set()
    findings = []
    for t in sorted(_implemented(model), key=lambda x: x.id):
        if t.id not in validated:
            findings.append(Finding(
                check=AC_COVERAGE, severity=ADVISORY, element_ids=(t.id,),
                detail=f"{t.source} --[{t.trigger}]--> {t.target}: no confirmed "
                       f"acceptance criterion validates it",
                remedy="reconcile against acceptance criteria (§3.3)",
            ))
    return findings


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------

def validate(model: Model, validated_transition_ids: set[str] | None = None,
             include_ac_coverage: bool = False,
             inherited: dict[str, str] | None = None) -> ValidationResult:
    """Run §2.6's checks. Ordering is fixed so output is comparable between runs.

    `inherited` maps a transition id to a guard it borrows across an `INVOKES`
    link (M-5c). Build it with `cross_surface.inherited_guards`.
    """
    result = ValidationResult(model_id=model.id, checked=len(_implemented(model)))
    result.findings.extend(check_observability(model))
    result.findings.extend(check_determinism(model, inherited))
    result.findings.extend(check_guard_completeness(model, inherited))
    result.findings.extend(check_reachability(model))
    if include_ac_coverage:
        result.findings.extend(check_ac_coverage(model, validated_transition_ids))
    return result


class ValidationFailed(Exception):
    """Raised when generation is attempted on a model that is not well-formed (M-18)."""


def require_valid(model: Model, allow_unverifiable: bool = False,
                  inherited: dict[str, str] | None = None) -> ValidationResult:
    """Spec M-18: validation failure **blocks** generation, with the finding shown.

    Shows the findings rather than a count, for the same reason `_require_approved`
    does: nobody can act on "3 problems".
    """
    result = validate(model, inherited=inherited)
    if result.is_valid(allow_unverifiable):
        return result

    lines = [f"{model.id} is not well-formed — generation blocked (M-18).", ""]
    for finding in result.blocking:
        lines.append(f"  {finding.describe()}")
    if result.unverifiable and not allow_unverifiable:
        lines += ["", "  Unverifiable — reported, never assumed correct (M-17):"]
        for finding in result.unverifiable:
            lines.append(f"  {finding.describe()}")
        lines += ["",
                  "  To proceed accepting that risk, pass --allow-unverifiable.",
                  "  It is recorded, not silent."]
    raise ValidationFailed("\n".join(lines))


def format_validation(result: ValidationResult, allow_unverifiable: bool = False) -> str:
    verdict = "WELL-FORMED" if result.is_valid(allow_unverifiable) else "BLOCKED"
    lines = [
        f"Validation — {result.model_id}",
        f"  verdict:       {verdict}",
        f"  transitions:   {result.checked} implemented",
        f"  blocking:      {len(result.blocking)}",
        f"  unverifiable:  {len(result.unverifiable)}   (reported, never assumed — M-17)",
        f"  advisory:      {len(result.advisory)}",
    ]
    for group, title in ((result.blocking, "BLOCKING"),
                         (result.unverifiable, "UNVERIFIABLE"),
                         (result.advisory, "ADVISORY")):
        if not group:
            continue
        lines += ["", f"  {title}"]
        lines += [f"    {f.describe()}" for f in group[:12]]
        if len(group) > 12:
            lines.append(f"    ... and {len(group) - 12} more")
    return "\n".join(lines)
