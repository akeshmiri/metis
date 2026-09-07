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


def bare_id(model_id: str, element_id: str) -> str:
    """Strip the `<model>::` namespace the graph writes, if present.

    **The same id means the same element whether it came from a file or the
    graph, and it did not.** `landing.graph_state_id` namespaces every state by
    its model — deliberately, so seven services' `Metric` do not MERGE onto one
    node — and nothing stripped it back on load. So a graph-loaded `Metric` keyed
    as `records-api::Metric` and a freshly-synthesised one keyed as
    `Metric`, every key differed, and `diff` reported 20 ADDED + 20 REMOVED where
    the right answer was 20 UNCHANGED.

    The consequence was silent and severe: `carry_human_facts` matched nothing,
    so every approval was dropped on re-ingest **and no revocation was reported
    either** — the graph kept asserting approvals whose behaviour had changed.

    This is the second place the same namespace has bitten. `workflow.run`'s
    `source_fingerprint` needed the identical fix, for the identical reason.
    """
    prefix = f"{model_id}::"
    return element_id[len(prefix):] if element_id.startswith(prefix) else element_id


def state_key(model_id: str, state: State) -> str:
    """(model, surface, observable signature).

    The state's id *is* its observable signature for synthesised models --
    `NoContent204` encodes status and discriminator, which is what a caller can
    actually distinguish (spec M-3). Display name is deliberately excluded: a
    rename must not change identity.

    Normalised through `bare_id`, so the key survives the file/graph boundary --
    which is the whole point of a natural key over meaning rather than over
    representation.
    """
    return f"{model_id}|{state.surface}|{bare_id(model_id, state.id)}"


def transition_key(model_id: str, transition: Transition, model: Model) -> str:
    """(model, source state, trigger, target state).

    References state keys rather than raw ids, so state identity resolves first
    and a change in a state's signature propagates correctly (spec I-4).
    """
    source = model.states.get(transition.source)
    target = model.states.get(transition.target)
    source_part = (state_key(model_id, source) if source
                   else f"{model_id}|?|{bare_id(model_id, transition.source)}")
    target_part = (state_key(model_id, target) if target
                   else f"{model_id}|?|{bare_id(model_id, transition.target)}")
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


# ---------------------------------------------------------------------------
# Claim identity — the four validity-carrying labels (D-8, D-15)
# ---------------------------------------------------------------------------
#
# `Intent`, `Specification`, `Requirement` and `AcceptanceCriterion` are CLAIMS,
# not elements. The distinction decides how identity has to work, and getting it
# wrong is what made a requirement change unrecordable.
#
# An element's identity is a natural key over its MEANING, and its guard is an
# attribute: a transition whose guard changes is the same transition, modified.
# That is right for a state machine, where the thing persists and its details
# move.
#
# A claim has no such separation. *When the token expires the system shall reject
# the request* and *...shall refresh it silently* are not one requirement with a
# changed attribute; they are two claims, and the first stopped being true when
# the second started. D-15 says so directly -- validity answers "was this ever
# true, and is it still" -- and D-8 says an id is content-derived.
#
# The intake path did neither. It derived a Requirement's id from its ANCHOR:
#
#     requirement_id = f"req-{sha256(anchor_id)[:12]}"
#
# so an edited Jira ticket resolved to the same node, `landing.split_row` put
# `text` in the clause rewritten on every land, and `lifecycle_state` in the
# `ON CREATE` clause that is never rewritten. An **Approved** requirement
# silently acquired new text and kept its approval, `revision` was rewritten to
# 1, and it never reappeared in `review queue` because lifecycle had not moved.
#
# Splitting the id into a stable logical key and a content digest fixes that by
# construction rather than by adding a check:
#
#     req-a1b2c3d4e5f6@9f86d081     revision 1, valid_to "2026-06-01", Approved
#     req-a1b2c3d4e5f6@2c26b46b     revision 2, valid_to "",           Quarantine
#
# The new text is a NEW node, so S-4 lands it at Quarantine with no special case,
# and I-19's "prior approval retained in history" is the old node still being
# there. `landing.invalidate` closes the old window. Nothing is deleted.
#
# The logical key is what edges in an authored file reference (`spec.intent_id`),
# and what the anchor keeps pointing at across revisions -- so "every version of
# PROJ-14" is the anchor's `REPRESENTS` edges, and "the current one" is those
# filtered on `valid_to = ''`. That is why no `SUPERSEDES` edge is added: it
# would be a second representation of a fact the graph already holds, and D-1's
# bar (a writer, a reader, and a requirement question needing it as a node) is
# not met by a traversal that already works.

CLAIM_SEPARATOR = "@"

# How much of the digest rides in the id. Eight hex characters is 32 bits: with
# the logical key already scoping it, a collision needs two DIFFERENT texts for
# the SAME requirement to collide, and the birthday bound over the revisions one
# requirement accumulates is not close.
_CLAIM_DIGEST = 8


def normalise_claim(text: str) -> str:
    """Whitespace only, exactly as `normalise_guard` treats a condition.

    Deliberately not smarter. Case, punctuation and word order all carry meaning
    in a requirement -- *shall* and *shall not* differ by three characters -- so
    anything that folded them would decide two different claims were one. Erring
    toward "changed" costs a re-review; erring toward "same" silently blesses a
    requirement nobody agreed to.
    """
    return _NORMALISE.sub(" ", text or "").strip()


def claim_id(logical_key: str, text: str) -> str:
    """`<logical key>@<digest of the text>` (spec D-8, D-15).

    `logical_key` is the stable identity of the thing being claimed about -- an
    anchor-derived `req-...`, or an author-chosen `INT-3`. `text` is the claim
    itself. Same key and same text is the same node, so re-landing unchanged
    content stays the no-op TR-6 requires.
    """
    if not logical_key:
        raise ValueError("a claim needs a logical key to be a revision OF")
    digest = hashlib.sha256(normalise_claim(text).encode()).hexdigest()
    return f"{logical_key}{CLAIM_SEPARATOR}{digest[:_CLAIM_DIGEST]}"


def logical_key_of(node_id: str) -> str:
    """The stable half of a claim id, or the id unchanged if it carries none.

    Tolerant on purpose: nodes landed before claim ids existed have no separator,
    and reading one has to yield its own key rather than raise. That is what lets
    a graph built by the old scheme be read, reported on, and re-ingested.
    """
    return node_id.split(CLAIM_SEPARATOR, 1)[0] if node_id else ""


def is_revision_of(node_id: str, logical_key: str) -> bool:
    return bool(node_id) and logical_key_of(node_id) == logical_key


def business_entity_key(name: str) -> str:
    """A business noun's natural key: what it means, normalised.

    I-2's rule applied to the business layer. Two sources describe the same noun
    and neither is wrong about it: the glossary carries an author-chosen id
    (`apispec`), and intake mints one from the UIF's `data_model` name. With two
    minting rules, `api spec` landed twice -- once per source -- and
    `list_entities` showed a duplicate with no way to tell which was canonical.

    A business entity has no model scope on purpose: `record` means one thing
    across every journey. That is the whole reason `BusinessEntity` is separate
    from `Class`, which is scoped to the code that declares it (D-13).
    """
    import re

    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "unnamed"
