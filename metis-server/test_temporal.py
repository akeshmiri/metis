"""
§5.4 (as_of/history/diff) + Layer 10 auditable rollback
(REQ-METIS-GRD-10) -- metis_mcp/temporal.py, against a real Neo4j
Revision supersession chain (no code anywhere else in this project
previously wrote more than one version of an entity -- this is the first
real exercise of the mechanism, deliberately using explicit t_recorded
timestamps spaced a month apart so as_of()'s point-in-time queries have
real, unambiguous instants to reconstruct against).
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.temporal import record_revision, history, as_of, diff, rollback

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

ENTITY_ID = "temporal-test-entity"
T1 = "2024-01-01T00:00:00Z"
T2 = "2024-02-01T00:00:00Z"
T3 = "2024-03-01T00:00:00Z"

_driver = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


def _setup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'temporal-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:TemporalTestFixture {id: $id})", id=ENTITY_ID,
        ).consume())
        record_revision(s, ENTITY_ID, {"status": "Draft", "priority": "low"},
                         "temporal-test-episode", t_recorded=T1)
        record_revision(s, ENTITY_ID, {"status": "Reviewed", "priority": "low"},
                         "temporal-test-episode", t_recorded=T2)
        record_revision(s, ENTITY_ID, {"status": "Approved", "priority": "high"},
                         "temporal-test-episode", t_recorded=T3)


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH $prefix OR n.id STARTS WITH 'rollback:temporal-test' "
            "DETACH DELETE n", prefix=ENTITY_ID,
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (e:Episode {id: 'temporal-test-episode'}) DETACH DELETE e"
        ).consume())


def test_history_returns_full_chain_oldest_first_with_only_latest_open():
    with _session() as s:
        chain = history(s, ENTITY_ID)
    assert [r.revision for r in chain] == [1, 2, 3]
    assert chain[0].properties == {"status": "Draft", "priority": "low"}
    assert chain[1].t_invalid is not None, "revision 1 must be closed once superseded"
    assert chain[2].t_invalid is None, "only the current revision stays open"


def test_as_of_reconstructs_exact_state_at_a_past_instant():
    with _session() as s:
        mid = as_of(s, ENTITY_ID, "2024-01-15T00:00:00Z")
        latest = as_of(s, ENTITY_ID, "2024-06-01T00:00:00Z")
        before_any = as_of(s, ENTITY_ID, "2023-01-01T00:00:00Z")
    assert mid.revision == 1
    assert mid.properties["status"] == "Draft"
    assert latest.revision == 3
    assert latest.properties["status"] == "Approved"
    assert before_any is None, "no revision existed yet -- must not fabricate a state"


def test_diff_reports_added_removed_and_changed_keys():
    with _session() as s:
        result = diff(s, ENTITY_ID, T1, T3)
    assert result["comparable"]
    assert result["changed"]["status"] == {"from": "Draft", "to": "Approved"}
    assert result["changed"]["priority"] == {"from": "low", "to": "high"}
    assert result["added"] == {}
    assert result["removed"] == {}


def test_diff_is_honest_when_a_timestamp_predates_all_history():
    with _session() as s:
        result = diff(s, ENTITY_ID, "2020-01-01T00:00:00Z", T3)
    assert result["comparable"] is False
    assert "t1" in result["reason"]


def test_rollback_restores_prior_state_as_a_new_revision_never_deleting_history():
    with _session() as s:
        result = rollback(s, ENTITY_ID, target_revision=1, actor="test-actor",
                           reason="testing REQ-METIS-GRD-10")
        assert result["rolled_back"] is True
        assert result["from_revision"] == 3
        assert result["restored_state_of_revision"] == 1
        assert result["new_revision"] == 4

        chain = history(s, ENTITY_ID)
        assert [r.revision for r in chain] == [1, 2, 3, 4], "no revision was deleted"
        assert chain[3].properties == {"status": "Draft", "priority": "low"}
        assert chain[2].t_invalid is not None, "revision 3 closed by the rollback"

        live = s.run(
            "MATCH (e:TemporalTestFixture {id: $id}) RETURN e.status AS status, e.revision AS rev",
            id=ENTITY_ID,
        ).single()
        assert live["status"] == "Draft", "live node reflects the restored state"
        assert live["rev"] == 4

        episode = s.run(
            "MATCH (ep:Episode {id: $id}) RETURN ep.episode_type AS t, ep.from_revision AS fr, "
            "ep.to_revision AS tr, ep.actor AS actor",
            id=result["episode_id"],
        ).single()
        assert episode["t"] == "RollbackPerformed"
        assert episode["fr"] == 3
        assert episode["tr"] == 1
        assert episode["actor"] == "test-actor"


def test_rollback_to_nonexistent_revision_refuses_honestly():
    with _session() as s:
        result = rollback(s, ENTITY_ID, target_revision=999, actor="test-actor", reason="bogus")
    assert result["rolled_back"] is False
    assert "No revision 999" in result["reason"]


def test_record_revision_ignores_a_dogfoodingitem_sharing_the_same_id():
    """Real bug caught for real building metis_mcp/constitution_gate.py:
    schema-01's id-uniqueness constraints are declared PER LABEL, not
    globally -- a :DogfoodingItem and a real production-ontology node
    (e.g. :Constitution) can legitimately share the same id string
    ('CONST-046', confirmed directly against this project's own real
    dogfooding corpus). Before this test's fix, record_revision's
    label-agnostic MATCH (e {id: $entity_id}) matched BOTH nodes,
    causing a real Neo4j constraint violation (a duplicate Revision id)
    the moment both existed for the same id."""
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (d:DogfoodingItem {id: 'temporal-test-collision-id'})"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (c:TemporalTestFixture {id: 'temporal-test-collision-id'})"
        ).consume())
        # Must succeed despite the DogfoodingItem sharing the same id --
        # not raise, not silently write to the wrong node.
        record_revision(s, "temporal-test-collision-id", {"x": 1}, "temporal-test-episode",
                         t_recorded=T1)
        chain = history(s, "temporal-test-collision-id")
        s.execute_write(lambda tx: tx.run(
            "MATCH (n {id: 'temporal-test-collision-id'}) DETACH DELETE n"
        ).consume())
    assert len(chain) == 1
    assert chain[0].properties == {"x": 1}


def test_record_revision_raises_for_a_nonexistent_entity_instead_of_a_silent_no_op():
    """Real bug caught building metis_mcp/academy.py's changelog: MATCH
    (e {id: $entity_id}) on a nonexistent entity matches zero rows, so the
    whole write silently became a no-op while still returning a revision
    number as if something had been written. Must raise instead."""
    with _session() as s:
        try:
            record_revision(s, "temporal-test-does-not-exist", {"x": 1}, "temporal-test-episode")
            assert False, "must raise, never silently no-op"
        except ValueError as e:
            assert "no entity with id" in str(e)


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
