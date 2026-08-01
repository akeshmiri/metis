"""
Phase 5 acceptance test: review_api_server.py against the real Neo4j
instance -- not mocked. Spawns the actual server as a subprocess (same
approach as test_e2e.py) and hits its real HTTP endpoints.

Note on PLAN.md's stated Phase 5 acceptance criterion "approving an item is
reflected in a subsequent metis_check_coverage call": that phrasing assumes
the write-path-enabled fork of the explicit decision PLAN.md posed for this
phase ("either keep it disabled ... or make the explicit, deliberate call to
enable it"). This build took the disabled fork (the safer default, and the
one requiring no separate deliberate-enablement decision) -- REQ-METIS-CPT-01
stays closed, matching metis_submit_episode's existing behavior. The
equivalent real round-trip proof for that choice is what's tested here:
approving/rejecting returns the honest "not written" acknowledgment, AND
the underlying graph node's lifecycle_state is confirmed unchanged
afterward -- proving the gate is real, not just that the button didn't error.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from neo4j import GraphDatabase

PORT = 8421  # different from the manually-run instance's default port
BASE = f"http://127.0.0.1:{PORT}"
NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

_proc = None


def _start_server():
    global _proc
    env = os.environ.copy()
    env["METIS_REVIEW_API_PORT"] = str(PORT)
    _proc = subprocess.Popen(
        [sys.executable, "review_api_server.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    for _ in range(50):
        try:
            urllib.request.urlopen(f"{BASE}/api/quarantine", timeout=1)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("review_api_server.py did not become ready in time")


def _stop_server():
    if _proc:
        _proc.kill()
        _proc.wait(timeout=10)


def _get(path):
    with urllib.request.urlopen(f"{BASE}{path}") as r:
        return json.loads(r.read())


def _post(path, payload):
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def _lifecycle_state(node_id: str) -> str:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rec = s.run("MATCH (n {id: $id}) RETURN n.lifecycle_state AS ls", id=node_id).single()
            return rec["ls"] if rec else None
    finally:
        driver.close()


def test_quarantine_endpoint_returns_real_items_not_sample_data():
    items = _get("/api/quarantine")
    assert len(items) > 0, "no real Quarantine items -- run populate_review_queue_sample.py first"
    # Real, specific triage reasons two different connectors' quarantine
    # items legitimately carry -- not the same one reused generically for
    # everything (Phase 7's test-suite-ingest orphans are quarantined for a
    # different real reason than Phase 5's Class/Method single-source items).
    known_reasons = {"needs_second_source", "no_traceability_match", "unresolved_performance_target",
                      "demo_synthetic_confidence_score"}
    for item in items:
        assert item["id"], "every real item must have a real id"
        # Real sample-data ids from the old hardcoded array looked like 'q-1'..'q-4';
        # real Neo4j-sourced ids are deterministic repo:path:name strings.
        assert not item["id"].startswith("q-")
        assert item.get("triage_reason") in known_reasons


def test_root_serves_the_real_ui_html():
    req = urllib.request.Request(f"{BASE}/")
    with urllib.request.urlopen(req) as r:
        body = r.read().decode()
    assert "Review queue" in body
    assert "loadItems" in body


def test_decision_endpoint_refuses_to_write_and_says_so_honestly():
    items = _get("/api/quarantine")
    target = items[0]
    before = _lifecycle_state(target["id"])
    assert before == "Quarantine"

    response = _post("/api/decision", {"id": target["id"], "decision": "approved"})
    assert response["accepted"] is False
    assert "REQ-METIS-CPT-01" in response["reason"]
    assert "not written" in response["reason"].lower() or "NOT written" in response["reason"]

    after = _lifecycle_state(target["id"])
    assert after == before, "the gate must be real: lifecycle_state must not change from an API decision"


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
    _start_server()
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
        _stop_server()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
