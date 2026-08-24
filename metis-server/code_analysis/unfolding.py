"""
Unfolding resource existence into explicit states (application spec M-6, M-7).

**Why the extracted models were stars.** `synthesis` gave every transition the
same source, `Ready`, so every model was one hub with terminal spokes. Across the
whole pilot estate that produced **236 paths with zero setup steps** -- and
`Scenario`, whose entire content is the ordered walk, carried nothing. The
hand-authored `login-api`, whose states are genuinely sequential, produces setup
on 13 of its 16 paths. The machinery was never the problem.

**M-6 decides this, and it decides it in favour of unfolding.** A condition
becomes a state when it is *bounded, enumerable, durable and observable through
the surface*. "Does this record exist" is all four: two values, persisted across
requests, and visible as 200 versus 204. The excluded cases are continuous or
unbounded values, per-request conditions like credential validity, and
combinatorial `A OR B` -- resource existence is none of them.

    before   Ready --[GET /metric/{id}]--> Ok200          when NOT (t.isEmpty())
             Ready --[GET /metric/{id}]--> NoContent204   when t.isEmpty()
             Ready --[POST /metric]-----> Created201

    after    Ready         --[POST /metric]-----> MetricPresent      (201)
             MetricPresent --[GET /metric/{id}]--> Ok200             (200)
             Ready         --[GET /metric/{id}]--> NoContent204      (204)

The 200 read now costs a setup step, which is the truth: you cannot read a metric
you have not created. The 204 read keeps `Ready` as its source, which is also the
truth -- "nothing exists yet" *is* the initial state, and inventing an `Absent`
state to sit beside it would add a node that means the same thing.

**Three rules, each guarding against a specific mistake.**

1. **The resource is keyed on the path, never the guard's variable name.** The
   guard is `t.isEmpty()` at 42 different endpoints, because it comes from one
   shared helper in `records-common`. Keying on `t` would fuse every resource in
   the estate into one.
2. **M-7: the unfolded condition is removed from the residual guard**, and every
   other condition is preserved verbatim.
3. **Fail-closed (§5.8, T-9d).** Where no creator can be found, nothing is
   unfolded and the transition is flagged `source_state_unresolved` rather than
   being given a source state that was guessed. A wrong precondition is worse
   than an admitted gap, because it looks executable.

**The creator link is an inference and is treated as one.** `POST /x` returning
2xx is taken to create what `GET /x/{id}` reads. On this estate that is backed by
real evidence -- `ResponseEntityUtils.created()` returns a `Location` header
pointing at the new id, and the service's own integration tests chain exactly
that way -- but it is a REST convention, not a proof. So it is reported, and
lands at Quarantine like everything else.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from metis_mcp.mbt.model import QUARANTINE, State, Transition

# A path parameter: `/metric/{id}` -> the segment before `{id}` is the resource.
_PATH_PARAM = re.compile(r"/\{[^}]+\}")
# Presence predicates. These are the recoverable form of "does this record
# exist"; anything else is left alone rather than guessed at.
_PRESENCE = re.compile(r"^(?:NOT\s*\()?\s*([A-Za-z_][\w.]*)\.(isEmpty|isPresent)\(\)\s*\)?$")
_NEGATED = re.compile(r"^NOT\s*\(")

CREATING_VERBS = ("POST", "PUT")


def resource_of(path: str) -> str:
    """`/metric/{id}` -> `/metric`; `/metric` -> `/metric`.

    The key a reader and its creator have to agree on. Everything from the first
    path parameter onwards is dropped, because that is the instance, not the
    resource.
    """
    if not path:
        return ""
    m = _PATH_PARAM.search(path)
    trimmed = path[:m.start()] if m else path
    return trimmed.rstrip("/") or "/"


def _atoms(guard: str) -> list[str]:
    return [a.strip() for a in re.split(r"\s+AND\s+", guard or "", flags=re.I) if a.strip()]


def presence_sense(guard: str) -> tuple[str, bool] | None:
    """`(atom, resource_is_present)` for the presence atom in a guard, if any.

    `t.isEmpty()` means absent; `NOT (t.isEmpty())` and `x.isPresent()` mean
    present. Returns None when the guard says nothing about existence -- which is
    the common case and must not be forced into one.
    """
    for atom in _atoms(guard):
        m = _PRESENCE.match(atom)
        if not m:
            continue
        negated = bool(_NEGATED.match(atom))
        empty_style = m.group(2) == "isEmpty"
        # isEmpty  -> absent ; NOT(isEmpty) -> present
        # isPresent-> present; NOT(isPresent) -> absent
        present = (not empty_style) if not negated else empty_style
        return atom, present
    return None


def residual_guard(guard: str, remove: str) -> str:
    """M-7: drop the unfolded atom, keep every other condition verbatim."""
    kept = [a for a in _atoms(guard) if a != remove]
    return " AND ".join(kept)


def resource_label(resource: str) -> str:
    """`/metric` -> `Metric`; `/tms/execution` -> `TmsExecution`.

    **Every segment, not just the last.** The pilot estate has `/project/all`,
    `/user/all`, `/version/all` and `/environment/all` in one service: keyed on
    the last segment all four become `All`, and fusing four distinct resources
    into one node asserts that a call to `/user/all` starts from the same
    situation as a call to `/project/all`. That is the same star this
    module exists to remove, in miniature, and it is also wrong.

    The collision was latent in `state_name_for` from the start and never bit,
    because a `*Present` state is only created for a resource that has both a
    creator and a presence-guarded reader — which none of the `/all` routes do.
    It bites immediately once every resource gets a node.
    """
    parts = [w for p in resource.split("/") if p
             for w in re.split(r"[-_]", p) if w]
    return "".join(w[:1].upper() + w[1:] for w in parts) or "Resource"


def resource_noun(resource: str) -> str:
    """`/metric` -> `metric`; `/tms/execution` -> `tms execution`.

    The prose form of `resource_label`, for a sentence rather than a node id.
    Every segment again, and for the same reason: "no execution exists" is
    ambiguous in a service with two execution resources.
    """
    parts = [w for p in resource.split("/") if p
             for w in re.split(r"[-_]", p) if w]
    return " ".join(w.lower() for w in parts)


def state_name_for(resource: str) -> str:
    """`/metric` -> `MetricPresent`; `/tms/execution` -> `TmsExecutionPresent`."""
    return f"{resource_label(resource)}Present"


@dataclass
class UnfoldResult:
    states: dict = field(default_factory=dict)
    transitions: dict = field(default_factory=dict)
    unfolded: list[str] = field(default_factory=list)
    unresolved: list[tuple[str, str]] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> int:
        return len(self.unfolded)


def unfold(states: dict, transitions: dict, surface: str = "api") -> UnfoldResult:
    """Apply M-6 to resource-existence guards. Pure; returns new dicts."""
    result = UnfoldResult(states=dict(states), transitions=dict(transitions))

    # Creators, by resource. A 2xx POST/PUT on the resource path is what puts the
    # system into the "it exists" state.
    creators: dict[str, list[str]] = {}
    for tid, t in transitions.items():
        parts = (t.trigger or "").split(None, 1)
        if len(parts) != 2 or parts[0].upper() not in CREATING_VERBS:
            continue
        status = t.outcome_status or 0
        if not (200 <= status < 300):
            continue
        creators.setdefault(resource_of(parts[1]), []).append(tid)

    # Readers whose guard asserts the resource is ABSENT. Collected here and
    # resolved below, because whether the atom is redundant depends on something
    # not yet known at this point: whether this resource unfolded at all.
    absent_readers: list[tuple[str, str]] = []

    # Readers whose guard asserts the resource is present.
    for tid, t in sorted(transitions.items()):
        sense = presence_sense(t.guard)
        if sense is None:
            continue
        atom, present = sense
        if not present:
            # "It does not exist" is the initial situation, and the resource's
            # own initial state already says so -- so the atom is redundant
            # there, not merely tolerable. Recorded now and stripped after the
            # loop, once it is known whether the resource actually unfolded.
            absent_readers.append((tid, atom))
            continue

        parts = (t.trigger or "").split(None, 1)
        resource = resource_of(parts[1]) if len(parts) == 2 else ""
        owning = creators.get(resource, [])
        if not resource or not owning:
            # §5.8 / T-9d. No creator was recovered, so the precondition cannot
            # be expressed as a reachable state. Flag it; do not invent one.
            result.transitions[tid] = replace(t, source_state_unresolved=True)
            result.unresolved.append(
                (tid, f"guard {atom!r} requires {resource or 'a resource'} to exist, "
                      f"and no creating transition was recovered for it"))
            continue

        target_state = state_name_for(resource)
        if target_state not in result.states:
            result.states[target_state] = State(
                id=target_state, name=target_state, surface=surface,
                lifecycle_state=QUARANTINE)

        # The reader now starts from the state its guard was describing, and M-7
        # removes that condition from the guard.
        result.transitions[tid] = replace(
            t, source=target_state, guard=residual_guard(t.guard, atom))
        result.unfolded.append(tid)

        # The creator lands there rather than in a status-named state. Its status
        # is not lost -- it lives on `outcome_status`.
        for cid in owning:
            creator = result.transitions[cid]
            if creator.target != target_state:
                result.transitions[cid] = replace(creator, target=target_state)
                result.findings.append(
                    f"{creator.trigger} now results in {target_state} "
                    f"(status {creator.outcome_status} retained on the transition) — "
                    f"inferred from the REST convention that a 2xx {parts[0]} on "
                    f"{resource} creates what {t.trigger} reads")

    _drop_redundant_absence(result, absent_readers)
    _drop_orphan_states(result)
    return result


def _drop_redundant_absence(result: UnfoldResult,
                            absent_readers: list[tuple[str, str]]) -> None:
    """M-7, applied to the other side of the fold.

    The present case already loses its atom: `GET /metric/{id}` reads from
    `MetricPresent`, so `NOT (t.isEmpty())` would restate the state it starts
    from. The absent case kept its `t.isEmpty()` and restated the state it
    starts from just as much -- the same condition said twice, once as a node
    and once in the implementation's own words.

    **Two conditions, and both are necessary.** The resource must have unfolded
    -- a `*Present` state existing is the proof that this model distinguishes
    present from absent here -- AND the transition must start from that
    resource's *own* state, so that the node it leaves is the exact complement
    of the atom being dropped.

    The second condition is what makes this safe on a model that has not adopted
    per-resource starting states. A transition leaving a shared `Ready` keeps its
    atom, because `Ready` means only "nothing has been called yet" and the atom
    is then the one thing saying the record is missing. Dropping it there would
    delete a real precondition rather than a duplicate.
    """
    unfolded = {sid for sid in result.states if sid.endswith("Present")}
    for tid, atom in absent_readers:
        transition = result.transitions.get(tid)
        if transition is None:
            continue
        parts = (transition.trigger or "").split(None, 1)
        if len(parts) != 2:
            continue
        resource = resource_of(parts[1])
        if state_name_for(resource) not in unfolded:
            continue
        if transition.source != resource_label(resource):
            continue
        result.transitions[tid] = replace(
            transition, guard=residual_guard(transition.guard, atom))

        # The atom moved into the state, so the state must say what it means.
        # `Given Metric` names the cluster and states nothing; `Given Metric (no
        # metric exists)` is the precondition a tester actually establishes.
        # `State.condition` already exists for exactly this on the Web surface.
        start = result.states.get(transition.source)
        if start is not None and not start.condition:
            result.states[transition.source] = replace(
                start, condition=f"no {resource_noun(resource)} exists")


def _drop_orphan_states(result: UnfoldResult) -> None:
    """Remove states nothing points at any more.

    Retargeting a creator can leave its old status state with no transitions at
    all. Leaving it would report an unreachable state on every validation run --
    a finding about this pass rather than about the system.
    """
    used = {t.source for t in result.transitions.values()}
    used |= {t.target for t in result.transitions.values()}
    for sid in list(result.states):
        if sid not in used and not result.states[sid].is_initial:
            del result.states[sid]
