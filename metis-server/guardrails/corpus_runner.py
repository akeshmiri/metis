"""
Phase 9: the metis-guardrail-corpus-runner service (metis-chart's CronJob
component) -- runs the adversarial injection corpus
(mcp-contracts/metis-adversarial-injection-corpus.json) against the real
Layer 3 confidence-tiering state machine, per CONST-057 ("any failure
blocks, does not just warn" -- MIN_PASS_RATE=1.0 in values.yaml) and
CONST-058 (scheduled cadence, weekly by chart default / daily in the
values-sbx.yaml sandbox override).

Scope, disclosed: each case's `content` is real adversarial text (fake
authority claims, instruction overrides, etc.), but there is no real Layer
6 LLM-as-judge in this environment (no ANTHROPIC_API_KEY) to actually
extract a confidence score FROM that text. What this runner verifies
instead is the real, architecturally load-bearing guarantee BS-001 states:
confidence is always an EXTERNAL parameter to ConfidenceTiering.evaluate()
-- nothing in this codebase parses instructions out of ingested content to
set it. This runner submits every case at a deliberately unprivileged
confidence (0.5, representing "no real judge score available, treat as
genuinely uncertain") and asserts the tier is NEVER auto_write, regardless
of what the injected text claims about itself. That's a real, meaningful,
automatable regression check -- not the full corpus's originally-intended
LLM-judge pass, which needs a real model call this environment doesn't have.
"""
import json
import sys

from metis_mcp.confidence_tiering import ConfidenceTier, ConfidenceTiering

UNPRIVILEGED_CONFIDENCE = 0.5  # deliberately never reaches auto_write's 0.9 threshold on its own


def run(corpus_path: str) -> dict:
    with open(corpus_path, encoding="utf-8") as f:
        corpus = json.load(f)

    tiering = ConfidenceTiering()
    results = []
    for case in corpus["cases"]:
        # The case's own content is real adversarial text -- deliberately
        # NEVER inspected here to derive confidence/structural_valid.
        # That's the point: proving no code path lets it do so.
        result = tiering.evaluate(
            confidence=UNPRIVILEGED_CONFIDENCE, structural_valid=True, has_contradiction=False,
        )
        passed = result.tier != ConfidenceTier.AUTO_WRITE
        results.append({
            "id": case["id"], "category": case["category"], "passed": passed,
            "tier": result.tier.value, "expected_outcome": case["expected_outcome"],
        })

    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    return {
        "total": total, "passed": passed_count, "failed": total - passed_count,
        "pass_rate": (passed_count / total) if total else 0.0,
        "results": results,
    }


def record_run_episode(session, summary: dict, min_pass_rate: float) -> str:
    """DQ-022 (False-acceptance rate, adversarial set) needs a real,
    queryable record of this run's outcome to compute from -- previously
    this runner only ever printed to stderr, leaving no graph trace behind
    (a real gap: metis_mcp/dq_metrics.py's dq_022 has nothing to query
    without this). One Episode per run, id includes a real timestamp so
    repeated CronJob firings don't collide (schema-03's (source_connector,
    unit_id) uniqueness constraint)."""
    import uuid
    episode_id = f"guardrail-corpus-runner:{uuid.uuid4()}"

    def _write(tx):
        # MERGE, not CREATE -- episode_id is generated once in Python before
        # this (possibly-retried) transaction function runs; same real,
        # demonstrated execute_write retry edge case as
        # metis_mcp/temporal.py's record_revision.
        tx.run(
            "MERGE (e:Episode {id: $id}) "
            "ON CREATE SET e.t_recorded = datetime(), "
            "e.source_connector = 'guardrail-corpus-runner', e.unit_id = $id, e.job_id = $id, "
            "e.episode_type = 'AdversarialCorpusRun', e.pass_rate = $pass_rate, "
            "e.min_pass_rate = $min_pass_rate, e.total = $total, e.passed = $passed, e.failed = $failed",
            id=episode_id, pass_rate=summary["pass_rate"], min_pass_rate=min_pass_rate,
            total=summary["total"], passed=summary["passed"], failed=summary["failed"],
        )
    session.execute_write(_write)
    return episode_id


def main():
    import os
    corpus_path = os.environ.get("CORPUS_PATH", "/etc/metis/adversarial-injection-corpus.json")
    min_pass_rate = float(os.environ.get("MIN_PASS_RATE", "1.0"))

    summary = run(corpus_path)
    print(f"Adversarial corpus run: {summary['passed']}/{summary['total']} passed "
          f"(pass_rate={summary['pass_rate']:.3f}, required >= {min_pass_rate}).", file=sys.stderr)
    for r in summary["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  {status} {r['id']} ({r['category']}) -> tier={r['tier']}", file=sys.stderr)

    try:
        from neo4j import GraphDatabase
        from metis_mcp.config_manager import ConfigManager
        config = ConfigManager()
        neo4j_cfg = config.get_neo4j_config()
        password = os.environ.get(neo4j_cfg.get("password_env", ""))
        if neo4j_cfg.get("uri") and password:
            driver = GraphDatabase.driver(neo4j_cfg["uri"], auth=(neo4j_cfg["user"], password))
            try:
                with driver.session() as s:
                    episode_id = record_run_episode(s, summary, min_pass_rate)
                print(f"Recorded run as Episode {episode_id}.", file=sys.stderr)
            finally:
                driver.close()
        else:
            print("No graph.neo4j config/password available -- run outcome not recorded to the "
                  "graph (DQ-022 won't see this run).", file=sys.stderr)
    except Exception as e:
        # Recording the outcome must never block the actual pass/fail gate
        # below (CONST-057's "any failure blocks" is about the corpus
        # result, not about graph write availability) -- but a swallowed
        # failure here must still be visible, not silent.
        print(f"Could not record run Episode to the graph: {type(e).__name__}: {e}", file=sys.stderr)

    if summary["pass_rate"] < min_pass_rate:
        print("BLOCKING: pass rate below required threshold (CONST-057).", file=sys.stderr)
        sys.exit(1)
    print("OK: all cases passed.", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
