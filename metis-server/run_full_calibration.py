"""
One-off runner for CONST-036's calibration batch at the real available
ceiling (127 real Class+Method entities with genuine source content in
this codebase, sample_size=500 requested per the spec's stated batch
size -- see guardrails/calibration.py's module docstring for why 500
itself isn't reachable with genuine, non-fabricated content here).
Writes the full real result to calibration_result.json for inspection
without re-incurring cost on a second run.
"""
import json
import os
import sys

from neo4j import GraphDatabase

from guardrails.calibration import run_calibration_batch

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

if not NEO4J_PASSWORD:
    print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
    sys.exit(1)

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
try:
    with driver.session() as s:
        # REQ-METIS-COST-08 (added after this script's original real run):
        # a batch this size requires explicit confirmation. confirmed=True
        # here reflects the real, already-given user approval for this
        # specific batch ("run the full 500-unit batch," accepting real
        # cost) -- a fresh caller without that prior approval should NOT
        # copy this line uncritically; call run_calibration_batch with
        # confirmed=False first, show the real BatchNotConfirmedError's
        # plan/prompt to the actual human deciding, and only pass
        # confirmed=True after they say yes.
        result = run_calibration_batch(s, sample_size=500, model="haiku", confirmed=True)
finally:
    driver.close()

total_cost = None  # cases don't carry cost individually in this module's current shape
serializable = {
    "sample_size": result["sample_size"],
    "spec_required_sample_size": result["spec_required_sample_size"],
    "real_available_pool": result["real_available_pool"],
    "ran_at_real_ceiling": result["ran_at_real_ceiling"],
    "distribution": result["distribution"],
    "distribution_pct": result["distribution_pct"],
    "cases": [
        {"entity_id": c.entity_id, "confidence": c.confidence, "tier": c.tier, "reasoning": c.reasoning}
        for c in result["cases"]
    ],
}
with open("calibration_result.json", "w", encoding="utf-8") as f:
    json.dump(serializable, f, indent=2)

print(f"Ran {result['sample_size']} real case(s) (spec requires {result['spec_required_sample_size']}, "
      f"real available pool in this codebase: {result['real_available_pool']}).")
print(f"Distribution: {result['distribution']} ({result['distribution_pct']})")
print("Full result written to calibration_result.json")
