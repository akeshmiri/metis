"""
Map a query-pack report onto the ontology (application spec §13.2, §13.5-13.7).

The sidecar's CPG never enters the Métis graph -- only ontology-shaped results do
(spec X-2). This module is that boundary, and it is pure: report in, candidate
nodes and edges out, no session.

What it produces today (Layers 1-3, §13's scope banner):

    Layer 1  structural    -- retained as anchors, not as graph nodes
    Layer 2  endpoints     -- entry points, which become transition triggers
    Layer 3  type registry -- the verified field set REQ-TST-008 gates generation on

Layer 4 (state-transition recovery) is deferred, and `plan_transitions` states
that explicitly rather than returning an empty result that would read as "no
behaviour found".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from code_analysis.contract import ExtractionReport, validate_report


@dataclass(frozen=True)
class TypeRegistryEntry:
    """One type and its verified fields (spec §13.7, REQ-TST-012).

    This is what turns Atlas's prose rule -- "no UNVERIFIED fields in payloads" --
    into a mechanical check: a field absent here fails generation rather than
    warning.
    """

    type_name: str
    fields: dict[str, str]          # field name -> declared type
    anchor: str

    def has(self, field_name: str) -> bool:
        return field_name in self.fields


@dataclass
class MappedReport:
    repo: str = ""
    commit: str = ""
    endpoints: list[dict] = field(default_factory=list)
    registry: dict[str, TypeRegistryEntry] = field(default_factory=dict)
    anchors: dict[str, str] = field(default_factory=dict)   # method id -> anchor
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        return not self.errors


def map_report(report: ExtractionReport) -> MappedReport:
    """Validate, then project onto ontology-shaped results.

    Refuses outright on a report that fails validation: an invalid report must
    not be partially consumed, because the parts that look fine are exactly the
    parts that would silently under-report (X-5).
    """
    mapped = MappedReport(repo=report.repo, commit=report.commit)

    errors = validate_report(report)
    if errors:
        mapped.errors = errors
        return mapped

    for method in report.methods:
        mapped.anchors[method.id] = str(method.anchor)

    for endpoint in report.endpoints:
        mapped.endpoints.append({
            "id": endpoint.id,
            "http_method": endpoint.http_method,
            "path": endpoint.path,
            "handler": endpoint.handler_method_id,
            "anchor": str(endpoint.anchor),
            # Carried through, not projected away. This mapping used to keep five
            # keys, so anything the pack learned about what a caller must send was
            # discarded one hop after it was recovered.
            "parameters": [
                {"name": p.name, "location": p.location, "type_name": p.type_name,
                 "required": p.required, "constraints": list(p.constraints)}
                for p in endpoint.parameters
            ],
            "security": [
                {"scheme": s.scheme, "expression": s.expression, "roles": list(s.roles)}
                for s in endpoint.security
            ],
            "consumes": list(endpoint.consumes),
            "produces": list(endpoint.produces),
        })

    by_type: dict[str, dict[str, str]] = {}
    anchors: dict[str, str] = {}
    for member in report.members:
        by_type.setdefault(member.type_name, {})[member.name] = member.type_full_name
        anchors.setdefault(member.type_name, str(member.anchor))
    for type_name, fields in by_type.items():
        mapped.registry[type_name] = TypeRegistryEntry(
            type_name=type_name, fields=fields, anchor=anchors[type_name],
        )

    if not report.endpoints:
        # Reported rather than silently producing nothing: an absent entry point
        # means the framework config did not match, which is a configuration
        # problem, not an empty service (spec X-4).
        mapped.notes.append(
            "no endpoints recovered — check the framework configuration matches "
            "this stack (spec X-4); an unrecognised framework is reported, never guessed"
        )

    return mapped


def verify_fields(mapped: MappedReport, type_name: str,
                  field_names: list[str]) -> tuple[bool, list[str]]:
    """Gate for generation (spec REQ-TST-008, REQ-CGA-012).

    Returns (ok, unverified). A type absent from the registry fails *closed*: an
    unknown type is not evidence that its fields exist.
    """
    entry = mapped.registry.get(type_name)
    if entry is None:
        return False, list(field_names)
    unverified = [f for f in field_names if not entry.has(f)]
    return not unverified, unverified


class LayerNotImplemented(NotImplementedError):
    """Raised for a deferred layer, carrying why and what it needs."""


MULTI_MODULE_WARNING = (
    "guards may be unrecoverable: response construction is commonly delegated to "
    "a shared utility module. If that module is outside the analysed unit, its "
    "methods resolve as <unresolvedSignature> and the condition selecting between "
    "outcomes cannot be recovered. Analyse the multi-module build, not one module."
)


def analysis_unit_is_sufficient(report: ExtractionReport) -> tuple[bool, str]:
    """Whether guards are recoverable from this report's analysis unit.

    A measured finding, not a theoretical one. Extracting `athena-boot-git` alone
    left `ResponseEntityUtils.okOrNoContent` unresolved, so the condition
    selecting 200 from 204 was invisible. Adding `athena-common` recovered
    `return t.isEmpty() ? noContent() : ok(t)` -- the guard itself.

    Detecting this *before* Layer 4 runs matters: otherwise it reports zero guards
    and someone reads that as "this service has no conditions".
    """
    emitted = {m.id for m in report.methods}
    unresolved = [c.callee_id for c in report.calls if c.callee_id not in emitted]
    if unresolved:
        return False, (f"{len(unresolved)} call(s) resolve outside the analysis unit. "
                       + MULTI_MODULE_WARNING)
    return True, ""


def plan_transitions(report: ExtractionReport):
    """Layer 4 -- state-transition recovery. **Not yet built.**

    Raising is deliberate. Returning an empty transition list would be
    indistinguishable from "this service has no recoverable behaviour", and that
    ambiguity is precisely what let R4 be dropped once already.

    What a measured probe of the pilot target established:

      * Outcomes ARE declared -- `@ApiResponse(responseCode = ...)` yields 200,
        204, 201 and 400 on the real controllers. Those become target states.
      * Guards are recoverable ONLY when the analysis unit includes the module
        where response construction lives (`analysis_unit_is_sufficient`).
      * Source states need the fixpoint pass; the probe neither confirms nor
        contradicts that.
    """
    sufficient, reason = analysis_unit_is_sufficient(report)
    raise LayerNotImplemented(
        "Layer 4 (state-transition extraction) is not built yet. It needs the "
        "six-step state-variable abstraction, dimension precedence recovery and "
        "the naming cascade (application spec §5.2-§5.4a).\n"
        f"Analysis unit sufficient for guard recovery: {sufficient}"
        + (f"\n  {reason}" if reason else "")
    )
