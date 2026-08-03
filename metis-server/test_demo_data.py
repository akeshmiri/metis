"""
Tests for the Demo Data generator (demo_data/generate_demo_data.py) --
against a real Neo4j instance, at a small scale (fast, still exercises
every code path the full-scale run does). The full-scale run itself
(~12,000 nodes, ~2s) is verified separately/manually -- see QUICKSTART.md.
"""
import os
import sys

from neo4j import GraphDatabase

from demo_data.generate_demo_data import generate, wipe_demo_data, Scale

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")


def _real_demo_node_count() -> int:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            return s.run("MATCH (n {is_demo_data: true}) RETURN count(n) AS c").single()["c"]
    finally:
        driver.close()


def test_generate_reported_total_matches_real_graph_count():
    wipe_demo_data(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    summary = generate(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, scale=Scale(factor=0.05), seed=7)
    assert summary["total_nodes"] > 0
    assert _real_demo_node_count() == summary["total_nodes"]


def test_generate_spans_many_labels_and_relationship_types():
    """Not just volume -- real variety, per the actual request this was
    built for ('over 10K of different types with different relationships
    to give the sense of reality')."""
    wipe_demo_data(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    summary = generate(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, scale=Scale(factor=0.1), seed=7)
    assert len(summary["nodes_by_label"]) >= 30
    assert len(summary["relationships_by_type"]) >= 8


def test_no_relationship_points_at_a_nonexistent_node():
    """No fabrication: every generated relationship's endpoints are real
    nodes this same run actually created."""
    wipe_demo_data(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    generate(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, scale=Scale(factor=0.1), seed=7)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            # Guard used to be excepted here (its nodes weren't is_demo_data-
            # tagged) -- it's a plain Transition property now, nothing left
            # to except.
            dangling = s.run(
                "MATCH (a {is_demo_data: true})-[r]->(b) "
                "WHERE b.is_demo_data IS NULL "
                "RETURN count(r) AS c"
            ).single()["c"]
        assert dangling == 0
    finally:
        driver.close()


def test_requirements_are_real_ears_conformant_and_really_tiered():
    wipe_demo_data(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    generate(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, scale=Scale(factor=0.1), seed=7)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rec = s.run(
                "MATCH (r:Requirement {is_demo_data: true}) "
                "RETURN count(r) AS total, "
                "count(CASE WHEN r.ears_pattern IS NULL THEN 1 END) AS missing_pattern, "
                "count(DISTINCT r.lifecycle_state) AS distinct_states"
            ).single()
        assert rec["total"] > 0
        assert rec["missing_pattern"] == 0  # Layer 2 gate: never written without a real pattern
        assert rec["distinct_states"] >= 2  # real tiering diversity, not one flat value
    finally:
        driver.close()


def test_wipe_only_removes_demo_tagged_nodes():
    wipe_demo_data(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    generate(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, scale=Scale(factor=0.05), seed=7)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            real_before = s.run("MATCH (n) WHERE n.is_demo_data IS NULL RETURN count(n) AS c").single()["c"]
    finally:
        driver.close()

    wipe_demo_data(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    assert _real_demo_node_count() == 0

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            real_after = s.run("MATCH (n) WHERE n.is_demo_data IS NULL RETURN count(n) AS c").single()["c"]
        assert real_after == real_before
    finally:
        driver.close()


def test_grounded_requirements_trace_to_real_metis_content():
    """The grounded layer (demo_data/metis_grounded.py) adds real Métis
    project Requirements alongside the fully synthetic layer -- this
    checks they're genuinely traceable, not just present."""
    wipe_demo_data(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    generate(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, scale=Scale(factor=0.05), seed=7)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rec = s.run(
                "MATCH (req:Requirement {source_kind: 'metis_project'}) "
                "RETURN count(req) AS total, "
                "count(CASE WHEN req.derived_from IS NULL THEN 1 END) AS missing_derived_from, "
                "count(CASE WHEN NOT req.derived_from STARTS WITH 'REQ-METIS-' THEN 1 END) AS bad_tag_shape"
            ).single()
            assert rec["total"] == 75  # every real REQ-METIS-* tag in corpus/*.md has a paraphrase
            assert rec["missing_derived_from"] == 0
            assert rec["bad_tag_shape"] == 0

            real_method_edge = s.run(
                "MATCH (m:Method)-[:IMPLEMENTS]->(req:Requirement {source_kind: 'metis_project'}) "
                "WHERE m.is_demo_data IS NULL "
                "RETURN count(*) AS c"
            ).single()["c"]
            assert real_method_edge > 0  # at least some resolve to the real, pre-existing Method pool

            confluence = s.run(
                "MATCH (e:Episode {source_kind: 'metis_project', episode_type: 'DocumentIngested'}) "
                "RETURN count(e) AS c"
            ).single()["c"]
            assert confluence > 0
    finally:
        driver.close()
        # dq_metrics.py's global metrics aren't demo-data-scoped -- other
        # test files in the regression suite assume no demo data is loaded
        # when they run. Leave the graph clean, same invariant every other
        # test in this file already maintains.
        wipe_demo_data(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)


def test_goals_carry_domain_and_some_requirements_trace_to_a_release():
    """Two real, previously-absent properties/edges quality_report.py's
    service_id/release_id scope resolution needs: Goal.domain (the
    generator's per-goal service string, now actually persisted, not
    stripped) and Requirement-[:TRACES_TO]->Release (previously zero such
    edges existed anywhere in the graph -- dq_017's own long-standing
    note)."""
    wipe_demo_data(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    generate(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, scale=Scale(factor=0.1), seed=7)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            goals_missing_domain = s.run(
                "MATCH (g:Goal {is_demo_data: true}) WHERE g.domain IS NULL RETURN count(g) AS c"
            ).single()["c"]
            assert goals_missing_domain == 0

            release_edges = s.run(
                "MATCH (:Requirement)-[:TRACES_TO]->(:Release) RETURN count(*) AS c"
            ).single()["c"]
            assert release_edges > 0

            # service_id scoping's real join: Service.owner_team must match
            # some real Goal.domain, or it silently resolves to nothing.
            matched = s.run(
                "MATCH (svc:Service), (g:Goal {is_demo_data: true}) "
                "WHERE svc.owner_team = g.domain RETURN count(DISTINCT svc) AS c"
            ).single()["c"]
            assert matched > 0
    finally:
        driver.close()
        wipe_demo_data(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
