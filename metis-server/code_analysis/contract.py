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

# How an outcome was linked to its entry point, weakest claim last. Named rather
# than spelled inline so a reviewer's UI, the synthesiser and the tests cannot
# drift on a string literal.
LINK_RESOLVED = "resolved"            # the call graph resolved it
LINK_AST_ENCLOSURE = "ast-enclosure"  # the enclosing control structure guards it
LINK_NAME_MATCH = "name-match"        # a disclosed name heuristic
LINK_DERIVED_VALIDATION = "derived-validation"  # declared, cause traced (see OutcomeFact)
LINK_DECLARED = "declared"            # an annotation says so; nothing was traced

# What a pack emits where a route exists but could not be resolved (T-9d). It is
# deliberately NOT "": a controller with no `@RequestMapping` at all and one
# whose mapping could not be parsed are different facts, and collapsing them is
# what hid the dual-mount defect. Declared here because Python readers must
# recognise it and until now only the Scala pack knew the string.
UNRESOLVED_PATH = "__unresolved__"


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


# Where a parameter rides on the request. Named after the HTTP position rather
# than the framework annotation, so a second frontend maps onto the same
# vocabulary instead of leaking `@RequestParam` into the model.
IN_PATH = "path"
IN_QUERY = "query"
IN_HEADER = "header"
IN_BODY = "body"
IN_FORM = "form"
# `in: cookie` is one of OpenAPI 3.0's four parameter locations, and leaving it
# out meant every cookie parameter was disclosed as unmappable and dropped. The
# adapter's own note said the right thing -- folding it into `header` would be a
# different claim about where the value rides -- but the fix for a real position
# missing from the vocabulary is to add it, not to keep reporting it.
#
# It matters for the same reason the others do: a test case has to construct the
# request, and "send this in a cookie" and "send this in a header" produce
# different requests.
IN_COOKIE = "cookie"
PARAMETER_LOCATIONS = (IN_PATH, IN_QUERY, IN_HEADER, IN_BODY, IN_FORM, IN_COOKIE)


@dataclass(frozen=True)
class ParameterFact:
    """One input an endpoint reads, Layer 2.

    **Without these a generated test cannot be executed, only described.** An
    endpoint recovered as `POST /metric` says nothing about what to send, so a
    case rendered from it can assert a status and never construct a request --
    which is why the pilot estate's `POST` transition rendered with no data
    requirement at all.

    `required` and `type_name` are FACTS from the signature; there is deliberately
    no `example` or `default_value` field. Inventing a value is what M-9 forbids:
    Métis states the requirement on the data, a person or a factory satisfies it.
    """

    name: str
    location: str                  # one of PARAMETER_LOCATIONS
    type_name: str
    required: bool = True
    # The declared constraint, verbatim (`@Size(max=64)`, `@NotNull`). Carried as
    # source text rather than parsed: a half-understood constraint asserted as
    # structure is worse than one quoted honestly.
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecurityFact:
    """What an endpoint requires of a caller, Layer 2.

    Recovered from declarative security only (`@PreAuthorize`, `@Secured`,
    `@RolesAllowed`, and any class-level equivalent). Security enforced in a
    filter chain or a gateway is **not** visible here, so an endpoint with no
    `SecurityFact` means *nothing was declared on it*, never *it is open*. The
    two are not the same claim and the second one is not ours to make.
    """

    scheme: str                    # e.g. "oauth2", "basic", "role"
    expression: str                # the declaration, verbatim
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class EndpointFact:
    """One HTTP entry point, Layer 2."""

    id: str
    http_method: str
    path: str
    handler_method_id: str
    anchor: Anchor
    # The route argument as written (`METRIC + "/{id}"`), before resolution. The
    # pack has always emitted it and the contract never declared it, so the first
    # code that rehydrated a structural report crashed on it -- the field was
    # real, only undocumented.
    path_source: str = ""
    # Everything a caller must supply. Empty means the pack recovered none --
    # which for a `POST` is a finding, not a fact about the endpoint (X-13).
    parameters: tuple[ParameterFact, ...] = ()
    security: tuple[SecurityFact, ...] = ()
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    # Who handles it. Carried as facts rather than parsed back out of
    # `handler_method_id`, whose shape is the pack's business and not a format
    # downstream code should depend on. These name the outcome states, so two
    # endpoints on one resource stay distinguishable.
    handler_type: str = ""
    handler_name: str = ""
    # What the caller gets back. `response_type` is the declaration verbatim
    # (`ResponseEntity<PageDto<ProjectDto>>`); `response_body` is what actually
    # arrives (`PageDto<ProjectDto>`), and is **empty for `Void`** -- a response
    # with no body, which is a fact and not missing information.
    #
    # Neither is available from the CPG's type information: javasrc2cpg erases
    # the generic, so `methodReturn.typeFullName` is a bare `ResponseEntity` on
    # every one of the pilot estate's 91 handlers. The pack reads the declaration text.
    response_type: str = ""
    response_body: str = ""
    # `@Valid`/`@Validated` on a bound parameter, or `@Validated` on the class.
    # This is what closes the bean-validation chain: without it a declared 400
    # can be *known to exist* and still not be attributable to payload validation
    # (spec GD-2, X-10a). False means the annotation was not found, never that
    # the endpoint accepts anything.
    validated: bool = False


@dataclass(frozen=True)
class MemberFact:
    """One field of a type, Layer 3 -- the verified registry (spec REQ-TST-008)."""

    type_name: str
    name: str
    type_full_name: str
    anchor: Anchor
    # The declaring type's FULLY-QUALIFIED name. `type_name` is the simple one,
    # and simple names collide: the pilot estate declares `PageResponse` in seven files,
    # one per feign module. Keying a graph node on the simple name fuses all
    # seven into one node that claims to be every one of them — the same defect
    # as `/project/all` and `/user/all` collapsing onto `All`.
    #
    # It is also what a parameter references: `ParameterFact.type_name` is
    # already fully qualified, so without this the two sides cannot be joined
    # without guessing.
    owner_full_name: str = ""
    # The `schema` role's facts (springdoc `@Schema`, or whatever a project
    # declares in its place). Documentation a person wrote, and two things that
    # are not documentation at all:
    #
    #   `required`     "true"/"false"/"" — and "" is a THIRD answer. "not
    #                  stated" and "stated optional" are different facts about a
    #                  payload, and collapsing them would invent a claim.
    #   `allowed_values`  an enum's values ARE its equivalence partitions, which
    #                  is a test-design input rather than a comment.
    description: str = ""
    required: str = ""
    allowed_values: tuple[str, ...] = ()
    owner_description: str = ""
    # Declared constraints on the field, verbatim (`@NotNull`, `@Size(max=64)`).
    # These are GD-3's variants: the data requirements a fixture must violate to
    # reach a validation rejection, and the reason 164 constrained fields stay
    # test data rather than becoming 164 transitions.
    #
    # **Kept alongside the typed properties below, not replaced by them** (X-6b).
    # The vocabulary Métis honours is closed, so an annotation outside it becomes
    # no property — and it has to remain visible here or it would simply vanish,
    # which is the silent-reduction failure X-5a exists to prevent.
    constraints: tuple[str, ...] = ()

    # The same constraints as **data** (X-6b). `@Size(max = 40)` is a string that
    # every consumer must re-parse, and two consumers parsing it differently is a
    # defect nobody can see; `expected_max_length = 40` is a bound a boundary
    # criterion reads directly. Absent means "not constrained that way", which is
    # why these are None rather than 0.
    #
    # `@Size` is length on a String and cardinality on a collection, and the two
    # are different things for a fixture to build, so they get different names.
    expected_min_length: int | None = None
    expected_max_length: int | None = None
    expected_min_size: int | None = None
    expected_max_size: int | None = None
    expected_min: str = ""
    expected_max: str = ""
    expected_exclusive_min: str = ""
    expected_exclusive_max: str = ""
    expected_pattern: str = ""
    expected_format: str = ""
    expected_integer_digits: int | None = None
    expected_fraction_digits: int | None = None
    expected_temporal: str = ""

    # Whether this field's type, or its owner, is an enum — so landing can write
    # `:Enum` instead of `:Class` (a specialisation replaces its parent) and a
    # field of that type can carry the constants as its partitions.
    type_is_enum: bool = False
    owner_is_enum: bool = False

    # A collection's element type, as a simple name. `type_full_name` erases the
    # generic — a `List<RecordDto>` field reports `java.util.List` — so without
    # this the nested payload edge stops at the collection and the element type,
    # which is what a fixture actually builds, is unreachable.
    element_type: str = ""


@dataclass(frozen=True)
class EntityFact:
    """A persisted type and the table it states it lives in (X-19a).

    `table` is empty where the source does not say — measured on a real service,
    `@Entity`/`@Table`/`@Column` were in **zero** files because the entities were
    in a dependency jar. Empty is the fact; a naming-strategy guess written here
    would be a plausible wrong table in the graph, and the catalogue is what
    settles it instead.
    """

    entity: str
    full_name: str
    anchor: Anchor
    table: str = ""
    columns: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RepositoryQueryFact:
    """One thing a repository asks, before any table is known (X-19a).

    `statement` is a `@Query`'s text, native or JPQL; empty means a derived
    method, whose predicates come out of the name.
    """

    repository: str
    method: str
    entity: str
    method_id: str
    anchor: Anchor
    statement: str = ""
    native: bool = False


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
    # The endpoint whose handler this condition was found in. A check whose
    # branches resolve to a status is referenced by an outcome; one whose branches
    # do not is referenced by nothing, and lands connected to nothing at all
    # without this. Both recovered checks on a real service were of that second
    # kind.
    endpoint_id: str = ""


@dataclass(frozen=True)
class ExceptionMappingFact:
    """`@ExceptionHandler(X.class)` + `@ResponseStatus(S)`, Layer 2.

    **This is what makes "which exception becomes a 400" evidence rather than
    inference.** The pilot estate's `GlobalExceptionHandler` maps four distinct exceptions
    onto 400, and only one of them (`MethodArgumentNotValidException`) is bean
    validation. Without this fact a declared 400 could only be labelled by
    guessing, and the guess would be wrong for the other three -- a test written
    from it would establish the wrong precondition and never reach the path.

    `advice_type` carries the declaring class because two `@ControllerAdvice`
    beans may handle the same exception. Where they do and neither declares an
    `@Order`, precedence is undecidable and that is a finding, never a guard.
    """

    exception_type: str
    status: int
    advice_type: str
    anchor: Anchor
    # The handler's declared response type. "" means the handler
    # genuinely returns no body, which is a different claim from not knowing.
    response_body: str = ""
    # The `@ExceptionHandler` itself. `advice_type` is the declaring class's
    # SIMPLE name and joins to nothing, so `HANDLED_BY` -- catalogued, and named
    # in EVIDENCE_LAYER as this label's reader -- could not be written.
    handler_method_id: str = ""


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
    #
    # `DERIVED_VALIDATION` is the third value, and it is deliberately narrow: a
    # declared outcome whose *cause* was traced through the bean-validation chain
    # (a `@Valid` body, a constrained DTO, and an `@ExceptionHandler` mapping that
    # exception to this status). It says more than "declared" and less than
    # "constructed" -- the outcome is annotation-sourced, the precondition is not.
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
    exception_mappings: list[ExceptionMappingFact] = field(default_factory=list)
    entities: list[EntityFact] = field(default_factory=list)
    repository_queries: list[RepositoryQueryFact] = field(default_factory=list)

    parse_errors: list[str] = field(default_factory=list)
    partial: bool = False

    # What extraction deliberately left out, and why (X-5a). A reduction nobody can see
    # is indistinguishable from a codebase that never had those elements -- the
    # same failure `partial` exists to prevent, one level down. Empty when a pack
    # filters nothing.
    filtered: dict = field(default_factory=dict)


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

    for mapping in report.exception_mappings:
        if not mapping.anchor or not mapping.anchor.file:
            errors.append(f"exception mapping {mapping.exception_type!r}: no anchor (X-6)")

    return errors


def exception_status_map(report: ExtractionReport) -> tuple[dict[str, int], list[str]]:
    """`exception type -> status`, plus the ones two advices disagree about.

    The second return value is the honest half. Where two `@ControllerAdvice`
    beans handle the same exception with **different** statuses and neither
    declares an `@Order`, Spring's choice is not statically decidable -- so the
    exception is excluded from the map and reported. A guess here would put a
    precondition on a transition that the runtime may never satisfy.

    Agreement across advices is not a conflict: the pilot estate's two beans both map
    `MethodArgumentNotValidException` to 400, so the status is certain even though
    the response body is not.
    """
    by_exception: dict[str, set[int]] = {}
    for mapping in report.exception_mappings:
        by_exception.setdefault(mapping.exception_type, set()).add(mapping.status)

    resolved = {exc: next(iter(s)) for exc, s in by_exception.items() if len(s) == 1}
    contested = sorted(exc for exc, s in by_exception.items() if len(s) > 1)
    return resolved, contested


def exception_anchors(report: ExtractionReport) -> dict[str, str]:
    """`exception type -> the @ExceptionHandler line`, for the audit trail.

    First declaration wins where several agree; a reviewer needs *a* line to open,
    and where two advices genuinely disagree `exception_status_map` has already
    excluded the exception from the map, so nothing reaches here to be anchored.
    """
    out: dict[str, str] = {}
    for mapping in report.exception_mappings:
        out.setdefault(mapping.exception_type, str(mapping.anchor))
    return out
