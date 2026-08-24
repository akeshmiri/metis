"""
`read.get_transition` — the evidence payload (spec §8.5, D-14).

Free to run: `session` is stubbed, so what is asserted is the shape of the
answer rather than the graph behind it.
"""
from __future__ import annotations

import pytest

from metis_mcp import read


class _Row(dict):
    pass


class _Session:
    def __init__(self, row):
        self._row = row

    def run(self, cypher, **params):
        assert "GUARDED_BY" in cypher, "the stronger claim is not queried"
        self.cypher = cypher
        return self

    def single(self):
        return self._row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _row(**over):
    base = {
        "transition": {"id": "m::t1", "trigger": "POST /x",
                       "guard_expression": "present AND owned"},
        "labels": ["ApiCall"],
        "source_state": "Ready", "target_state": "Ok200",
        "endpoints": [], "outcomes": [], "parameters": [], "payload_types": [],
        "checks": [{"expression": "near this transition", "dimension": ""}],
        "guarding_checks": [
            {"expression": "owned", "order": 2, "dimension": "business",
             "anchor": "Ctl.java:41@c0ffee"},
            {"expression": "present", "order": 1, "dimension": "structural",
             "anchor": "Ctl.java:38@c0ffee"},
        ],
        "criteria": [],
    }
    base.update(over)
    return base


@pytest.fixture
def stub(monkeypatch):
    def _install(row):
        monkeypatch.setattr("metis_mcp.mbt.graph_session.session",
                            lambda: _Session(row))
    return _install


def test_the_guarding_checks_are_returned_at_all(stub):
    """`GUARDED_BY` was written by landing and read by nothing — six production
    readers for the guard string, none for the `Check` node."""
    stub(_row())
    out = read.get_transition("m::t1")
    assert [c["expression"] for c in out["evidence"]["guarding_checks"]] \
        == ["present", "owned"]


def test_they_come_back_in_evaluation_order(stub):
    """Which is the fact the guard string cannot carry. `collect` in Cypher has
    no order of its own, so sorting here is what makes the answer meaningful."""
    stub(_row())
    orders = [c["order"] for c in read.get_transition("m::t1")["evidence"]
              ["guarding_checks"]]
    assert orders == sorted(orders) == [1, 2]


def test_each_one_carries_the_line_it_was_recovered_from(stub):
    """T-9a — the anchor is the reason to prefer a `Check` over a substring."""
    stub(_row())
    anchors = [c["anchor"] for c in read.get_transition("m::t1")["evidence"]
               ["guarding_checks"]]
    assert anchors == ["Ctl.java:38@c0ffee", "Ctl.java:41@c0ffee"]


def test_the_two_kinds_of_check_are_not_merged(stub):
    """`CONSTRAINED_BY` says a condition was FOUND near this transition;
    `GUARDED_BY` says this condition SELECTED this outcome over its siblings.
    Landing already refuses to conflate them and so does the reader — a
    reviewer approves the two differently."""
    stub(_row())
    ev = read.get_transition("m::t1")["evidence"]
    assert [c["expression"] for c in ev["checks"]] == ["near this transition"]
    assert "near this transition" not in [c["expression"]
                                          for c in ev["guarding_checks"]]


def test_a_transition_with_no_guarding_check_says_so_with_an_empty_list(stub):
    """Most of the estate: `GUARDED_BY` is written only where dimension
    recovery resolved the checks, and the live mfa graph has none at all."""
    stub(_row(guarding_checks=[]))
    assert read.get_transition("m::t1")["evidence"]["guarding_checks"] == []
