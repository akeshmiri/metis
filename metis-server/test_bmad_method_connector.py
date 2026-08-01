"""
Tests for the bmad-method-specs connector -- real deterministic markdown
parsing, tested against a real, clearly-disclosed SYNTHETIC BMAD-shaped
fixture (test_fixtures/bmad/1.1-reject-negative-refund.md), since no real
BMAD-METHOD project exists in this environment. The parsing/ingestion code
itself is real and would process a real BMAD project's sharded story files
identically.
"""
import os
import sys

from neo4j import GraphDatabase

from connectors.bmad_method_connector import parse_story_file, land_story

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "test_fixtures", "bmad", "1.1-reject-negative-refund.md",
)
NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")


def test_parses_real_story_id_title_and_ac():
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        parsed = parse_story_file(f.read())
    assert parsed["story_id"] == "1.1"
    assert parsed["title"] == "Reject Negative Refund Amounts"
    assert len(parsed["acceptance_criteria"]) == 2
    assert "reject the refund" in parsed["requirement_text"].lower()


def test_land_story_creates_real_requirement_and_linked_acceptance_criteria():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            s.execute_write(lambda tx: tx.run(
                "MERGE (e:Episode {id: 'bmad-test-episode'}) "
                "SET e.t_recorded = datetime(), e.source_connector = 'bmad-method-specs', e.job_id = 'test'"
            ).consume())
            with open(FIXTURE_PATH, encoding="utf-8") as f:
                parsed = parse_story_file(f.read())
            result = land_story(s, FIXTURE_PATH, parsed, "bmad-test-episode", repo="bmad-test")

            assert result["requirement_written"]
            assert result["requirement_ears_conformant"]
            assert result["acceptance_criteria_written"] == 2

            edges = s.run(
                "MATCH (r:Requirement {id: $id})-[:HAS_AC]->(ac:AcceptanceCriterion) RETURN count(ac) AS c",
                id=result["requirement_id"],
            ).single()["c"]
            assert edges == 2
    finally:
        s2 = driver.session()
        s2.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'bmad-test' DETACH DELETE n"
        ).consume())
        s2.execute_write(lambda tx: tx.run(
            "MATCH (e:Episode {id: 'bmad-test-episode'}) DETACH DELETE e"
        ).consume())
        s2.close()
        driver.close()


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
