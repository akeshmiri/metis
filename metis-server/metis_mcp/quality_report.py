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
    same discipline dq_017 uses for its own TestExecution/TestCase gap.
    SEC-02 (open high/critical Defects, scoped) is real as of Session 11:
    Defect<-[:PRODUCES]-TestExecution-[:EXECUTES]->TestCase-[:VERIFIES]->
    AcceptanceCriterion<-[:HAS_AC]-Requirement traces a Defect back to a
    Requirement scope (Session 12 renamed TestRun to TestCycle and moved
    both PRODUCES and EXECUTES down to the new per-case TestExecution node
    -- demo_data/generate_demo_data.py's TestCycle/TestExecution block) --
    falls back to None when no such edge exists yet (e.g. a
    pre-Session-11 graph)."""
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

    if requirement_ids is not None and not requirement_ids:
        sec02 = Metric("SEC-02", "Open high/critical Defects (scoped)", None, "0", None,
                        "No Requirement in scope.")
    else:
        has_execs = session.run(
            "MATCH (:TestExecution)-[:EXECUTES]->(:TestCase) RETURN count(*) > 0 AS any"
        ).single()["any"]
        if not has_execs:
            sec02 = Metric("SEC-02", "Open high/critical Defects (scoped)", None, "0", None,
                            "Not computable: no TestExecution->TestCase edge exists anywhere in this "
                            "codebase yet, so Defect nodes cannot be traced back to a Requirement "
                            "scope -- disclosed, not fabricated.")
        elif requirement_ids is None:
            open_defects = session.run(
                """
                MATCH (d:Defect)<-[:PRODUCES]-(:TestExecution)-[:EXECUTES]->(:TestCase)-[:VERIFIES]->
                      (:AcceptanceCriterion)<-[:HAS_AC]-(:Requirement)
                WHERE d.severity IN ['high', 'critical'] AND d.jira_status <> 'Done'
                RETURN count(DISTINCT d) AS c
                """
            ).single()["c"]
            sec02 = Metric("SEC-02", "Open high/critical Defects (scoped)", float(open_defects), "0",
                            open_defects == 0, f"{open_defects} open high/critical Defect(s) traced to "
                            f"scope via Defect<-PRODUCES-TestExecution-EXECUTES->TestCase-VERIFIES->"
                            f"AC<-HAS_AC-Requirement.")
        else:
            open_defects = session.run(
                """
                MATCH (d:Defect)<-[:PRODUCES]-(:TestExecution)-[:EXECUTES]->(:TestCase)-[:VERIFIES]->
                      (:AcceptanceCriterion)<-[:HAS_AC]-(req:Requirement)
                WHERE req.id IN $ids AND d.severity IN ['high', 'critical'] AND d.jira_status <> 'Done'
                RETURN count(DISTINCT d) AS c
                """, ids=requirement_ids,
            ).single()["c"]
            sec02 = Metric("SEC-02", "Open high/critical Defects (scoped)", float(open_defects), "0",
                            open_defects == 0, f"{open_defects} open high/critical Defect(s) traced to "
                            f"scope via Defect<-PRODUCES-TestExecution-EXECUTES->TestCase-VERIFIES->"
                            f"AC<-HAS_AC-Requirement.")
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


def build_test_design_report(session, scope: dict) -> dict:
    """Session 10: the real Intent/TestDesign backbone made queryable as a
    report -- per scoped Requirement, its AcceptanceCriteria, which real
    test-design technique(s) covered each one, and which TestCases (with
    real 6-level `.type`) resulted. Reuses resolve_scope() unchanged.

    Requirements with no AcceptanceCriterion/TestDesign at all (the bulk
    synthetic/grounded layers, which predate this session's backbone) show
    up with an empty acceptance_criteria list -- an honest, real "not
    covered by this backbone yet" signal, not an error."""
    scope_result = resolve_scope(session, scope)
    ids = scope_result.requirement_ids
    if ids is not None and not ids:
        return {
            "scope_description": scope_result.scope_description, "requirements": [],
            "total_acceptance_criteria": 0, "acceptance_criteria_with_test_design": 0,
            "techniques_used": [],
        }

    where_clause = "WHERE r.id IN $ids " if ids is not None else ""
    rows = session.run(
        f"MATCH (r:Requirement) {where_clause}"
        "OPTIONAL MATCH (r)-[:HAS_AC]->(ac:AcceptanceCriterion) "
        "OPTIONAL MATCH (td:TestDesign)-[:COVERS]->(ac) "
        "OPTIONAL MATCH (td)-[:PRODUCES]->(tc:TestCase) "
        "RETURN r.id AS req_id, r.text AS req_text, ac.id AS ac_id, ac.text AS ac_text, "
        "td.id AS design_id, td.techniques AS techniques, tc.id AS tc_id, tc.type AS tc_type",
        ids=ids,
    ).data()

    reqs: dict = {}
    for row in rows:
        req = reqs.setdefault(row["req_id"], {
            "requirement_id": row["req_id"], "text": row["req_text"], "acceptance_criteria": {},
        })
        if row["ac_id"] is None:
            continue
        ac = req["acceptance_criteria"].setdefault(row["ac_id"], {
            "ac_id": row["ac_id"], "text": row["ac_text"], "test_design": None, "test_cases": [],
        })
        if row["design_id"] is not None:
            ac["test_design"] = {"design_id": row["design_id"], "techniques": row["techniques"] or []}
        if row["tc_id"] is not None:
            entry = {"test_case_id": row["tc_id"], "type": row["tc_type"]}
            if entry not in ac["test_cases"]:
                ac["test_cases"].append(entry)

    result_requirements = []
    for req in reqs.values():
        acs = list(req["acceptance_criteria"].values())
        result_requirements.append({
            "requirement_id": req["requirement_id"], "text": req["text"],
            "acceptance_criteria": acs,
            "ac_count": len(acs),
            "ac_with_test_design_count": sum(1 for a in acs if a["test_design"] is not None),
        })

    total_acs = sum(r["ac_count"] for r in result_requirements)
    covered_acs = sum(r["ac_with_test_design_count"] for r in result_requirements)
    techniques_used = sorted({
        t for r in result_requirements for a in r["acceptance_criteria"]
        if a["test_design"] for t in a["test_design"]["techniques"]
    })

    return {
        "scope_description": scope_result.scope_description,
        "requirements": result_requirements,
        "total_acceptance_criteria": total_acs,
        "acceptance_criteria_with_test_design": covered_acs,
        "techniques_used": techniques_used,
    }
