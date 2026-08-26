"""
The HTTP API (§9.4 over a network rather than a terminal).

**What this module is allowed to be: routing.** Every rule it upholds is upheld
by a module that can be tested without a socket — `policy.authorise` decides
capability, `roles.record_decision` writes the audit record, `Screen.require`
decides whether evidence is presentable, `ConfirmationTickets` binds G2. This
file translates HTTP into those calls and their refusals into status codes. A
rule enforced *here* would be a rule the CLI and the review UI do not have.

**The four properties that must survive the transport**

* **N-1** — every decision, through any surface, produces the same audit record.
  Handlers call `roles.record_decision(..., surface="rest")`; no endpoint has a
  privileged or unlogged path.
* **N-4** — a decision that cannot show its evidence is blocked, not partially
  taken. That is a **409**, never a 200 with a thinner body.
* **N-10** — the proposer may not approve. Inherited from `authorise`, free.
* **N-8** — the read-only deployment stays read-only *by construction*: the write
  half is not imported when `METIS_MCP_WRITE` is off, so the routes do not exist
  rather than existing and declining.

**On the dependency.** `review_ui` argues against a web framework, citing §11.2
and NF-4. That argument is weaker than it was: `mcp` already brings starlette,
pydantic and uvicorn, so FastAPI adds one package on top of a tree that is
entirely installed. The argument it does not weaken is the one about surface —
this reaches a network, and everything in `auth.py` exists because of that.
"""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request

from metis_mcp import policy
from metis_mcp.api import auth
from metis_mcp.mbt.graph_session import GraphNotConfigured

# Issued tickets live with the app, not with a request. One instance, per NF-4.
from metis_mcp.publishing.publish import (
    ConfirmationRefused,
    ConfirmationReplayed,
    ConfirmationTickets,
)


def identity_of(request: Request):
    """Who is calling. The only way an endpoint learns that.

    Both failures answer **401** with the same body: distinguishing "no
    credential" from "wrong credential" to the caller is free help to an
    attacker, even though the code distinguishes them.
    """
    try:
        return auth.authenticate(request.headers.get(auth.HEADER, ""))
    except (auth.AuthenticationRequired, auth.AuthenticationFailed):
        raise HTTPException(status_code=401, detail="authentication required",
                            headers={"WWW-Authenticate": auth.SCHEME})


def create_app(tickets: ConfirmationTickets | None = None) -> FastAPI:
    """Build the application.

    A factory rather than a module-level singleton so a test can hold its own
    ticket store, and so importing this module does not stand anything up.
    """
    app = FastAPI(title="Métis", docs_url=None, redoc_url=None)
    app.state.tickets = tickets or ConfirmationTickets()

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        """Unauthenticated on purpose: a load balancer is not a principal, and it
        reveals nothing but that the process is up."""
        return {"ok": True, "write_mode": policy.mode()}

    @app.get("/whoami")
    def whoami(who=Depends(identity_of)) -> dict[str, Any]:
        """What this credential can do — the cheapest way for an operator to see
        that a token resolves to the role they expected, before discovering it at
        the moment of a decision."""
        return {"name": who.name, "role": who.role, "write_mode": policy.mode()}

    # ---- Reads ------------------------------------------------------------
    #
    # **The MCP tool IS the implementation.** Each endpoint calls the same
    # function the tool exposes and returns its JSON verbatim, so the two
    # surfaces cannot answer the same question differently. Re-deriving the shape
    # here would give the graph two vocabularies — which is where nearly every
    # real defect in this codebase has come from.
    #
    # **Reads do not require `METIS_MCP_WRITE`.** A read-only deployment that
    # could not read would be a strange thing to have built; N-8 is about what
    # may be WRITTEN, and these write nothing.

    def _tool(name: str, **kwargs) -> Any:
        import json

        from metis_mcp import server as tools

        try:
            return json.loads(getattr(tools, name)(**kwargs))
        except GraphNotConfigured as exc:
            # A safety net, not the usual path: the tools already catch this and
            # answer `{"ok": false, "reason": ...}`. If one ever stops doing so,
            # 503 is the truthful code — the deployment is missing configuration
            # and the caller can neither fix nor retry it.
            raise HTTPException(status_code=503, detail=str(exc))

    # **A read that cannot answer returns 204, with no body.**
    #
    # The tools answer `{"ok": false, "reason": ...}` when there is no graph. Over
    # MCP that is the whole response and a caller reads it. Over HTTP, returning
    # it with a 200 would mean `raise_for_status()` reports success and the body
    # then says otherwise — a trap laid for every client library's happy path.
    #
    # 204 rather than a 4xx or 5xx because nothing is wrong with the request and
    # nothing is broken on the server: there is simply no content to give. A read
    # that legitimately finds nothing is different and stays 200 with an empty
    # list — "I looked and there is none" is an answer; this is the absence of
    # one.
    #
    # The reason rides in a header because a 204 may not carry a body and
    # discarding it would leave an operator with a blank response and no idea
    # that a password is missing. `X-Metis-Reason` is readable by a human in
    # `curl -i` and by a client that thinks to look.
    REASON_HEADER = "X-Metis-Reason"

    def _header_safe(text: str) -> str:
        """A reason that can survive an HTTP header.

        Header values are latin-1, and these messages are written for humans —
        the graph one contains an em-dash, which raised `UnicodeEncodeError`
        inside starlette and turned a 204 into a 500. Transliterated rather than
        dropped: an operator reading `curl -i` needs the sentence, not its
        surviving fragments.
        """
        swaps = {"\u2014": "--", "\u2013": "-", "\u2018": "'", "\u2019": "'",
                 "\u201c": '"', "\u201d": '"', "\u2026": "..."}
        for fancy, plain in swaps.items():
            text = text.replace(fancy, plain)
        return text.encode("latin-1", "replace").decode("latin-1")

    def _answer(payload: Any) -> Any:
        """A tool's JSON as an HTTP response."""
        from fastapi import Response

        if isinstance(payload, dict) and payload.get("ok") is False:
            return Response(status_code=204, headers={
                REASON_HEADER: _header_safe(
                    str(payload.get("reason", "no content")))})
        return payload

    @app.get("/workflows")
    def workflows(who=Depends(identity_of)) -> Any:
        return _answer(_tool("list_workflows"))

    @app.get("/policy")
    def policy_view(who=Depends(identity_of)) -> Any:
        return _answer(_tool("describe_policy"))

    @app.get("/models/{journey}")
    def model(journey: str, surface: str = "api", detail: bool = False,
              who=Depends(identity_of)) -> Any:
        return _answer(_tool("get_model", journey=journey, surface=surface,
                             detail=detail))

    @app.get("/models/{journey}/coverage")
    def coverage(journey: str, surface: str = "api",
                 who=Depends(identity_of)) -> Any:
        return _answer(_tool("coverage", journey=journey, surface=surface))

    @app.get("/search")
    def search(q: str, limit: int = 20, who=Depends(identity_of)) -> Any:
        return _answer(_tool("search_knowledge", query=q, limit=limit))

    @app.get("/impact")
    def impact(files: str, who=Depends(identity_of)) -> Any:
        """`files` is comma-separated — what `git diff --name-only` prints, joined.

        `engine.changed_files` produces exactly that list from a commit range.
        """
        return _answer(_tool("impact",
                             changed_files=[f for f in files.split(",") if f]))

    @app.post("/publications/{batch_id}/confirmation")
    def open_confirmation(batch_id: str, fingerprint: str,
                          who=Depends(identity_of)) -> dict[str, Any]:
        """Show a batch and issue a single-use ticket for it (G2, T-17).

        The fingerprint of what was shown is bound into the ticket, so a batch
        that changes afterwards cannot be confirmed by a decision taken about its
        earlier self.
        """
        try:
            grant = policy.authorise(policy_capability_confirm(), who.name, who.role)
        except Exception as exc:                       # policy raises its own types
            raise _as_http(exc)
        ticket = secrets.token_urlsafe(24)
        app.state.tickets.issue(ticket, fingerprint, grant.identity.name, 0)
        return {"batch_id": batch_id, "ticket": ticket,
                "confirm_with": "the literal word `publish` (T-18)"}

    @app.post("/publications/{batch_id}/confirm")
    def confirm_publication(batch_id: str, ticket: str, literal: str,
                            fingerprint: str,
                            who=Depends(identity_of)) -> dict[str, Any]:
        """Redeem a ticket. Once.

        **409, not 400, on a replay.** The request is well-formed; the conflict is
        with the state of the world — this publication was already confirmed, and
        the caller needs to re-read rather than re-send.
        """
        try:
            policy.authorise(policy_capability_confirm(), who.name, who.role)
            confirmation = app.state.tickets.redeem(
                ticket, literal, fingerprint, who.name)
        except ConfirmationReplayed as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except ConfirmationRefused as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise _as_http(exc)
        return {"batch_id": batch_id, "confirmed_by": confirmation.confirmed_by,
                "at": confirmation.at, "literal": confirmation.literal,
                "published": False,
                "note": "dry-run is the only transport registered (T-21/C3); "
                        "nothing was sent"}

    @app.post("/models/{model_id}/elements/{element_id}/approval")
    def approve(model_id: str, element_id: str, rationale: str = "",
                who=Depends(identity_of)) -> dict[str, Any]:
        """G1 over HTTP. Every step is the one the CLI and the review UI take.

        The sequence is not rearranged for convenience, because each step refuses
        for a different reason and the order is what makes the refusals
        meaningful: capability, then self-approval, then whether the evidence can
        be shown, then the decision, then the record.
        """
        from datetime import datetime, timezone

        from metis_mcp.review.decisions import (
            FILE_VERSION,
            ReviewFile,
            model_fingerprint,
        )
        from metis_mcp.review.decisions import apply as apply_decisions
        from metis_mcp.review.roles import (
            APPROVE_MODEL,
            check_self_approval,
            record_decision,
        )
        from metis_mcp.review_ui.evidence import approve_model_screen
        from metis_mcp.review_ui.server import _items_for
        from metis_mcp.mbt.validation import validate
        from metis_mcp.reconciliation import reconcile

        context = getattr(app.state, "review_context", None)
        if context is None or context.model.id != model_id:
            raise HTTPException(status_code=404, detail=f"no model {model_id!r}")

        # **A decision this surface cannot keep is refused, not taken.** The
        # review UI learned this the hard way: an approval was acknowledged with
        # 200 and then discarded, which is exactly the privileged, unlogged path
        # N-1 prohibits. A context with no `commit` is read-only.
        if context.commit is None:
            raise HTTPException(
                status_code=409,
                detail="this deployment cannot persist a decision, so it will "
                       "not accept one (N-1). Nothing was changed.")

        try:
            policy.authorise(APPROVE_MODEL, who.name, who.role)
        except Exception as exc:
            raise _as_http(exc)

        outcome = check_self_approval(
            who, context.proposers.get(element_id),
            allow_self_approval=context.allow_self_approval)
        if not outcome.permitted:
            raise HTTPException(status_code=403, detail=outcome.reason)

        # N-4: a screen that cannot show its evidence blocks the decision. 409,
        # never a 200 with a thinner body.
        screen = approve_model_screen(
            context.model, validation=validate(context.model),
            reconciliation=reconcile(context.model, [], []),
            element_sources=context.proposers)
        try:
            screen.require()
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        items = _items_for(context.model, element_id, {"rationale": rationale},
                           context.proposers)
        if items is None:
            raise HTTPException(
                status_code=404,
                detail=f"no state or transition {element_id!r} in {model_id}")

        result = apply_decisions(
            context.model,
            ReviewFile(version=FILE_VERSION, model_id=context.model.id,
                       fingerprint=model_fingerprint(context.model),
                       exported_at=datetime.now(timezone.utc).isoformat(
                           timespec="seconds"),
                       items=items, reviewer=who.name,
                       allow_self_approval=context.allow_self_approval),
            drafted=context.drafted)
        if not result.ok:
            raise HTTPException(status_code=409, detail=result.blocked_reason)
        if result.refused and not result.applied:
            raise HTTPException(status_code=403, detail=result.refused[0][1])

        context.commit(context, result.applied)

        # N-1: the same record the CLI and the UI write, differing only in the
        # surface it names.
        decision = record_decision(
            context.audit, who, APPROVE_MODEL, element_id,
            outcome="Approved", evidence=screen.evidence, rationale=rationale,
            self_approval=outcome.is_self_approval, surface="rest")

        return {"recorded": True, "element_id": element_id,
                "applied": [r.element_id for r in result.applied],
                "refused": [{"id": e, "reason": r} for e, r in result.refused],
                "self_approval": decision.self_approval, "at": decision.at}

    return app


def policy_capability_confirm() -> str:
    from metis_mcp.review.roles import CONFIRM_PUBLICATION
    return CONFIRM_PUBLICATION


def _as_http(exc: Exception) -> HTTPException:
    """Policy refusals, as status codes.

    Each maps to the thing the caller must change: **403** you are not permitted,
    **409** this deployment is configured not to allow it. Collapsing them into
    one code would tell an operator to ask for a role when the answer is an
    environment variable.
    """
    from metis_mcp.review.roles import NotPermitted

    if isinstance(exc, policy.WriteDisabled):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, NotPermitted):
        return HTTPException(status_code=403, detail=str(exc))
    raise exc
