"""
The review UI's HTTP backend (application spec §9.2, §9.3; N-1, N-4, N-13).

`evidence.py` decides what a screen must show and `view.py` renders the machine;
this serves both over HTTP and is deliberately thin. Everything it enforces is
enforced by a module that can be tested without a socket -- the handler's job is
routing, not judgement.

Three properties it must not lose, each inherited rather than reimplemented:

  * **N-1** every decision recorded through any surface produces the same audit
    record. This calls `roles.record_decision`, the same function the CLI uses.
    No surface has a privileged or unlogged path.
  * **N-4** a decision screen that cannot show its evidence blocks the decision.
    The handler calls `Screen.require()` and returns **409**, not a partial page.
  * **N-9/N-10** capability is checked per request, and the proposer of an element
    may not approve it.

Built on `http.server` deliberately: §11.2 targets a single interactive operator,
NF-4 states a single instance with no HA target, and adding a web framework to a
codebase whose whole point is a closed, auditable dependency set would be a poor
trade for reload-on-save.

**Not a public surface.** It binds loopback by default, and there is no
authentication here -- identity arrives as a header and is *trusted*. That is
honest for a localhost review tool and unacceptable for anything else; the
docstring on `serve` says so, and `--host` warns when it is widened.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

from metis_mcp.mbt.coverage import build_ledger
from metis_mcp.mbt.criteria import DEFAULT_CRITERION
from metis_mcp.mbt.model import Model
from metis_mcp.mbt.path_generation import DEFAULT_SETUP_CAP, generate
from metis_mcp.mbt.validation import format_validation, validate
from metis_mcp.reconciliation import reconcile
# N-1: this surface applies decisions through the SAME function the CLI uses.
# Reimplementing the mutation here is how the two surfaces drifted into
# disagreeing about what an approval does.
from metis_mcp.review.decisions import (
    APPROVE,
    FILE_VERSION,
    ReviewFile,
    ReviewItem,
    apply as apply_decisions,
    model_fingerprint,
)
from metis_mcp.review.roles import (
    APPROVE_MODEL,
    NAME_STATE,
    AuditLog,
    Identity,
    NotPermitted,
    check_self_approval,
    format_audit,
    record_decision,
    require,
)
from metis_mcp.review_ui.evidence import (
    EvidenceMissing,
    approve_model_screen,
    name_state_screen,
)
from metis_mcp.review_ui.view import build_layout, render_html

IDENTITY_HEADER = "X-Metis-User"
ROLE_HEADER = "X-Metis-Role"


@dataclass
class ReviewContext:
    """What the server serves. One model per instance, matching §9.3's screens.

    `commit` is how a decision made here becomes durable. It is injected rather
    than decided in this module because the server must not know whether the
    model came from a file or the graph -- but it must know that *something*
    stores the result. Before it existed, an approval taken through this surface
    mutated nothing and was written to an `AuditLog` that `cmd_ui` constructed
    fresh and dropped on exit: the decision was acknowledged with HTTP 200 and
    then discarded, which is precisely the privileged, unlogged path N-1
    prohibits.

    A context with no `commit` is read-only, and `_approve` refuses rather than
    accepting a decision it cannot keep (N-4's discipline: better to block than
    to present a decision as taken when it was not).
    """

    model: Model
    audit: AuditLog
    proposers: dict[str, str]
    criterion: str = DEFAULT_CRITERION
    max_setup: int = DEFAULT_SETUP_CAP
    allow_self_approval: bool = False
    commit: "Callable[[ReviewContext, list], None] | None" = None
    drafted: dict[str, str] = field(default_factory=dict)

    def ledger(self):
        return build_ledger(self.model, generate(self.model, self.criterion,
                                                 self.max_setup))


def _items_for(model: Model, element_id: str, body: dict,
               proposers: dict[str, str]) -> list[ReviewItem] | None:
    """Turn one web approval into the same `ReviewItem`s the CLI would apply.

    **`element_id == model.id` means the whole model**, which is what G1 actually
    asks about: `_require_approved` checks every element, so "approve the model"
    has to expand to its outstanding elements or the approval is a label with
    nothing under it. N-5 permits the batch and forbids batch blindness, so the
    response reports what was decided rather than only that something was.

    `criterion_text` and `affirmed_as_intent` come from the request body, giving
    the web reviewer the same two ways to promote a criterion the review file
    gives (S-19). Neither surface can promote by merely clicking approve.
    """
    def one(kind: str, eid: str, element) -> ReviewItem:
        return ReviewItem(
            kind=kind, id=eid, decision=APPROVE,
            current_state=element.lifecycle_state,
            rationale=body.get("rationale", ""),
            proposed_by=proposers.get(eid),
            criterion_id=body.get("criterion_id"),
            criterion_text=body.get("criterion_text"),
            affirmed_as_intent=bool(body.get("affirmed_as_intent", False)),
        )

    if element_id == model.id:
        # Built from `unapproved_elements()` rather than from a second walk of
        # the model, so "what G1 is waiting on" has exactly one definition. A
        # separate walk here silently included `planned` transitions, which P-11
        # excludes precisely because approving behaviour nobody has built asks a
        # reviewer to confirm something that does not exist.
        return [one(kind, eid,
                    model.states[eid] if kind == "state" else model.transitions[eid])
                for kind, eid, _ in model.unapproved_elements()]

    state = model.states.get(element_id)
    if state is not None:
        return [one("state", element_id, state)]
    transition = model.transitions.get(element_id)
    if transition is not None:
        return [one("transition", element_id, transition)]
    return None


def _identity(headers) -> Identity:
    name = (headers.get(IDENTITY_HEADER) or "").strip()
    role = (headers.get(ROLE_HEADER) or "").strip()
    if not name or not role:
        raise NotPermitted(
            f"identity required: send {IDENTITY_HEADER} and {ROLE_HEADER}. "
            f"Every decision records who made it (N-13, O-4c)")
    return Identity(name, role)


def make_handler(context: ReviewContext):
    class Handler(BaseHTTPRequestHandler):
        server_version = "metis-review/1"

        def log_message(self, *args):        # noqa: D102 - quiet by default
            pass

        # ---------------- helpers ----------------

        def _send(self, code: int, body: str, content_type: str) -> None:
            payload = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            # No external asset is ever loaded (see view.py), so the policy can
            # be this tight without breaking the page.
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; style-src 'unsafe-inline'; "
                             "img-src data:")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, json.dumps(payload, indent=2, default=str), "application/json")

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length))
            except json.JSONDecodeError as e:
                raise ValueError(f"body is not JSON: {e}") from e

        # ---------------- routes ----------------

        def do_GET(self):                                        # noqa: N802
            route = urlparse(self.path)
            query = parse_qs(route.query)
            try:
                if route.path in ("/", "/model"):
                    ledger = context.ledger()
                    summary = ledger.summary()
                    page = render_html(
                        context.model, build_layout(context.model, ledger),
                        coverage_summary=(f"{summary['covered']} covered, "
                                          f"{summary['uncovered']} uncovered under "
                                          f"`{summary['criterion']}`."))
                    return self._send(200, page, "text/html")

                if route.path == "/api/validation":
                    result = validate(context.model)
                    return self._json(200, {
                        "verdict": "well-formed" if result.is_valid() else "blocked",
                        "blocking": [f.describe() for f in result.blocking],
                        "unverifiable": [f.describe() for f in result.unverifiable],
                        "advisory": [f.describe() for f in result.advisory],
                        "text": format_validation(result),
                    })

                if route.path == "/api/screen/approve":
                    screen = approve_model_screen(
                        context.model, validation=validate(context.model),
                        reconciliation=reconcile(context.model, [], []),
                        element_sources=context.proposers)
                    return self._json(200 if screen.can_decide else 409, {
                        "decision": screen.decision,
                        "can_decide": screen.can_decide,
                        "blocked_reason": screen.blocked_reason,
                        "evidence": screen.evidence,
                        "notes": screen.notes,
                    })

                if route.path == "/api/screen/name-state":
                    state_id = (query.get("state") or [""])[0]
                    screen = name_state_screen(context.model, state_id,
                                               ac_candidates=[], code_candidates=[])
                    return self._json(200 if screen.can_decide else 409, {
                        "decision": screen.decision,
                        "can_decide": screen.can_decide,
                        "blocked_reason": screen.blocked_reason,
                        "evidence": screen.evidence,
                        "notes": screen.notes,
                    })

                if route.path == "/api/audit":
                    return self._json(200, {
                        "entries": context.audit.to_json_ready(),
                        "self_approvals": [d.element_id
                                           for d in context.audit.self_approvals()],
                        "text": format_audit(context.audit),
                    })

                return self._json(404, {"error": f"no route {route.path}"})

            except Exception as e:                    # noqa: BLE001 - surfaced, not hidden
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})

        def do_POST(self):                                       # noqa: N802
            route = urlparse(self.path)
            try:
                identity = _identity(self.headers)
            except (NotPermitted, ValueError) as e:
                return self._json(401, {"error": str(e)})

            try:
                body = self._body()
            except ValueError as e:
                return self._json(400, {"error": str(e)})

            try:
                if route.path == "/api/decide/approve":
                    return self._approve(identity, body)
                if route.path == "/api/decide/name-state":
                    return self._name_state(identity, body)
                return self._json(404, {"error": f"no route {route.path}"})
            except NotPermitted as e:
                return self._json(403, {"error": str(e)})
            except EvidenceMissing as e:
                # N-4: a screen that cannot show its evidence blocks the decision.
                return self._json(409, {"error": str(e)})
            except Exception as e:                    # noqa: BLE001
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})

        # ---------------- decisions ----------------

        def _approve(self, identity: Identity, body: dict):
            require(identity, APPROVE_MODEL)
            element_id = body.get("element_id") or context.model.id

            if context.commit is None:
                # N-4 applied to durability: a decision this surface cannot keep
                # is a decision it must not accept. Returning 200 here is how the
                # old path silently discarded every web approval.
                return self._json(409, {
                    "error": "this review session is read-only — no commit target "
                             "was configured, so a decision could not be stored. "
                             "Nothing was changed (N-1)."})

            outcome = check_self_approval(
                identity, context.proposers.get(element_id),
                allow_self_approval=context.allow_self_approval)
            if not outcome.permitted:
                return self._json(403, {"error": outcome.reason})

            screen = approve_model_screen(
                context.model, validation=validate(context.model),
                reconciliation=reconcile(context.model, [], []),
                element_sources=context.proposers)
            screen.require()

            items = _items_for(context.model, element_id, body, context.proposers)
            if items is None:
                return self._json(404, {
                    "error": f"no state or transition {element_id!r} in "
                             f"{context.model.id}"})

            # The same call the CLI makes. Lifecycle mutation, N-10 enforcement
            # and S-19 promotion all live in there; duplicating any of them here
            # would give this surface its own, weaker definition of "approved".
            result = apply_decisions(
                context.model,
                ReviewFile(version=FILE_VERSION, model_id=context.model.id,
                           fingerprint=model_fingerprint(context.model),
                           exported_at=datetime.now(timezone.utc).isoformat(
                               timespec="seconds"),
                           items=items, reviewer=identity.name,
                           allow_self_approval=context.allow_self_approval),
                drafted=context.drafted)
            if not result.ok:
                return self._json(409, {"error": result.blocked_reason})
            if result.refused and not result.applied:
                return self._json(403, {"error": result.refused[0][1]})

            context.commit(context, result.applied)

            decision = record_decision(
                context.audit, identity, APPROVE_MODEL, element_id,
                outcome="Approved", evidence=screen.evidence,
                rationale=body.get("rationale", ""),
                self_approval=outcome.is_self_approval, surface="web")
            promoted = [r.criterion_id for r in result.applied
                        if r.criterion_promoted_to]
            return self._json(200, {
                "recorded": True, "element_id": element_id,
                "self_approval": decision.self_approval,
                "note": outcome.reason or "",
                "at": decision.at,
                # N-5: a batch decision names what it covered.
                "applied": [r.element_id for r in result.applied],
                "refused": [{"id": e, "reason": r} for e, r in result.refused],
                "criteria_promoted": promoted,
            })

        def _name_state(self, identity: Identity, body: dict):
            require(identity, NAME_STATE)
            state_id, name = body.get("state_id", ""), body.get("name", "")
            if not name.strip():
                return self._json(400, {"error": "a name is required; a placeholder "
                                                 "never persists (X-10)"})
            screen = name_state_screen(context.model, state_id,
                                       ac_candidates=[], code_candidates=[])
            screen.require()

            decision = record_decision(
                context.audit, identity, NAME_STATE, state_id, outcome=name,
                evidence=screen.evidence, rationale=body.get("rationale", ""),
                surface="web")
            return self._json(200, {
                "recorded": True, "state_id": state_id, "name": name,
                "at": decision.at,
                "note": ("X-11: this name is not evidence that the code model and "
                         "the AC model agree"),
            })

    return Handler


def serve(context: ReviewContext, host: str = "127.0.0.1", port: int = 8731):
    """Run the review UI.

    **Loopback by default, and there is no authentication.** Identity arrives in
    a header and is trusted, which is honest for a single-operator localhost tool
    and unacceptable for anything reachable by anyone else. Widening `host`
    without putting a real authenticator in front of it would make every audit
    record unfalsifiable -- N-13 records *who*, and a header anyone can set is not
    a who.
    """
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"WARNING: binding {host}, but this server does not authenticate. "
              f"Identity is taken from the {IDENTITY_HEADER} header and trusted. "
              f"Put a real authenticator in front of it, or every audit record "
              f"it writes is unfalsifiable (N-13).")
    server = HTTPServer((host, port), make_handler(context))
    print(f"Review UI on http://{host}:{port}/  (model: {context.model.id})")
    print(f"Send {IDENTITY_HEADER} and {ROLE_HEADER} with any decision (N-13).")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return server
