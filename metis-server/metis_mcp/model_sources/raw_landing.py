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
from metis_mcp.ontology import validate, validate_relationship

# Everything in this layer is evidence about one repository, so ids are namespaced
# by it: two services may both declare `MetricDto`, and fusing them would say one
# type is two things at once.
_ID_LEN = 16


def _ident(*parts: str) -> str:
    """A short, content-derived id (D-8). Deterministic across runs."""
    basis = "|".join(p or "" for p in parts)
    return hashlib.sha256(basis.encode()).hexdigest()[:_ID_LEN]


def endpoint_id(repo: str, http_method: str, path: str, service: str = "") -> str:
    """**Scoped to the service, because a path is not unique across a monorepo.**

    athena declares `GET /summary` in two deployables and `GET /trend` in two
    more. Keyed on `(method, path)` alone all of them fuse, and one service's
    transitions then point at another's endpoint — the same cross-service
    contamination the INVOKES matcher had to be fixed for.
    """
    return f"ep:{_ident(repo, service, http_method, path)}"


def class_id(repo: str, name: str) -> str:
    """Keyed on the FULLY-QUALIFIED name where one is known.

    Simple names collide: athena declares `PageResponse` in seven files, one per
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
                     include_call_graph: bool = True) -> LandingPlan:
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
                                      include_call_graph)
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


def _plan_types(plan, add_node, add_edge, base, report, repo,
                include_call_graph) -> tuple[set[str], dict[str, str]]:
    """`Class` and its `Field`s — and `Class` is deliberately also the schema.

    A DTO *is* a class. Reaching `MetricDto` as a parameter's type and reaching
    it as a declared type must arrive at ONE node, or the graph says two
    different things about one type.
    """
    seen: set[str] = set()
    fq_names: set[str] = set()
    for member in getattr(report, "members", ()) or ():
        type_name = getattr(member, "type_name", "")
        owner = getattr(member, "owner_full_name", "") or type_name
        if not type_name:
            continue
        cid = class_id(repo, owner)
        fq_names.add(owner)
        if cid not in seen:
            seen.add(cid)
            add_node("Class", {**base(cid, type_name), "package": owner})
        fid = field_id(repo, owner, getattr(member, "name", ""))
        add_node("Field", {
            **base(fid, getattr(member, "name", "")),
            "type_name": getattr(member, "type_full_name", ""),
            # GD-3's variants: what a fixture must violate to reach a validation
            # rejection. One node per field, however many transitions need it.
            "constraints": list(getattr(member, "constraints", ()) or ()),
            **_anchor_props(getattr(member, "anchor", None)),
        })
        add_edge("Class", cid, "HAS_FIELD", "Field", fid)

    if not include_call_graph:
        return seen, _index_by_simple(fq_names)

    for method in getattr(report, "methods", ()) or ():
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
            cid = class_id(repo, fq or simple)
            fq_names.add(fq or simple)
            if cid not in seen:
                seen.add(cid)
                add_node("Class", {**base(cid, simple), "package": fq})
            add_edge("Class", cid, "DECLARES_METHOD", "Method", mid)

    known = {method_id(repo, m.id) for m in getattr(report, "methods", ()) or ()}
    for call in getattr(report, "calls", ()) or ():
        caller, callee = method_id(repo, call.caller_id), method_id(repo, call.callee_id)
        if caller in known and callee in known:
            add_edge("Method", caller, "CALLS", "Method", callee)

    return seen, _index_by_simple(fq_names)


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

        if include_call_graph and getattr(endpoint, "handler_method_id", ""):
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


def _plan_behaviour(plan, add_node, add_edge, base, behaviour, repo,
                    by_handler: dict[str, str] | None = None):
    """`Check` and `DeclaredOutcome` — the guard's and the outcome's own evidence."""
    if behaviour is None:
        return
    by_handler = by_handler or {}
    unjoined = 0

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
        })
