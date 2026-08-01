"""
Layer 8: Fabrication/invalid-spec heuristics (REQ-METIS-GRD-08,
metis-specification.md §7's ten-layer table): "EARS non-conformance,
circular traceability, orphan-claim detection, vagueness -- catches bad
requirements, not just bad extractions." Four real, deterministic checks
run against the actual production ontology (Requirement/AcceptanceCriterion/
TestCase), not the dogfooding corpus's separate DogfoodingItem/CITES shape
that neo4j_graph_store.py's own orphan_rate() is scoped to -- that method
answers a different, narrower question (dogfooding-corpus cross-reference
orphans) and doesn't reach these production labels at all.

  EARS non-conformance     -- ears_checker.py's real regex check, applied
                               across every real Requirement.text in the
                               graph (DQ-003's underlying mechanism, but
                               ears_checker.py itself only ever checked one
                               string at a time before this module)
  Vagueness/unfalsifiable  -- DQ-004: vagueness.py's shared term-list
                               heuristic, applied to AcceptanceCriterion.text
  Circular traceability    -- DQ-018: a Requirement whose only traceability
                               evidence is a single TestCase VERIFIES edge,
                               with no independent AcceptanceCriterion of
                               its own -- "this pattern indicates
                               reverse-engineered rather than derived
                               traceability" (the test looks like it was
                               written first, then linked back, rather than
                               derived from a real AC)
  Orphan-claim detection   -- an AcceptanceCriterion with no HAS_AC edge
                               from any Requirement -- a claim that exists
                               without anything it's actually accepting
"""
from dataclasses import dataclass, field

from metis_mcp.ears_checker import check_ears_conformance
from metis_mcp.vagueness import detect_vagueness


@dataclass
class LayerFinding:
    check: str
    flagged_ids: list = field(default_factory=list)
    total: int = 0
    rate: float | None = None


def check_ears_nonconformance(session) -> LayerFinding:
    rows = session.run("MATCH (r:Requirement) RETURN r.id AS id, r.text AS text").data()
    flagged = [row["id"] for row in rows if row["text"] and not check_ears_conformance(row["text"]).conformant]
    total = len(rows)
    return LayerFinding(
        check="ears_nonconformance", flagged_ids=flagged, total=total,
        rate=round(len(flagged) / total, 3) if total else None,
    )


def check_vagueness(session, write_flags: bool = False) -> LayerFinding:
    """DQ-004. Optionally persists `vagueness_flagged`/`vagueness_reason` on
    each AcceptanceCriterion so the flag is queryable later, not just
    returned once and discarded -- off by default (a pure read-only scan
    is the safer default for a metric computation)."""
    rows = session.run("MATCH (ac:AcceptanceCriterion) RETURN ac.id AS id, ac.text AS text").data()
    flagged = []
    reasons: dict = {}
    for row in rows:
        if not row["text"]:
            continue
        result = detect_vagueness(row["text"])
        if result.vague:
            flagged.append(row["id"])
            reasons[row["id"]] = result.reason
    total = len(rows)

    if write_flags:
        def _write(tx):
            for ac_id in flagged:
                tx.run(
                    "MATCH (ac:AcceptanceCriterion {id: $id}) SET ac.vagueness_flagged = true, "
                    "ac.vagueness_reason = $reason",
                    id=ac_id, reason=reasons[ac_id],
                )
            tx.run(
                "MATCH (ac:AcceptanceCriterion) WHERE NOT ac.id IN $flagged "
                "SET ac.vagueness_flagged = false",
                flagged=flagged,
            )
        session.execute_write(_write)

    return LayerFinding(
        check="vagueness", flagged_ids=flagged, total=total,
        rate=round(len(flagged) / total, 3) if total else None,
    )


def check_circular_traceability(session) -> LayerFinding:
    """DQ-018. Target: 0. 'Any nonzero count is investigated individually.'"""
    rows = session.run(
        """
        MATCH (req:Requirement)
        WHERE NOT EXISTS { MATCH (req)-[:HAS_AC]->(:AcceptanceCriterion) }
        WITH req, [(tc:TestCase)-[:VERIFIES]->(req) | tc.id] AS verifying_test_ids
        WHERE size(verifying_test_ids) = 1
        RETURN req.id AS id
        """
    ).data()
    total = session.run("MATCH (req:Requirement) RETURN count(req) AS c").single()["c"]
    flagged = [row["id"] for row in rows]
    return LayerFinding(
        check="circular_traceability", flagged_ids=flagged, total=total,
        rate=round(len(flagged) / total, 3) if total else None,
    )


def check_orphan_claims(session) -> LayerFinding:
    rows = session.run(
        "MATCH (ac:AcceptanceCriterion) WHERE NOT EXISTS { MATCH (:Requirement)-[:HAS_AC]->(ac) } "
        "RETURN ac.id AS id"
    ).data()
    total = session.run("MATCH (ac:AcceptanceCriterion) RETURN count(ac) AS c").single()["c"]
    flagged = [row["id"] for row in rows]
    return LayerFinding(
        check="orphan_claims", flagged_ids=flagged, total=total,
        rate=round(len(flagged) / total, 3) if total else None,
    )


def run_layer8(session, write_vagueness_flags: bool = False) -> dict:
    """REQ-METIS-GRD-08's full aggregate -- all 4 real sub-checks in one call."""
    findings = [
        check_ears_nonconformance(session),
        check_vagueness(session, write_flags=write_vagueness_flags),
        check_circular_traceability(session),
        check_orphan_claims(session),
    ]
    return {f.check: {"flagged_ids": f.flagged_ids, "flagged_count": len(f.flagged_ids),
                       "total": f.total, "rate": f.rate} for f in findings}
