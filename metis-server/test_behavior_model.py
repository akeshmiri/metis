"""
Phase 8 tests for determinism/completeness/reachability (CONST-048/049) --
against a real Neo4j instance, modeling this project's OWN real
lifecycle_state machine (Draft/Reviewed/Approved/Deprecated/Disputed/
Rejected, per metis-specification.md's real, already-specified entity
lifecycle) rather than a fabricated business scenario. The deliberately
ambiguous pair mirrors this project's own real confidence-tiering
boundaries (Phase 4's 0.9/0.6 thresholds) -- a genuine domain ambiguity
("a decision at confidence 0.95 satisfies both guards"), not a contrived one.
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.behavior_model import (
    load_transition, check_determinism, check_completeness, check_reachability, guards_conflict,
)

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
    # Real bug caught before ever running this: the original single WHERE
    # clause mixed OR/AND without parens -- Cypher's AND binds tighter than
    # OR, so it parsed as "match every :State/:Transition/:Guard node in
    # the whole database, regardless of id prefix" and would have deleted
    # unrelated data. Split into one explicitly-scoped statement per label.
    with _session() as s:
        for label in ("State", "Transition", "Trigger"):
            s.execute_write(lambda tx, lbl=label: tx.run(
                f"MATCH (n:{lbl}) WHERE n.id STARTS WITH 'bm-test-' DETACH DELETE n"
            ).consume())
        # Guard nodes are keyed by expression text, not a bm-test- prefixed
        # id -- sweep any left with no remaining Transition pointing at them.
        s.execute_write(lambda tx: tx.run(
            "MATCH (g:Guard) WHERE NOT (g)<-[:WHEN_GUARD]-() DETACH DELETE g"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (e:Episode {id: 'bm-test-episode'}) DETACH DELETE e"
        ).consume())


def _seed_episode():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'bm-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test-fixture', e.job_id = 'test'"
        ).consume())


def _load_real_lifecycle_state_machine():
    """Draft --reviewer_decision--> Approved (confidence >= 0.9)
       Draft --reviewer_decision--> Rejected (confidence >= 0.6)   <- overlaps with the above
       Draft --reviewer_decision--> Quarantine (confidence < 0.6)  <- mutually exclusive with both
       Approved --supersede--> Deprecated
       (Disputed is intentionally left unreachable from Draft in this
       fixture -- Disputed is only ever entered via a guardrail-detected
       violation, never a normal reviewer_decision transition, so it's a
       genuinely real "not reachable via the modeled transitions" case.)
    """
    with _session() as s:
        load_transition(s, "bm-test-t-approve", "bm-test-episode", "bm-test-Draft", "bm-test-Approved",
                         "bm-test-reviewer_decision", "confidence >= 0.9")
        load_transition(s, "bm-test-t-reject", "bm-test-episode", "bm-test-Draft", "bm-test-Rejected",
                         "bm-test-reviewer_decision", "confidence >= 0.6")
        load_transition(s, "bm-test-t-quarantine", "bm-test-episode", "bm-test-Draft", "bm-test-Quarantine",
                         "bm-test-reviewer_decision", "confidence < 0.6")
        load_transition(s, "bm-test-t-deprecate", "bm-test-episode", "bm-test-Approved", "bm-test-Deprecated",
                         "bm-test-supersede", "true")
        # Disputed state exists but has no incoming transition from Draft.
        s.execute_write(lambda tx: tx.run(
            "MERGE (s:State {id: 'bm-test-Disputed'}) SET s.source_episode_id = 'bm-test-episode'"
        ).consume())


def test_guards_conflict_detects_real_overlapping_thresholds():
    conflict, reason = guards_conflict("confidence >= 0.9", "confidence >= 0.6")
    assert conflict
    assert "overlap" in reason.lower()


def test_guards_conflict_recognizes_real_mutually_exclusive_thresholds():
    conflict, _ = guards_conflict("confidence >= 0.9", "confidence < 0.6")
    assert not conflict


def test_guards_conflict_fails_closed_on_unparseable_guard():
    """A guard this checker can't parse must be flagged, not assumed safe --
    same fail-closed discipline as classification_gate.py's unclassified-repo default."""
    conflict, reason = guards_conflict("confidence >= 0.9", "the reviewer says so")
    assert conflict
    assert "cannot verify" in reason.lower() or "not a simple threshold" in reason.lower()


def test_determinism_check_catches_real_ambiguous_pair_and_marks_disputed():
    """The flagship Phase 8 acceptance criterion: an ambiguous pair (same
    trigger, overlapping guards) is caught, not silently resolved."""
    _cleanup()
    _seed_episode()
    _load_real_lifecycle_state_machine()
    with _session() as s:
        result = check_determinism(s, "bm-test-Draft")
    assert not result.deterministic
    pairs = {(f.transition_a, f.transition_b) for f in result.findings}
    assert ("bm-test-t-approve", "bm-test-t-reject") in pairs

    with _session() as s:
        rec = s.run(
            "MATCH (t:Transition {id: 'bm-test-t-approve'}) RETURN t.lifecycle_state AS ls"
        ).single()
    assert rec["ls"] == "Disputed"


def test_determinism_check_does_not_flag_the_mutually_exclusive_pair():
    """Proves the checker isn't just flagging everything -- the
    Draft->Quarantine transition (confidence < 0.6) is provably exclusive
    of the >= 0.9 branch and must NOT be reported as ambiguous with it."""
    _cleanup()
    _seed_episode()
    _load_real_lifecycle_state_machine()
    with _session() as s:
        result = check_determinism(s, "bm-test-Draft")
    pairs = {frozenset((f.transition_a, f.transition_b)) for f in result.findings}
    assert frozenset(("bm-test-t-approve", "bm-test-t-quarantine")) not in pairs
    assert frozenset(("bm-test-t-reject", "bm-test-t-quarantine")) not in pairs


def test_completeness_check_finds_real_gap():
    """Approved has no defined outcome for 'bm-test-reviewer_decision' (only
    Draft does) -- a real, correctly-detected completeness gap."""
    _cleanup()
    _seed_episode()
    _load_real_lifecycle_state_machine()
    with _session() as s:
        gaps = check_completeness(s)
    gap_pairs = {(g.state_id, g.trigger_id) for g in gaps}
    assert ("bm-test-Approved", "bm-test-reviewer_decision") in gap_pairs


def test_reachability_check_finds_real_unreachable_disputed_state():
    _cleanup()
    _seed_episode()
    _load_real_lifecycle_state_machine()
    with _session() as s:
        unreachable = check_reachability(s, "bm-test-Draft")
    assert "bm-test-Disputed" in unreachable
    assert "bm-test-Approved" not in unreachable
    assert "bm-test-Deprecated" not in unreachable


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
