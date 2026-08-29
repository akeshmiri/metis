"""
Land the processed intake as an evidence layer (spec §8.2's D-12, D-14, X-6).

**The intake was never in the graph.** The packs recover 91 endpoints, 245
parameters, 1,581 DTO fields, 4,149 methods, 405 outcomes, 102 checks and 5
exception mappings, and every one of them lived in a JSON file under `/tmp`. What
landed was only the *derived* result — States and Transitions — so a transition's
entire provenance was a `source_episode_id` property pointing at an Episode that
recorded "the code source ran". Which endpoint, which outcome, which field: none
of it answerable without re-reading a file outside the repository.

This module lands the facts themselves, and the control-flow layer then points at
them (D-14: provenance is an edge, not a property).

**D-12 — contract-shaped, so X-2 still holds.** What lands is
`code_analysis.contract`'s dataclasses. They are already normalised and
engine-independent; that is the entire reason that module exists. No Joern node
type, id or schema enters the graph, so an engine upgrade still touches only the
pack. Landing ontology-shaped code structure is what §8.7 stages; merging the
engine's graph is what X-2 forbids, and this is the first.

Same shape as `landing.py` and for the same reason: **pure planner, thin
writer**. Under Community edition the application gate is the sole guarantee that
required properties exist (D-8a/D-8b), so nothing reaches the database until the
whole plan has passed `validate`/`validate_relationship`.

**Ids exclude the commit** (D-8). The natural key is the fully-qualified name or
the `method + path`, so re-landing a later commit updates in place. Including the
commit would duplicate the whole 6,885-node estate on every ingest; the commit
stays where it already belongs, on each node's anchor.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from metis_mcp.model_sources.landing import LandingPlan, PlannedEdge, PlannedNode
from metis_mcp.model_sources.structure import normalised_page_name
from metis_mcp.ontology import validate, validate_relationship

# Everything in this layer is evidence about one repository, so ids are namespaced
# by it: two services may both declare `RecordDto`, and fusing them would say one
# type is two things at once.
_ID_LEN = 16


def _ident(*parts: str) -> str:
    """A short, content-derived id (D-8). Deterministic across runs."""
    basis = "|".join(p or "" for p in parts)
    return hashlib.sha256(basis.encode()).hexdigest()[:_ID_LEN]


def endpoint_id(repo: str, http_method: str, path: str, service: str = "") -> str:
    """**Scoped to the service, because a path is not unique across a monorepo.**

    the pilot estate declares `GET /summary` in two deployables and `GET /trend` in two
    more. Keyed on `(method, path)` alone all of them fuse, and one service's
    transitions then point at another's endpoint — the same cross-service
    contamination the INVOKES matcher had to be fixed for.
    """
    return f"ep:{_ident(repo, service, http_method, path)}"


def class_id(repo: str, name: str) -> str:
    """Keyed on the FULLY-QUALIFIED name where one is known.

    Simple names collide: the pilot estate declares `PageResponse` in seven files, one per
    feign module, and 21 simple names are declared in more than one place.
    Fusing them produces one node claiming to be all seven at once — the same
    defect as `/project/all` and `/user/all` collapsing onto `All`.
    """
    return f"cls:{_ident(repo, name)}"


def field_id(repo: str, type_name: str, name: str) -> str:
    return f"fld:{_ident(repo, type_name, name)}"


def method_id(repo: str, full_name: str) -> str:
    return f"mth:{_ident(repo, full_name)}"


def parameter_id(repo: str, endpoint: str, name: str, location: str) -> str:
    return f"prm:{_ident(repo, endpoint, name, location)}"


def security_id(repo: str, endpoint: str, scheme: str, expression: str) -> str:
    """Keyed on the DECLARATION, not on the scheme.

    One endpoint may carry two `role` schemes — a class-level `hasRole(RECORDS)`
    and a method-level `@DemoSecured(...)` — and keying on the scheme alone would
    MERGE them onto one node, silently overwriting one declaration with the
    other. That is the mistake `outcome_id` documents below, in a smaller place.
    """
    return f"sec:{_ident(repo, endpoint, scheme, expression)}"


def outcome_id(repo: str, raw_id: str, guards: tuple = (), sense: str = "") -> str:
    """Keyed on the guard as well as the pack's id.

    **The pack's id is not unique and cannot be.** It is
    `<endpoint>::<status>`, so `EnvironmentController.save::POST::201` names
    four recovered outcomes that differ only in which check guards them — four
    branches that all produce a 201. Keyed on the id alone they MERGE onto one
    node, three sets of properties are silently overwritten, and the "all
    processed intake" the evidence layer promises is 345 of 405 rows.
    """
    return f"out:{_ident(repo, raw_id, '+'.join(sorted(guards)), sense)}"


def outcome_id_for(repo: str, outcome) -> str:
    """The id for a recovered outcome. One definition, two callers.

    `raw_landing` writes the node and `synthesis` writes the transition that
    points at it; deriving the key twice is how a `DERIVED_FROM` edge ends up
    aimed at a node that does not exist.
    """
    return outcome_id(repo, outcome.id,
                      tuple(getattr(outcome, "guarding_check_ids", ()) or ()),
                      getattr(outcome, "guard_sense", "") or "")


def check_id(repo: str, raw_id: str, expression: str) -> str:
    # The pack numbers checks `chk-1..n` per RUN, so the number alone is not an
    # identity -- re-running with one more branch renumbers everything after it.
    # The expression is what makes the node the same node.
    return f"chk:{_ident(repo, raw_id, expression)}"


def mapping_id(repo: str, exception_type: str, advice: str) -> str:
    return f"exm:{_ident(repo, exception_type, advice)}"


def route_id(repo: str, path: str) -> str:
    return f"rte:{_ident(repo, path)}"


def _present(**values) -> dict:
    """Only the keys that actually have a value.

    An empty description written as `""` is a property the graph has to store
    and every reader has to test for. Absent says the same thing and says it
    once.
    """
    return {k: v for k, v in values.items() if v}


def _anchor_props(anchor) -> dict:
    """`file`/`line`/`commit` as flat properties (X-6).

    Flat rather than nested because a Neo4j property cannot hold a map, and
    separate rather than a joined string because a reviewer filters on file.
    """
    if anchor is None:
        return {"anchor_file": "", "anchor_line": 0, "anchor_commit": ""}
    get = anchor.get if isinstance(anchor, dict) else lambda k, d=None: getattr(anchor, k, d)
    return {"anchor_file": get("file", "") or "",
            "anchor_line": int(get("line", 0) or 0),
            "anchor_commit": get("commit", "") or ""}


def _simple(type_name: str) -> str:
    return (type_name or "").rsplit(".", 1)[-1]


def service_of(anchor) -> str:
    """Which deployable a fact belongs to, from its anchor's path.

    The same derivation the model side uses, so an endpoint's identity and the
    service a transition is attributed to cannot disagree.
    """
    from metis_mcp.mbt.test_levels import service_of_path

    if anchor is None:
        return ""
    path = anchor.get("file", "") if isinstance(anchor, dict) else getattr(anchor, "file", "")
    return service_of_path(path or "")


def resolve_class(repo: str, expression: str, declared: set[str],
                  by_simple: dict[str, str]) -> list[str]:
    """Class node ids for every type named in `expression`.

    A parameter carries a fully-qualified name and a response body carries only
    simple ones, so both forms have to resolve to the same node. An **ambiguous**
    simple name resolves to nothing: 21 of them name more than one declared type
    here, and picking one would attach a payload schema to the wrong class.
    """
    out: list[str] = []
    for token in type_names_in(expression, qualified=True):
        cid = class_id(repo, token) if token in declared else None
        if cid is None:
            fq = by_simple.get(_simple(token))
            cid = class_id(repo, fq) if fq else None
        if cid and cid not in out:
            out.append(cid)
    return out


_TYPE_TOKEN = __import__("re").compile(r"[A-Za-z_][A-Za-z0-9_.]*")


def type_names_in(expression: str, qualified: bool = False) -> list[str]:
    """Every simple type name mentioned in a type expression, in order.

    `PageDto<EnvironmentDto>` mentions two real classes and a generated case
    needs both: the envelope it asserts the shape of, and the element type
    inside it. `List<MetricTrendPointDto>` mentions one that matters and one
    that is a JDK collection — which is why the caller filters by what was
    actually declared rather than trusting this to know.
    """
    seen: list[str] = []
    for token in _TYPE_TOKEN.findall(expression or ""):
        value = token if qualified else _simple(token)
        if value and value not in seen:
            seen.append(value)
    return seen


def plan_raw_landing(report, journey: str, repo: str = "",
                     behaviour=None, ui_facts: dict | None = None,
                     job_id: str = "manual", t_recorded: str | None = None,
                     include_call_graph: bool = False,
                     compact: bool = True) -> LandingPlan:
    """Build a fully-validated evidence plan. No session, no writes.

    `report` is the structural pack's `ExtractionReport`; `behaviour` the
    behaviour pack's (checks and outcomes); `ui_facts` the frontend pack's raw
    dict. Any may be absent — a partial evidence layer is better than none, and
    the caller is told what it got rather than being handed a silent subset.

    `include_call_graph` writes the 4,149 `Method` nodes and 7,226 `CALLS` edges.
    D-13 records that these are landed ahead of their reader by explicit choice;
    the flag exists so that choice stays reversible without a code change.
    """
    repo = repo or getattr(report, "repo", "") or "repo"
    commit = getattr(report, "commit", "") or ""
    recorded = t_recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")

    episode_id = "ep-raw-" + _ident(repo, commit, journey)
    plan = LandingPlan(episode_id=episode_id)

    def add_node(label: str, props: dict) -> None:
        outcome = validate(label, props)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        plan.nodes.append(PlannedNode(label=label, properties=props))

    def add_edge(from_label, from_id, rel, to_label, to_id) -> None:
        outcome = validate_relationship(from_label, rel, to_label)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        plan.edges.append(PlannedEdge(from_label, from_id, rel, to_label, to_id))

    def base(node_id: str, name: str) -> dict:
        return {"id": node_id, "source_episode_id": episode_id, "name": name}

    # The Episode is exempt from `source_episode_id` -- it IS the provenance
    # record and cannot point at one (D-8, BASELINE_EXEMPT).
    add_node("Episode", {
        "id": episode_id,
        "name": f"raw-intake: {repo}",
        "t_recorded": recorded,
        "source_connector": "raw-intake",
        "job_id": job_id,
        "evidence": f"repo={repo}, commit={commit}, pack={getattr(report, 'pack', '')}",
        "proposed_by": f"{getattr(report, 'pack', 'pack')}@"
                       f"{getattr(report, 'pack_version', '?')}",
    })

    declared, by_simple = _plan_types(plan, add_node, add_edge, base, report, repo,
                                      include_call_graph, compact)
    _plan_endpoints(plan, add_node, add_edge, base, report, repo,
                    include_call_graph, declared, by_simple)
    _plan_behaviour(plan, add_node, add_edge, base, behaviour, repo,
                    endpoints_by_handler(report, repo))
    _plan_ui(plan, add_node, add_edge, base, ui_facts, repo, journey)

    return plan


def endpoints_by_handler(report, repo: str) -> dict[str, str]:
    """`"<handler fullName>::<VERB>" -> Endpoint node id`.

    **The two packs key an endpoint differently and neither is wrong.** The
    behaviour pack owns no route information, so it identifies an entry point by
    the handler it found plus the verb; the structural pack owns the route and
    keys on `method + path`. Without this join `Endpoint-[:DECLARES]->
    DeclaredOutcome` is in the catalogue and never written — 405 outcomes
    floating free of the endpoints that produce them.
    """
    out: dict[str, str] = {}
    for endpoint in getattr(report, "endpoints", ()) or ():
        handler = getattr(endpoint, "handler_method_id", "")
        if handler:
            out[f"{handler}::{endpoint.http_method}"] = endpoint_id(
                repo, endpoint.http_method, endpoint.path,
                service_of(getattr(endpoint, "anchor", None)))
    return out


# X-6b: the closed set of typed constraint properties, and what each holds. An
# int property absent means "not constrained that way" -- writing 0 instead would
# be a bound the code never stated, and a boundary criterion would honour it.
_INT_CONSTRAINTS = ("expected_min_length", "expected_max_length",
                    "expected_min_size", "expected_max_size",
                    "expected_integer_digits", "expected_fraction_digits")
_STR_CONSTRAINTS = ("expected_min", "expected_max", "expected_exclusive_min",
                    "expected_exclusive_max", "expected_pattern",
                    "expected_format", "expected_temporal")


def class_label_for(is_enum: bool) -> str:
    """`Enum` or `Class`, and a specialisation is written INSTEAD of its parent.

    So every query over types must use `label_expression("Class")`; a hardcoded
    `:Class` silently skips every enum, which is the same defect a hardcoded
    `:Transition` produces against `:ApiCall`.
    """
    return "Enum" if is_enum else "Class"


def _typed_constraints(member, prefix: str = "") -> dict:
    """The validation bounds as data, dropping anything not stated."""
    out: dict = {}
    for key in _INT_CONSTRAINTS:
        value = getattr(member, key, None)
        if value is not None:
            out[prefix + key] = int(value)
    for key in _STR_CONSTRAINTS:
        value = getattr(member, key, "")
        if value:
            out[prefix + key] = value
    return out


def _security_node(fact) -> dict:
    """One declared security requirement, as a node's properties.

    **Was three parallel arrays on the Endpoint**, documented as positional. A
    scheme with two roles cannot be positional: `@DemoSecured({"records:write",
    "records:admin"})` produced `schemes=2, roles=3` on a real endpoint, and a
    third of the corpus was misaligned — so `auth_facts` handed callers a
    correspondence they could not decode.

    `roles` is an array ON this node, which is legal precisely because a scheme
    owns its roles. Absent when nothing was declared, which stays a different
    claim from "open" (see `recipe.NO_SECURITY_NOTE`).
    """
    return _present(
        scheme=getattr(fact, "scheme", ""),
        expression=getattr(fact, "expression", ""),
        roles=sorted(getattr(fact, "roles", ()) or ()),
        source=getattr(fact, "source", ""),
    )


def _field_properties(members) -> dict:
    """A type's fields, flattened onto the type (X-6d).

    The prefix and the reason for it live in `ontology.facts`, beside the decoder
    that reads these back — one module, so the two cannot drift.

    `required` stays a STRING and "" is a third answer: "not stated" and "stated
    optional" are different facts about a payload, and a boolean collapses them.
    """
    from metis_mcp.ontology.facts import FIELD_PREFIX

    out: dict = {}
    for member in members:
        name = getattr(member, "name", "")
        if not name:
            continue
        p = f"{FIELD_PREFIX}{name}_"
        out[p + "type"] = getattr(member, "type_full_name", "")
        for key, value in (
            ("required", getattr(member, "required", "")),
            ("description", getattr(member, "description", "")),
            ("element_type", getattr(member, "element_type", "")),
        ):
            if value:
                out[p + key] = value
        # GD-3's variants: what a fixture must violate to reach a validation
        # rejection, kept verbatim beside the typed form (X-6b).
        constraints = list(getattr(member, "constraints", ()) or ())
        if constraints:
            out[p + "constraints"] = constraints
        allowed = list(getattr(member, "allowed_values", ()) or ())
        if allowed:
            out[p + "allowed_values"] = allowed
        out.update(_typed_constraints(member, prefix=p))
    return out


def _plan_types(plan, add_node, add_edge, base, report, repo,
                include_call_graph, compact: bool = True) -> tuple[set[str], dict[str, str]]:
    """`Class` and its `Field`s — and `Class` is deliberately also the schema.

    A DTO *is* a class. Reaching `RecordDto` as a parameter's type and reaching
    it as a declared type must arrive at ONE node, or the graph says two
    different things about one type.
    """
    seen: set[str] = set()
    fq_names: set[str] = set()
    # Which types this repository declares, so a nested field edge stops at the
    # JDK boundary rather than inventing a node for `java.lang.String`
    # (REQ-CGA-010), and which of them are enums.
    members = list(getattr(report, "members", ()) or ())
    declared_types = {getattr(m, "owner_full_name", "") or getattr(m, "type_name", "")
                      for m in members}
    declared_types.discard("")

    # **A type nothing references is not part of this service's surface.**
    # `TwilioProperties` and a service implementation's fields are real code and
    # tell the model nothing: on a real service 29 classes and 126 fields were
    # unreachable from the model through any meaningful edge, which is a third of
    # what remained after the call graph went.
    #
    # Referenced means: a parameter carries it, an endpoint returns it, another
    # kept type nests it, or it is an enum whose constants are somebody's
    # partitions. Computed transitively, because a payload two levels deep is
    # still a payload — and REQ-CGA-010 already stops the walk at the JDK.
    wanted: set[str] = set()
    by_owner: dict[str, list] = {}
    for m in members:
        by_owner.setdefault(
            getattr(m, "owner_full_name", "") or getattr(m, "type_name", ""), []).append(m)

    # A type is named as a fully-qualified name in one place and a simple one in
    # another — a parameter carries the FQN, a member's owner may be either — so
    # resolution is on the last dot-segment, which is the only form both sides
    # always share. Ambiguous segments resolve to nothing rather than to
    # whichever came first: `_index_by_simple` omits them for the same reason.
    by_segment: dict[str, set[str]] = {}
    for owner in by_owner:
        by_segment.setdefault(owner.rsplit(".", 1)[-1], set()).add(owner)

    def resolve(name: str) -> str:
        name = unwrap_generic(name)
        if not name:
            return ""
        if name in by_owner:
            return name
        candidates = by_segment.get(name.rsplit(".", 1)[-1], set())
        return next(iter(candidates)) if len(candidates) == 1 else ""

    frontier: list[str] = []
    for endpoint in getattr(report, "endpoints", ()) or ():
        for parameter in getattr(endpoint, "parameters", ()) or ():
            frontier.append(getattr(parameter, "type_name", ""))
        frontier.append(getattr(endpoint, "response_body", ""))

    while frontier:
        owner = resolve(frontier.pop())
        if not owner or owner in wanted:
            continue
        wanted.add(owner)
        for m in by_owner.get(owner, ()):
            # The field's own type, and a collection's element type: a payload
            # two levels deep is still a payload.
            frontier.append(getattr(m, "type_full_name", ""))
            frontier.append(getattr(m, "element_type", ""))
    enum_types = {getattr(m, "owner_full_name", "") or getattr(m, "type_name", "")
                  for m in members if getattr(m, "owner_is_enum", False)}
    enum_types.discard("")
    by_simple = _index_by_simple(declared_types)
    skipped_types: set[str] = set()
    skipped_fields = 0

    # **A scalar field is a property of its type; a complex one is an edge
    # between types** (X-6d). A field was its own node, which put 68 nodes into
    # the graph to say what four properties say, and none of them was ever
    # queried on its own: what a test-designer asks is "what values does this
    # type accept", and that is one question about one node.
    #
    # Grouped first, because a type's properties are written once with the node
    # rather than accreted by 68 separate visits.
    grouped: dict[str, list] = {}
    for member in members:
        owner_fq = getattr(member, "owner_full_name", "") or getattr(member, "type_name", "")
        if compact and owner_fq not in wanted:
            skipped_types.add(owner_fq)
            skipped_fields += 1
            continue
        if getattr(member, "type_name", ""):
            grouped.setdefault(owner_fq, []).append(member)

    for owner, owned in grouped.items():
        first = owned[0]
        type_name = getattr(first, "type_name", "")
        cid = class_id(repo, owner)
        fq_names.add(owner)
        owner_is_enum = bool(getattr(first, "owner_is_enum", False))
        if cid in seen:
            continue
        seen.add(cid)
        add_node(class_label_for(owner_is_enum), {
            **base(cid, type_name), "package": owner,
            # What a person wrote about this type in `@Schema`. Zero Class nodes
            # carried one before the `schema` role existed, while 71 such
            # annotations sat in the source.
            **_present(description=getattr(first, "owner_description", "")),
            "fields": sorted(getattr(m, "name", "") for m in owned),
            **_field_properties(owned),
        })

        for member in owned:
            # X-6d: the nested payload, now an edge between the two TYPES. A
            # field whose type is another declared type continues the graph; a
            # field typed by the JDK stops here, because REQ-CGA-010 forbids
            # stubbing a type this repository does not declare. Which field
            # carries it is on `f_<name>_type`, so the edge needs no property —
            # `landing.PlannedEdge` has none, unlike `graph_writer`'s.
            #
            # A collection resolves through its ELEMENT type. `List<RecordDto>`
            # has `type_full_name = java.util.List`, which is true and useless:
            # the type a fixture builds is `RecordDto`.
            nested = getattr(member, "type_full_name", "")
            if nested not in declared_types:
                element = getattr(member, "element_type", "")
                # Resolved as a response body is, and omitted when the simple
                # name is ambiguous — attaching a payload to whichever type came
                # first is worse than leaving it unattached.
                nested = by_simple.get(element, "") if element else ""
            if nested and nested in declared_types and nested != owner:
                add_edge(class_label_for(owner_is_enum), cid, "OF_TYPE",
                         class_label_for(nested in enum_types),
                         class_id(repo, nested))

    # **"Off" means bounded, not absent.** Returning here landed no `Method` at
    # all while `Endpoint -[:HANDLED_BY]-> Method` and
    # `ExceptionMapping -[:HANDLED_BY]-> Method` were still planned, so both would
    # have merged nothing — the flag was written before either edge existed.
    #
    # What stays is what something points at: the twelve handlers and the five
    # exception handlers. What goes is the call graph, which on a real service was
    # 199 methods and 180 CALLS edges landed for a reader — `behavior_model.
    # corroborate` — that **nothing calls**, and which needs 17 of them when it
    # finally does. D-13 chose to land it ahead of that reader; the reader has not
    # arrived, and 182 unreferenced nodes is what the choice costs per service.
    if skipped_types:
        # X-5a: never silent. A jump in this count means a payload chain broke,
        # not that the service got smaller.
        plan.skipped.append((
            f"{len(skipped_types)} type(s) and {skipped_fields} field(s)",
            "no parameter, response body or nested payload field references "
            "them, so the model can lead you to none of it — landed only with "
            "compact=False"))

    referenced = {getattr(e, "handler_method_id", "")
                  for e in getattr(report, "endpoints", ()) or ()}
    referenced |= {getattr(m, "handler_method_id", "")
                   for m in getattr(report, "exception_mappings", ()) or ()}
    referenced.discard("")

    methods = list(getattr(report, "methods", ()) or ())
    if not include_call_graph:
        kept = [m for m in methods if m.id in referenced]
        dropped = len(methods) - len(kept)
        if dropped:
            # Never silent (X-5a): a graph that quietly lost its call graph looks
            # exactly like a codebase whose methods call nothing.
            plan.skipped.append((
                f"{dropped} method(s) and their CALLS edges",
                "the call graph is not landed by default — its only reader, "
                "`behavior_model.corroborate`, is called by nothing, and the "
                "handlers something does point at are kept. Pass "
                "include_call_graph=True to land it"))
        methods = kept

    for method in methods:
        mid = method_id(repo, method.id)
        add_node("Method", {
            **base(mid, getattr(method, "name", "")),
            "type_name": getattr(method, "type_name", ""),
            "signature": getattr(method, "signature", ""),
            **_anchor_props(getattr(method, "anchor", None)),
        })
        # `fullName` is `<pkg>.<Type>.<name>:<sig>`, so the declaring type's FQN
        # is the qualifier with the method name removed.
        simple = getattr(method, "type_name", "")
        fq = (method.id.rsplit(":", 1)[0].rsplit(".", 1)[0]
              if ":" in method.id else simple)
        if simple:
            owner_fq = fq or simple
            cid = class_id(repo, owner_fq)
            fq_names.add(owner_fq)
            # **`:Enum` or `:Class`, and getting it wrong here merges nothing.**
            # An enum with a method (`fromValue`, `getLabel`) already has its node
            # from the members pass carrying `:Enum`, because a specialisation
            # replaces its parent. Planning this edge against `:Class`
            # regardless passed the ontology check — `is_allowed` walks the
            # specialisation chain — and then matched no node: three
            # DECLARES_METHOD edges reported as unmatched, which is the same
            # defect a hardcoded `:Transition` produces against `:ApiCall`.
            enum_owner = owner_fq in enum_types
            if cid not in seen:
                seen.add(cid)
                add_node(class_label_for(enum_owner),
                         {**base(cid, simple), "package": fq})
            add_edge(class_label_for(enum_owner), cid,
                     "DECLARES_METHOD", "Method", mid)

    known = {method_id(repo, m.id) for m in methods}
    for call in getattr(report, "calls", ()) or ():
        caller, callee = method_id(repo, call.caller_id), method_id(repo, call.callee_id)
        if caller in known and callee in known:
            add_edge("Method", caller, "CALLS", "Method", callee)

    return seen, _index_by_simple(fq_names)


def unwrap_generic(name: str) -> str:
    """`List<RecordDto>` -> `RecordDto`; anything else unchanged.

    A collection OF the body is not the body, and the body is what a case asserts
    against and what a fixture builds. Shared with `workflow.handlers` so the two
    cannot disagree about what a response type is — they did, and the disagreement
    cost one `EXPECTS` edge that pointed at a class compaction had dropped.
    """
    name = (name or "").strip()
    if "<" in name and name.endswith(">"):
        name = name[name.index("<") + 1:-1].strip()
        if "," in name:                     # Map<String, Dto> -- the value type
            name = name.rsplit(",", 1)[-1].strip()
    return name


def _index_by_simple(fq_names: set[str]) -> dict[str, str]:
    """`simple name -> the one FQN that declares it`, ambiguous names omitted.

    Omission is the point. 21 simple names name more than one declared type in
    this repository, and resolving `PageResponse` to whichever came first would
    attach a schema to the wrong class.
    """
    grouped: dict[str, set[str]] = {}
    for fq in fq_names:
        grouped.setdefault(_simple(fq), set()).add(fq)
    return {simple: next(iter(fqs)) for simple, fqs in grouped.items() if len(fqs) == 1}


def _plan_endpoints(plan, add_node, add_edge, base, report, repo,
                    include_call_graph, declared: set[str] | None = None,
                    by_simple: dict[str, str] | None = None):
    """Endpoints, their inputs, and the types those resolve to.

    **A type edge is planned only where the type is DECLARED in this repository.**
    `java.lang.Long` and `int` have no `Class` node and must not get one:
    REQ-CGA-010 refuses to emit a stub for anything external, and an edge to a
    node that will never exist is a dangling plan, not a fact. The type name is
    still on the `Parameter`, so nothing is lost -- only the traversal is absent,
    correctly.
    """
    declared = declared if declared is not None else set()
    by_simple = by_simple or {}
    external = 0

    def link_types(from_label, from_id, rel, expression) -> int:
        resolved = resolve_class(repo, expression, declared, by_simple)
        for cid in resolved:
            add_edge(from_label, from_id, rel, "Class", cid)
        # Every token that named nothing declared here: JDK types, and the JDK
        # half of a generic like `List<Dto>`.
        return max(len(type_names_in(expression)) - len(resolved), 0)

    for endpoint in getattr(report, "endpoints", ()) or ():
        eid = endpoint_id(repo, endpoint.http_method, endpoint.path,
                          service_of(getattr(endpoint, "anchor", None)))
        add_node("Endpoint", {
            **base(eid, f"{endpoint.http_method} {endpoint.path}"),
            "http_method": endpoint.http_method,
            "path": endpoint.path,
            "handler_type": getattr(endpoint, "handler_type", ""),
            "handler_name": getattr(endpoint, "handler_name", ""),
            "validated": bool(getattr(endpoint, "validated", False)),
            "response_type": getattr(endpoint, "response_type", ""),
            "response_body": getattr(endpoint, "response_body", ""),
            "consumes": list(getattr(endpoint, "consumes", ()) or ()),
            "produces": list(getattr(endpoint, "produces", ()) or ()),
            **_anchor_props(getattr(endpoint, "anchor", None)),
        })

        # **Declared security, as nodes.** Absent means nothing was DECLARED,
        # never "it is open": security enforced in a filter chain or at a gateway
        # is invisible to extraction, and the two claims are not the same (see
        # `recipe.NO_SECURITY_NOTE`).
        #
        # One node per declaration rather than three parallel arrays on the
        # endpoint — a scheme with two roles has no positional representation,
        # and a third of the corpus was already misaligned.
        for security in getattr(endpoint, "security", ()) or ():
            scheme = getattr(security, "scheme", "")
            if not scheme:
                continue
            sid = security_id(repo, eid, scheme,
                              getattr(security, "expression", ""))
            add_node("SecurityScheme", {
                **base(sid, scheme),
                **_security_node(security),
            })
            add_edge("Endpoint", eid, "SECURED_BY", "SecurityScheme", sid)

        for parameter in getattr(endpoint, "parameters", ()) or ():
            pid = parameter_id(repo, eid, parameter.name, parameter.location)
            add_node("Parameter", {
                **base(pid, parameter.name),
                "location": parameter.location,
                "type_name": getattr(parameter, "type_name", ""),
                "required": bool(getattr(parameter, "required", True)),
                "constraints": list(getattr(parameter, "constraints", ()) or ()),
            })
            add_edge("Endpoint", eid, "ACCEPTS", "Parameter", pid)
            # The schema link, and the reason `Class` doubles as the schema: this
            # is how a generator walks parameter -> type -> field constraints.
            external += link_types("Parameter", pid, "OF_TYPE",
                                   getattr(parameter, "type_name", ""))

        external += link_types("Endpoint", eid, "RETURNS",
                               getattr(endpoint, "response_body", ""))

        # No longer conditional on the call graph: a referenced method is landed
        # whether or not the call graph is. The condition was correct when "off"
        # meant no `Method` node existed at all, and became a reason the handler
        # was unreachable the moment "off" started meaning "bounded".
        if getattr(endpoint, "handler_method_id", ""):
            add_edge("Endpoint", eid, "HANDLED_BY", "Method",
                     method_id(repo, endpoint.handler_method_id))

    if external:
        plan.skipped.append((
            f"{external} type reference(s)",
            "resolve to types this repository does not declare (JDK types, and "
            "the JDK half of a generic like List<Dto>) — the name is kept on the "
            "node and no stub Class is invented (REQ-CGA-010)"))

    for mapping in getattr(report, "exception_mappings", ()) or ():
        mid = mapping_id(repo, mapping.exception_type, mapping.advice_type)
        add_node("ExceptionMapping", {
            **base(mid, f"{mapping.exception_type} → {mapping.status}"),
            "exception_type": mapping.exception_type,
            "status": mapping.status,
            "advice_type": mapping.advice_type,
            **_anchor_props(getattr(mapping, "anchor", None)),
        })
        # The catalogued reader for this label, and it was never written:
        # `advice_type` is a simple class name that joins to nothing, so five
        # mappings landed connected to nothing while EVIDENCE_LAYER named this
        # edge as the reason the label exists.
        handler = getattr(mapping, "handler_method_id", "")
        if handler:
            add_edge("ExceptionMapping", mid, "HANDLED_BY", "Method",
                     method_id(repo, handler))


def _plan_behaviour(plan, add_node, add_edge, base, behaviour, repo,
                    by_handler: dict[str, str] | None = None):
    """`Check` and `DeclaredOutcome` — the guard's and the outcome's own evidence."""
    if behaviour is None:
        return
    by_handler = by_handler or {}
    unjoined = 0
    stranded = 0
    referenced: set[str] = set()

    checks: dict[str, str] = {}
    for check in getattr(behaviour, "checks", ()) or ():
        cid = check_id(repo, check.id, check.expression)
        checks[check.id] = cid
        add_node("Check", {
            **base(cid, check.expression),
            "expression": check.expression,
            "order": check.order,
            "dimension_class": getattr(check, "dimension_class", "") or "",
            **_anchor_props(getattr(check, "anchor", None)),
        })

    for outcome in getattr(behaviour, "outcomes", ()) or ():
        oid = outcome_id_for(repo, outcome)
        add_node("DeclaredOutcome", {
            **base(oid, outcome.signature),
            "signature": outcome.signature,
            "status": outcome.status,
            "discriminator": getattr(outcome, "discriminator", "") or "",
            # How it was established: `declared` is an annotation, `name-match` a
            # disclosed heuristic. A reviewer weighs them differently.
            "link": getattr(outcome, "link", ""),
            "guard_sense": getattr(outcome, "guard_sense", ""),
            "endpoint_ref": outcome.endpoint_id,
            **_anchor_props(getattr(outcome, "anchor", None)),
        })
        eid = by_handler.get(outcome.endpoint_id)
        if eid:
            add_edge("Endpoint", eid, "DECLARES", "DeclaredOutcome", oid)
        else:
            unjoined += 1

        for raw_check in getattr(outcome, "guarding_check_ids", ()) or ():
            if raw_check in checks:
                add_edge("DeclaredOutcome", oid, "GUARDED_BY", "Check", checks[raw_check])
                referenced.add(raw_check)

    # **A guard whose outcome could not be recovered is still a real condition in
    # real code.** The pack emits the check whether or not either branch resolves
    # to a status, so a ternary branching to two helpers that name no status
    # leaves the check referenced by nothing. Both checks recovered from a real
    # service were of exactly that shape, and both landed connected to nothing.
    #
    # Attached to the endpoint whose handler it was found in, which is a weaker
    # claim than `GUARDED_BY` and is labelled as one: this says "a condition was
    # recovered here", not "this condition selects that outcome".
    for check in getattr(behaviour, "checks", ()) or ():
        if check.id in referenced:
            continue
        eid = by_handler.get(getattr(check, "endpoint_id", ""))
        if eid:
            add_edge("Endpoint", eid, "CONSTRAINED_BY", "Check", checks[check.id])
        else:
            stranded += 1

    if stranded:
        plan.skipped.append((
            f"{stranded} recovered check(s)",
            "no outcome references them and their endpoint was not recovered "
            "either, so they would land connected to nothing — reported instead"))

    if unjoined:
        # Reported, not dropped. An outcome whose endpoint the structural pack
        # never recovered is a real recovery gap (O-2c) and the node still lands
        # carrying its `endpoint_ref`, so the join can be made later by hand.
        plan.skipped.append((
            f"{unjoined} declared outcome(s)",
            "no endpoint in the structural report matches their handler+verb — "
            "they land unattached rather than being dropped or guessed at"))


def _plan_ui(plan, add_node, add_edge, base, ui_facts, repo, journey):
    """`Route` — where a UI query starts.

    Deliberately a source and never a target: a route IS the entry point, and
    inventing an edge into it to satisfy a symmetry rule would add a claim
    nothing observed.
    """
    if not ui_facts:
        return
    for route in ui_facts.get("routes", ()) or ():
        path = route.get("path") if isinstance(route, dict) else str(route)
        if not path:
            continue
        rid = route_id(repo, path)
        screen = route.get("screen", "") if isinstance(route, dict) else ""
        add_node("Route", {
            **base(rid, path),
            "path": path,
            "screen": screen,
            # The basis `route_page` joins on (X-19). Held as a property so the
            # proposal can be re-run against a structure that lands later.
            "join_name": normalised_page_name(screen),
        })
