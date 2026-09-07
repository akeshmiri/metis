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

**Decisions are authenticated; reads are not.** This surface used to trust
`X-Metis-User` and `X-Metis-Role` outright, which defeated N-10, the role table
and the audit record together: all six of §9.1's decisions arrive here, and any
of them could be attributed to anybody by typing a name. `_identity` now
resolves the actor through `api/auth.py` -- the same credential store, the same
constant-time comparison the HTTP API uses -- so there is one authentication
implementation behind two transports rather than two ideas of what identity is.

`do_GET` is deliberately untouched. Reading a model is not a decision, and a
bearer token on page navigation would make the UI unusable in a browser. With no
credential store configured the surface still serves everything and refuses to
take a decision, which is the same shape as the refusal it already gives when it
has nowhere to store one.

**Still not a public surface**, for a different reason: it binds loopback by
default and serves every requirement, criterion and specification in the graph
to whoever reaches it. `--host` warns when that is widened.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable
from html import escape as html_escape
from urllib.parse import parse_qs, quote, urlparse

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
    DEFER,
    FILE_VERSION,
    REJECT,
    confirm_match,
    decide_drift,
    resolve_divergence,
    ReviewFile,
    ReviewItem,
    apply as apply_decisions,
    model_fingerprint,
)
from metis_mcp.review.roles import (
    APPROVE_MODEL,
    CONFIRM_MATCH,
    DECIDE_DRIFT,
    NAME_STATE,
    RESOLVE_DIVERGENCE,
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
    confirm_match_screen,
    decide_drift_screen,
    name_state_screen,
    resolve_divergence_screen,
)
from metis_mcp.review_ui import pages, resolve, sessions
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

    # The durable store for §9.1's decisions 3, 4 and 5. Injected for exactly
    # the reason `commit` is: this module must not know where the state lives,
    # and must know that *somewhere* is. A context without both is read-only for
    # those three, and the handlers refuse rather than returning 200 for a
    # decision they cannot keep -- the failure `commit` was added to fix.
    review_state: "ReviewState | None" = None
    save_state: "Callable[[ReviewState], None] | None" = None

    # What `review_ui/resolve.py` needs to draw the decisions that have no page.
    # Empty by default and empty is honest: a context constructed without them
    # renders the refusal naming what is absent, rather than a partial screen.
    criteria: list = field(default_factory=list)
    validating: dict = field(default_factory=dict)

    # Browser sessions. On the context rather than module-level so two servers
    # in one process (which the test suite runs) cannot see each other's
    # logins, and so a test can assert what is open.
    sessions: sessions.SessionStore = field(
        default_factory=sessions.SessionStore)

    def ledger(self):
        return build_ledger(self.model, generate(self.model, self.criterion,
                                                 self.max_setup))


def _items_for(model: Model, element_id: str, body: dict,
               proposers: dict[str, str],
               element_ids=None, decision: str = APPROVE) -> list[ReviewItem] | None:
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
            kind=kind, id=eid, decision=decision,
            current_state=element.lifecycle_state,
            rationale=body.get("rationale", ""),
            proposed_by=proposers.get(eid),
            criterion_id=body.get("criterion_id"),
            criterion_text=body.get("criterion_text"),
            affirmed_as_intent=bool(body.get("affirmed_as_intent", False)),
        )

    # **A chosen subset, which is the case the old form could not express.**
    # It offered one element or the whole model, so a reviewer happy with thirty
    # of forty had to submit thirty times with thirty rationales — while
    # approving all forty took one click. That made the blanket decision the
    # cheapest action available and the considered one the most expensive, which
    # is exactly backwards for a gate.
    chosen = [e for e in (element_ids or []) if e]
    if chosen:
        picked = []
        for eid in chosen:
            state = model.states.get(eid)
            if state is not None:
                picked.append(one("state", eid, state))
                continue
            transition = model.transitions.get(eid)
            if transition is None:
                return None
            picked.append(one("transition", eid, transition))
        return picked

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


def _recorded(payload: dict) -> str:
    """One sentence describing what was just recorded.

    **Says what was decided, not that something was** (N-5). A batch approval
    that answered only "done" would be exactly the batch blindness the rule
    forbids, so the count and the element come back with it.
    """
    element = payload.get("element_id", "")
    if payload.get("approved") is not None:
        return f"Recorded: {payload['approved']} element(s) approved."
    applied = payload.get("applied")
    if isinstance(applied, list):
        return f"Recorded: {len(applied)} element(s) approved ({element})."
    if payload.get("name"):
        return f"Recorded: {element} named {payload['name']!r}. Naming is not approval (M-14)."
    return f"Recorded: {element}." if element else "Recorded."


def _identity(headers) -> Identity:
    """Who is deciding — from a credential, never from a header they chose.

    **This surface trusted `X-Metis-User` and its own docstring said that was
    "unacceptable for anything else".** It was the last decision surface to do
    so, and it was the one that mattered most: all six of §9.1's decisions go
    through here, while the authenticated HTTP API exposes one. N-10 (the
    proposer may not approve), the five-role capability table and the
    evidence-fingerprint audit record were all defeated by typing a different
    name into a header.

    **The rule is imported, not invented.** `policy.py` already settled it for
    the MCP write surface: *an asserted name is enough to author at Quarantine
    and is not enough to pass a gate (N-10).* Every route that reaches this
    function is a decision, so every one of them needs a verified identity.
    `api/auth.py` is the one implementation -- one credential store, one
    constant-time comparison, two transports. A second check here would be a
    second thing to keep correct, which is how the two surfaces disagreed in the
    first place.

    **Reads are untouched.** `do_GET` never calls this: looking at a model on
    your own machine is not a decision, and requiring a bearer token on page
    navigation would make the UI unusable in a browser and get this reverted.
    The surface degrades to read-only, which is the same shape as the refusal it
    already gives when it has nowhere to store a decision.

    The name and role come from the STORE. A header that disagrees is not
    preferred and not merged -- it is refused, exactly as `policy.authorise`
    refuses an `actor` argument that contradicts the credential.
    """
    from metis_mcp.api import auth

    try:
        identity = auth.authenticate(headers.get(auth.HEADER, ""))
    except auth.AuthenticationRequired as e:
        raise NotPermitted(
            f"this review session cannot take a decision: {e} Reading is "
            f"unaffected — the model, the evidence and the coverage figures are "
            f"all still served. An asserted name is enough to author at "
            f"Quarantine and is not enough to pass a gate (N-10, O-4c).")
    except auth.AuthenticationFailed as e:
        raise NotPermitted(f"{e} (N-13)")

    # A header that disagrees with the credential is a mistake worth naming: the
    # caller believes they are acting as somebody they are not, and silently
    # using the credential would record a decision under a name they did not
    # expect to see in the audit trail.
    asserted = (headers.get(IDENTITY_HEADER) or "").strip()
    if asserted and asserted != identity.name:
        raise NotPermitted(
            f"the credential is {identity.name!r} and {IDENTITY_HEADER} says "
            f"{asserted!r}. The credential decides who is acting; a header does "
            f"not override it (N-13, O-4c)")
    asserted_role = (headers.get(ROLE_HEADER) or "").strip()
    if asserted_role and asserted_role != identity.role:
        raise NotPermitted(
            f"{identity.name!r} is a {identity.role} in the credential store "
            f"and {ROLE_HEADER} says {asserted_role!r}. Roles come from the "
            f"store, not from the caller (N-1)")
    return identity


def _json_param(query: dict, name: str):
    """A JSON-encoded query parameter, or None when absent.

    None rather than `{}`: `Screen` distinguishes evidence that is missing from
    evidence that is empty, and N-4 blocks on the first. Collapsing them would
    let a screen render with an empty `code_side` and call itself decidable.
    """
    raw = (query.get(name) or [""])[0]
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _drift_item(query: dict):
    """The minimum a drift screen needs, rebuilt from the query.

    A real `DriftItem` comes from `drift.compare` against a ledger this server
    does not hold. Rather than fabricate one, the caller passes what it has and
    `Screen.require()` blocks if that is not enough -- which is the same
    contract every other screen here works under.
    """
    from metis_mcp.publishing.drift import DriftItem

    case_id = (query.get("case") or [""])[0]
    drift_class = (query.get("class") or [""])[0]
    if not case_id or not drift_class:
        return None
    return DriftItem(
        case_id=case_id, drift_class=drift_class,
        action=(query.get("action") or ["propose_nothing"])[0],
        diff=tuple(_json_param(query, "diff") or ()),
        detail=(query.get("detail") or [""])[0])


def make_handler(context: ReviewContext):
    class Handler(BaseHTTPRequestHandler):
        server_version = "metis-review/1"

        def log_message(self, *args):        # noqa: D102 - quiet by default
            pass

        # ---------------- helpers ----------------

        def _send(self, code: int, body: str, content_type: str,
                  extra: tuple = ()) -> None:
            payload = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            # No external asset is ever loaded (see view.py), so the policy can
            # be this tight without breaking the page.
            #
            # `form-action 'self'` is explicit rather than inherited: it does
            # NOT fall back to `default-src`, so without it the decision forms
            # would be governed by nothing. `script-src` stays absent -- the
            # decision pages use plain forms precisely so it can (pages.py).
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; style-src 'unsafe-inline'; "
                             "img-src data:; form-action 'self'")
            for name, value in extra:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

        def _html(self, code: int, body: str, extra: tuple = ()) -> None:
            self._send(code, body, "text/html", extra)

        def _redirect(self, location: str, extra: tuple = ()) -> None:
            """POST-then-redirect, so a refresh does not re-submit a decision."""
            self.send_response(303)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            for name, value in extra:
                self.send_header(name, value)
            self.end_headers()

        #: Fields a decision form may legitimately repeat. Everything else stays
        #: one value per key, for the reason `_form` gives: silently keeping the
        #: last of a duplicated field hides a form bug rather than surfacing it.
        #: A checkbox list is the one place repetition is the point, so it is
        #: named here rather than allowed everywhere.
        REPEATABLE = ("element_ids",)

        def _form(self) -> dict:
            """A form-encoded body as the same flat dict the JSON routes take.

            One value per key except for `REPEATABLE`, which comes back as a
            list. That exception is declared rather than general: a decision body
            repeating a field it should not is a bug, and collapsing it silently
            is how that bug reaches a decision record.
            """
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            raw = self.rfile.read(length).decode("utf-8", "replace")
            parsed = parse_qs(raw, keep_blank_values=True)
            return {k: (v if k in self.REPEATABLE else v[0])
                    for k, v in parsed.items()}

        def _session_identity(self):
            """The signed-in reviewer, or None. Never raises.

            A browser that is not signed in gets the login page, not a 401 body
            it cannot read -- and reading is unaffected either way.
            """
            sid = sessions.cookie_value(self.headers.get("Cookie", ""))
            return context.sessions.get(sid)

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
                # ---- the rendered decision surface (§9.3) ----
                #
                # Separate paths from `/api/*` on purpose: those speak JSON and
                # take a bearer token, these speak HTML and take a session
                # cookie. Same handlers underneath, so neither can develop its
                # own idea of what a decision is.
                if route.path == "/login":
                    return self._html(200, pages.login_page(
                        next_path=(query.get("next") or ["/model"])[0]))

                if route.path == "/logout":
                    sid = sessions.cookie_value(self.headers.get("Cookie", ""))
                    context.sessions.close(sid)
                    return self._redirect("/model",
                                          (("Set-Cookie", sessions.clear_cookie()),))

                if route.path == "/queue":
                    # Needs no graph and no model: run records are files. So the
                    # queue answers on a deployment where every model read
                    # returns 204 — a gate somebody owes a decision on does not
                    # stop mattering because Neo4j is down.
                    import json as _json_mod

                    from metis_mcp import server as tools

                    payload = _json_mod.loads(tools.decision_queue(
                        workflow=(query.get("workflow") or [""])[0]))
                    return self._html(200, pages.queue_page(
                        payload.get("waiting") or [],
                        self._session_identity(),
                        payload.get("by_workflow") or {}))

                if route.path == "/decide/confirm-match":
                    # **The first of the four to get a page**, because it is the
                    # one fillable from a review session: the model is loaded and
                    # the pre-filter is pure. The other three need a live read —
                    # a tracker, or a generation run — and say so rather than
                    # rendering half a screen.
                    who = self._session_identity()
                    if who is None:
                        return self._redirect(
                            "/login?next=/decide/confirm-match")
                    ac_id = (query.get("ac") or [""])[0]
                    transition_id = (query.get("transition") or [""])[0]
                    provided, missing = resolve.for_confirm_match(
                        context.model, ac_id, transition_id, context.criteria)
                    if missing:
                        return self._html(409, pages.unfillable_page(
                            "confirm match", f"{ac_id} -> {transition_id}",
                            missing,
                            resolve.describe("confirm_match", missing), who))
                    return self._html(200, pages.confirm_match_page(
                        ac_id, transition_id, provided, who,
                        result=(query.get("done") or [""])[0]))

                if route.path == "/decide/approve":
                    who = self._session_identity()
                    if who is None:
                        return self._redirect("/login?next=/decide/approve")
                    screen = approve_model_screen(
                        context.model, validation=validate(context.model),
                        reconciliation=reconcile(context.model, [], []),
                        element_sources=context.proposers)
                    return self._html(200 if screen.can_decide else 409,
                                      pages.approve_page(
                                          context.model, screen, who,
                                          context.model.unapproved_elements(),
                                          result=(query.get("done") or [""])[0]))

                if route.path == "/decide/name-state":
                    who = self._session_identity()
                    if who is None:
                        return self._redirect("/login?next=/decide/name-state")
                    state_id = (query.get("state") or [""])[0]
                    screen = (name_state_screen(context.model, state_id,
                                                ac_candidates=[],
                                                code_candidates=[])
                              if state_id else None)
                    return self._html(200, pages.name_state_page(
                        context.model, state_id, screen, who,
                        result=(query.get("done") or [""])[0]))

                if route.path == "/audit":
                    who = self._session_identity()
                    if who is None:
                        return self._redirect("/login?next=/audit")
                    return self._html(200, pages.audit_page(
                        context.audit.to_json_ready(),
                        [d.element_id for d in context.audit.self_approvals()],
                        who, context.model.id))

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

                if route.path == "/api/screen/divergence":
                    element_id = (query.get("element") or [""])[0]
                    screen = resolve_divergence_screen(
                        element_id,
                        code_side=_json_param(query, "code_side"),
                        ac_side=_json_param(query, "ac_side"),
                        blocked_paths=_json_param(query, "blocked_paths"))
                    return self._screen(screen)

                if route.path == "/api/screen/match":
                    ac_id = (query.get("ac") or [""])[0]
                    transition_id = (query.get("transition") or [""])[0]
                    screen = confirm_match_screen(
                        context.model, ac_id,
                        ac_text=(query.get("ac_text") or [""])[0],
                        transition_id=transition_id,
                        code_anchor=(query.get("anchor") or [""])[0],
                        why_proposed=_json_param(query, "why_proposed"))
                    return self._screen(screen)

                if route.path == "/api/screen/drift":
                    item = _drift_item(query)
                    if item is None:
                        return self._json(400, {
                            "error": "a drift screen needs the item it is about: "
                                     "?case=<id>&class=<drift class>"})
                    screen = decide_drift_screen(
                        item,
                        published_content=(query.get("published") or [""])[0],
                        last_generated=(query.get("last_generated") or [""])[0],
                        newly_generated=(query.get("newly_generated") or [""])[0])
                    return self._screen(screen)

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

            # ---- the form surface ----
            #
            # Handled before `_identity`, because these establish or use a
            # session rather than presenting a bearer token. Everything they
            # then call is the same code the JSON routes call.
            if route.path == "/login":
                return self._login()
            if route.path.startswith("/decide/"):
                return self._form_decision(route.path)

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
                if route.path == "/api/decide/divergence":
                    return self._resolve_divergence(identity, body)
                if route.path == "/api/decide/match":
                    return self._confirm_match(identity, body)
                if route.path == "/api/decide/drift":
                    return self._decide_drift(identity, body)
                return self._json(404, {"error": f"no route {route.path}"})
            except NotPermitted as e:
                return self._json(403, {"error": str(e)})
            except EvidenceMissing as e:
                # N-4: a screen that cannot show its evidence blocks the decision.
                return self._json(409, {"error": str(e)})
            except Exception as e:                    # noqa: BLE001
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})

        # ---------------- the form surface ----------------

        def _login(self):
            """Exchange a token for a session.

            The token is verified by `api/auth.py` -- the same call `_identity`
            makes for a bearer credential -- and then discarded. What the cookie
            names is a row holding the `Identity` that verification produced, so
            there is still one authentication implementation and this only
            remembers its answer.
            """
            from metis_mcp.api import auth

            form = self._form()
            destination = form.get("next") or "/model"
            # Only ever a path on this server. A caller-supplied absolute URL
            # here would make the login form an open redirect.
            if not destination.startswith("/") or destination.startswith("//"):
                destination = "/model"

            token = (form.get("token") or "").strip()
            if not token:
                return self._html(400, pages.login_page(
                    "No token given. Reading the model needs none; deciding does.",
                    destination))
            try:
                identity = auth.authenticate(f"{auth.SCHEME} {token}")
            except (auth.AuthenticationRequired, auth.AuthenticationFailed) as e:
                # Deliberately the same page for "no store configured" and "wrong
                # token": which half of the guess was right is not the caller's
                # business, and `auth` already makes that distinction internally.
                return self._html(401, pages.login_page(str(e), destination))

            sid = context.sessions.open(identity)
            return self._redirect(destination,
                                  (("Set-Cookie", sessions.set_cookie(sid)),))

        def _form_decision(self, path: str):
            """A rendered decision, applied through the JSON handlers.

            **It reuses `_approve` rather than reimplementing it**, which is the
            whole point: N-1 says every surface produces the same audit record,
            and a second application path here would be a second definition of
            what an approval does. The JSON handler writes a JSON response; this
            captures it and answers with a redirect so a refresh cannot
            re-submit.
            """
            who = self._session_identity()
            if who is None:
                return self._redirect(f"/login?next={path}")

            form = self._form()
            captured: dict = {}

            def capture(code, payload):
                captured["code"] = code
                captured["payload"] = payload

            real_json = self._json
            self._json = capture                       # type: ignore[assignment]
            try:
                if path == "/decide/approve":
                    self._approve(who, form)
                    back = "/decide/approve"
                elif path == "/decide/name-state":
                    self._name_state(who, form)
                    back = f"/decide/name-state?state={quote(form.get('state_id', ''))}"
                else:
                    self._json = real_json             # type: ignore[assignment]
                    return self._html(404, pages.page(
                        "No such decision",
                        f'<div class="blocked">no route {html_escape(path)}</div>'))
            except NotPermitted as e:
                self._json = real_json                 # type: ignore[assignment]
                return self._html(403, pages.page(
                    "Not permitted",
                    f'<div class="blocked">{html_escape(str(e))}</div>'
                    f'{pages.nav(context.model.id)}', who))
            except EvidenceMissing as e:
                # N-4 through the rendered surface: the refusal is the page.
                self._json = real_json                 # type: ignore[assignment]
                return self._html(409, pages.page(
                    "Cannot decide yet",
                    f'<div class="blocked">{html_escape(str(e))}</div>'
                    f'{pages.nav(context.model.id)}', who))
            finally:
                self._json = real_json                 # type: ignore[assignment]

            code = captured.get("code", 500)
            payload = captured.get("payload", {})
            if code != 200:
                return self._html(code, pages.page(
                    "Not recorded",
                    f'<div class="blocked">'
                    f'{html_escape(str(payload.get("error", payload)))}</div>'
                    f'{pages.nav(context.model.id)}', who))

            return self._redirect(f"{back}?done={quote(_recorded(payload))}")

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

            # `defer` is what makes approving the rest safe: a reviewer unsure
            # about three of forty can say so and approve the thirty-seven,
            # instead of either blessing all forty or grinding through them one
            # at a time. `apply_decisions` already required a rationale for
            # anything but approve, so nothing is looser here.
            decision = str(body.get("decision") or APPROVE).strip().lower()
            if decision not in (APPROVE, REJECT, DEFER):
                return self._json(400, {
                    "error": f"unknown decision {decision!r}; "
                             f"expected one of {APPROVE}, {REJECT}, {DEFER}"})

            items = _items_for(context.model, element_id, body,
                               context.proposers,
                               element_ids=body.get("element_ids"),
                               decision=decision)
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

            recorded = record_decision(
                context.audit, identity, APPROVE_MODEL, element_id,
                outcome=decision.capitalize(), evidence=screen.evidence,
                # N-13/N-14. `Screen.fingerprint` was written for exactly this
                # and had no caller on this surface: every web decision recorded
                # an EMPTY fingerprint while its docstring explained why the
                # field is what makes an audit answerable. N-1 says every surface
                # produces the same record, and only `policy.py` did.
                evidence_fingerprint=screen.fingerprint(),
                rationale=body.get("rationale", ""),
                self_approval=outcome.is_self_approval, surface="web")
            promoted = [r.criterion_id for r in result.applied
                        if r.criterion_promoted_to]
            return self._json(200, {
                "recorded": True, "element_id": element_id,
                "decision": decision,
                "self_approval": recorded.self_approval,
                "note": outcome.reason or "",
                "at": recorded.at,
                # N-5: a batch decision names what it covered.
                "applied": [r.element_id for r in result.applied],
                "refused": [{"id": e, "reason": r} for e, r in result.refused],
                "criteria_promoted": promoted,
            })

        def _screen(self, screen):
            """One shape for every screen response, blocking on missing evidence.

            N-4 lives here: a screen that cannot show what §9.3 requires returns
            409 rather than a partial page. Factored out when the three
            remaining decisions were served, because four handlers repeating the
            same five keys is four chances for one of them to answer 200 with an
            incomplete screen.
            """
            return self._json(200 if screen.can_decide else 409, {
                "decision": screen.decision,
                "can_decide": screen.can_decide,
                "blocked_reason": screen.blocked_reason,
                "evidence": screen.evidence,
                "notes": screen.notes,
            })

        def _durable(self):
            """The review state, or the 409 that says why there is none."""
            if context.review_state is None or context.save_state is None:
                return None, self._json(409, {
                    "error": "this review session is read-only — no review-state "
                             "target was configured, so a decision could not be "
                             "stored. Nothing was changed (N-1)."})
            return context.review_state, None

        def _decided(self, identity, capability, screen, result, kind, element_id,
                     outcome, rationale):
            """Persist, audit and answer. Shared by the three decisions below.

            Every step is the one `_approve` takes and in the same order, because
            each refuses for a different reason and the order is what makes the
            refusals meaningful: capability, then evidence, then the decision,
            then the record.
            """
            if not result.ok:
                return self._json(409, {"error": result.blocked_reason})
            context.save_state(context.review_state)
            decision = record_decision(
                context.audit, identity, capability, element_id,
                outcome=outcome, evidence=screen.evidence,
                evidence_fingerprint=screen.fingerprint(),
                rationale=rationale, surface="web")
            return self._json(200, {"recorded": True, "kind": kind,
                                    "element_id": element_id,
                                    "outcome": outcome, "at": decision.at})

        def _resolve_divergence(self, identity: Identity, body: dict):
            require(identity, RESOLVE_DIVERGENCE)
            state, refusal = self._durable()
            if refusal is not None:
                return refusal

            element_id = body.get("element_id", "")
            screen = resolve_divergence_screen(
                element_id, code_side=body.get("code_side"),
                ac_side=body.get("ac_side"),
                blocked_paths=body.get("blocked_paths"))
            screen.require()

            result = resolve_divergence(
                state, element_id, body.get("choice", ""),
                body.get("rationale", ""), actor=identity.name,
                fingerprint=screen.fingerprint())
            return self._decided(identity, RESOLVE_DIVERGENCE, screen, result,
                                 "divergence", element_id,
                                 body.get("choice", ""), body.get("rationale", ""))

        def _confirm_match(self, identity: Identity, body: dict):
            require(identity, CONFIRM_MATCH)
            state, refusal = self._durable()
            if refusal is not None:
                return refusal

            ac_id = body.get("ac_id", "")
            transition_id = body.get("transition_id", "")
            screen = confirm_match_screen(
                context.model, ac_id, body.get("ac_text", ""), transition_id,
                code_anchor=body.get("code_anchor", ""),
                why_proposed=body.get("why_proposed"))
            screen.require()

            confirmed = bool(body.get("confirmed", True))
            result = confirm_match(
                state, ac_id, transition_id, confirmed,
                rationale=body.get("rationale", ""), actor=identity.name,
                fingerprint=screen.fingerprint())
            return self._decided(
                identity, CONFIRM_MATCH, screen, result, "match",
                f"{ac_id}->{transition_id}",
                "confirmed" if confirmed else "rejected",
                body.get("rationale", ""))

        def _decide_drift(self, identity: Identity, body: dict):
            require(identity, DECIDE_DRIFT)
            state, refusal = self._durable()
            if refusal is not None:
                return refusal

            from metis_mcp.publishing.drift import DriftItem

            case_id = body.get("case_id", "")
            item = DriftItem(case_id=case_id,
                             drift_class=body.get("drift_class", ""),
                             action=body.get("action", "propose_nothing"),
                             detail=body.get("detail", ""),
                             diff=tuple(body.get("diff") or ()))
            screen = decide_drift_screen(
                item, published_content=body.get("published", ""),
                last_generated=body.get("last_generated", ""),
                newly_generated=body.get("newly_generated", ""))
            screen.require()

            resolution = body.get("resolution", "")
            result = decide_drift(state, case_id, resolution,
                                  rationale=body.get("rationale", ""),
                                  actor=identity.name,
                                  fingerprint=screen.fingerprint())
            return self._decided(identity, DECIDE_DRIFT, screen, result, "drift",
                                 case_id, resolution, body.get("rationale", ""))

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
                evidence=screen.evidence,
                evidence_fingerprint=screen.fingerprint(),
                rationale=body.get("rationale", ""),
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

    **Loopback by default. Decisions need a credential; reads do not.**
    `_identity` resolves the actor through `api/auth.py`, so an audit record
    names somebody who presented a token rather than somebody who typed a name.
    Reads stay open on the bound interface, which is why widening `host` is still
    a disclosure decision even though decisions are now authenticated: this
    serves every requirement, criterion and specification in the graph.
    """
    from metis_mcp.api import auth

    decisions_possible = bool(os.environ.get(auth.TOKENS_ENV, "").strip())
    if not decisions_possible:
        # Announced at startup rather than discovered on the first POST. A
        # reviewer who has read a screen and formed a judgement should not learn
        # only then that nothing can record it.
        print(f"NOTE: no credential store — ${auth.TOKENS_ENV} is unset, so this "
              f"session is READ-ONLY. Everything is served; no decision can be "
              f"taken. Point {auth.TOKENS_ENV} at a file of "
              f"`sha256<TAB>name<TAB>role` lines to enable the six decisions.")

    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"WARNING: binding {host}. Decisions are authenticated, but READS "
              f"are not: this serves every requirement, criterion and "
              f"specification in the graph to whoever reaches it. Put something "
              f"authenticating in front of it before exposing this interface.")
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
