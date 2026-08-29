"""
Matching and delta (application spec I-5, I-11, I-14, I-17, I-18; R12, R13).

Two requirements, one mechanism:

    R12  many sources, one model  -- never duplicate an element that exists
    R13  code changes produce incremental changes, never a reset and rebuild

Both need identity that is stable across *sources* and across *runs*. Given that,
deduplication and incrementality are the same lookup.

Matching is four steps (I-5), not a hash comparison:

    1. find existing elements with the same natural key
    2. exactly one match   -> same element; a guard difference is MODIFIED
    3. several matches     -> disambiguate by normalised-guard similarity
    4. no match            -> ADDED

and the counterpart, REMOVED, for keys the candidate no longer has.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher

from metis_mcp.identity.keys import (
    keyed_states,
    keyed_transitions,
    normalise_guard,
    state_key,
    transition_key,
)
from metis_mcp.rendering.contract import asserted_fields
from metis_mcp.mbt.model import APPROVED, QUARANTINE, Model, State, Transition

ADDED = "ADDED"
MODIFIED = "MODIFIED"
REMOVED = "REMOVED"
UNCHANGED = "UNCHANGED"

# Above this, a REMOVED/ADDED pair is *proposed* as a rename (I-21). Never
# applied automatically -- an unconfirmed pair stays REMOVED + ADDED (I-22).
RENAME_SIMILARITY = 0.6


@dataclass
class Change:
    kind: str                    # element kind: "state" | "transition"
    delta: str                   # ADDED | MODIFIED | REMOVED | UNCHANGED
    key: str
    element_id: str
    detail: str = ""
    invalidates_approval: bool = False


@dataclass
class RenameProposal:
    kind: str
    removed_key: str
    added_key: str
    removed_id: str
    added_id: str
    similarity: float


@dataclass
class Delta:
    changes: list[Change] = field(default_factory=list)
    renames: list[RenameProposal] = field(default_factory=list)

    def of(self, delta: str) -> list[Change]:
        return [c for c in self.changes if c.delta == delta]

    @property
    def summary(self) -> dict[str, int]:
        return {d: len(self.of(d)) for d in (ADDED, MODIFIED, REMOVED, UNCHANGED)}

    @property
    def has_behaviour_change(self) -> bool:
        return any(c.invalidates_approval for c in self.changes)


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _transition_detail(previous: Transition, candidate: Transition) -> tuple[str, bool]:
    """What differs, and whether it invalidates approval (spec I-17)."""
    before, after = normalise_guard(previous.guard), normalise_guard(candidate.guard)
    if before != after:
        # Behaviour changed: approval is revoked for this transition.
        return f"guard changed: {before!r} -> {after!r}", True
    if previous.implementation_status != candidate.implementation_status:
        return (f"implementation_status: {previous.implementation_status} -> "
                f"{candidate.implementation_status}"), True

    # **What a generated test asserts is evidence** (E-8/N-14). This checked the
    # guard and the implementation status and nothing else, so a re-extraction
    # changing `outcome_status` 201 -> 200, or a response body from `RecordDto`
    # to `Void`, revoked nothing — and the approval recorded against the old
    # response was carried onto a transition that now asserts a different one.
    #
    # Driven from `rendering.contract` rather than a second hand-list, so the
    # question "which facts are evidence" has one answer.
    for field in asserted_fields("Transition"):
        if field in ("guard", "implementation_status"):
            continue                      # reported above, with better wording
        before_value = getattr(previous, field, None)
        after_value = getattr(candidate, field, None)
        if before_value != after_value:
            return f"{field} changed: {before_value!r} -> {after_value!r}", True
    return "", False


def diff(previous: Model, candidate: Model) -> Delta:
    """Compare a stored model against freshly-extracted candidates.

    Never resets. Elements the candidate no longer proposes are REMOVED from the
    *new version*; nothing is deleted (spec I-12).
    """
    delta = Delta()

    prev_states, cand_states = keyed_states(previous), keyed_states(candidate)
    for key in sorted(set(prev_states) | set(cand_states)):
        p, c = prev_states.get(key), cand_states.get(key)
        if p and c:
            # Name is not identity, so a rename is MODIFIED, not a new element,
            # and it does not invalidate approval (I-17: presentation, not behaviour).
            if p.name != c.name:
                delta.changes.append(Change("state", MODIFIED, key, c.id,
                                            f"name: {p.name!r} -> {c.name!r}", False))
            else:
                delta.changes.append(Change("state", UNCHANGED, key, c.id))
        elif c:
            delta.changes.append(Change("state", ADDED, key, c.id))
        else:
            delta.changes.append(Change("state", REMOVED, key, p.id))

    prev_trans, cand_trans = keyed_transitions(previous), keyed_transitions(candidate)
    for key in sorted(set(prev_trans) | set(cand_trans)):
        p_list, c_list = prev_trans.get(key, []), cand_trans.get(key, [])

        if p_list and c_list:
            # Step 3: several sharing a key are disambiguated by guard similarity,
            # best match first, so a guard edit pairs with its own predecessor.
            unmatched = list(c_list)
            for p in p_list:
                if not unmatched:
                    delta.changes.append(Change("transition", REMOVED, key, p.id,
                                                "no counterpart in this key group"))
                    continue
                best = max(unmatched, key=lambda c: _similar(
                    normalise_guard(p.guard), normalise_guard(c.guard)))
                unmatched.remove(best)
                detail, invalidates = _transition_detail(p, best)
                delta.changes.append(Change(
                    "transition", MODIFIED if detail else UNCHANGED, key, best.id,
                    detail, invalidates))
            for leftover in unmatched:
                delta.changes.append(Change("transition", ADDED, key, leftover.id))
        elif c_list:
            for c in c_list:
                delta.changes.append(Change("transition", ADDED, key, c.id))
        else:
            for p in p_list:
                delta.changes.append(Change("transition", REMOVED, key, p.id))

    _propose_renames(delta)
    return delta


def _propose_renames(delta: Delta) -> None:
    """Pair a REMOVED with a similar ADDED and propose it (spec I-20, I-21).

    The natural-key weak point: a state whose observable signature changes gets a
    new key, so it looks like removal plus addition and would lose its name,
    matches and approval. Proposed, never assumed -- an unconfirmed pair stays
    REMOVED + ADDED (I-22).
    """
    removed = [c for c in delta.changes if c.delta == REMOVED]
    added = [c for c in delta.changes if c.delta == ADDED]
    used: set[str] = set()
    for r in removed:
        best, score = None, 0.0
        for a in added:
            if a.key in used or a.kind != r.kind:
                continue
            s = _similar(r.key, a.key)
            if s > score:
                best, score = a, s
        if best and score >= RENAME_SIMILARITY:
            used.add(best.key)
            delta.renames.append(RenameProposal(
                kind=r.kind, removed_key=r.key, added_key=best.key,
                removed_id=r.element_id, added_id=best.element_id, similarity=round(score, 3)))


@dataclass
class CarryResult:
    model: Model
    carried: int = 0
    revoked: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def carry_human_facts(previous: Model, candidate: Model, delta: Delta) -> CarryResult:
    """Move human facts onto the freshly-extracted model (spec I-14, I-15, I-16).

    Human facts -- lifecycle decisions and resolved names -- survive
    re-extraction. Machine facts -- guards, triggers, anchors -- are replaced by
    it. Approval is revoked only where behaviour actually changed (I-17), and
    revocation propagates to the whole `(state, trigger)` group (I-18), because
    determinism and guard completeness are group properties: a modified sibling
    can break a transition that did not itself change.

    **Every carry is a `replace`, never a reconstruction.** This function used to
    rebuild each element by naming its fields positionally, which was complete
    when a `Transition` had seven of them and silently lossy by the time it had
    twenty-one: `inputs`, `outcome_status`, `response_body`, `guard_wording`,
    `data_requirements` and `evidence` were all discarded by the function whose
    entire job is to preserve things. It had never run in production, so nothing
    caught it drifting.

    `replace` overrides exactly the human fields and carries everything else
    through untouched -- correct for every field that exists now and every field
    added later. `test_human_facts_survive.py` enumerates the fields from
    `dataclasses.fields` rather than by hand, so a new one cannot start being
    dropped again without a test failing.
    """
    result = CarryResult(model=candidate)
    prev_states = keyed_states(previous)
    prev_trans = keyed_transitions(previous)

    invalidated_keys = {c.key for c in delta.changes if c.invalidates_approval}

    for sid, state in list(candidate.states.items()):
        key = state_key(candidate.id, state)
        p = prev_states.get(key)
        if p is None:
            continue
        # A human-resolved name survives; extraction may propose, never overwrite
        # (I-15). `name_tier` rides with the name it describes -- carrying the
        # name and leaving the tier behind would claim a reviewer's wording came
        # from a code convention.
        candidate.states[sid] = replace(
            state, name=p.name, lifecycle_state=p.lifecycle_state,
            name_tier=p.name_tier or state.name_tier,
        )
        result.carried += 1

    # I-18: which (state, trigger) groups were disturbed at all.
    disturbed_groups = set()
    for change in delta.changes:
        if change.kind != "transition" or change.delta == UNCHANGED:
            continue
        for t in candidate.transitions.values():
            if t.id == change.element_id:
                disturbed_groups.add((t.source, t.trigger))
        for t in previous.transitions.values():
            if t.id == change.element_id:
                disturbed_groups.add((t.source, t.trigger))

    for tid, transition in list(candidate.transitions.items()):
        key = transition_key(candidate.id, transition, candidate)
        previous_matches = prev_trans.get(key, [])
        if not previous_matches:
            continue

        p = previous_matches[0]
        group = (transition.source, transition.trigger)
        behaviour_changed = key in invalidated_keys
        group_disturbed = group in disturbed_groups

        if p.lifecycle_state == APPROVED and (behaviour_changed or group_disturbed):
            lifecycle = QUARANTINE
            reason = ("behaviour changed" if behaviour_changed
                      else f"group ({group[0]}, {group[1]}) was disturbed — "
                           f"determinism and guard completeness are group properties (I-18)")
            result.revoked.append(f"{transition.id}: {reason}")
        else:
            lifecycle = p.lifecycle_state

        # Only the human facts are overridden. The guard, trigger, anchors,
        # inputs, evidence and everything else are the freshly-extracted values
        # and must stay that way -- that is the whole machine/human split.
        candidate.transitions[tid] = replace(
            transition, lifecycle_state=lifecycle,
            name_tier=p.name_tier or transition.name_tier,
        )
        result.carried += 1

    candidate.reindex()
    if delta.renames:
        result.notes.append(
            f"{len(delta.renames)} rename(s) proposed but NOT applied — confirm "
            f"them to carry identity and human facts across (spec I-22)")
    return result
