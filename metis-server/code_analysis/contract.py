"""
The query-pack output contract (application spec §13.4, X-3).

A query pack's job is to produce **this shape**, whatever the engine's own output
looks like. Everything downstream consumes the contract, never Joern directly.

Why the indirection is worth a module: Joern moves fast (the 2.x→4.x migration
replaced its whole storage backend), and X-3 requires the engine version to be
pinned per pack. Binding the mapper to a declared contract instead of to raw
engine output means an engine upgrade touches the pack and nothing else. Without
it, every version bump would ripple into extraction, naming and landing.

The contract is deliberately *narrower* than the CPG. It carries what §5.2 says a
model needs -- triggers, guards, outcomes, anchors -- and nothing else. A wide
contract would leak engine concepts into the ontology, which is exactly what
§13.2's sidecar rule exists to prevent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CONTRACT_VERSION = "metis.cpg-extract/1"

# Layers per §13's scope banner. 1-3 are in scope; 4-5 are the funded follow-on.
LAYER_STRUCTURAL = 1
LAYER_ENDPOINTS = 2
LAYER_TYPE_REGISTRY = 3
LAYER_TRANSITIONS = 4
LAYER_AC_MATCHING = 5


@dataclass(frozen=True)
class Anchor:
    """Where a fact came from. Required on everything (spec X-6, M-14)."""

    file: str
    line: int
    commit: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}@{self.commit}"


@dataclass(frozen=True)
class MethodFact:
    """One method, from Layer 1."""

    id: str
    name: str
    type_name: str
    signature: str
    anchor: Anchor
    is_external: bool = False


@dataclass(frozen=True)
class CallFact:
    """One resolved call edge, Layer 1."""

    caller_id: str
    callee_id: str
    anchor: Anchor


@dataclass(frozen=True)
class EndpointFact:
    """One HTTP entry point, Layer 2."""

    id: str
    http_method: str
    path: str
    handler_method_id: str
    anchor: Anchor


@dataclass(frozen=True)
class MemberFact:
    """One field of a type, Layer 3 -- the verified registry (spec REQ-TST-008)."""

    type_name: str
    name: str
    type_full_name: str
    anchor: Anchor


@dataclass(frozen=True)
class CheckFact:
    """One condition evaluated on a path, Layer 4's substrate.

    `order` is the **evaluation** order recovered from the framework chain and
    control flow -- never source line position (spec X-10d). `dimension_class`
    is filled by configuration, not by the engine (X-10b).
    """

    id: str
    expression: str
    order: int
    anchor: Anchor
    dimension_class: str | None = None


@dataclass(frozen=True)
class OutcomeFact:
    """One observable result of an entry point, Layer 4's target states.

    `signature` is what makes two outcomes distinguishable through the surface
    (spec M-3) -- for an API, status plus error discriminator.
    """

    id: str
    endpoint_id: str
    signature: str
    status: int | None = None
    discriminator: str | None = None
    guarding_check_ids: tuple[str, ...] = ()
    # "" when the guard holds, "!" when the outcome occurs on its negation.
    # Carried explicitly rather than inferred from ordering, which would be a
    # guess about branch structure.
    guard_sense: str = ""
    # How the fact was linked: "name-match" is a disclosed heuristic (generic
    # signatures do not resolve without dependencies); "declared" is an
    # annotation, not a construction. A reviewer weighs these differently.
    link: str = "resolved"
    anchor: Anchor | None = None


@dataclass
class ExtractionReport:
    """What a pack emits. Validated before it leaves the sidecar (spec X-5)."""

    contract_version: str = CONTRACT_VERSION
    pack: str = ""
    pack_version: str = ""
    engine: str = ""
    engine_version: str = ""
    repo: str = ""
    commit: str = ""
    frontend: str = ""
    layers: tuple[int, ...] = ()

    methods: list[MethodFact] = field(default_factory=list)
    calls: list[CallFact] = field(default_factory=list)
    endpoints: list[EndpointFact] = field(default_factory=list)
    members: list[MemberFact] = field(default_factory=list)
    checks: list[CheckFact] = field(default_factory=list)
    outcomes: list[OutcomeFact] = field(default_factory=list)

    parse_errors: list[str] = field(default_factory=list)
    partial: bool = False


REQUIRED_PROVENANCE = (
    "pack", "pack_version", "engine", "engine_version", "repo", "commit", "frontend",
)


def validate_report(report: ExtractionReport) -> list[str]:
    """Check a report before anything downstream consumes it.

    Two rules do the heavy lifting:

    * **X-5** a partially-parsed tree fails the run. A partial report
      under-reports, and under-reporting is indistinguishable from clean code --
      the most dangerous failure mode this pipeline has.
    * **X-6** every element carries an anchor. An element without one cannot be
      traced back, so it is not emitted at all.
    """
    errors: list[str] = []

    if report.contract_version != CONTRACT_VERSION:
        errors.append(
            f"unknown contract version {report.contract_version!r}; "
            f"expected {CONTRACT_VERSION}"
        )

    for field_name in REQUIRED_PROVENANCE:
        if not getattr(report, field_name, ""):
            errors.append(f"missing provenance: {field_name} (spec X-5)")

    if report.partial or report.parse_errors:
        errors.append(
            f"partial parse — {len(report.parse_errors)} error(s). A partial report "
            f"is refused: under-reporting is indistinguishable from clean code (X-5)"
        )

    for method in report.methods:
        if method.is_external:
            errors.append(
                f"{method.id}: external methods must be filtered in the pack, "
                f"never emitted (spec REQ-CGA-010)"
            )
        if not method.anchor.file or method.anchor.commit != report.commit:
            errors.append(f"{method.id}: anchor missing or from a different commit (X-6)")

    known_methods = {m.id for m in report.methods}
    for call in report.calls:
        for side, mid in (("caller", call.caller_id), ("callee", call.callee_id)):
            if mid not in known_methods:
                errors.append(f"call {side} {mid!r} is not an emitted method")

    for endpoint in report.endpoints:
        if endpoint.handler_method_id not in known_methods:
            errors.append(
                f"endpoint {endpoint.id}: handler {endpoint.handler_method_id!r} "
                f"is not an emitted method"
            )

    known_checks = {c.id for c in report.checks}
    for outcome in report.outcomes:
        for cid in outcome.guarding_check_ids:
            if cid not in known_checks:
                errors.append(f"outcome {outcome.id}: guard check {cid!r} not emitted")

    orders = [c.order for c in report.checks]
    if len(orders) != len(set(orders)) and report.checks:
        errors.append(
            "check evaluation order is not unique; precedence would be ambiguous "
            "(spec GD-9 requires fail-closed rather than a guessed order)"
        )

    return errors
