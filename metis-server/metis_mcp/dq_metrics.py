"""
The full 22-metric Data Quality catalog (docs/metis-data-quality-framework.md
§2) + the weighted composite quality_score (§3.1) -- REQ-METIS-DQ-01.

Every metric below is a real Cypher computation against the actual
production ontology already built (schema/metis-graph-01/02/03-*.cypher),
reusing this project's own already-built real mechanisms wherever one
exists (metis_mcp/ears_checker.py for DQ-003, metis_mcp/layer8_heuristics.py
for DQ-004/DQ-018, metis_mcp/pyramid_gap_check.py for DQ-008's coverage
signal) rather than re-implementing them.

Several metrics are honestly not yet computable against this codebase's
real current state -- not stubbed with a fabricated number, `value: None`
with a `note` explaining exactly what real mechanism is missing:
  DQ-005/DQ-007  -- no :MicroRequirement node or PRODUCES(MicroRequirement
                     -> Transition) edge is written by any connector yet
                     (MicroRequirement decomposition, metis_mcp/
                     microrequirement.py, produces the node but nothing
                     yet writes it to the graph with PRODUCES edges)
  DQ-009         -- no TestCase carries a real t_valid property tied to a
                     specific Transition's supersession (t_valid is
                     currently only ever written on relationship
                     properties by demo_data, not on TestCase nodes)
  DQ-011         -- no ContradictionDetected episode type is ever created
                     (Disputed lifecycle_state is set directly by
                     behavior_model.py/llm_judge.py -- real, but without
                     the episode-level open/resolved timestamps this
                     metric needs)
  DQ-014         -- no SpecDriftDetected episode type is ever created (no
                     live API-spec connector exists -- locust_performance_
                     connector.py's own docstring already discloses zero
                     real :Endpoint entities exist in this graph)
  DQ-021         -- metis_submit_episode/the review API's decision endpoint
                     are disabled by default (REQ-METIS-CPT-01) -- there is
                     no real reviewer-override data to compute a rate from
                     until that write path is deliberately enabled
"""
from dataclasses import dataclass, field

from metis_mcp.ears_checker import check_ears_conformance
from metis_mcp.layer8_heuristics import check_vagueness, check_circular_traceability


@dataclass
class Metric:
    id: str
    name: str
    value: float | None       # 0.0-1.0 rate, or a raw count, per metric's own formula
    target: str
    target_met: bool | None
    note: str


def _rate_metric(mid, name, numerator, denominator, target, target_fn, note_ok, note_empty):
    if denominator == 0:
        return Metric(mid, name, None, target, None, note_empty)
    value = round(numerator / denominator, 4)
    return Metric(mid, name, value, target, target_fn(value), note_ok.format(n=numerator, d=denominator))


# ---------------- Dimension 1 -- Grounding ----------------

def dq_001(session) -> Metric:
    row = session.run(
        "MATCH (n) WHERE NOT n:Episode AND NOT n:Revision RETURN count(n) AS total, "
        "count(CASE WHEN n.source_episode_id IS NOT NULL THEN 1 END) AS grounded"
    ).single()
    return _rate_metric(
        "DQ-001", "Source-grounding completeness", row["grounded"], row["total"], "100%, always",
        lambda v: v == 1.0,
        "{n}/{d} entities carry source_episode_id.",
        "No entities in scope.",
    )


def dq_002(session) -> dict:
    """Not a single rate -- a tier distribution. Real property location
    disclosed: the framework doc specifies confidence_tier on Episode
    nodes, but the only real writer of this property in this codebase
    (demo_data/generate_demo_data.py) sets it on entity nodes (e.g.
    Requirement) instead -- computed here from wherever it actually is."""
    rows = session.run(
        "MATCH (n) WHERE n.confidence_tier IS NOT NULL RETURN n.confidence_tier AS tier, count(*) AS c"
    ).data()
    total = sum(r["c"] for r in rows)
    by_tier = {r["tier"]: r["c"] for r in rows}
    if total == 0:
        return {"id": "DQ-002", "name": "Extraction-confidence distribution", "value": None,
                "target": "auto_write >= 60%, quarantine <= 30%, rejected <= 10%", "target_met": None,
                "note": "No node in the graph currently carries confidence_tier."}
    dist = {tier: round(c / total, 4) for tier, c in by_tier.items()}
    target_met = dist.get("auto_write", 0) >= 0.6 and dist.get("quarantine", 0) <= 0.3 \
        and dist.get("rejected", 0) <= 0.1
    return {"id": "DQ-002", "name": "Extraction-confidence distribution", "value": dist,
            "target": "auto_write >= 60%, quarantine <= 30%, rejected <= 10%", "target_met": target_met,
            "note": f"Computed from {total} node(s) carrying confidence_tier "
                    f"(property found on entity nodes in practice, not Episode)."}


# ---------------- Dimension 2 -- Conformance ----------------

_REAL_EARS_PATTERNS = {"Ubiquitous", "EventDriven", "StateDriven", "UnwantedBehavior", "Optional"}


def dq_003(session, requirement_ids: set | None = None) -> Metric:
    """Real discrepancy from the doc's literal formula, disclosed: schema-01
    requires ears_pattern IS NOT NULL on every Requirement (enforced at
    write time by Layer 2 structural_validation.py, per
    test_structural_validation.py's own
    test_requirement_missing_ears_pattern_rejected_with_specific_reason) --
    so `ears_pattern IS NOT NULL` can never be false for any Requirement
    that actually made it into the graph, making the doc's literal formula
    vacuously 100% always. What's real and meaningful instead: whether the
    stored value is one of the five actual EARS pattern names
    ears_checker.py can produce, vs. the 'NonConformant' sentinel this
    project's own fixtures/connectors use for text that failed the real
    check (see test_requirement_quality.py/test_layer8_heuristics.py).

    requirement_ids: when given, scopes to exactly that Requirement set
    (metis_mcp/quality_report.py's real scope resolution) instead of the
    whole graph -- None (the default) preserves every existing caller's
    unscoped, whole-graph behavior unchanged."""
    if requirement_ids is not None:
        rows = session.run(
            "MATCH (r:Requirement) WHERE r.id IN $ids RETURN r.ears_pattern AS p", ids=list(requirement_ids)
        ).data()
    else:
        rows = session.run("MATCH (r:Requirement) RETURN r.ears_pattern AS p").data()
    total = len(rows)
    conformant = sum(1 for r in rows if r["p"] in _REAL_EARS_PATTERNS)
    return _rate_metric(
        "DQ-003", "EARS conformance rate", conformant, total, ">= 95%", lambda v: v >= 0.95,
        "{n}/{d} Requirement(s) carry one of the 5 real EARS pattern names.", "No Requirement nodes exist.",
    )


def dq_004(session) -> Metric:
    result = check_vagueness(session)
    if result.total == 0:
        return Metric("DQ-004", "Vagueness/unfalsifiability rate", None, "<= 5%", None,
                       "No AcceptanceCriterion nodes exist.")
    value = round(len(result.flagged_ids) / result.total, 4)
    return Metric("DQ-004", "Vagueness/unfalsifiability rate", value, "<= 5%", value <= 0.05,
                  f"{len(result.flagged_ids)}/{result.total} AcceptanceCriterion(s) flagged "
                  f"by the real Layer 8 vagueness heuristic.")


def dq_005(session) -> Metric:
    total = session.run("MATCH (m:MicroRequirement) RETURN count(m) AS c").single()["c"]
    return Metric("DQ-005", "Atomicity", None, "100%", None,
                   f"No :MicroRequirement nodes exist in the graph (found {total}) -- "
                   f"microrequirement.py's decomposition output isn't written back to the "
                   f"graph by any connector yet.")


# ---------------- Dimension 3 -- Completeness ----------------

def dq_006(session, requirement_ids: set | None = None) -> Metric:
    """requirement_ids: see dq_003's docstring -- same real scoping mechanism."""
    scope_clause = "WHERE r.id IN $ids " if requirement_ids is not None else ""
    rows = session.run(
        # count(ac), not count(*) -- count(*) counts the row OPTIONAL MATCH
        # still produces even on no match (with ac=null), silently reporting
        # every Requirement as covered regardless of whether HAS_AC matched.
        f"MATCH (r:Requirement) {scope_clause}"
        "OPTIONAL MATCH (r)-[:HAS_AC]->(ac:AcceptanceCriterion) "
        "WITH r, count(ac) AS ac_count "
        "RETURN r.lifecycle_state AS state, CASE WHEN ac_count > 0 THEN 1 ELSE 0 END AS covered",
        ids=list(requirement_ids) if requirement_ids is not None else None,
    ).data()
    approved = [r for r in rows if r["state"] == "Approved"]
    if not approved:
        return Metric("DQ-006", "AC coverage (Approved)", None, "100% for Approved",
                       None, f"No Approved-tier Requirement exists (of {len(rows)} total).")
    covered = sum(r["covered"] for r in approved)
    value = round(covered / len(approved), 4)
    return Metric("DQ-006", "AC coverage (Approved)", value, "100% for Approved", value == 1.0,
                  f"{covered}/{len(approved)} Approved Requirement(s) have >=1 HAS_AC edge.")


def dq_007(session) -> Metric:
    total = session.run("MATCH (m:MicroRequirement) RETURN count(m) AS c").single()["c"]
    return Metric("DQ-007", "Transition coverage", None, ">= 95% for Approved",
                   None, f"No :MicroRequirement nodes exist in the graph (found {total}) -- "
                        f"same real gap as DQ-005.")


def dq_008(session, requirement_ids: set | None = None) -> Metric:
    """Real signal reused from Stage 3's Pyramid-Gap Check
    (metis_mcp/pyramid_gap_check.py): a Transition counts as covered here
    iff its functional layer is covered per that module's own real
    coverage computation. Scoped to determinable Transitions (those with
    a real implementing_method_id claim) -- Transitions with no claim
    aren't silently counted as either covered or uncovered.

    requirement_ids: see dq_003's docstring. A Transition is in scope iff
    its implementing_method_id resolves to a Method that IMPLEMENTS a
    Requirement in the given set -- real graph traversal, not string
    matching."""
    from metis_mcp.pyramid_gap_check import check_pyramid_gaps
    # implementation_status = 'planned' Transitions are excluded outright
    # (Session 10) -- a not-yet-built Transition with zero test coverage
    # isn't a real gap, it doesn't exist yet. Absent property (pre-Session-10
    # data) defaults to "implemented", not silently excluded.
    planned_clause = "AND (t.implementation_status <> 'planned' OR t.implementation_status IS NULL)"
    if requirement_ids is not None:
        transition_ids = [r["id"] for r in session.run(
            "MATCH (t:Transition) WHERE t.implementing_method_id IS NOT NULL " + planned_clause + " "
            "MATCH (m:Method {id: t.implementing_method_id})-[:IMPLEMENTS]->(req:Requirement) "
            "WHERE req.id IN $ids "
            "RETURN DISTINCT t.id AS id", ids=list(requirement_ids),
        ).data()]
    else:
        transition_ids = [r["id"] for r in session.run(
            "MATCH (t:Transition) WHERE t.implementation_status <> 'planned' OR t.implementation_status IS NULL "
            "RETURN t.id AS id"
        ).data()]
    determinable = []
    covered = 0
    for tid in transition_ids:
        result = check_pyramid_gaps(session, tid)
        if not result.determinable:
            continue
        determinable.append(tid)
        if result.coverage.get("api_functional") or result.coverage.get("web_functional"):
            covered += 1
    if not determinable:
        return Metric("DQ-008", "Test coverage (functional)", None, "100%", None,
                       f"None of {len(transition_ids)} Transition(s) carry a determinable "
                       f"implementing_method_id -- no real functional-coverage signal to compute.")
    value = round(covered / len(determinable), 4)
    return Metric("DQ-008", "Test coverage (functional)", value, "100%", value == 1.0,
                  f"{covered}/{len(determinable)} determinable Transition(s) have real "
                  f"functional-layer coverage (Stage 3's own signal).")


def dq_009(session) -> Metric:
    total = session.run("MATCH (t:TestCase) RETURN count(t) AS c").single()["c"]
    with_t_valid = session.run("MATCH (t:TestCase) WHERE t.t_valid IS NOT NULL RETURN count(t) AS c").single()["c"]
    return Metric("DQ-009", "Stale-coverage rate", None, "<= 3%", None,
                   f"No TestCase node carries a real t_valid tied to a Transition's "
                   f"supersession ({with_t_valid}/{total} TestCase(s) have any t_valid at all) "
                   f"-- not computable yet.")


# ---------------- Dimension 4 -- Consistency ----------------

def dq_010(session) -> Metric:
    count = session.run("MATCH (n) WHERE n.lifecycle_state = 'Disputed' RETURN count(n) AS c").single()["c"]
    return Metric("DQ-010", "Open contradiction count", float(count), "Trend flat-to-down (no fixed target)",
                  None, f"{count} node(s) currently Disputed.")


def dq_011(session) -> Metric:
    count = session.run(
        "MATCH (e:Episode) WHERE e.episode_type = 'ContradictionDetected' RETURN count(e) AS c"
    ).single()["c"]
    return Metric("DQ-011", "Contradiction resolution latency", None, "<= 10 business days", None,
                  f"No ContradictionDetected episode type is ever created by this codebase "
                  f"(found {count}) -- Disputed is set directly on the affected node without "
                  f"an episode-level open/resolved timestamp pair to compute latency from.")


# ---------------- Dimension 5 -- Corroboration ----------------

def dq_012(session) -> Metric:
    rows = session.run(
        "MATCH (n) WHERE (n:Requirement OR n:BusinessRule) AND n.risk_tag = 'High' "
        "AND n.lifecycle_state = 'Approved' "
        "RETURN n.corroboration_count AS cc"
    ).data()
    if not rows:
        return Metric("DQ-012", "High-risk corroboration compliance", None, "100%", None,
                       "No Approved High-risk Requirement/BusinessRule exists.")
    compliant = sum(1 for r in rows if (r["cc"] or 0) >= 2)
    value = round(compliant / len(rows), 4)
    return Metric("DQ-012", "High-risk corroboration compliance", value, "100%", value == 1.0,
                  f"{compliant}/{len(rows)} Approved High-risk entity(ies) have corroboration_count >= 2.")


def dq_013(session) -> Metric:
    rows = session.run(
        "MATCH (n) WHERE (n:Requirement OR n:AcceptanceCriterion) AND n.lifecycle_state = 'Approved' "
        "RETURN n.corroboration_count AS cc"
    ).data()
    values = [r["cc"] for r in rows if r["cc"] is not None]
    if not values:
        return Metric("DQ-013", "Average corroboration count (non-high-risk)", None,
                       "Track as trend, no hard target", None, "No Approved Requirement/AcceptanceCriterion exists.")
    avg = round(sum(values) / len(values), 3)
    return Metric("DQ-013", "Average corroboration count (non-high-risk)", avg,
                  "Track as trend, no hard target", None, f"Averaged over {len(values)} Approved entity(ies).")


# ---------------- Dimension 6 -- Currency ----------------

def dq_014(session) -> Metric:
    count = session.run(
        "MATCH (e:Episode) WHERE e.episode_type = 'SpecDriftDetected' RETURN count(e) AS c"
    ).single()["c"]
    endpoints = session.run("MATCH (e:Endpoint) RETURN count(e) AS c").single()["c"]
    return Metric("DQ-014", "Spec-vs-deployed drift rate", None, "<= 2%", None,
                  f"No SpecDriftDetected episode is ever created (found {count}), and no real "
                  f":Endpoint entity exists yet ({endpoints}) -- not computable.")


def dq_015(session) -> Metric:
    """Real proxy, disclosed: no Requirement node ever carries its own
    t_valid (demo_data only ever writes t_valid on relationship
    properties, e.g. the TRACES_TO edge to Feature) -- so this uses that
    edge's t_valid as a real, if indirect, freshness signal instead of
    fabricating a node-level timestamp."""
    rows = session.run(
        "MATCH (r:Requirement)-[e:TRACES_TO]->() WHERE e.t_valid IS NOT NULL "
        "RETURN duration.inDays(datetime(e.t_valid), datetime()).days AS age_days"
    ).data()
    if not rows:
        return Metric("DQ-015", "Median requirement age since last validity check", None,
                       "<= 180 days", None,
                       "No Requirement carries a TRACES_TO edge with t_valid -- not computable.")
    ages = sorted(r["age_days"] for r in rows)
    median = ages[len(ages) // 2] if len(ages) % 2 else (ages[len(ages) // 2 - 1] + ages[len(ages) // 2]) / 2
    return Metric("DQ-015", "Median requirement age since last validity check", float(median),
                  "<= 180 days", median <= 180,
                  f"Median over {len(ages)} Requirement(s), using each one's TRACES_TO edge "
                  f"t_valid as a real proxy for node-level t_valid (which nothing writes yet).")


# ---------------- Dimension 7 -- Uniqueness ----------------

def dq_016(session) -> Metric:
    """Now real: metis_mcp/sleep_time_consolidation.py's find_near_duplicates
    (§8.3) -- real lexical Jaccard similarity, not semantic (no embedding
    model available, same disclosed constraint as hybrid_retrieval.py's
    semantic_vector_search)."""
    from metis_mcp.sleep_time_consolidation import find_near_duplicates
    total = session.run("MATCH (r:Requirement) RETURN count(r) AS c").single()["c"]
    if total == 0:
        return Metric("DQ-016", "Near-duplicate density", None, "<= 5%", None,
                       "No Requirement nodes exist.")
    proposals = find_near_duplicates(session, "Requirement", threshold=0.7)
    flagged_ids = {pid for p in proposals for pid in (p.id_a, p.id_b)}
    value = round(len(flagged_ids) / total, 4)
    return Metric("DQ-016", "Near-duplicate density", value, "<= 5%", value <= 0.05,
                  f"{len(flagged_ids)}/{total} Requirement(s) appear in >=1 real near-duplicate "
                  f"pair (Jaccard >= 0.7, lexical not semantic).")


# ---------------- Dimension 8 -- Traceability Integrity ----------------

def dq_017(session) -> Metric:
    """Real, disclosed narrowing of the doc's formula: no connector or demo
    generator anywhere in this codebase ever creates a TestRun->TestCase
    edge (verified by grep -- demo_data.py's only TestRun edge is
    TestRun-[:PRODUCES]->Defect), so 'unbroken path to >=1 Approved
    TestRun' cannot be computed as literally specified. What's real and
    checkable today is the Requirement-[:HAS_AC]->AcceptanceCriterion
    <-[:VERIFIES]-TestCase chain -- VERIFIES targets AcceptanceCriterion,
    never Requirement directly (Requirement<-VERIFIES-TestCase with no
    HAS_AC in between is the exact anti-pattern metis_mcp/
    layer8_heuristics.py's DQ-018 check already flags as suspicious). This
    metric measures the real AC-mediated chain, and says so, rather than
    inventing a TestRun-linkage edge type that doesn't exist anywhere in
    this system."""
    approved_in_release = session.run(
        "MATCH (r:Requirement)-[:TRACES_TO]->(:Release) WHERE r.lifecycle_state = 'Approved' "
        "RETURN count(DISTINCT r) AS c"
    ).single()["c"]
    if approved_in_release == 0:
        return Metric("DQ-017", "End-to-end chain completeness", None, "100% for anything shipped",
                       None, "No Approved Requirement is linked to a Release via TRACES_TO -- "
                             "not computable (this platform has no real Release-linkage data yet).")
    complete = session.run(
        """
        MATCH (r:Requirement)-[:TRACES_TO]->(:Release) WHERE r.lifecycle_state = 'Approved'
        MATCH (r)-[:HAS_AC]->(:AcceptanceCriterion)<-[:VERIFIES]-(:TestCase)
        RETURN count(DISTINCT r) AS c
        """
    ).single()["c"]
    value = round(complete / approved_in_release, 4)
    return Metric("DQ-017", "End-to-end chain completeness", value, "100% for anything shipped",
                  value == 1.0, f"{complete}/{approved_in_release} Approved+Released Requirement(s) "
                                 f"have >=1 AcceptanceCriterion with a real VERIFIES edge from a "
                                 f"TestCase -- narrowed to the AC-mediated chain since no "
                                 f"TestRun-linkage edge exists anywhere in this codebase yet "
                                 f"(see docstring).")


def dq_018(session) -> Metric:
    result = check_circular_traceability(session)
    return Metric("DQ-018", "Circular-traceability count", float(len(result.flagged_ids)), "0",
                  len(result.flagged_ids) == 0,
                  f"{len(result.flagged_ids)} Requirement(s) flagged: {result.flagged_ids[:5]}"
                  + ("..." if len(result.flagged_ids) > 5 else ""))


def dq_019(session) -> Metric:
    # No OPTIONAL MATCH here deliberately -- one on an unused variable would
    # duplicate rows for any Method with >1 IMPLEMENTS edge, inflating
    # count(m) (the same real class of bug fixed in dq_006 above).
    row = session.run(
        "MATCH (m:Method) "
        "RETURN count(m) AS total, count(CASE WHEN NOT EXISTS { (m)-[:IMPLEMENTS]->(:Requirement) } "
        "THEN 1 END) AS orphans"
    ).single()
    return _rate_metric(
        "DQ-019", "Orphan-code rate", row["orphans"], row["total"], "Track as trend, not a hard gate",
        lambda v: None, "{n}/{d} Method(s) have no IMPLEMENTS edge to a Requirement.",
        "No Method nodes exist.",
    )


# ---------------- Dimension 9 -- Process Trust ----------------

def dq_020(session) -> Metric:
    rows = session.run(
        "MATCH (n) WHERE n.judge_verdict IS NOT NULL RETURN n.judge_verdict AS v"
    ).data()
    if not rows:
        return Metric("DQ-020", "Judge disagreement rate", None, "Tracked by connector/source type",
                       None, "No node has been through the Layer 6 judge yet (llm_judge.py).")
    disagreements = sum(1 for r in rows if r["v"] is False)
    value = round(disagreements / len(rows), 4)
    return Metric("DQ-020", "Judge disagreement rate", value, "Tracked by connector/source type", None,
                  f"{disagreements}/{len(rows)} judged node(s) disagreed with their claim.")


def dq_021(session) -> Metric:
    return Metric("DQ-021", "Reviewer override rate", None, "Rising trend investigated", None,
                  "review_api_server.py's /api/decision endpoint refuses to write "
                  "(REQ-METIS-CPT-01, disabled by default) -- no real reviewer-decision data "
                  "exists to compute an override rate from until that write path is enabled.")


def dq_022(session) -> Metric:
    row = session.run(
        "MATCH (e:Episode) WHERE e.source_connector = 'guardrail-corpus-runner' "
        "RETURN e.pass_rate AS pass_rate, e.min_pass_rate AS min_pass_rate ORDER BY e.t_recorded DESC LIMIT 1"
    ).single()
    if row is None or row["pass_rate"] is None:
        return Metric("DQ-022", "False-acceptance rate (adversarial set)", None,
                       "The platform's core safety metric", None,
                       "No guardrail-corpus-runner Episode found -- run guardrails/corpus_runner.py "
                       "at least once to populate this (test_corpus_runner.py exercises it in-memory "
                       "without writing an Episode, so it alone doesn't populate this metric).")
    false_acceptance = round(1 - row["pass_rate"], 4)
    return Metric("DQ-022", "False-acceptance rate (adversarial set)", false_acceptance,
                  "The platform's core safety metric", false_acceptance == 0.0,
                  f"Derived from the most recent guardrail-corpus-runner pass_rate "
                  f"({row['pass_rate']}, min required {row['min_pass_rate']}).")


ALL_METRIC_FNS = [dq_001, dq_003, dq_004, dq_005, dq_006, dq_007, dq_008, dq_009, dq_010,
                   dq_011, dq_012, dq_013, dq_014, dq_015, dq_016, dq_017, dq_018, dq_019,
                   dq_020, dq_021, dq_022]


def compute_all_metrics(session) -> dict:
    metrics = {m.id: {"name": m.name, "value": m.value, "target": m.target,
                       "target_met": m.target_met, "note": m.note}
               for m in (fn(session) for fn in ALL_METRIC_FNS)}
    metrics["DQ-002"] = dq_002(session)
    return metrics


# ---------------- §3.1 Composite score ----------------

_COMPOSITE_WEIGHTS = {
    "conformance": 0.15,     # DQ-003
    "completeness": 0.30,    # avg(DQ-006, DQ-007, DQ-008)
    "consistency": 0.10,     # DQ-010, inverted/normalized
    "corroboration": 0.20,   # DQ-012
    "currency": 0.10,        # DQ-014, inverted
    "traceability": 0.15,    # DQ-017
}


def _invert_dq010(open_count: float) -> float:
    """§3.1 says 'inverted, normalized' without pinning an exact formula
    (DQ-010 itself has no fixed target -- 'trend flat-to-down'). Disclosed,
    chosen normalization: each open Disputed item costs 10 points off 100,
    floored at 0 -- a real, simple, documented choice, not derived from
    the framework doc (which leaves this specific curve unspecified)."""
    return max(0.0, 100.0 - open_count * 10.0)


def compute_quality_score(session, scope: str | None = None) -> dict:
    """§3.1's weighted composite + §3.2's release-gate threshold (85).
    Any constituent metric with value=None (real, disclosed 'not yet
    computable') is excluded from the weighted average rather than
    silently treated as 0 or 100 -- the reported score's own `coverage`
    field states exactly which components it's actually based on, and
    `all_release_gate_metrics_computed` is False whenever any of the six
    isn't real data yet, so the release gate can't be silently satisfied
    by missing data looking like a good score."""
    d003 = dq_003(session)
    d006 = dq_006(session)
    d007 = dq_007(session)
    d008 = dq_008(session)
    d010 = dq_010(session)
    d012 = dq_012(session)
    d014 = dq_014(session)
    d017 = dq_017(session)

    completeness_parts = [m.value for m in (d006, d007, d008) if m.value is not None]
    completeness = (sum(completeness_parts) / len(completeness_parts) * 100) if completeness_parts else None

    components = {
        "conformance": d003.value * 100 if d003.value is not None else None,
        "completeness": completeness,
        "consistency": _invert_dq010(d010.value) if d010.value is not None else None,
        "corroboration": d012.value * 100 if d012.value is not None else None,
        "currency": (1 - d014.value) * 100 if d014.value is not None else None,
        "traceability": d017.value * 100 if d017.value is not None else None,
    }

    computed = {k: v for k, v in components.items() if v is not None}
    if not computed:
        return {
            "scope": scope or "all", "quality_score": None, "release_gate_pass": None,
            "components": components, "all_release_gate_metrics_computed": False,
            "note": "No constituent metric had real data -- composite score not computable.",
        }
    total_weight = sum(_COMPOSITE_WEIGHTS[k] for k in computed)
    score = sum(components[k] * _COMPOSITE_WEIGHTS[k] for k in computed) / total_weight
    score = round(score, 2)
    all_computed = len(computed) == len(_COMPOSITE_WEIGHTS)

    return {
        "scope": scope or "all", "quality_score": score,
        "release_gate_pass": (score >= 85) if all_computed else None,
        "components": components,
        "all_release_gate_metrics_computed": all_computed,
        "note": None if all_computed else
                f"Only {len(computed)}/{len(_COMPOSITE_WEIGHTS)} composite components have real "
                f"data -- score is a partial weighted average (weights renormalized over what's "
                f"available), not a decision-ready release-gate number.",
    }
