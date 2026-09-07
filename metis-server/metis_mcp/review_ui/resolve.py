"""
Gathering the half a decision page cannot hold.

**Why four of the six decisions have no rendered surface.** Each is *about*
something the review context does not carry: a divergence needs both claims side
by side, a match needs the criterion's own words and why it was proposed, a drift
item needs the case as the tracker now holds it. The existing handlers take those
fields from the request body — which works for a JSON client that already has
them, and leaves a GET with nothing to draw. `Screen.require()` then blocks,
correctly, and the decision is unreachable over the browser for a reason that
looks like a bug and is actually a rule.

This module is the missing step: given what the review session holds, go and get
the rest, so the page can be drawn honestly rather than partially.

**It reports what it could not reach, and never substitutes for it.** Every
resolver returns `(provided, missing)`. A caller renders the decision only when
`missing` is empty; otherwise it renders the refusal and says which input is
absent and who holds it. That is the same discipline `risk/inputs.py` applies to
an assessment — a gap is named, never defaulted — and the same one
`Screen.require()` already enforces one layer down. Filling a field with a
plausible value to make a page render is the single worst thing this module
could do: it would put a decision in front of somebody over evidence nobody
gathered.

**Nothing here decides, and nothing here writes.** The resolvers read. The
decision still goes through the handler that owns it, which still builds its own
`Screen` and still calls `require()` — so a resolver that returned something
wrong makes the page refuse, not the decision pass.
"""
from __future__ import annotations

#: What each decision needs beyond the model, and who holds it. Stated as data so
#: a refusal can name the source rather than saying "not available".
SOURCES: dict[str, dict[str, str]] = {
    "confirm_match": {
        "ac_text": "the AcceptanceCriterion node in the graph",
        "why_proposed": "a reconciliation run over this model (X-17)",
    },
    "resolve_divergence": {
        "code_side": "the recovered transition and its anchor",
        "ac_side": "the criterion that contradicts it",
        "blocked_paths": "the paths generation refuses while this is open",
    },
    "decide_drift": {
        "published_content": "the test-management tool — the ledger stores a "
                             "content HASH, never the text, so this is a live read",
        "last_generated": "the publication ledger",
        "newly_generated": "a generation run over the current model",
    },
}


def sources_for(decision: str) -> dict[str, str]:
    """Which inputs a decision needs and who holds each. Empty for a rendered one."""
    return dict(SOURCES.get(decision, {}))


def for_confirm_match(model, ac_id: str, transition_id: str,
                      criteria=None) -> tuple[dict, list[str]]:
    """The criterion's words, the transition it would validate, and why proposed.

    Fillable from a review session, which is what makes this the one to render
    first: the model is already loaded and the pre-filter is pure, so nothing
    here reaches outside the process.

    `why_proposed` comes from the real matcher rather than being described in
    prose. X-17 says the pre-filter narrows without deciding, and the reviewer
    has to see that a match rests on a route and a status rather than on wording
    similarity — which is never sufficient on its own.
    """
    provided: dict = {}
    missing: list[str] = []

    criterion = next((c for c in (criteria or ())
                      if getattr(c, "id", "") == ac_id), None)
    if criterion is None:
        missing.append("ac_text")
    else:
        provided["ac_text"] = getattr(criterion, "text", "") or ""
        if not provided["ac_text"]:
            # An empty criterion is not a criterion. Rendering the page would
            # ask somebody to confirm that a blank validates a transition.
            provided.pop("ac_text")
            missing.append("ac_text")

    if transition_id not in getattr(model, "transitions", {}):
        missing.append("transition_tuple")
    else:
        anchor = getattr(model.transitions[transition_id], "guard_anchor", "")
        if anchor:
            provided["code_anchor"] = anchor

    if criterion is not None:
        from metis_mcp.reconciliation.matching import prefilter

        proposal = prefilter(criterion, model)
        candidate = next((c for c in proposal.candidates
                          if c.transition_id == transition_id), None)
        provided["why_proposed"] = {
            "evidence": dict(candidate.evidence) if candidate else {},
            "strength": candidate.strength if candidate else 0,
            "ambiguous": proposal.is_ambiguous,
            "note": proposal.note or "",
        }
        if candidate is None:
            # Real information, and the reason this is not a missing input: the
            # matcher did not propose this pairing at all. A reviewer confirming
            # it is overriding the pre-filter, which they may do — and must be
            # told they are doing.
            provided["why_proposed"]["note"] = (
                "the pre-filter proposed no evidence for this pairing. "
                "Confirming it is an override, not an agreement."
            )
    else:
        missing.append("why_proposed")

    return provided, missing


def for_resolve_divergence(model, element_id: str, criteria=None,
                           validating=None) -> tuple[dict, list[str]]:
    """Both claims about one behaviour, and what stays blocked while it is open.

    **Neither side is marked as the likely one.** S-10 forbids a precedence
    rule, because a rule would silently decide which of a defect and a stale
    requirement is right — the exact judgement the decision exists to take.
    """
    provided: dict = {}
    missing: list[str] = []

    transition = getattr(model, "transitions", {}).get(element_id)
    if transition is None:
        missing.append("code_side")
    else:
        provided["code_side"] = {
            "transition_id": transition.id,
            "trigger": transition.trigger,
            "guard": transition.guard or "",
            "outcome": transition.outcome_status,
            "anchor": getattr(transition, "guard_anchor", ""),
        }

    # **The edge lives in the graph, not on the criterion.** An
    # `AcceptanceCriterion` carries its text and provenance; `VALIDATES` is a
    # relationship, and `load_validating_criteria` is what reads it back as
    # `{transition_id: [criterion_id]}`. Looking for a `validates` attribute
    # found none on every criterion and would have reported every divergence as
    # unfillable — a resolver failing silently in the direction of "no evidence".
    validated_by = set((validating or {}).get(element_id, ()))
    against = [c for c in (criteria or ())
               if getattr(c, "id", "") in validated_by]
    if not against:
        missing.append("ac_side")
    else:
        provided["ac_side"] = {
            "criteria": [{"id": getattr(c, "id", ""),
                          "text": getattr(c, "text", ""),
                          "provenance": getattr(c, "provenance", "")}
                         for c in against],
        }

    # Computable here: a divergence blocks whatever generation would produce
    # from this transition. Empty is a real answer and not a missing input.
    provided["blocked_paths"] = [transition.id] if transition is not None else []
    return provided, missing


def for_decide_drift(item, ledger=None, published_reader=None) -> tuple[dict, list[str]]:
    """The three texts a drift decision compares.

    **`published_content` cannot come from the ledger and that is not an
    oversight.** `PublicationLedger` stores a content *hash* per published case —
    which is precisely what makes a hand edit detectable — and never the text. So
    the only way to show a reviewer what the tracker currently holds is to read
    the tracker, and this takes a `published_reader` to do it rather than
    pretending the ledger can.

    Absent a reader, `published_content` is reported missing and the page
    refuses. That refusal is the honest outcome: deciding whether to overwrite
    somebody's edit, without being shown the edit, is not a decision.
    """
    provided: dict = {}
    missing: list[str] = []

    if ledger is not None:
        last = getattr(ledger, "last_generated", {}) or {}
        if item.case_id in last:
            provided["last_generated"] = last[item.case_id]
        else:
            missing.append("last_generated")
    else:
        missing.append("last_generated")

    if published_reader is None:
        missing.append("published_content")
    else:
        try:
            text = published_reader(item.case_id)
        except Exception as e:                      # transport, auth, refusal
            text = ""
            provided["read_failed"] = f"{type(e).__name__}: {e}"
        if text:
            provided["published_content"] = text
        else:
            missing.append("published_content")

    if item.diff:
        provided["diff"] = list(item.diff)
    return provided, missing


def describe(decision: str, missing: list[str]) -> str:
    """One sentence a refusal can show, naming each absent input and its source.

    Written for the person looking at the page, not for a log: "not available"
    tells them nothing they can act on, and who holds the value is the only part
    that lets them go and get it.
    """
    if not missing:
        return ""
    sources = sources_for(decision)
    parts = [f"{name} (from {sources.get(name, 'a source not recorded here')})"
             for name in missing]
    return ("This decision cannot be drawn yet. Still needed: "
            + "; ".join(parts) + ".")
