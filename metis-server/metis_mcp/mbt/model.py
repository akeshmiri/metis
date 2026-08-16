"""
Pure model types for the MBT engine (application spec §2, §6).

Deliberately database-free. The engine operates on these dataclasses, never on a
Neo4j session, for the same reason `requirement_landing.py` splits its planner
from its writer: the interesting logic becomes provable without a container.

A `Model` here is one `<journey>-<surface>` machine (spec M-1) -- a
user-perspective state machine, not a data-lifecycle one (M-3). Nothing in this
module knows which source produced the model; that is spec F-29, and it is why
the same engine serves hand-authored, AC-mined and code-extracted models alike.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Transition.implementation_status values. `planned` behaviour is excluded from
# coverage because it is not a gap -- it does not exist yet (spec P-11).
IMPLEMENTED = "implemented"
PLANNED = "planned"

# lifecycle_state values (spec §8.6). Generation reads ONLY `Approved` elements
# (spec D-10); everything else is excluded with its own distinct reason, because
# "not yet reviewed" and "sources disagree" are different facts.
#
# The default is QUARANTINE, not APPROVED: every model source produces candidates
# (spec S-4), and a default of "approved" would mean a carelessly-constructed
# element silently earns authority it was never granted.
QUARANTINE = "Quarantine"
APPROVED = "Approved"
DISPUTED = "Disputed"
REJECTED = "Rejected"
DEPRECATED = "Deprecated"


@dataclass(frozen=True)
class State:
    """One observable situation on one surface (spec M-3).

    `is_initial` marks a state a tester can establish from nothing. Paths start
    only at initial states (spec P-8) -- a test whose precondition cannot be
    established is not executable.
    """

    id: str
    name: str
    surface: str = "api"
    is_initial: bool = False
    lifecycle_state: str = QUARANTINE


@dataclass(frozen=True)
class Transition:
    """One interaction: trigger, guard, source and target state.

    `trigger` and `guard` are properties, never separate entities (spec M-11).
    `guard` is preserved verbatim as recovered and is a *test data requirement*,
    not a solved value (spec M-8, M-9) -- this module never attempts to satisfy it.
    """

    id: str
    source: str
    trigger: str
    target: str
    guard: str = ""
    implementation_status: str = IMPLEMENTED
    lifecycle_state: str = QUARANTINE

    @property
    def is_generatable(self) -> bool:
        """Whether this transition may take part in generation at all.

        Spec D-10: generation reads only `Approved` elements. Everything else is
        excluded, and `exclusion_reason` says which of several distinct reasons
        applies -- "not yet reviewed", "sources disagree" and "not built yet" are
        different facts and must never be collapsed into one number (spec P-12).
        """
        return (
            self.implementation_status == IMPLEMENTED
            and self.lifecycle_state == APPROVED
        )

    @property
    def exclusion_reason(self) -> str | None:
        if self.implementation_status == PLANNED:
            return "excluded_planned"
        if self.lifecycle_state == DISPUTED:
            return "excluded_disputed"
        if self.lifecycle_state == REJECTED:
            return "excluded_rejected"
        if self.lifecycle_state != APPROVED:
            return "excluded_unapproved"
        return None


@dataclass
class Model:
    """One `<journey>-<surface>` state machine.

    Indexes are built once at construction. Every accessor returns results in a
    deterministic order -- spec P-7 requires byte-identical generation across
    runs, and unordered iteration is the usual way that guarantee is lost.
    """

    id: str
    states: dict[str, State] = field(default_factory=dict)
    transitions: dict[str, Transition] = field(default_factory=dict)

    _outgoing: dict[str, list[str]] = field(default_factory=dict, repr=False)
    _incoming: dict[str, list[str]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.reindex()

    def reindex(self) -> None:
        self._outgoing = {sid: [] for sid in self.states}
        self._incoming = {sid: [] for sid in self.states}
        for tid in sorted(self.transitions):
            t = self.transitions[tid]
            # A transition referencing an unknown state is a model defect, not
            # something to silently tolerate: it would silently shrink coverage.
            if t.source not in self.states:
                raise ValueError(f"{t.id}: source state {t.source!r} not in model {self.id}")
            if t.target not in self.states:
                raise ValueError(f"{t.id}: target state {t.target!r} not in model {self.id}")
            self._outgoing[t.source].append(tid)
            self._incoming[t.target].append(tid)

    # -- ordered accessors ------------------------------------------------

    def state_ids(self) -> list[str]:
        return sorted(self.states)

    def transition_ids(self) -> list[str]:
        return sorted(self.transitions)

    def outgoing(self, state_id: str, generatable_only: bool = True) -> list[Transition]:
        out = [self.transitions[tid] for tid in self._outgoing.get(state_id, [])]
        if generatable_only:
            out = [t for t in out if t.is_generatable]
        return out

    def incoming(self, state_id: str, generatable_only: bool = True) -> list[Transition]:
        inc = [self.transitions[tid] for tid in self._incoming.get(state_id, [])]
        if generatable_only:
            inc = [t for t in inc if t.is_generatable]
        return inc

    def initial_state_ids(self) -> list[str]:
        return sorted(sid for sid, s in self.states.items() if s.is_initial)

    def generatable_transitions(self) -> list[Transition]:
        return [self.transitions[tid] for tid in self.transition_ids()
                if self.transitions[tid].is_generatable]

    def excluded_transitions(self) -> list[Transition]:
        return [self.transitions[tid] for tid in self.transition_ids()
                if not self.transitions[tid].is_generatable]

    # -- approval (spec G1, D-10) ----------------------------------------

    def unapproved_elements(self) -> list[tuple[str, str, str]]:
        """Every element not yet `Approved`, as (kind, id, lifecycle_state).

        Reported rather than counted: G1 blocks generation on an unapproved
        model, and a reviewer needs to know *which* elements to look at.
        """
        out = []
        for sid in self.state_ids():
            state = self.states[sid]
            if state.lifecycle_state != APPROVED:
                out.append(("state", sid, state.lifecycle_state))
        for tid in self.transition_ids():
            transition = self.transitions[tid]
            if transition.implementation_status == PLANNED:
                continue  # not a gap; it does not exist yet (spec P-11)
            if transition.lifecycle_state != APPROVED:
                out.append(("transition", tid, transition.lifecycle_state))
        return out

    @property
    def is_approved(self) -> bool:
        return not self.unapproved_elements()
