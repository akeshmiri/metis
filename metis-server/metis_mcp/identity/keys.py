"""
Natural keys over meaning (application spec I-2, R12, R13).

Identity is a **natural key over what an element means**, not a hash over how it
happens to be represented. Representation changes constantly -- a method is
renamed, a parameter type changes, a file moves -- and meaning does not.

Why this is urgent rather than tidy: Layer 4 currently derives a transition id
from the Java method's full name. Rename `search` to `find`, or change a
parameter type, and the id changes -- so re-extraction would report REMOVED +
ADDED and silently discard every review decision attached to it. That is the
failure I-16 exists to prevent, and a content hash would make it worse, not better.

    State       key = (model, surface, observable signature)
    Transition  key = (model, source state, trigger, target state)

**Guard is an attribute, not identity.** A guard changing is the commonest edit
there is; if it changed identity, nothing would ever survive a code tweak.
"""
from __future__ import annotations

import hashlib
import re

from metis_mcp.mbt.model import Model, State, Transition

_NORMALISE = re.compile(r"\s+")


def normalise_guard(guard: str) -> str:
    """Minimal, non-interpreting normalisation (spec I-6).

    Whitespace and outer parentheses only. It never simplifies, reorders or
    interprets a condition: `a AND b` and `b AND a` stay different, because
    deciding they are equivalent is an interpretation this module has no business
    making. Erring toward "changed" costs a re-review; erring toward "same"
    silently blesses a different condition.
    """
    if not guard:
        return ""
    text = _NORMALISE.sub(" ", guard).strip()
    while text.startswith("(") and text.endswith(")") and text.count("(") == text.count(")"):
        inner = text[1:-1].strip()
        if inner.count("(") != inner.count(")"):
            break
        text = inner
    return text


def state_key(model_id: str, state: State) -> str:
    """(model, surface, observable signature).

    The state's id *is* its observable signature for synthesised models --
    `NoContent204` encodes status and discriminator, which is what a caller can
    actually distinguish (spec M-3). Display name is deliberately excluded: a
    rename must not change identity.
    """
    return f"{model_id}|{state.surface}|{state.id}"


def transition_key(model_id: str, transition: Transition, model: Model) -> str:
    """(model, source state, trigger, target state).

    References state keys rather than raw ids, so state identity resolves first
    and a change in a state's signature propagates correctly (spec I-4).
    """
    source = model.states.get(transition.source)
    target = model.states.get(transition.target)
    source_part = state_key(model_id, source) if source else f"{model_id}|?|{transition.source}"
    target_part = state_key(model_id, target) if target else f"{model_id}|?|{transition.target}"
    return f"{source_part}=[{transition.trigger}]=>{target_part}"


def short(key: str) -> str:
    """A stable short form, for use as a node id."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def keyed_states(model: Model) -> dict[str, State]:
    return {state_key(model.id, s): s for s in model.states.values()}


def keyed_transitions(model: Model) -> dict[str, list[Transition]]:
    """Transitions by key.

    A list, not a single value: two transitions may legitimately share
    `(source, trigger, target)` and differ only by guard -- two distinct reasons
    to reach the same state. I-5's step 3 disambiguates those by guard.
    """
    out: dict[str, list[Transition]] = {}
    for t in model.transitions.values():
        out.setdefault(transition_key(model.id, t, model), []).append(t)
    return out
