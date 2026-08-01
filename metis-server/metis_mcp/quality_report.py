"""
Real, scoped quality reporting -- backs metis_generate_quality_report and
metis_generate_release_report (metis_mcp/server.py).

Fixes a real, verified gap in the existing metis_quality_score tool: its
`scope` parameter is threaded through 4 layers (server.py -> academy.
assemble_content -> dq_metrics.compute_quality_score -> every individual
dq_XXX(session) call) but used by NONE of them -- confirmed by reading
every dq_XXX function, not assumed. `metis_quality_score(scope="payments")`
and `metis_quality_score(scope="all")` return byte-identical numbers today.

This module implements the REAL production contract's scope shape
(mcp-contracts/metis-mcp-tool-contracts.json's metis_quality_score entry:
exactly one of release_id/service_id/requirement_id/project_wide) with
actual Cypher filtering -- not a new, invented shape.

Two real, pre-existing schema gaps had to be closed (in demo_data/
generate_demo_data.py, not here) before service_id/release_id scoping
could resolve to anything: Goal carried no domain/service property at all
(the generator's `_svc` field was Python-only bookkeeping, stripped before
every write), and zero Requirement-[:TRACES_TO]->Release edges existed
anywhere in the graph (confirmed by dq_017's own long-standing note).

Functional/performance/security are NOT the DQ framework's own 6-dimension
composite (conformance/completeness/consistency/corroboration/currency/
traceability) -- they're a different, real breakdown, requested explicitly
by name, built from a mix of existing DQ metrics (functional) and two new
metrics (SEC-01/PERF-01) grounded in real, already-established rules
(GRD-04's corroboration requirement, CONST-021/044's SLA-critical
performance-test requirement). Security's open-Defect signal is honestly
`None` with a note, not fabricated -- no TestRun->TestCase edge exists
anywhere in this codebase (dq_017's own documented gap), so Defect nodes
cannot be traced back to any Requirement scope.
"""
from dataclasses import dataclass

from metis_mcp.dq_metrics import Metric, dq_003, dq_006, dq_008
from metis_mcp.pyramid_gap_check import check_pyramid_gaps

COMPOSITE_RELEASE_GATE_THRESHOLD = 85  # reused from the DQ framework's own §3.2 threshold, not a new number


@dataclass
class ScopeResult:
    kind: str
    scope_description: str
    requirement_ids: list | None  # None means "project-wide, don't filter" (fast, existing unscoped path)


def resolve_scope(session, scope: dict) -> ScopeResult:
    """scope: exactly one of {requirement_id}, {service_id}, {release_id},
    {project_wide: true} -- the real, already-designed contract shape."""
    if scope.get("project_wide"):
        return ScopeResult("project_wide", "Whole project", None)

    if "requirement_id" in scope:
        rid = scope["requirement_id"]
        found = session.run("MATCH (r:Requirement {id: $id}) RETURN r.id AS id", id=rid).data()
        return ScopeResult("requirement_id", f"Requirement {rid}", [row["id"] for row in found])

    if "service_id" in scope:
        sid = scope["service_id"]
        rows = session.run(
            "MATCH (svc:Service {id: $id}) "
            "MATCH (g:Goal {domain: svc.owner_team})<-[:TRACES_TO]-(:Capability)<-[:TRACES_TO]-(:Epic)"
            "<-[:TRACES_TO]-(:Feature)<-[:TRACES_TO]-(req:Requirement) "
            "RETURN DISTINCT req.id AS id",
            id=sid,
        ).data()
        return ScopeResult("service_id", f"Service {sid}", [row["id"] for row in rows])

    if "release_id" in scope:
        rid = scope["release_id"]
        rows = session.run(
            "MATCH (req:Requirement)-[:TRACES_TO]->(:Release {id: $id}) RETURN DISTINCT req.id AS id",
            id=rid,
        ).data()
        return ScopeResult("release_id", f"Release {rid}", [row["id"] for row in rows])

    raise ValueError(
        f"scope must be exactly one of requirement_id/service_id/release_id/project_wide, got {scope!r}"
    )


def _score_functional(session, requirement_ids: list | None) -> list[Metric]:
    scope_ids = set(requirement_ids) if requirement_ids is not None else None
    return [dq_003(session, scope_ids), dq_006(session, scope_ids), dq_008(session, scope_ids)]


def _score_performance(session, requirement_ids: list | None) -> list[Metric]:
    """Performance-layer pyramid coverage (metis_mcp/pyramid_gap_check.py)
    among SLA-critical Transitions (CONST-021/044) whose implementing
    Method IMPLEMENTS a Requirement in scope."""
    # implementation_status = 'planned' Transitions are excluded outright
    # (Session 10) -- same reasoning as dq_metrics.py's DQ-008: a not-yet-built
    # Transition with zero test coverage isn't a real gap.
    planned_clause = "AND (t.implementation_status <> 'planned' OR t.implementation_status IS NULL)"
    if requirement_ids is None:
        transition_ids = [r["id"] for r in session.run(
            "MATCH (t:Transition) WHERE t.performance_sla_critical = true "
            "AND t.implementing_method_id IS NOT NULL " + planned_clause + " RETURN t.id AS id"
        ).data()]
    else:
        if not requirement_ids:
            return [Metric("PERF-01", "Performance-layer coverage (SLA-critical, scoped)", None, "100%",
                            None, "No Requirement in scope.")]
        transition_ids = [r["id"] for r in session.run(
            "MATCH (t:Transition) WHERE t.performance_sla_critical = true AND t.implementing_method_id IS NOT NULL "
            + planned_clause + " "
            "MATCH (m:Method {id: t.implementing_method_id})-[:IMPLEMENTS]->(req:Requirement) "
            "WHERE req.id IN $ids RETURN DISTINCT t.id AS id",
            ids=requirement_ids,
        ).data()]

    if not transition_ids:
        return [Metric("PERF-01", "Performance-layer coverage (SLA-critical, scoped)", None, "100%", None,
                        "No SLA-critical Transition with a determinable implementing Method resolves into this scope.")]
    covered = 0
    for tid in transition_ids:
        result = check_pyramid_gaps(session, tid)
        if result.coverage.get("performance"):
            covered += 1
    value = round(covered / len(transition_ids), 4)
    return [Metric("PERF-01", "Performance-layer coverage (SLA-critical, scoped)", value, "100%", value == 1.0,
                    f"{covered}/{len(transition_ids)} SLA-critical Transition(s) in scope have real "
                    f"performance-layer coverage.")]


def _score_security(session, requirement_ids: list | None) -> list[Metric]:
    """SEC-01 reuses GRD-04's real corroboration rule (Risk=High Requirement/
    BusinessRule/security-relevant guard/Constraint require >=2 independent
    sources), restricted to what's actually scopable today: BusinessRule
    and Constraint carry no real edge to any Requirement anywhere in this
    codebase (verified by grep), so only Requirement.risk_tag/
    corroboration_count is computable per-scope -- disclosed narrowing,
    same discipline dq_017 already uses for its own TestRun/TestCase gap.
    SEC-02 (open high/critical Defects) is honestly None -- no TestRun->
    TestCase edge exists anywhere in this codebase, so Defect nodes can't
    be traced back to a Requirement scope."""
    if requirement_ids is None:
        rows = session.run(
            "MATCH (r:Requirement) WHERE r.risk_tag = 'High' RETURN r.corroboration_count AS cc"
        ).data()
    elif not requirement_ids:
        rows = []
    else:
        rows = session.run(
            "MATCH (r:Requirement) WHERE r.id IN $ids AND r.risk_tag = 'High' RETURN r.corroboration_count AS cc",
            ids=requirement_ids,
        ).data()

    if requirement_ids is not None and not requirement_ids:
        sec01 = Metric("SEC-01", "High-risk corroboration compliance (scoped)", None, "100%", None,
                        "No Requirement in scope.")
    elif not rows:
        sec01 = Metric("SEC-01", "High-risk corroboration compliance (scoped)", None, "100%", None,
                        "No Risk=High Requirement in scope.")
    else:
        compliant = sum(1 for r in rows if (r["cc"] or 0) >= 2)
        value = round(compliant / len(rows), 4)
        sec01 = Metric("SEC-01", "High-risk corroboration compliance (scoped)", value, "100%", value == 1.0,
                        f"{compliant}/{len(rows)} Risk=High Requirement(s) in scope carry >=2 "
                        f"corroborating sources (GRD-04).")

    sec02 = Metric("SEC-02", "Open high/critical Defects (scoped)", None, "0", None,
                    "Not computable: no TestRun->TestCase edge exists anywhere in this codebase "
                    "(dq_017's own documented gap), so Defect nodes cannot be traced back to a "
                    "Requirement scope -- disclosed, not fabricated.")
    return [sec01, sec02]


_ATTRIBUTE_FNS = {"functional": _score_functional, "performance": _score_performance, "security": _score_security}
ALL_ATTRIBUTES = tuple(_ATTRIBUTE_FNS)


def _build_executive_summary(scope_result: ScopeResult, attribute_metrics: dict, gate_status: str,
                              composite: float | None) -> str:
    verdict = {
        "clear": "Ready to ship -- no blocking quality gate is currently failing.",
        "blocked_individual_gate": "NOT ready to ship -- at least one hard quality gate is failing.",
        "blocked_composite_threshold": "NOT ready to ship -- overall functional quality is below "
                                        f"the {COMPOSITE_RELEASE_GATE_THRESHOLD}-point release threshold.",
    }[gate_status]
    lines = [f"Scope: {scope_result.scope_description}.", verdict]
    lines.append(f"Functional quality: {composite}/100." if composite is not None
                 else "Functional quality: not computable for this scope yet (see detail).")
    for attr in ALL_ATTRIBUTES:
        metrics = attribute_metrics.get(attr, [])
        computable = [m for m in metrics if m.value is not None]
        if not computable:
            lines.append(f"{attr.capitalize()}: no real signal available for this scope yet.")
            continue
        worst = min(computable, key=lambda m: m.value)
        lines.append(f"{attr.capitalize()}: {worst.note}")
    return " ".join(lines)


def build_report(session, scope: dict, attributes: list[str] | None = None) -> dict:
    scope_result = resolve_scope(session, scope)
    attrs = list(attributes) if attributes else list(ALL_ATTRIBUTES)
    unknown = set(attrs) - set(ALL_ATTRIBUTES)
    if unknown:
        raise ValueError(f"Unknown attribute(s) {sorted(unknown)} -- must be a subset of {ALL_ATTRIBUTES}.")

    attribute_metrics: dict[str, list[Metric]] = {}
    dimension_breakdown = []
    for attr in attrs:
        metrics = _ATTRIBUTE_FNS[attr](session, scope_result.requirement_ids)
        attribute_metrics[attr] = metrics
        for m in metrics:
            status = "pass" if m.target_met else ("warn" if m.target_met is None else "fail")
            dimension_breakdown.append({
                "metric_id": m.id, "dimension": attr, "value": m.value,
                "target": m.target, "status": status, "note": m.note,
            })

    # Hard gates: any real, failing security/performance metric blocks
    # regardless of the functional composite (mirrors the real contract's
    # own "individual hard-gate failure blocks regardless of composite
    # score" note, CONST-034).
    blocking_reasons = [
        f"{m.id} ({attr}): {m.note}"
        for attr in ("security", "performance") if attr in attribute_metrics
        for m in attribute_metrics[attr] if m.target_met is False
    ]
    functional_values = [m.value for m in attribute_metrics.get("functional", []) if m.value is not None]
    composite = round(sum(functional_values) / len(functional_values) * 100, 1) if functional_values else None

    if blocking_reasons:
        gate_status = "blocked_individual_gate"
    elif composite is not None and composite < COMPOSITE_RELEASE_GATE_THRESHOLD:
        gate_status = "blocked_composite_threshold"
        blocking_reasons.append(
            f"Composite functional score {composite} is below the "
            f"{COMPOSITE_RELEASE_GATE_THRESHOLD}-point release-gate threshold (Data Quality Framework §3.2)."
        )
    else:
        gate_status = "clear"

    return {
        "scope_description": scope_result.scope_description,
        "scope_kind": scope_result.kind,
        "requirement_count": len(scope_result.requirement_ids) if scope_result.requirement_ids is not None else None,
        "composite_score": composite,
        "gate_status": gate_status,
        "blocking_reasons": blocking_reasons,
        "executive_summary": _build_executive_summary(scope_result, attribute_metrics, gate_status, composite),
        "detail": {"dimension_breakdown": dimension_breakdown},
    }


def build_release_report(session, release_id: str) -> dict:
    """REQ-METIS-ACD-05-style real changelog + a deterministic, rule-based
    recommendation (never a model judgment call) layered on top of
    build_report's real scoring."""
    from metis_mcp.academy import generate_changelog, format_changelog_plain_language

    report = build_report(session, {"release_id": release_id})
    scope_result = resolve_scope(session, {"release_id": release_id})
    entries = generate_changelog(session, scope_result.requirement_ids or [])

    recommendation = {
        "clear": "Ship it -- no blocking quality gate is failing for this release.",
        "blocked_individual_gate": "Do not ship -- a hard quality gate (security or performance) "
                                    "is failing. See blocking_reasons.",
        "blocked_composite_threshold": "Hold -- functional quality is below the release threshold. "
                                        "See blocking_reasons.",
    }[report["gate_status"]]

    report["release_id"] = release_id
    report["changelog"] = format_changelog_plain_language(entries)
    report["recommendation"] = recommendation
    return report
