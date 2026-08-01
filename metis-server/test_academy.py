"""
§12 Academy -- metis_mcp/academy.py. Real content pages (4 real markdown
files under academy/), real why-link mapping against this project's own
actual rejection-reason strings, real next-step guidance, and a real
changelog generated from metis_mcp/temporal.py's real :Revision history.
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.academy import (
    ACADEMY_PAGES, load_page, get_why_link, next_step_guidance,
    generate_changelog, format_changelog_plain_language, assemble_content,
)
from metis_mcp.temporal import record_revision
from guardrails.pipeline import submit_candidate

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

_driver = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'academy-test-' DETACH DELETE n"
        ).consume())


def test_all_four_real_pages_load_and_are_non_trivial():
    for page_id in ACADEMY_PAGES:
        content = load_page(page_id)
        assert len(content) > 500, f"{page_id} should be real, substantive content"
        assert ACADEMY_PAGES[page_id]["title"] in content or "#" in content


def test_why_link_maps_real_rejection_reasons():
    assert get_why_link("CONST-047 violation -- failed deterministic 29148 check(s)") == \
        "academy/confidence-tiers.html#constitution-gate"
    assert get_why_link("Missing required property 'ears_pattern'") == \
        "academy/graph-model-basics.html#closed-ontology"
    assert get_why_link("Does not match any of the five EARS sentence patterns") == \
        "academy/ears-authoring.html#non-conformant"


def test_why_link_returns_none_for_unrecognized_reason():
    assert get_why_link("some totally novel reason never seen before xyz123") is None


def test_next_step_guidance_covers_real_gap_types():
    assert next_step_guidance("not_found") is not None
    assert next_step_guidance("circular_traceability") is not None
    assert next_step_guidance("nonexistent_gap_type") is None


def test_next_step_guidance_actually_wired_into_real_mcp_tools():
    """Real wiring, not just an unused lookup table -- calls the actual
    tool functions from metis_mcp.server (local backend, dogfooding
    corpus already loaded)."""
    import metis_mcp.server as server

    not_found = server.metis_get_context("CONST-99999-does-not-exist")
    assert not_found["found"] is False
    assert not_found["next_step"] == next_step_guidance("not_found")

    traceability_not_found = server.metis_get_traceability("CONST-99999-does-not-exist")
    assert traceability_not_found["found"] is False
    assert traceability_not_found["next_step"] == next_step_guidance("not_found")

    coverage_not_found = server.metis_check_coverage("CONST-99999-does-not-exist")
    assert coverage_not_found["found"] is False
    assert coverage_not_found["next_step"] == next_step_guidance("not_found")

    # A real, currently-uncited item (per store.orphan_rate()'s own real
    # computation) -- covered=False, so no_traceability guidance must show.
    orphan_id = server.store.orphan_rate(None)["orphan_ids"][0]
    orphan_result = server.metis_check_coverage(orphan_id)
    assert orphan_result["covered"] is False
    assert orphan_result["next_step"] == next_step_guidance("no_traceability")


def test_submit_candidate_result_carries_a_real_academy_link_on_rejection():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'academy-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())
        entity = {
            "id": "academy-test-bad-req", "source_episode_id": "academy-test-episode",
            "ears_pattern": "Ubiquitous", "revision": 1, "corroboration_count": 1,
            "text": "The system shall provide a user-friendly experience.",
        }
        result = submit_candidate(s, "Requirement", entity, confidence=0.99)
    assert not result.written
    assert result.academy_link == "academy/confidence-tiers.html#constitution-gate"


def test_generate_changelog_reflects_real_revision_history():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'academy-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())
        # record_revision requires the base entity node to already exist
        # (MATCH, not MERGE, on the entity itself) -- real gap in this
        # fixture caught running the test: without this, record_revision's
        # MATCH silently matches zero rows and writes nothing at all, no
        # error raised, empty history() on the other end.
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:AcademyTestFixture {id: 'academy-test-entity'})"
        ).consume())
        record_revision(s, "academy-test-entity", {"status": "Draft"}, "academy-test-episode",
                         t_recorded="2024-01-01T00:00:00Z")
        record_revision(s, "academy-test-entity", {"status": "Approved"}, "academy-test-episode",
                         t_recorded="2024-02-01T00:00:00Z")

        entries = generate_changelog(s, ["academy-test-entity"])
    assert len(entries) == 2
    assert entries[1].changed_fields["status"] == {"from": "Draft", "to": "Approved"}

    plain = format_changelog_plain_language(entries)
    assert "status changed from 'Draft' to 'Approved'" in plain


def test_assemble_content_is_the_single_real_shared_stage():
    page = assemble_content(None, kind="academy_page", page_id="ears-authoring")
    assert page["title"] == "EARS Authoring"
    assert len(page["content"]) > 500

    with _session() as s:
        summary = assemble_content(s, kind="quality_summary")
    assert "quality_score" in summary

    try:
        assemble_content(None, kind="not-a-real-kind")
        assert False, "must raise on an unknown kind, never silently return empty content"
    except ValueError:
        pass


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
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
