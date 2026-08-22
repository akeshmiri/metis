"""
Landing writes one statement per group, not per row (application spec §16.1).

`land()` ran a `session.run` for every node and every edge. That is invisible at
the ~250 nodes a behaviour model produces and it is not at the ~23,000 writes an
evidence layer produces — 6,885 nodes and ~16,000 edges, each its own round trip.

**The risk in batching is silent divergence**, so these tests do not check that
it is faster. They check that a plan lands *identically* through the batched
writer, and that the counts come back from the database rather than from
`len(rows)` — which is the bug this project has already shipped twice.

Free to run: the session is a recording fake, so no container is needed. What it
cannot prove is that the Cypher is valid; `rebuild_graph.sh` does that against a
real database, and verification 3 checks the edges actually resolved.
"""
from __future__ import annotations

import sys

from metis_mcp.model_sources.landing import (
    LandingPlan,
    PlannedEdge,
    PlannedNode,
    land,
)


class FakeSession:
    """Records statements and answers `RETURN count(...)`.

    `matched` names the endpoint ids that exist, so an edge whose endpoint is
    missing merges nothing — exactly what a real `MATCH` does, and the case the
    old counter got wrong.
    """

    def __init__(self, matched: set[str] | None = None):
        self.statements: list[tuple[str, dict]] = []
        self.matched = matched            # None means "everything resolves"

    def run(self, query: str, **params):
        self.statements.append((query, params))
        rows = params.get("rows", [])
        if "MATCH" in query and "MERGE (a)" in query:
            if self.matched is None:
                written = len(rows)
            else:
                written = sum(1 for r in rows
                              if r["a"] in self.matched and r["b"] in self.matched)
        else:
            written = len(rows)
        return [{"written": written}]


def _plan() -> LandingPlan:
    plan = LandingPlan(episode_id="ep-1")
    plan.nodes = [
        PlannedNode("State", {"id": "s1", "name": "Metric"}),
        PlannedNode("State", {"id": "s2", "name": "MetricPresent"}),
        PlannedNode("ApiCall", {"id": "t1", "name": "POST /metric"}),
        PlannedNode("Endpoint", {"id": "e1", "path": "/metric"}),
    ]
    plan.edges = [
        PlannedEdge("State", "s1", "WHEN", "ApiCall", "t1"),
        PlannedEdge("ApiCall", "t1", "THEN", "State", "s2"),
        PlannedEdge("ApiCall", "t1", "DERIVED_FROM", "Endpoint", "e1"),
    ]
    return plan


# --------------------------------------------------------------------------
# Grouping.
# --------------------------------------------------------------------------

def test_one_statement_per_label_and_per_relationship_triple():
    """Four nodes over three labels and three edges over three triples is six
    statements, not seven — the two `State`s share one."""
    session = FakeSession()
    land(session, _plan())
    assert len(session.statements) == 6
    assert all("UNWIND $rows AS row" in q for q, _ in session.statements)


def test_rows_of_one_group_ride_in_a_single_call():
    session = FakeSession()
    land(session, _plan())
    state_calls = [p for q, p in session.statements if "MERGE (n:State" in q]
    assert len(state_calls) == 1
    assert [r["id"] for r in state_calls[0]["rows"]] == ["s1", "s2"]


def test_the_id_is_the_merge_key_exactly_as_before():
    """D-8: re-landing identical output is a no-op, and that depends on MERGE
    keying on `id` alone rather than on the whole property map."""
    session = FakeSession()
    land(session, _plan())
    node_queries = [q for q, _ in session.statements if "MERGE (n:" in q]
    assert all("{id: row.id}" in q for q in node_queries)
    assert all("SET n += row" in q for q in node_queries)


def test_additional_labels_survive_grouping():
    """A node carrying `also` must not be grouped with a plain one of the same
    label, or it silently loses its extra label."""
    plan = LandingPlan(episode_id="ep-1")
    plan.nodes = [
        PlannedNode("State", {"id": "a"}),
        PlannedNode("State", {"id": "b"}, also=("Deprecated",)),
    ]
    session = FakeSession()
    land(session, plan)
    queries = [q for q, _ in session.statements]
    assert len(queries) == 2
    assert any("SET n:Deprecated" in q for q in queries)


# --------------------------------------------------------------------------
# Counting. The half this project has got wrong before.
# --------------------------------------------------------------------------

def test_counts_come_from_the_database_not_from_the_plan():
    session = FakeSession()
    result = land(session, _plan())
    assert result.nodes_written == 4
    assert result.edges_written == 3
    assert result.unmatched == []


def test_an_edge_whose_endpoint_is_missing_is_not_counted_as_written():
    """`persist_invokes` reported "91 INVOKES" into a graph holding zero: the
    statement opens with two MATCHes, merges nothing when an id is absent, and
    the old counter incremented anyway."""
    session = FakeSession(matched={"s1", "s2", "t1"})   # `e1` never landed
    result = land(session, _plan())
    assert result.edges_written == 2, "the DERIVED_FROM edge matched nothing"
    assert len(result.unmatched) == 1
    assert "DERIVED_FROM" in result.unmatched[0][0]


def test_the_unmatched_report_names_the_likely_cause():
    """An evidence layer landing after the model that derives from it is the way
    this happens, so the message says so rather than only counting."""
    session = FakeSession(matched={"s1", "s2", "t1"})
    result = land(session, _plan())
    assert "evidence layer must land before" in result.unmatched[0][2]


def test_an_illegal_plan_writes_nothing_at_all():
    plan = _plan()
    plan.errors.append("State: required property 'surface' is missing")
    session = FakeSession()
    result = land(session, plan)
    assert not result.ok
    assert session.statements == [], "a refused plan must not half-write"


def test_an_empty_plan_is_a_no_op_rather_than_an_error():
    session = FakeSession()
    result = land(session, LandingPlan(episode_id="ep-1"))
    assert result.ok
    assert (result.nodes_written, result.edges_written) == (0, 0)
    assert session.statements == []


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:                                    # noqa: BLE001
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
