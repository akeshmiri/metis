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

from code_analysis.contract import ExtractionReport
from metis_mcp.mbt.model import IMPLEMENTED, QUARANTINE, Model, State, Transition

# The pre-request condition. Synthetic, and named so it is obvious: no response
# has been produced yet. Every generated path starts here (spec P-8).
INITIAL_STATE = "Ready"

_WORD = re.compile(r"[^A-Za-z0-9]+")


def state_name(status: int, discriminator: str) -> str:
    """Tier-2 naming from a code convention (spec X-7).

    `noContent` + 204 -> `NoContent204`. The helper's own name is the convention;
    nothing is invented. A human may rename it at review (tier 3).
    """
    parts = [p for p in _WORD.split(discriminator or "") if p]
    label = "".join(p[:1].upper() + p[1:] for p in parts) or "Outcome"
    return f"{label}{status}"


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
               journey: str, surface: str = "api") -> SynthesisResult:
    """Build a model from Layer 4 facts plus Layer 2's endpoints.

    `endpoints` comes from the structural pack's mapped output, keyed by the same
    handler id the behaviour pack used, so the two packs join without either
    knowing about the other.
    """
    result = SynthesisResult()

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

    states: dict[str, State] = {
        INITIAL_STATE: State(id=INITIAL_STATE, name=INITIAL_STATE, surface=surface,
                             is_initial=True, lifecycle_state=QUARANTINE)
    }
    transitions: dict[str, Transition] = {}

    # Declared (@ApiResponse) versus constructed (actual code) -- compared, not
    # merged. Where they disagree that is a finding, not something to reconcile.
    declared: dict[str, set[int]] = {}
    constructed: dict[str, set[int]] = {}

    for outcome in behaviour.outcomes:
        endpoint_id = outcome.endpoint_id
        bucket = declared if outcome.discriminator == "declared" else constructed
        if outcome.status is not None:
            bucket.setdefault(endpoint_id, set()).add(outcome.status)

        if outcome.discriminator == "declared":
            continue  # declared outcomes are evidence, not transitions

        handler = endpoint_id.rsplit("::", 1)[0]
        endpoint = endpoint_by_handler.get(handler)
        trigger = (f"{endpoint['http_method']} {endpoint['path']}"
                   if endpoint else endpoint_id.rsplit("::", 1)[-1])

        target = state_name(outcome.status or 0, outcome.discriminator or "")
        if target not in states:
            states[target] = State(id=target, name=target, surface=surface,
                                   lifecycle_state=QUARANTINE)

        guard = ""
        if outcome.guarding_check_ids:
            expressions = [checks[cid].expression for cid in outcome.guarding_check_ids
                           if cid in checks]
            sense = getattr(outcome, "guard_sense", "")
            guard = " AND ".join(
                (f"NOT ({e})" if sense == "!" else e) for e in expressions
            )
        else:
            result.unguarded.append(f"{trigger} -> {target}")

        tid = f"{endpoint_id}->{target}"
        transitions[tid] = Transition(
            id=tid, source=INITIAL_STATE, trigger=trigger, target=target,
            guard=guard, implementation_status=IMPLEMENTED, lifecycle_state=QUARANTINE,
        )

    for endpoint_id in sorted(set(declared) | set(constructed)):
        d, c = declared.get(endpoint_id, set()), constructed.get(endpoint_id, set())
        if d and c and d != c:
            # Deliberately not called a defect. A status declared but not
            # constructed *in the handler* is most often produced by a framework
            # exception handler elsewhere (a validation 400, say) -- which is real
            # behaviour this pack cannot see, not a contradiction. Claiming a
            # disagreement here would manufacture a defect out of a recovery
            # limitation. It is surfaced for triage, with both readings named.
            only_declared = sorted(d - c)
            result.findings.append(
                f"{endpoint_id}: declares {sorted(d)}, constructed {sorted(c)}. "
                f"Not recovered: {only_declared} — either produced by a framework "
                f"exception handler outside this method, or genuinely absent. "
                f"Needs triage; this pack cannot distinguish them."
            )
        elif d and not c:
            result.findings.append(
                f"{endpoint_id}: declares {sorted(d)} but no construction was "
                f"recovered — the response helper may be outside the analysis unit (O-2c)"
            )

    result.model = Model(id=f"{journey}-{surface}", states=states, transitions=transitions)
    return result
