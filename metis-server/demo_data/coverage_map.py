"""
Real coverage map over the live demo dataset -- exercises the platform's
own coverage tooling (metis_mcp/dq_metrics.py, metis_mcp/
pyramid_gap_check.py) against whatever's actually in Neo4j right now,
plus a new per-Goal Requirement-coverage aggregation (AcceptanceCriterion/
TestCase/IMPLEMENTS via real Cypher) that no existing DQ metric reports at
that granularity. Every number below is a real query result against the
live graph -- not derived from generate_demo_data.py's own reported
summary, which only tracks what it wrote, not what's actually true of the
graph afterward.

Usage: .venv/bin/python3 -m demo_data.coverage_map > coverage_map.json
"""
import json
import os
import sys

from metis_mcp.config_manager import ConfigManager
from metis_mcp.dq_metrics import compute_all_metrics, compute_quality_score
from metis_mcp.pyramid_gap_check import check_pyramid_gaps, LAYERS


def per_goal_requirement_coverage(session) -> list[dict]:
    rows = session.run(
        """
        MATCH (g:Goal)<-[:TRACES_TO]-(:Capability)<-[:TRACES_TO]-(:Epic)<-[:TRACES_TO]-(:Feature)<-[:TRACES_TO]-(req:Requirement)
        OPTIONAL MATCH (req)-[:HAS_AC]->(ac:AcceptanceCriterion)
        OPTIONAL MATCH (req)-[:HAS_AC]->(:AcceptanceCriterion)<-[:VERIFIES]-(tc:TestCase)
        OPTIONAL MATCH (req)<-[:IMPLEMENTS]-(m:Method)
        WITH g, req,
             count(DISTINCT ac) AS ac_count, count(DISTINCT tc) AS tc_count,
             count(DISTINCT m) AS method_count,
             count(DISTINCT CASE WHEN m.is_demo_data IS NULL THEN m END) AS real_method_count
        RETURN g.id AS goal_id, g.name AS goal_name, g.source_kind AS source_kind,
               count(req) AS total_reqs,
               sum(CASE WHEN ac_count > 0 THEN 1 ELSE 0 END) AS with_ac,
               sum(CASE WHEN tc_count > 0 THEN 1 ELSE 0 END) AS with_test,
               sum(CASE WHEN method_count > 0 THEN 1 ELSE 0 END) AS with_implements,
               sum(CASE WHEN real_method_count > 0 THEN 1 ELSE 0 END) AS with_real_implements
        ORDER BY source_kind, goal_name
        """
    ).data()
    return rows


def transition_pyramid_coverage(session) -> dict:
    transition_ids = [r["id"] for r in session.run("MATCH (t:Transition) RETURN t.id AS id").data()]
    determinable = 0
    layer_covered = {layer: 0 for layer in LAYERS}
    not_determinable = 0
    for tid in transition_ids:
        result = check_pyramid_gaps(session, tid)
        if not result.determinable:
            not_determinable += 1
            continue
        determinable += 1
        for layer in LAYERS:
            if result.coverage.get(layer):
                layer_covered[layer] += 1
    return {
        "total_transitions": len(transition_ids),
        "determinable": determinable,
        "not_determinable_no_implementing_method": not_determinable,
        "layer_coverage_pct": {
            layer: (round(layer_covered[layer] / determinable * 100, 1) if determinable else None)
            for layer in LAYERS
        },
    }


def build_report(session) -> dict:
    return {
        "dq_metrics": {k: {"value": v["value"], "target": v["target"], "target_met": v["target_met"],
                            "note": v["note"]} for k, v in compute_all_metrics(session).items()},
        "quality_score": compute_quality_score(session),
        "per_goal_requirement_coverage": per_goal_requirement_coverage(session),
        "transition_pyramid_coverage": transition_pyramid_coverage(session),
    }


def main():
    from neo4j import GraphDatabase
    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{neo4j_cfg.get('password_env')} must be set.")
    driver = GraphDatabase.driver(neo4j_cfg["uri"], auth=(neo4j_cfg["user"], password))
    driver.verify_connectivity()
    try:
        with driver.session() as session:
            report = build_report(session)
    finally:
        driver.close()
    json.dump(report, sys.stdout, indent=2, default=str)


if __name__ == "__main__":
    main()
