"""
OpenAPI → the extraction contract (application spec §5.2, §4.6a; X-2, X-5, X-6).

**The one adapter the API side was missing.** `raw_landing` already writes
`Endpoint`, `Parameter`, `Field`, `DeclaredOutcome` and `Class` — which is
precisely what an OpenAPI document contains — but it consumes
`contract.ExtractionReport`, and nothing mapped a specification into one. The
swagger extractor that exists lives in a skill and emits UIF, whose landing path
has no implementation. So OpenAPI stopped at the engine boundary.

**What this changes, and why it is the component level.** An OpenAPI document is
the contract: every endpoint, every parameter, every constraint, every declared
response. Criteria at that level are derivable, so they are **generated, never
authored** — writing by hand what a contract already states invites drift against
the contract, and S-19's `code_derived` grade already describes exactly what such
a criterion is worth. The *system* level — the preconditions that produce a given
set of parameters — is not in the document and never will be; that is what the
knowledge file and its Gherkin form are for.

**X-2 holds here as it does for Joern.** No OpenAPI vocabulary reaches the graph:
what lands is the same normalised contract a code pack emits, so a document in
Swagger 2.0 or OpenAPI 3.1 produces the same node shapes as a Java controller.

**Three honest limits, stated rather than discovered later.**

1. **A response is DECLARED, never constructed.** Every outcome is emitted with
   `link=LINK_DECLARED`, so a reviewer weighs it as an annotation — which it is.
   A document saying a 403 exists is not evidence that any code path produces one.
2. **No guards.** A document declares *which* statuses occur and never *when*.
   The transitions synthesised from this carry empty guards, and
   `check_guard_completeness` will correctly report that. That is the tool
   working: the contract genuinely does not contain the conditions.
3. **`in: cookie` now has a home.** It is one of OpenAPI 3.0's four parameter
   locations and it used to be absent from the contract's vocabulary, so every
   cookie parameter was disclosed as unmappable -- a required one refusing the
   whole document, an optional one becoming a note.

   The reasoning for not folding it into `header` was right and still holds: a
   cookie and a header are different claims about where the value rides, and a
   generated request has to construct one or the other. The error was treating a
   real position as an unmappable one. `IN_COOKIE` is now first-class, so a
   cookie parameter lands like any other and neither blocks nor warns.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from code_analysis.contract import (
    IN_COOKIE,
    CONTRACT_VERSION,
    LAYER_TRANSITIONS,
    CheckFact,
    IN_BODY,
    IN_FORM,
    IN_HEADER,
    IN_PATH,
    IN_QUERY,
    LAYER_ENDPOINTS,
    LAYER_STRUCTURAL,
    LAYER_TYPE_REGISTRY,
    LINK_DECLARED,
    Anchor,
    EndpointFact,
    ExtractionReport,
    MemberFact,
    MethodFact,
    OutcomeFact,
    ParameterFact,
    SecurityFact,
)

PACK = "openapi-document"
PACK_VERSION = "1"
ENGINE = "openapi"
FRONTEND = "openapi"

# OpenAPI's `in:` values that map onto an HTTP position the contract names.
_LOCATIONS = {"path": IN_PATH, "query": IN_QUERY, "header": IN_HEADER,
              "formData": IN_FORM, "cookie": IN_COOKIE}

# Schema keywords that constrain a value. Carried as `keyword: value` source
# text, in OpenAPI's own vocabulary — never rewritten into a Java annotation,
# which would claim the document said something it did not.
_CONSTRAINT_KEYWORDS = (
    "maxLength", "minLength", "pattern", "format", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "maxItems", "minItems",
    "uniqueItems", "enum",
)

_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


class OpenAPIRefused(Exception):
    """The document could not be read at all — shape, not content."""


@dataclass
class AdapterResult:
    """The report, and what was disclosed but did not invalidate it.

    Two channels on purpose. `report.parse_errors` is X-5's: anything there stops
    the run. `notes` is for a limitation that is real, named, and does not make
    the report wrong -- an optional cookie parameter nothing has to send. Putting
    both in one list would either block real documents on a technicality or bury
    a genuine gap among advisories, and this codebase keeps "this is wrong" and
    "this is worth knowing" apart everywhere else (M-17's third outcome).
    """

    report: ExtractionReport
    notes: list[str] = field(default_factory=list)


def _pointer(*parts: str) -> str:
    """A JSON Pointer, RFC 6901-escaped. This is the anchor's locator.

    A YAML/JSON document has no line number without a position-tracking parser,
    and `Anchor.line` is an int. Rather than invent a line, the pointer rides in
    `Anchor.file` -- `openapi.yaml#/paths/~1metric~1{id}/get` resolves exactly and
    is what a reviewer opens. `line` is 0, meaning *not applicable*, and this
    comment is the only place that claim is made.
    """
    escaped = [p.replace("~", "~0").replace("/", "~1") for p in parts]
    return "/" + "/".join(escaped) if escaped else ""


def _schema_of(node: dict, spec: dict) -> dict:
    """Resolve a `$ref` one hop. Returns `{}` for anything it cannot follow.

    Deliberately one hop and local-only. A remote `$ref` is a document this
    process has not read, and following it would either fetch over the network
    from a build step or silently produce an empty schema. Both are worse than
    reporting it.
    """
    if not isinstance(node, dict):
        return {}
    ref = node.get("$ref")
    if not ref:
        return node
    if not ref.startswith("#/"):
        return {}
    target = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, dict) or part not in target:
            return {}
        target = target[part]
    return target if isinstance(target, dict) else {}


def _ref_name(node: dict) -> str:
    """`#/components/schemas/MetricDto` -> `MetricDto`. Empty when inline."""
    ref = (node or {}).get("$ref", "")
    return ref.rsplit("/", 1)[-1] if ref.startswith("#/") else ""


def constraints_of(schema: dict, *, required: bool = False) -> tuple[str, ...]:
    """The declared constraints, as source text (GD-3's variants).

    These are what a fixture must violate to reach a validation rejection, which
    is why they stay data rather than becoming transitions of their own.
    """
    out = []
    if required:
        out.append("required")
    for keyword in _CONSTRAINT_KEYWORDS:
        if keyword in schema:
            value = schema[keyword]
            if isinstance(value, list):
                value = "|".join(str(v) for v in value)
            out.append(f"{keyword}: {value}")
    if schema.get("nullable") is False:
        out.append("nullable: false")
    return tuple(out)


def _type_name(schema: dict) -> str:
    """The declared type. A `$ref` name where there is one, else the primitive."""
    name = _ref_name(schema)
    if name:
        return name
    items = schema.get("items")
    if schema.get("type") == "array" and isinstance(items, dict):
        inner = _ref_name(items) or items.get("type", "object")
        return f"array<{inner}>"
    return schema.get("type", "object")


def _operation_id(method: str, path: str, operation: dict) -> str:
    """The document's own `operationId`, or a deterministic stand-in.

    A stand-in rather than a refusal: `operationId` is optional in OpenAPI and
    plenty of real documents omit it, but `validate_report` requires every
    endpoint's handler to be an emitted method. The id is derived from the two
    things that are always present and always unique together.
    """
    declared = operation.get("operationId")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    return f"{method.lower()}:{path}"


def _security_facts(names: list, spec: dict) -> tuple[SecurityFact, ...]:
    """Declared security only.

    An operation with no `security` and no document-level default means *nothing
    was declared*, never *it is open* -- the same distinction `SecurityFact`
    already records for `@PreAuthorize`. The two are not the same claim.
    """
    schemes = (spec.get("components", {}) or {}).get("securitySchemes", {}) or {}
    # Swagger 2.0 keeps them at the top level.
    schemes = schemes or spec.get("securityDefinitions", {}) or {}
    out = []
    for requirement in names or ():
        if not isinstance(requirement, dict):
            continue
        for name, scopes in requirement.items():
            declared = schemes.get(name, {}) or {}
            out.append(SecurityFact(
                scheme=declared.get("type", "unknown"),
                expression=f"{name}({', '.join(scopes)})" if scopes else name,
                roles=tuple(scopes or ()),
            ))
    return tuple(out)


def _parameters(operation: dict, spec: dict, path_item: dict,
                errors: list[str], notes: list[str],
                where: str) -> tuple[ParameterFact, ...]:
    out: list[ParameterFact] = []

    # Path-level parameters apply to every operation on that path (OpenAPI 3 §4.8.9).
    declared = list(path_item.get("parameters", []) or [])
    declared += list(operation.get("parameters", []) or [])

    for parameter in declared:
        parameter = _schema_of(parameter, spec)
        location = parameter.get("in", "")
        # `cookie` used to be intercepted here and dropped -- a required one
        # refusing the document, an optional one becoming a note. It is one of
        # OpenAPI 3.0's four parameter locations, so the vocabulary was the thing
        # that was wrong. It now maps through `_LOCATIONS` like any other.
        mapped = _LOCATIONS.get(location)
        if mapped is None:
            errors.append(f"{where}: parameter {parameter.get('name','?')!r} has "
                          f"unrecognised `in: {location!r}`")
            continue
        # Swagger 2.0 puts the schema keywords on the parameter itself.
        schema = _schema_of(parameter.get("schema", {}) or {}, spec) or parameter
        out.append(ParameterFact(
            name=parameter.get("name", ""),
            location=mapped,
            type_name=_type_name(schema),
            required=bool(parameter.get("required", location == "path")),
            constraints=constraints_of(schema,
                                       required=bool(parameter.get("required"))),
        ))

    body = operation.get("requestBody")
    if isinstance(body, dict):
        body = _schema_of(body, spec)
        content = body.get("content", {}) or {}
        for media_type, media in content.items():
            schema = (media or {}).get("schema", {}) or {}
            out.append(ParameterFact(
                name="body",
                location=IN_FORM if "form" in media_type else IN_BODY,
                type_name=_type_name(_schema_of(schema, spec) if _ref_name(schema)
                                     else schema) if not _ref_name(schema)
                          else _ref_name(schema),
                required=bool(body.get("required", False)),
                constraints=constraints_of(_schema_of(schema, spec)),
            ))
            break  # one body per operation; the media types ride on `consumes`

    return tuple(out)


# GD-2's dimension chain, restricted to what an OpenAPI document actually
# declares. Each entry is `(atom, dimension_class, the statuses that mean this
# dimension FAILED)`. Order is the evaluation order, which for HTTP is fixed and
# is a fact about the protocol rather than a guess: a request is authenticated
# before it is authorised, and authorised before its payload is read.
_DIMENSIONS = (
    ("authenticated", "authentication", (401,)),
    ("authorized", "authorization", (403,)),
    ("payload_valid", "validation", (400, 422)),
)


def _declared_dimensions(operation: dict, security: tuple) -> list[tuple]:
    """The dimensions this operation genuinely declares. Never assumed.

    A 403 is groundable only where the document says the endpoint requires
    something -- otherwise `authorized` is a word nobody wrote, and asserting it
    would be the invention S-13 forbids. The same for a 400 with no request
    schema: the document declares the status and not the condition.
    """
    declared = []
    for atom, dimension_class, failing in _DIMENSIONS:
        if atom == "authenticated" and not security:
            continue
        if atom == "authorized" and not any(f.roles for f in security):
            continue
        if atom == "payload_valid" and not (operation.get("requestBody", {}) or {}).get("content"):
            continue
        declared.append((atom, dimension_class, failing))
    return declared


def _outcomes(endpoint_id: str, operation: dict, anchor: Anchor, spec: dict,
              security: tuple, checks: list[CheckFact],
              order: list[int]) -> list[OutcomeFact]:
    """One declared response, one outcome. `link` is always `declared`.

    **Guards, where and only where the document grounds them (GD-2).** A
    rejection at dimension *k* is guarded by `(dimensions 1..k-1 pass) AND NOT
    (dimension k)`; a success is guarded by all of them passing. The prefix is
    written into the check's own expression because `synthesise` applies one
    `guard_sense` across the whole list, so a mixed-sense chain cannot be
    expressed as several checks.

    A status the document declares and does not explain -- a 404, a 409 -- is
    left **unguarded and reported**. That is the honest answer: the contract
    says the outcome exists and never says when, and `check_guard_completeness`
    surfacing it is the tool working.
    """
    out = []
    dimensions = _declared_dimensions(operation, security)

    for status, response in sorted((operation.get("responses", {}) or {}).items()):
        response = _schema_of(response, spec)
        try:
            code = int(status)
        except (TypeError, ValueError):
            # `default` is a real OpenAPI response and is not a status. Kept,
            # with no status, rather than dropped or invented.
            code = None
        description = (response.get("description") or "").strip()

        expression = ""
        dimension_class = ""
        if code is not None and dimensions:
            failing = next(((i, atom, klass) for i, (atom, klass, statuses)
                            in enumerate(dimensions) if code in statuses), None)
            if failing is not None:
                index, atom, dimension_class = failing
                prefix = [a for a, _, _ in dimensions[:index]]
                expression = " AND ".join([*prefix, f"NOT {atom}"])
            elif 200 <= code < 300:
                dimension_class = "success"
                expression = " AND ".join(a for a, _, _ in dimensions)

        guarding: tuple[str, ...] = ()
        if expression:
            check_id = f"{endpoint_id}::check::{status}"
            # `order` must be unique across the whole report or precedence is
            # ambiguous, and GD-9 requires failing closed rather than guessing.
            order[0] += 1
            checks.append(CheckFact(id=check_id, expression=expression,
                                    order=order[0], anchor=anchor,
                                    dimension_class=dimension_class))
            guarding = (check_id,)

        out.append(OutcomeFact(
            id=f"{endpoint_id}::{status}",
            endpoint_id=endpoint_id,
            signature=f"{status}" + (f" {description}" if description else ""),
            status=code,
            discriminator=description or None,
            guarding_check_ids=guarding,
            link=LINK_DECLARED,
            anchor=anchor,
        ))
    return out


def _members(spec: dict, commit: str, document: str) -> list[MemberFact]:
    """`components.schemas` → one fact per property, with its constraints."""
    schemas = ((spec.get("components", {}) or {}).get("schemas", {})
               or spec.get("definitions", {}) or {})
    out = []
    for type_name, schema in sorted(schemas.items()):
        schema = _schema_of(schema, spec)
        required = set(schema.get("required", []) or [])
        for name, prop in sorted((schema.get("properties", {}) or {}).items()):
            resolved = _schema_of(prop, spec)
            out.append(MemberFact(
                type_name=type_name,
                name=name,
                type_full_name=_type_name(prop if _ref_name(prop) else resolved),
                owner_full_name=type_name,
                constraints=constraints_of(resolved, required=name in required),
                anchor=Anchor(
                    file=f"{document}#{_pointer('components', 'schemas', type_name, 'properties', name)}",
                    line=0, commit=commit),
            ))
    return out


def load(path: str | Path) -> dict:
    """Read an OpenAPI document. JSON always; YAML when PyYAML is present.

    Refuses rather than guessing: a YAML document with no parser available is
    reported with the reason, not read as an empty spec.
    """
    text = Path(path).read_text()
    if str(path).endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError as e:
            raise OpenAPIRefused(
                f"{path} is YAML and PyYAML is not installed. Convert it to JSON, "
                f"or install pyyaml — reading it as anything else would produce a "
                f"document this did not parse") from e
        return yaml.safe_load(text)
    try:
        return json.loads(text)
    except ValueError as e:
        raise OpenAPIRefused(f"{path}: not valid JSON — {e}") from e


def to_report(spec: dict, *, repo: str, commit: str = "",
              document: str = "openapi") -> AdapterResult:
    """One OpenAPI document as an `ExtractionReport`.

    `commit` is M-14's requirement that every element name the exact version it
    came from. For a specification the analogue is `info.version`, used when no
    commit is given — but a real repository commit is better and is preferred
    when supplied.
    """
    if not isinstance(spec, dict):
        raise OpenAPIRefused("the document is not a mapping")
    version = str((spec.get("info", {}) or {}).get("version", "")).strip()
    commit = commit or version
    if not commit:
        raise OpenAPIRefused(
            "no commit and no `info.version`: every element must name the exact "
            "version it came from (M-14), and there is nothing here to name")

    if not (spec.get("openapi") or spec.get("swagger")):
        raise OpenAPIRefused(
            "no `openapi` or `swagger` version key — this is not an OpenAPI document")

    errors: list[str] = []
    notes: list[str] = []
    check_order = [0]
    report = ExtractionReport(
        contract_version=CONTRACT_VERSION,
        pack=PACK, pack_version=PACK_VERSION,
        engine=ENGINE, engine_version=str(spec.get("openapi") or spec.get("swagger")),
        repo=repo, commit=commit, frontend=FRONTEND,
        layers=(LAYER_STRUCTURAL, LAYER_ENDPOINTS, LAYER_TYPE_REGISTRY,
                LAYER_TRANSITIONS),
    )

    default_security = spec.get("security", []) or []
    base_path = spec.get("basePath", "") or ""

    for path, path_item in sorted((spec.get("paths", {}) or {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method in _METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue

            full_path = f"{base_path}{path}"
            where = f"{method.upper()} {full_path}"
            pointer = _pointer("paths", path, method)
            anchor = Anchor(file=f"{document}#{pointer}", line=0, commit=commit)

            handler_id = _operation_id(method, full_path, operation)
            report.methods.append(MethodFact(
                id=handler_id,
                name=handler_id.rsplit(".", 1)[-1],
                type_name=(operation.get("tags") or ["default"])[0],
                signature=f"{method.upper()} {full_path}",
                anchor=anchor,
            ))

            responses = operation.get("responses", {}) or {}
            success = next((r for r in sorted(responses) if r.startswith("2")), "")
            body_schema = ((responses.get(success, {}) or {}).get("content", {})
                           or {})
            response_body = ""
            for media in body_schema.values():
                response_body = _ref_name((media or {}).get("schema", {}) or {})
                if response_body:
                    break

            # **`<handler>::<METHOD>`, which is the pack's convention, not a
            # readable label.** `synthesise` recovers the handler with
            # `endpoint_id.rsplit("::", 1)[0]` and looks the endpoint up by it,
            # so an id in any other shape joins to nothing -- silently. The first
            # version of this adapter used `POST /record`, the lookup missed on
            # every endpoint, and every recovered parameter was dropped: the
            # model still built, and `check_callability` then reported "takes a
            # request body, and none was recovered" for bodies this had in hand.
            endpoint_id = f"{handler_id}::{method.upper()}"
            report.endpoints.append(EndpointFact(
                id=endpoint_id,
                http_method=method.upper(),
                path=full_path,
                handler_method_id=handler_id,
                anchor=anchor,
                path_source=path,
                parameters=_parameters(operation, spec, path_item,
                                       errors, notes, where),
                security=_security_facts(
                    operation.get("security", default_security), spec),
                consumes=tuple(sorted((operation.get("requestBody", {}) or {})
                                      .get("content", {}) or {})),
                produces=tuple(sorted(body_schema)),
                handler_type=(operation.get("tags") or ["default"])[0],
                handler_name=handler_id.rsplit(".", 1)[-1],
                response_type=response_body,
                response_body=response_body,
                # A declared request schema is OpenAPI's `@Valid`: the document
                # states the shape the server will enforce. False means no schema
                # was declared, never that the endpoint accepts anything.
                validated=bool((operation.get("requestBody", {}) or {}).get("content")),
            ))
            security = _security_facts(
                operation.get("security", default_security), spec)
            report.outcomes.extend(_outcomes(
                endpoint_id, operation, anchor, spec, security,
                report.checks, check_order))

    report.members.extend(_members(spec, commit, document))

    # X-5: a partial parse is refused downstream, and these are the reasons.
    report.parse_errors.extend(errors)
    report.partial = bool(errors)
    return AdapterResult(report=report, notes=notes)


def to_dict(report: ExtractionReport) -> dict:
    """The report in the pack's own JSON shape.

    **This is the whole integration.** Writing the pack's format rather than a
    private one means the existing `code` source consumes an OpenAPI document
    with no change at all -- `sources._report_from_dict` rehydrates it, and
    `synthesise` joins the same way it does for Joern output. X-2's rule that no
    engine vocabulary reaches the graph is what makes one contract serve two
    producers this different.
    """
    from dataclasses import asdict

    data = asdict(report)
    data["layers"] = list(report.layers)
    return data
