"""
The two gates, through the agent surface (spec §3.4, G1/G2, N-10, N-13, N-14).

**The only module here that may write `Approved`.** Everything in `write.py`
lands at Quarantine and stays there; this is where an element stops being a
candidate. That asymmetry is the whole reason the split exists, and
`test_mcp_write_policy.py` asserts it over the module source.

Four things a decision costs, and none of them is negotiable by a caller:

  * **an identity** — `roles.Identity`, checked for the capability (N-9)
  * **the fingerprint it was decided against** — `review_queue` returns one and
    `approve_elements` demands it back. If the model moved in between, the whole
    batch is refused rather than partly applied (N-14). A half-applied review
    leaves nobody able to say what was decided.
  * **the literal word** — `policy.APPROVE_LITERAL`, in this call (G1)
  * **not having proposed it** — N-10, resolved from the Episode the element
    already points at, so the gate fires on landed models and not only on
    hand-edited ones

Nothing here reimplements any of that. `review.decisions.apply` is the same
function `review apply` and the review UI call, and it refuses for the same
reasons; this module builds it a `ReviewFile` from tool arguments instead of
from a file a human edited. N-1 is "one record per decision", not "one code
path per surface" — but sharing the path is how the records stay identical.
"""
from __future__ import annotations

from metis_mcp import policy

# The graph's own answer to "who proposed this", joined through the Episode
# every node already points at (N-10). Copied from `cli.PROPOSERS_CYPHER`
# deliberately rather than imported: `mbt.cli` reaches every write path in the
# codebase, and importing it at module scope here would drag them into a server
# that is not configured to write.
PROPOSERS_CYPHER = """
MATCH (n)
WHERE ($journey IN n.functional_areas) AND (n:State OR n:Transition OR n:ApiCall OR n:UiAction)
MATCH (e:Episode {id: n.source_episode_id})
RETURN n.id AS element_id, e.proposed_by AS proposed_by
"""


def _load(journey: str, surface: str):
    from metis_mcp.mbt.graph_loader import load_from_graph
    from metis_mcp.mbt.graph_session import session

    with session() as s:
        return load_from_graph(s, journey, surface).model


def _proposers(journey: str) -> dict:
    from metis_mcp.mbt.graph_session import GraphNotConfigured, session

    try:
        with session() as s:
            return {r["element_id"]: r["proposed_by"]
                    for r in s.run(PROPOSERS_CYPHER, journey=journey)
                    if r["proposed_by"]}
    except GraphNotConfigured:
        return {}


def review_queue(journey: str, surface: str = "api") -> dict:
    """What is outstanding, the evidence for deciding it, and the fingerprint.

    Read-only, and it is the required first step: the `fingerprint` it returns is
    what `approve_elements` demands back. That is not ceremony — it is the only
    way a later reader can tell an approval made against this model from one made
    against a model that has since moved (N-14).

    The evidence is what §3.4 says a reviewer decides *with*: the validation
    findings, and reconciliation's two gap reports, which are never merged into
    one number because they go to different people (F-5).
    """
    from metis_mcp.mbt.validation import validate
    from metis_mcp.review.decisions import model_fingerprint

    model = _load(journey, surface)
    result = validate(model)
    outstanding = model.unapproved_elements()
    proposers = _proposers(journey)

    return {
        "ok": True,
        "model_id": model.id,
        # Pass this back to approve_elements. It is the evidence identity.
        "fingerprint": model_fingerprint(model),
        "outstanding": len(outstanding),
        # `unapproved_elements` yields (kind, id, lifecycle_state) — reported
        # rather than counted, because G1 needs to know WHICH elements.
        "elements": [
            {"id": element_id, "kind": kind, "lifecycle_state": lifecycle,
             "proposed_by": proposers.get(element_id, "")}
            for kind, element_id, lifecycle in outstanding
        ],
        "validation": {
            "blocking": [f.describe() for f in result.blocking],
            "unverifiable": [f.describe() for f in result.unverifiable],
            "advisory": [f.describe() for f in result.advisory],
            "generation_would_be_blocked": not result.is_valid(),
        },
        "means": ("unverifiable is neither a pass nor a defect (M-17); approving "
                  "past one is a decision, not a formality"),
        "next": (f"approve_elements(journey={journey!r}, element_ids=[...], "
                 f"fingerprint=<the value above>, confirm={policy.APPROVE_LITERAL!r})"),
    }


def _decide(decision: str, journey: str, surface: str, element_ids: list,
            fingerprint: str, confirm: str, actor: str, role: str,
            rationale: str, allow_self_approval: bool) -> dict:
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.review.decisions import (
        APPROVE, FILE_VERSION, ReviewFile, ReviewItem, apply, model_fingerprint,
    )
    from metis_mcp.review.roles import APPROVE_MODEL

    grant = policy.authorise(APPROVE_MODEL, actor, role)
    if decision == APPROVE:
        # Only approval costs the literal. A rejection makes nothing generatable
        # and is reversible by approving later; charging the same toll for both
        # would train people to type the word without reading.
        policy.require_confirmation(confirm, policy.APPROVE_LITERAL,
                                    "approval (G1)")
    if not element_ids:
        return {"ok": False, "refused": "no element_ids given; "
                                        "call review_queue first"}
    if decision != APPROVE and not rationale.strip():
        return {"ok": False, "refused": f"{decision} requires a rationale — a "
                                        f"refusal nobody can read is not a review"}

    model = _load(journey, surface)
    proposers = _proposers(journey)
    unknown = [e for e in element_ids
               if e not in model.states and e not in model.transitions]
    if unknown:
        return {"ok": False, "refused": f"not in {model.id}: {unknown[:5]}"}

    review = ReviewFile(
        version=FILE_VERSION, model_id=model.id,
        # The caller's, not the current one — `apply` compares them, and that
        # comparison is the staleness check. Substituting the live value here
        # would make it always pass and delete N-14 in one line.
        fingerprint=fingerprint,
        exported_at="", reviewer=grant.identity.name,
        allow_self_approval=allow_self_approval,
        items=[ReviewItem(
            kind="state" if e in model.states else "transition",
            id=e, decision=decision,
            current_state=(model.states[e].lifecycle_state if e in model.states
                           else model.transitions[e].lifecycle_state),
            rationale=rationale, proposed_by=proposers.get(e)) for e in element_ids],
    )

    result = apply(model, review)
    if not result.ok:
        return {"ok": False, "refused": result.blocked_reason,
                "current_fingerprint": model_fingerprint(model),
                "hint": ("call review_queue again and decide against the "
                         "fingerprint it returns")}

    if not result.applied:
        # **Nothing accepted, so nothing is written.** `apply` mutates the model
        # in place, so an all-refused batch leaves every lifecycle_state exactly
        # as it was and the write below would be a no-op -- except for
        # `SET n.name`, which would rewrite names for a decision that did not
        # happen. Returning here also keeps the audit honest: no entries, because
        # there were no decisions.
        return {
            "ok": False,
            "model_id": model.id,
            "refused": [{"element_id": e, "reason": r} for e, r in result.refused],
            "applied": 0,
            "means": "every element was refused; the graph is untouched",
        }

    # Only now, and only for what `apply` actually accepted.
    from metis_mcp.ontology.labels import NEEDS_REVIEW_STATES

    def marker(lifecycle: str) -> str:
        # Derived from lifecycle_state and cleared in the same statement that
        # settles it. An approved element left carrying `:NeedReview` sits in
        # the review queue forever.
        return ("SET n:NeedReview" if lifecycle in NEEDS_REVIEW_STATES
                else "REMOVE n:NeedReview")

    with session() as s:
        for element_id, state in model.states.items():
            s.run(f"MATCH (n:State {{id:$i}}) "
                  f"SET n.lifecycle_state=$l, n.name=$n {marker(state.lifecycle_state)}",
                  i=element_id, l=state.lifecycle_state, n=state.name)
        for element_id, transition in model.transitions.items():
            s.run(f"MATCH (n:Transition|ApiCall|UiAction {{id:$i}}) "
                  f"SET n.lifecycle_state=$l {marker(transition.lifecycle_state)}",
                  i=element_id, l=transition.lifecycle_state)

    audit, audit_path = policy.audit_state(model.id)
    for record in result.applied:
        # An `AuditRecord` carries the transition it made; the evidence is that
        # movement plus the fingerprint it was decided against (N-13/N-14).
        policy.record(grant, audit, record.element_id, record.decision,
                      evidence={"kind": record.kind,
                                "from_state": record.from_state,
                                "to_state": record.to_state},
                      fingerprint=record.fingerprint,
                      rationale=record.rationale,
                      self_approval=record.self_approval)
    policy.save_audit(audit, audit_path)

    outstanding = model.unapproved_elements()
    return {
        "ok": True,
        "model_id": model.id,
        "decision": decision,
        "applied": len(result.applied),
        "refused": [{"element_id": e, "reason": r} for e, r in result.refused],
        # A-27: a permitted self-approval is recorded as one and stays visible.
        "self_approvals": sum(1 for r in result.applied if r.self_approval),
        "still_outstanding": len(outstanding),
        "model_is_approved": not outstanding,
        "audit": str(audit_path),
        "means": ("generation reads only Approved (D-10); "
                  + ("this model is now generatable" if not outstanding
                     else f"{len(outstanding)} element(s) still block it")),
    }


def approve_elements(journey: str, surface: str = "api",
                     element_ids: list | None = None, fingerprint: str = "",
                     confirm: str = "", actor: str = "", role: str = "",
                     rationale: str = "", allow_self_approval: bool = False) -> dict:
    """**G1.** Approve elements, against the fingerprint you were shown.

    Needs the literal word `approve` in this call, an identity with the reviewer
    capability, and the `fingerprint` from `review_queue`. Refuses the whole
    batch if the model moved since — partial application leaves nobody able to
    say what was decided.

    `allow_self_approval` is N-11's override for a team with no second reviewer.
    Every use is recorded as a self-approval and is visible in the audit; it is
    not a way to make the check quieter.
    """
    from metis_mcp.review.decisions import APPROVE

    return _decide(APPROVE, journey, surface, element_ids or [], fingerprint,
                   confirm, actor, role, rationale, allow_self_approval)


def reject_elements(journey: str, surface: str = "api",
                    element_ids: list | None = None, fingerprint: str = "",
                    actor: str = "", role: str = "", rationale: str = "") -> dict:
    """Reject elements, with a reason. No literal needed; a rationale is."""
    from metis_mcp.review.decisions import REJECT

    return _decide(REJECT, journey, surface, element_ids or [], fingerprint,
                   "", actor, role, rationale, False)


def defer_elements(journey: str, surface: str = "api",
                   element_ids: list | None = None, fingerprint: str = "",
                   actor: str = "", role: str = "", rationale: str = "") -> dict:
    """Defer elements — left at Quarantine, with the reason recorded."""
    from metis_mcp.review.decisions import DEFER

    return _decide(DEFER, journey, surface, element_ids or [], fingerprint,
                   "", actor, role, rationale, False)
