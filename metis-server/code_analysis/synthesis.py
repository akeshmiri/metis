"""
Layer 4 synthesis: extraction facts -> a user-perspective model
(application spec §2.1, §5.2, R4).

This is the module that delivers R4. It turns what the CPG can see -- endpoints,
conditions, response constructions -- into `State`/`Transition` objects the rest
of the system already knows how to validate, review, cover and render.

Pure: reports in, `Model` out. No session, no engine.

**Honest shape of what is recoverable.** For a REST surface the observable states
are response conditions (spec M-2), so a handler yields a one-hop machine:

    Ready --[GET /commit, t.isEmpty()]--> NoContent204
    Ready --[GET /commit, NOT t.isEmpty()]--> Ok200

That is a real machine with real guards, and it is what static analysis of a
controller can support. It is **not** a resource lifecycle -- deriving that
`POST /commit` creates what `GET /commit/{id}` later reads needs REST-convention
inference, which is a heuristic and is deliberately not done here. §5.8's limits
say only explicitly-represented behaviour is recoverable, and this is the shape
of that limit for a CRUD API.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from code_analysis.contract import (
    LINK_DECLARED,
    LINK_DERIVED_VALIDATION,
    UNRESOLVED_PATH,
    ExtractionReport,
)
from code_analysis.unfolding import resource_label, resource_noun, resource_of
from metis_mcp.mbt.model import (
    CONSTRUCTED,
    DECLARED,
    IMPLEMENTED,
    QUARANTINE,
    Model,
    State,
    Transition,
)

# The fallback pre-request condition, used only where the endpoint's path could
# not be recovered and there is therefore nothing to name a state after.
#
# **It used to be the source of every transition in the model, and that made each
# model a star.** One `Ready` with 43 edges is not a cluster, it is a hairball —
# and it was also an over-claim: a single node standing for "nothing has been
# called" simultaneously asserts that no metric exists AND no project exists AND
# no user exists. Those are separate situations and a tester establishes them
# separately.
#
# Each resource now gets its own initial state (`Metric`, `ProjectAll`,
# `TmsExecution`), so the endpoint is the cluster and the HTTP methods on it are
# the edges leaving that cluster.
INITIAL_STATE = "Ready"


def initial_state_for(trigger: str) -> str:
    """The state a call to this endpoint starts from — the resource itself.

    Keyed on the resource rather than the exact path, so `/metric` and
    `/metric/{id}` share one node: they are the same resource reached two ways,
    and separating them would put `GET /metric/{id}` in a cluster of its own
    while its own creator sat in another. `resource_of` is the same key
    `unfolding` uses, which is what makes `Metric` and `MetricPresent` a
    coherent pair rather than two unrelated names.

    **The honest limit.** For a resource with a lifecycle this state means "the
    resource does not exist yet", which is observable and establishable. For a
    computed read-only route like `/summary` it means only "nothing has been
    called yet" — a grouping rather than a distinguishable situation. Both are
    legitimate starting points for a path; only the first is a claim about the
    system's contents.
    """
    _, _, path = (trigger or "").partition(" ")
    resource = resource_of(path.strip())
    if not resource or resource == "/" or UNRESOLVED_PATH in resource:
        return INITIAL_STATE
    return resource_label(resource)

# The target state a rejection lands in. Named for what the *user* observes --
# the request was rejected -- rather than for the exception behind it, which is
# an implementation fact and is carried in the guard's anchors instead.
REJECTED_DISCRIMINATOR = "rejected"

_WORD = re.compile(r"[^A-Za-z0-9]+")

# Statuses that carry no body, per RFC 9110. The handler's declared return type
# is what it *can* return, not what THIS path returns: `getActionById` declares
# `ResponseEntity<RecordDto>` and its 204 branch sends nothing at all. Copying
# the declared type onto the 204 would tell a generated test to assert a
# `RecordDto` the caller never receives — a wrong assertion, not a vague one.
BODYLESS_STATUSES = frozenset({204, 304}) | frozenset(range(100, 200))


def response_body_for(status: int | None, declared: str) -> str:
    """The body this outcome actually carries, not the one the signature allows."""
    return "" if (status or 0) in BODYLESS_STATUSES else declared


def state_name(status: int, discriminator: str) -> str:
    """Tier-2 naming from a code convention (spec X-7).

    `noContent` + 204 -> `NoContent204`. The helper's own name is the convention;
    nothing is invented. A human may rename it at review (tier 3).
    """
    parts = [p for p in _WORD.split(discriminator or "") if p]
    label = "".join(p[:1].upper() + p[1:] for p in parts) or "Outcome"
    return f"{label}{status}"


def outcome_state_for(endpoint: dict | None, status: int, discriminator: str) -> str:
    """One outcome state per endpoint (spec M-3).

    **These used to converge: every 200 in a model was one `Ok200` node.** The
    reasoning was that a response is indistinguishable to a caller whichever
    endpoint produced it -- which is false as soon as you look at the body. The
    pack now recovers it, and `GET /environment/{id}` returns an
    `EnvironmentDto` where `GET /environment/all` returns a
    `PageDto<EnvironmentDto>`: 48 distinct body types across 91 endpoints.

    It is the stronger claim even where two responses ARE byte-identical. A
    state is the situation the system is left in, not the bytes on the wire:
    after `POST /environment` an environment exists, after `POST /project` a
    project does, and both return `ResponseEntity<Void>`. Those are different
    situations and a later GET tells them apart, so merging them on the response
    alone erased a distinction the surface really does expose.

    **Named from the ROUTE, because that is what two intakes agree on** (I-2).
    It was named from the handler — `EnvironmentController.getById` + 200 ->
    `EnvironmentGetByIdOk200` — and every ingredient of that is representation:
    the controller class, the method name, and the discriminator the pack chose.
    Describe the same service twice and none of them survives. Measured on the
    demo corpus, `GET /record/page` -> 200:

        code intake     RecordPageOk200
        OpenAPI intake  DefaultPageRecordsAPageOfRecords200

    One endpoint, two nodes, and the graph then says the service has twice the
    behaviour it has. The route and the status are the observable facts both
    carry, so `GetRecordPage200` is what both produce.

    The prefix stays load-bearing for the reason it always was — `save`,
    `getById` and `getAll` recur in every controller — and the route separates
    them at least as well: `POST /project` and `POST /user` are different routes
    before they are different methods.

    The **verb** is part of it because a state is the situation the system is
    left in, not the bytes on the wire: after `PUT /record/{id}` the record is
    changed and after `GET /record/{id}` it is not, and both answer 200.

    `discriminator` survives only as the fallback when no endpoint is known,
    which is the one case where there is no route to name.
    """
    if not endpoint:
        return state_name(status, discriminator)
    verb = (endpoint.get("http_method") or "").lower()
    path = endpoint.get("path") or ""
    parts = [p for p in _WORD.split(f"{verb} {path}") if p and not p.startswith("{")]
    label = "".join(p[:1].upper() + p[1:] for p in parts) or "Outcome"
    return f"{label}{status}"


@dataclass(frozen=True)
class Rejection:
    """One negative user path, planned before any transition is built."""

    endpoint_id: str
    trigger: str
    status: int
    # `payload_valid` where the cause was traced, `request_accepted` where only
    # the annotation is known. The transition's guard is its negation.
    expression: str
    claim: str
    anchor: str = ""
    constraints: tuple[str, ...] = ()
    inputs: tuple = ()
    security: tuple = ()
    media_types: tuple = ()
    # The endpoint dict, so the rejection's outcome state is named for the same
    # handler its success is. Without it every rejection in a model collapsed
    # back onto one shared `Rejected400`.
    endpoint: dict | None = None
    # `(type_name, field_name)` per constrained field, and the ExceptionMapping
    # node id where the cause was traced. Both are evidence a derived rejection
    # points AT, rather than quotes.
    fields: tuple = ()
    exception_ref: str = ""
    # The body this rejection actually returns, from the exception handler's own
    # return type. "" means no claim is made — not "no body".
    response_body: str = ""


def _plan_rejections(behaviour: ExtractionReport, endpoint_by_handler: dict,
                     declared: dict, constructed: dict,
                     structural, result: "SynthesisResult") -> dict[str, Rejection]:
    """Which endpoints have a declared rejection, and how precisely it is known.

    **Every declared rejection becomes a path.** What varies is the precondition:
    where the bean-validation chain closes it is `NOT (payload_valid)` with four
    anchors; where it does not it is `NOT (request_accepted)`, which says exactly
    what the `@ApiResponse` says and names no cause. A path with the weaker
    precondition is a real use case with a vague setup, not a lesser element --
    an acceptance criterion or a person can sharpen it later, and reconciliation
    attaches that to this same transition (§4.3).

    Two exclusions, both deliberate:

    * **2xx.** A declared 200 that no construction was recovered for is a
      *recovery gap* -- the response helper is outside the analysis unit (O-2c) --
      and it is already reported as a finding. Turning it into a guarded
      transition would model a success the pack failed to find as a conditional
      behaviour, which is a different and false claim.
    * **already constructed.** Three endpoints declare a 409 and also build it,
      with a real `ast-enclosure` guard. The declaration duplicates a transition
      that exists; taking both would produce two transitions for one behaviour,
      one of them guarded on a minted atom.
    """
    from code_analysis.contract import exception_anchors, exception_status_map
    from code_analysis.dimension_recovery import (
        BEAN_VALIDATION_EXCEPTION,
        recover_chain,
    )

    checks_by_endpoint: dict[str, list] = {}
    for outcome in behaviour.outcomes:
        for cid in outcome.guarding_check_ids or ():
            checks_by_endpoint.setdefault(outcome.endpoint_id, []).append(cid)

    all_checks = {c.id: c for c in behaviour.checks}
    members = list(getattr(structural, "members", ()) or ())
    if structural is not None:
        status_map, contested = exception_status_map(structural)
        anchors = exception_anchors(structural)
        for exception in contested:
            # X-13 / GD-9: two advices disagree and neither declares an order.
            # Reported, never resolved by picking one -- the whole point of the
            # exception map is that the cause is evidence rather than a guess.
            result.findings.append(
                f"{exception} is mapped to more than one status by different "
                f"@ControllerAdvice beans with no @Order; precedence is not "
                f"statically decidable, so no rejection is attributed to it")
    else:
        status_map, anchors = {}, {}

    declared_anchor_by_endpoint = {
        o.endpoint_id: str(o.anchor) for o in behaviour.outcomes
        if o.discriminator == "declared" and getattr(o, "anchor", None)
    }

    # **A controller's own `@ExceptionHandler` is a declared rejection for its
    # endpoints.** Spring scopes an in-controller handler to that controller, so
    # `@ExceptionHandler(RecordConflictException)` returning 400 in
    # `RecordController` means every endpoint on that controller can answer
    # 400. Nothing else says so: demo_project/records-service annotates only `@ApiResponse(200)`,
    # so `declared` held no rejection at all and the service modelled as twelve
    # transitions and no error path whatever.
    #
    # Scoped to the DECLARING class, never estate-wide. A `@ControllerAdvice`
    # bean applies globally and is a different claim; attributing one
    # controller's handler to every endpoint would invent rejections that cannot
    # occur, which is worse than missing them.
    declared = {k: set(v) for k, v in declared.items()}
    scoped = 0
    # `endpoint_id -> [(exception, advice)]`, so a scoped rejection can name its
    # cause instead of falling back to the anonymous `NOT (request_accepted)`.
    # "RecordConflictException is thrown" is a setup a tester can build;
    # "the request was not accepted" is not.
    scoped_cause: dict[str, list] = {}
    # An `@ControllerAdvice` bean applies to every controller, so nothing in the
    # annotations says which endpoints can reach its throw. Those mappings are
    # therefore not attributed -- but they were *extracted*, and dropping them
    # without a word is how a recovered 404 disappears between two stages while
    # both report success. Collected here and reported below.
    unattributed: list[tuple[str, int, str]] = []
    for fact in list(getattr(structural, "exception_mappings", ()) or ()):
        advice = getattr(fact, "advice_type", "")
        status = getattr(fact, "status", None)
        if not advice or status is None or 200 <= status < 300:
            continue
        if not any(e.get("handler_type") == advice
                   for e in endpoint_by_handler.values()):
            unattributed.append(
                (getattr(fact, "exception_type", ""), status, advice))
        for handler, endpoint in endpoint_by_handler.items():
            if endpoint.get("handler_type") != advice:
                continue
            for outcome_id in (o.endpoint_id for o in behaviour.outcomes
                               if o.endpoint_id.rsplit("::", 1)[0] == handler):
                if status not in declared.get(outcome_id, set()):
                    declared.setdefault(outcome_id, set()).add(status)
                    scoped += 1
                scoped_cause.setdefault(outcome_id, []).append(
                    (getattr(fact, "exception_type", ""), advice,
                     getattr(fact, "response_body", "")))
    for exception, status, advice in sorted(set(unattributed)):
        result.findings.append(
            f"{exception} -> {status} is declared by {advice}, which is an "
            f"estate-wide @ControllerAdvice: it applies to every controller, so "
            f"nothing here says which endpoints can reach the throw. The mapping "
            f"is recovered and NOT modelled as a transition — attributing it to "
            f"all of them would invent rejections that cannot occur. An "
            f"acceptance criterion naming the endpoint would settle it")
    if scoped:
        result.findings.append(
            f"{scoped} rejection(s) attributed from in-controller "
            f"@ExceptionHandler scope — Spring applies a controller's own "
            f"handler to its own endpoints. Weigh them: the handler exists, and "
            f"whether a given endpoint can reach the throw is not established "
            f"here")

    planned: dict[str, Rejection] = {}
    for endpoint_id in sorted(declared):
        rejected = sorted(s for s in declared[endpoint_id]
                          if not (200 <= s < 300)
                          and s not in constructed.get(endpoint_id, set()))
        if not rejected:
            continue
        if len(rejected) > 1:
            # More than one declared rejection on one endpoint would need an
            # ordered chain to separate them, and nothing in the annotations
            # provides one. Reported rather than guessed at (GD-9).
            result.findings.append(
                f"{endpoint_id}: declares {rejected} rejections; only the first is "
                f"modelled — separating them needs a precedence the annotations "
                f"do not carry")
        status = rejected[0]

        handler = endpoint_id.rsplit("::", 1)[0]
        endpoint = endpoint_by_handler.get(handler)
        if endpoint is None:
            result.findings.append(
                f"{endpoint_id}: declares {status} but its endpoint was not "
                f"recovered by the structural pack; no rejection path is modelled "
                f"because the trigger is unknown")
            continue

        own_checks = [all_checks[cid] for cid in checks_by_endpoint.get(endpoint_id, ())
                      if cid in all_checks]
        recovery = recover_chain(
            endpoint, own_checks, members, status_map, status,
            declared_anchor=declared_anchor_by_endpoint.get(endpoint_id, ""),
            exception_anchors=anchors)

        if recovery.has_validation:
            claim, anchor = LINK_DERIVED_VALIDATION, recovery.validation.anchor
        else:
            claim = LINK_DECLARED
            anchor = declared_anchor_by_endpoint.get(endpoint_id, "")
            result.findings.append(
                f"{endpoint_id}: {status} modelled with the precondition "
                f"'{recovery.rejection_expression()}' — {recovery.reason}. The path "
                f"is real; its setup is not yet specific enough to build a fixture "
                f"from, and an acceptance criterion can sharpen it")

        # A scoped rejection knows its cause where exactly one exception in the
        # controller produces this status. Two would mean guessing which, and
        # GD-9 refuses that — the generic precondition stays and says so.
        expression = recovery.rejection_expression()
        causes = {c for c, _, _ in scoped_cause.get(endpoint_id, ())
                  if c and c != BEAN_VALIDATION_EXCEPTION}
        # **The rejection's body is the HANDLER's return type, not the
        # endpoint's.** A 400 built by `handleX` returning
        # `ResponseEntity<ErrorDto>` has that body; taking the
        # endpoint's success type would be wrong, and taking nothing is worse —
        # landing documents an empty `response_body` as meaning NO body, so a
        # generated case asserted an empty payload against a populated one.
        #
        # Where the handlers disagree, no claim is made rather than picking.
        scoped_bodies = {b for _, _, b in scoped_cause.get(endpoint_id, ()) if b}
        rejection_body = scoped_bodies.pop() if len(scoped_bodies) == 1 else ""
        scoped_ref = ""
        if not recovery.has_validation and causes:
            if len(causes) == 1:
                cause = next(iter(causes))
                expression = f"{cause} is thrown"
                advice = next(a for c, a, _ in scoped_cause[endpoint_id]
                              if c == cause)
                from metis_mcp.model_sources.raw_landing import mapping_id

                scoped_ref = mapping_id(getattr(structural, "repo", "") or "repo",
                                        cause, advice)
                claim = "advice-scope"
            else:
                result.findings.append(
                    f"{endpoint_id}: {len(causes)} exceptions in this controller "
                    f"produce {status} ({', '.join(sorted(causes))}); which one a "
                    f"given call raises is not statically decidable, so the "
                    f"precondition stays generic (GD-9)")

        exception_ref = scoped_ref
        if recovery.has_validation:
            from metis_mcp.model_sources.raw_landing import mapping_id
            advice = next((m.advice_type for m in
                           getattr(structural, "exception_mappings", ()) or ()
                           if m.exception_type == BEAN_VALIDATION_EXCEPTION), "")
            exception_ref = mapping_id(getattr(structural, "repo", "") or "repo",
                                       BEAN_VALIDATION_EXCEPTION, advice)

        planned[endpoint_id] = Rejection(
            endpoint_id=endpoint_id,
            trigger=f"{endpoint['http_method']} {endpoint['path']}",
            status=status, expression=expression,
            claim=claim, anchor=anchor, constraints=recovery.constraints,
            inputs=tuple(endpoint.get("parameters", ())),
            security=tuple(endpoint.get("security", ())),
            media_types=tuple(endpoint.get("produces", ())),
            endpoint=endpoint, fields=recovery.fields,
            exception_ref=exception_ref, response_body=rejection_body)

    return planned


@dataclass
class SynthesisResult:
    model: Model | None = None
    findings: list[str] = field(default_factory=list)
    unguarded: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.model is not None and not self.errors


def synthesise(behaviour: ExtractionReport, endpoints: list[dict],
               journey: str, surface: str = "api",
               unfold_resources: bool = True,
               structural: ExtractionReport | None = None) -> SynthesisResult:
    """Build a model from Layer 4 facts plus Layer 2's endpoints.

    `endpoints` comes from the structural pack's mapped output, keyed by the same
    handler id the behaviour pack used, so the two packs join without either
    knowing about the other.

    `structural` is that same pack's full report. It carries the two facts the
    endpoint dicts alone cannot supply -- the Layer 3 member constraints and the
    `@ExceptionHandler` map -- and without it a declared rejection can still be
    modelled, just never attributed to payload validation.
    """
    result = SynthesisResult()
    repo = getattr(behaviour, "repo", "") or getattr(structural, "repo", "") or "repo"
    known_types, types_by_simple = (declared_types(structural)
                                    if structural is not None else (set(), {}))

    if not behaviour.outcomes:
        # Distinguishable from "no behaviour": say which it is (spec §5.8).
        result.errors.append(
            "no outcomes recovered. Either the analysis unit excludes the module "
            "constructing responses (spec O-2c), or the framework config does not "
            "match this stack (X-4). It is not evidence that the service has no behaviour."
        )
        return result

    checks = {c.id: c for c in behaviour.checks}
    endpoint_by_handler = {}
    for e in endpoints:
        # The structural pack emits `handler_method_id`. This module previously
        # read `handler`, and its own fixture used that name too -- so the tests
        # passed against a shape the pack has never produced. Caught by running
        # the real pack output through it, not by a test. Both names are accepted
        # so a pack at either version still resolves.
        key = e.get("handler_method_id") or e.get("handler")
        if key:
            endpoint_by_handler[key] = e

    states: dict[str, State] = {}
    transitions: dict[str, Transition] = {}

    def start_of(trigger: str) -> str:
        """The resource's own initial state, created on first use.

        Every one of these is initial: a tester establishes "no metric exists"
        and "no project exists" the same way and independently, so there is no
        ordering between them to express (P-8). `check_reachability` and
        `path_generation` both already seed from every initial state, so more
        than one has always been supported -- nothing had ever produced one.
        """
        sid = initial_state_for(trigger)
        if sid not in states:
            states[sid] = State(id=sid, name=sid, surface=surface,
                                is_initial=True, lifecycle_state=QUARANTINE)
        return sid

    # Declared (@ApiResponse) versus constructed (actual code) -- compared, not
    # merged. Where they disagree that is a finding, not something to reconcile.
    declared: dict[str, set[int]] = {}
    constructed: dict[str, set[int]] = {}

    for outcome in behaviour.outcomes:
        if outcome.status is not None:
            bucket = declared if outcome.discriminator == "declared" else constructed
            bucket.setdefault(outcome.endpoint_id, set()).add(outcome.status)

    # Which endpoints gain a rejection path, and what atom expresses it. Decided
    # before any transition is built, because the answer changes the guard on the
    # endpoint's EXISTING transitions too: a guarded rejection beside an unguarded
    # success is a determinism conflict, and a blocking one.
    rejections = _plan_rejections(behaviour, endpoint_by_handler, declared,
                                  constructed, structural, result)

    for outcome in behaviour.outcomes:
        endpoint_id = outcome.endpoint_id
        if outcome.discriminator == "declared":
            continue  # handled by `rejections`; a declaration is not a construction

        handler = endpoint_id.rsplit("::", 1)[0]
        endpoint = endpoint_by_handler.get(handler)
        trigger = (f"{endpoint['http_method']} {endpoint['path']}"
                   if endpoint else endpoint_id.rsplit("::", 1)[-1])

        target = outcome_state_for(endpoint, outcome.status or 0,
                                   outcome.discriminator or "")
        if target not in states:
            states[target] = State(id=target, name=target, surface=surface,
                                   lifecycle_state=QUARANTINE)

        guard = ""
        guard_anchor = ""
        if outcome.guarding_check_ids:
            present = [checks[cid] for cid in outcome.guarding_check_ids if cid in checks]
            sense = getattr(outcome, "guard_sense", "")
            guard = " AND ".join(
                (f"NOT ({c.expression})" if sense == "!" else c.expression)
                for c in present
            )
            # Spec §8.5 / T-9a: a guard is only auditable if you can find the line
            # it came from. The pack has always emitted these anchors and this
            # function has always discarded them, so a reviewer asked to confirm
            # `t.isEmpty()` had no way to reach the code that says it.
            guard_anchor = ", ".join(
                str(c.anchor) for c in present if getattr(c, "anchor", None))
        else:
            result.unguarded.append(f"{trigger} -> {target}")

        # GD-2/GD-4: reaching any constructed outcome means every earlier
        # dimension passed. Applied only where a rejection actually exists --
        # prefixing an endpoint that has no negative path would stale its review
        # (N-14) and buy nothing.
        rejection = rejections.get(endpoint_id)
        if rejection is not None:
            guard = (f"{rejection.expression} AND {guard}" if guard
                     else rejection.expression)
            guard_anchor = ", ".join(
                a for a in (rejection.anchor, guard_anchor) if a)

        tid = f"{endpoint_id}->{target}"
        transitions[tid] = Transition(
            id=tid, source=start_of(trigger), trigger=trigger, target=target,
            guard=guard, implementation_status=IMPLEMENTED, lifecycle_state=QUARANTINE,
            guard_anchor=guard_anchor, outcome_status=outcome.status,
            inputs=tuple(endpoint.get("parameters", ())) if endpoint else (),
            security=tuple(endpoint.get("security", ())) if endpoint else (),
            response_body=response_body_for(
                outcome.status, (endpoint or {}).get("response_body", "")),
            media_types=tuple((endpoint or {}).get("produces", ())),
            evidence=_evidence_for(
                repo, endpoint, outcome,
                checks=[checks[cid] for cid in (outcome.guarding_check_ids or ())
                        if cid in checks],
                declared=known_types, by_simple=types_by_simple),
        )

    for endpoint_id, rejection in sorted(rejections.items()):
        target = outcome_state_for(rejection.endpoint, rejection.status,
                                   REJECTED_DISCRIMINATOR)
        if target not in states:
            states[target] = State(id=target, name=target, surface=surface,
                                   lifecycle_state=QUARANTINE)
        tid = f"{endpoint_id}->{target}"
        transitions[tid] = Transition(
            id=tid, source=start_of(rejection.trigger), trigger=rejection.trigger,
            target=target,
            guard=f"NOT ({rejection.expression})",
            implementation_status=IMPLEMENTED, lifecycle_state=QUARANTINE,
            guard_anchor=rejection.anchor, outcome_status=rejection.status,
            inputs=rejection.inputs, security=rejection.security,
            data_requirements=rejection.constraints,
            outcome_source=DECLARED, guard_claim=rejection.claim,
            evidence=_evidence_for(repo, rejection.endpoint,
                                   rejection=rejection, declared=known_types,
                                   by_simple=types_by_simple),
            # A rejection's body is the framework's error shape, not the
            # ENDPOINT's declared type -- claiming `EnvironmentDto` here would
            # tell a test to assert a body the caller never receives.
            #
            # Where the exception handler's own return type is known, that IS
            # the error shape and it is used: `handleRecordConflictException`
            # returns `ResponseEntity<ErrorDto>`, so the 400 carries
            # `ErrorDto`. Leaving it empty was not neutral — landing
            # documents an empty `response_body` as meaning NO body, so twelve
            # generated cases would have asserted an empty payload against a
            # populated one. "" now means only that no handler stated it.
            response_body=rejection.response_body,
            media_types=rejection.media_types,
        )

    for endpoint_id in sorted(set(declared) | set(constructed)):
        d, c = declared.get(endpoint_id, set()), constructed.get(endpoint_id, set())
        # A status that BECAME a rejection transition is no longer "not
        # recovered", and saying so would make this finding contradict the model
        # it was produced alongside: a reviewer would read "the 400 was not
        # recovered" while looking at the 400's own transition.
        modelled = ({rejections[endpoint_id].status}
                    if endpoint_id in rejections else set())
        only_declared = sorted(d - c - modelled)
        if not only_declared:
            continue
        if c:
            # Deliberately not called a defect. A status declared but not
            # constructed *in the handler* is most often produced by a framework
            # exception handler elsewhere -- which is real behaviour this pack
            # cannot see, not a contradiction. Claiming a disagreement here would
            # manufacture a defect out of a recovery limitation. It is surfaced
            # for triage, with both readings named.
            result.findings.append(
                f"{endpoint_id}: declares {sorted(d)}, constructed {sorted(c)}. "
                f"Not recovered: {only_declared} — either produced by a framework "
                f"exception handler outside this method, or genuinely absent. "
                f"Needs triage; this pack cannot distinguish them."
            )
        else:
            result.findings.append(
                f"{endpoint_id}: declares {sorted(d)} but no construction was "
                f"recovered — the response helper may be outside the analysis unit (O-2c)"
            )

    if unfold_resources:
        # M-6: resource existence is bounded, enumerable, durable and observable,
        # so it becomes a state rather than staying a guard. Without this every
        # model is a star and no generated path ever has a setup step.
        from code_analysis.unfolding import unfold

        unfolded = unfold(states, transitions, surface=surface)
        states, transitions = unfolded.states, unfolded.transitions
        result.findings.extend(unfolded.findings)
        for tid, why in unfolded.unresolved:
            # §5.8: reported, never given a guessed source state.
            result.findings.append(f"{tid}: source state unresolved — {why}")

    # Guard wording LAST, after unfolding has finished rewriting guards. M-7
    # strips the unfolded atom and `_drop_redundant_absence` strips the other
    # side, so wording computed earlier would describe conditions the final
    # model no longer carries.
    _word_guards(states, transitions)

    result.model = Model(id=f"{journey}-{surface}", states=states, transitions=transitions)
    return result


def declared_types(structural) -> tuple[set[str], dict[str, str]]:
    """`(fully-qualified names, simple -> the one FQN declaring it)`.

    A `Class` node exists only for these, so an evidence reference to anything
    else would be an edge to a node that never exists. `List`, `Set` and
    `java.lang.Long` are external and REQ-CGA-010 refuses to stub them.

    **Derived exactly as `raw_landing` derives it**, because two definitions of
    "which types exist" is how a derivation edge silently points at nothing.
    """
    from metis_mcp.model_sources.raw_landing import _index_by_simple

    names: set[str] = set()
    for member in getattr(structural, "members", ()) or ():
        owner = getattr(member, "owner_full_name", "") or getattr(member, "type_name", "")
        if owner:
            names.add(owner)
    for method in getattr(structural, "methods", ()) or ():
        mid = getattr(method, "id", "")
        fq = mid.rsplit(":", 1)[0].rsplit(".", 1)[0] if ":" in mid else ""
        if fq:
            names.add(fq)
    return names, _index_by_simple(names)


def _evidence_for(repo: str, endpoint: dict | None, outcome=None,
                  checks=(), rejection=None,
                  declared: set[str] | None = None,
                  by_simple: dict | None = None) -> tuple:
    """`(label, node_id)` pairs into the evidence layer (spec D-14).

    Computed here, where the raw facts are still in hand. By the time a model
    reaches landing it holds only ids and names, so a transition that did not
    record its evidence on the way through can never recover it.

    Ids come from `raw_landing`'s own functions rather than being re-derived,
    because two definitions of "the id of this endpoint" is how a derivation edge
    silently points at nothing.
    """
    from metis_mcp.model_sources import raw_landing as raw

    pairs: list[tuple[str, str]] = []
    if endpoint:
        # Same key as `raw_landing`, service included: `GET /summary` exists in
        # two deployables, and an unscoped id points one service's transition at
        # another service's endpoint.
        eid = raw.endpoint_id(repo, endpoint["http_method"], endpoint["path"],
                              raw.service_of(endpoint.get("anchor")))
        pairs.append(("Endpoint", eid))
        for parameter in endpoint.get("parameters", ()) or ():
            pairs.append(("Parameter", raw.parameter_id(
                repo, eid, parameter.get("name", ""), parameter.get("location", ""))))
        for cid in raw.resolve_class(repo, endpoint.get("response_body", ""),
                                     declared or set(), by_simple or {}):
            pairs.append(("Class", cid))

    if outcome is not None:
        pairs.append(("DeclaredOutcome", raw.outcome_id_for(repo, outcome)))
    for check in checks:
        pairs.append(("Check", raw.check_id(repo, check.id, check.expression)))
    if rejection is not None and rejection.exception_ref:
        pairs.append(("ExceptionMapping", rejection.exception_ref))

    return tuple(dict.fromkeys(pairs))


def _type_names(expression: str) -> list[str]:
    from metis_mcp.model_sources.raw_landing import type_names_in
    return type_names_in(expression)


def _word_guards(states: dict, transitions: dict) -> None:
    """Say every guard in business language, recording the tier (X-7, X-8).

    The raw `guard` is never touched. It is the auditable fact anchored to a
    line of code; this is a rendering beside it, exactly as `name` is a rendering
    beside a content-derived `id` (D-8).
    """
    from dataclasses import replace as _replace

    from metis_mcp.mbt.guard_language import TIER_CODE_CONVENTION, describe_guard

    for tid, transition in list(transitions.items()):
        _, _, path = (transition.trigger or "").partition(" ")
        wording = describe_guard(transition.guard, resource_noun(resource_of(path)))
        transitions[tid] = _replace(
            transition, guard_wording=wording.text, guard_tier=wording.tier,
            # Tier 2 is what synthesis can produce: the code's own vocabulary,
            # decoded and rearranged. Tier 1 arrives later, from a confirmed
            # acceptance criterion, and overwrites this.
            name_tier=transition.name_tier or TIER_CODE_CONVENTION)

    for sid, state in list(states.items()):
        states[sid] = _replace(state, name_tier=state.name_tier or TIER_CODE_CONVENTION)
