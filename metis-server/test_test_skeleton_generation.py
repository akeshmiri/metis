"""
Tests for Stage 3/4/5 of metis-behavior-model-test-pipeline.md:
metis_mcp/pyramid_gap_check.py + metis_mcp/test_skeleton_generator.py --
against the real Neo4j graph, including the real Method
(ClassificationGate.check, cognify/code_graph_archaeology.py's real
extraction from this project's own actual code) and the real 119 TestCase
nodes already ingested for this repo by test-suite-ingest.
"""
import os
import shutil
import sys

from neo4j import GraphDatabase

from metis_mcp.behavior_model import load_transition
from metis_mcp.pyramid_gap_check import check_pyramid_gaps
from metis_mcp.test_skeleton_generator import propose_test_skeletons, commit_generated_test

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

# Real Method, real code, no fabricated fixture -- same one test_bm01_corroboration.py uses.
METHOD_ID = "metis-server:metis_mcp/classification_gate.py:ClassificationGate.check"
# A repo prefix no real connector has ever landed a TestCase/Method under --
# used to exercise the clean "no coverage at all" path without relying on
# real repo-wide state (which, correctly, already has real performance/
# integration TestCase coverage -- see test_real_method_with_... below).
NO_COVERAGE_METHOD_ID = "pgc-test-isolated-repo:pgc/isolated_module.py:Isolated.method"
OUTPUT_DIR = "pgc-test-generated-tests"

_driver = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


def _setup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'pgc-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())
        load_transition(s, "pgc-test-transition-no-method", "pgc-test-episode",
                         "pgc-test-A", "pgc-test-B", "pgc-test-trig", "true")
        load_transition(s, "pgc-test-transition-functional-gap", "pgc-test-episode",
                         "pgc-test-A", "pgc-test-C", "pgc-test-trig2", "true",
                         implementing_method_id=METHOD_ID)
        load_transition(s, "pgc-test-transition-perf-critical", "pgc-test-episode",
                         "pgc-test-A", "pgc-test-D", "pgc-test-trig3", "true",
                         implementing_method_id=NO_COVERAGE_METHOD_ID, performance_sla_critical=True)


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'pgc-test-' DETACH DELETE n"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (gt:GeneratedTest) WHERE gt.transition_id STARTS WITH 'pgc-test-' DETACH DELETE gt"
        ).consume())
    if os.path.isdir(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)


def test_no_implementing_method_id_is_not_determinable():
    with _session() as s:
        result = check_pyramid_gaps(s, "pgc-test-transition-no-method")
    assert not result.determinable
    assert "no implementing_method_id claim" in result.reason


def test_real_method_with_no_functional_or_unit_coverage_reports_real_gaps():
    """ClassificationGate.check has 0 real IMPLEMENTS edges and 0 real
    TestCase nodes at its exact file path -- verified directly against
    Neo4j before writing this test (not assumed)."""
    with _session() as s:
        result = check_pyramid_gaps(s, "pgc-test-transition-functional-gap")
    assert result.determinable
    assert result.coverage["api_functional"] is False
    assert result.coverage["web_functional"] is False
    assert result.coverage["unit"] is False
    # 119 other real TestCase nodes exist under repo 'metis-server:' at other
    # paths (including real performance-type ones from perf/locustfile.py) --
    # a real (if coarse) integration-layer signal, not fabricated.
    assert result.coverage["integration"] is True
    assert "api_functional" in result.gaps  # the one functional-gap slot, untyped default
    assert "unit" in result.gaps
    assert "performance" not in result.gaps, "not SLA-critical -- performance isn't a relevant layer"


def test_performance_sla_critical_with_isolated_method_has_no_coverage_anywhere():
    """NO_COVERAGE_METHOD_ID's repo has never had any connector land a Method
    or TestCase under it -- every layer should honestly report uncovered."""
    with _session() as s:
        result = check_pyramid_gaps(s, "pgc-test-transition-perf-critical")
    assert result.performance_sla_critical
    assert result.coverage == {
        "unit": False, "integration": False, "api_functional": False,
        "web_functional": False, "e2e": False, "performance": False,
    }
    assert set(result.gaps) == {"unit", "integration", "api_functional", "e2e", "performance"}


def test_propose_test_skeletons_generates_only_for_api_functional_and_performance():
    with _session() as s:
        result = propose_test_skeletons(s, "pgc-test-transition-perf-critical")
    assert result["applicable"]
    assert result["requires_human_review"] is True
    generated_types = {sk["test_type"] for sk in result["skeletons"]}
    # unit and e2e are also real gaps for this Method, but Stage 3 never
    # auto-generates skeletons for either.
    assert "unit" not in generated_types
    assert "e2e" not in generated_types
    assert "api_functional" in generated_types
    assert "performance" in generated_types
    for sk in result["skeletons"]:
        assert "TODO(body-fill)" in sk["skeleton_code"]
        assert "pgc-test-transition-perf-critical" in sk["skeleton_code"]


def test_generated_skeleton_flags_const050_completeness_gap_closure():
    """CONST-050/REQ-METIS-BM-05: pgc-test-transition-functional-gap is the
    ONLY Transition firing on (pgc-test-A, pgc-test-trig2) -- its existence
    is what keeps that pair off check_completeness()'s gap list, so its
    generated test must be flagged as closing that gap."""
    with _session() as s:
        result = propose_test_skeletons(s, "pgc-test-transition-functional-gap")
        functional_sk = next(sk for sk in result["skeletons"] if sk["test_type"] == "api_functional")
        assert functional_sk["closes_completeness_gap"] is True

        # Add a real sibling Transition on the identical (state, trigger) pair --
        # now pgc-test-transition-functional-gap is no longer the sole reason
        # that pair isn't a completeness gap, so it should no longer claim closure.
        load_transition(s, "pgc-test-transition-sibling", "pgc-test-episode",
                         "pgc-test-A", "pgc-test-E", "pgc-test-trig2", "false")
        result2 = propose_test_skeletons(s, "pgc-test-transition-functional-gap")
        functional_sk2 = next(sk for sk in result2["skeletons"] if sk["test_type"] == "api_functional")
        assert functional_sk2["closes_completeness_gap"] is False


def test_propose_test_skeletons_reports_not_applicable_without_implementing_method():
    with _session() as s:
        result = propose_test_skeletons(s, "pgc-test-transition-no-method")
    assert result["applicable"] is False
    assert result["skeleton"] is None


def test_commit_generated_test_refuses_without_confirmed_convention():
    """CONST-045/REQ-METIS-CONN-06: no project_test_id_conventions entry is
    confirmed for 'metis-server' -- must halt, never fabricate an
    annotation format."""
    with _session() as s:
        proposal = propose_test_skeletons(s, "pgc-test-transition-functional-gap")
        result = commit_generated_test(
            s, "pgc-test-transition-functional-gap", proposal["skeletons"][0],
            repo="metis-server", source_episode_id="pgc-test-episode",
            project_test_id_conventions=None,
        )
    assert result["committed"] is False
    assert result["pr_created"] is False
    assert "REQ-METIS-CONN-06" in result["reason"]
    assert not os.path.isdir(OUTPUT_DIR), "must not write a file when no convention is confirmed"


def test_commit_generated_test_writes_real_file_and_provenance_when_configured():
    conventions = {"metis-server": {"pattern_type": "comment_tag", "pattern": "# TC-ID: (\\S+)"}}
    with _session() as s:
        proposal = propose_test_skeletons(s, "pgc-test-transition-functional-gap")
        result = commit_generated_test(
            s, "pgc-test-transition-functional-gap", proposal["skeletons"][0],
            repo="metis-server", source_episode_id="pgc-test-episode",
            project_test_id_conventions=conventions, output_dir=OUTPUT_DIR,
        )
        assert result["committed"] is True
        assert result["pr_created"] is False, "no real git repo in this environment -- must not fake a PR"
        assert os.path.isfile(result["file_path"])
        with open(result["file_path"]) as f:
            content = f.read()
        assert "# TC-ID:" in content

        node = s.run(
            "MATCH (gt:GeneratedTest {id: $id}) RETURN gt.lifecycle_state AS ls, "
            "gt.committed_to_repo AS committed",
            id=result["generated_test_id"],
        ).single()
        assert node["ls"] == "PendingCommit"
        assert node["committed"] is False

        edge = s.run(
            "MATCH (gt:GeneratedTest {id: $id})-[:GENERATED_FROM]->(t:Transition) RETURN t.id AS tid",
            id=result["generated_test_id"],
        ).single()
        assert edge["tid"] == "pgc-test-transition-functional-gap"


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
    _setup()
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    try:
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
    finally:
        _cleanup()
        if _driver:
            _driver.close()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
