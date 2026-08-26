"""
`demo_data/land_spec_criteria.py` — the intent side of the demo corpus.

**Why this file exists.** The script hand-builds its `AcceptanceCriterion` rows
rather than going through `model_sources.landing`, and it had no test at all. It
never set `search_text`, `valid_from` or `valid_to`, so `validate` refused all 24
of them and the stage printed `REFUSED: ... nothing written`. Every acceptance
criterion in the demo graph was simply absent — the half that a recovered model
is supposed to be *compared against*, so its absence makes the comparison vacuous
rather than noisy.

Nothing caught it because nothing ran it: `rebuild_graph.sh` aborted two stages
earlier, on a legitimate §5.8 synthesis refusal it treated as fatal.

The check reuses `ontology.validate` rather than naming the three properties it
was missing. A test that asserted those three by name would pass again the day a
fourth is added, which is the same failure wearing a different number.

Free to run: `plan` is pure and this needs no Neo4j.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "demo_data"))

from metis_mcp.ontology import validate  # noqa: E402

SPECS = HERE / "demo_project" / "specs"


def _rows():
    import land_spec_criteria

    _episode, rows = land_spec_criteria.plan(SPECS)
    return rows


def test_the_demo_specs_are_readable_at_all():
    """Guarding the guard: an empty row list would make every assertion below
    vacuously true, which is how a scanner passes forever and proves nothing."""
    rows = _rows()
    assert len(rows) >= 8, f"expected the demo criteria, got {len(rows)}"


def test_every_planned_criterion_passes_the_gate_it_will_be_landed_through():
    """The exact check `main` runs before writing, on the real demo corpus.

    This is the regression: it failed for all of them, and the stage reported it
    honestly to a log nobody was reading because the script had already exited.
    """
    refused = []
    for row in _rows():
        outcome = validate("AcceptanceCriterion", row)
        if not outcome.valid:
            refused.append(f"{row['id']}: {'; '.join(outcome.errors)}")

    assert not refused, (
        "planned criteria would be REFUSED at landing, so the intent side of "
        "the demo graph would be empty:\n  " + "\n  ".join(refused))


@pytest.mark.parametrize("prop", ("search_text", "valid_from", "valid_to"))
def test_the_three_that_were_missing_are_present(prop):
    """Named individually only so a failure says which one went, and kept
    deliberately *alongside* the validator check above rather than instead of it:
    this one explains, that one is authoritative."""
    for row in _rows():
        assert prop in row, f"{row['id']} carries no {prop}"


def test_valid_to_is_empty_so_the_claim_reads_as_still_true():
    """`valid_to` present-but-empty is the live state; a missing key and a filled
    one mean opposite things, and only one of the three is 'still true'."""
    for row in _rows():
        assert row["valid_to"] == "", (
            f"{row['id']} lands already invalidated ({row['valid_to']!r})")


def test_search_text_is_derived_from_the_criterion_not_a_constant():
    """A constant would satisfy the validator and make every criterion match
    every query — the failure mode that looks like working retrieval."""
    rows = _rows()
    texts = {r["search_text"] for r in rows}
    assert len(texts) > 1, "every criterion folded to the same search text"
    for row in rows:
        assert row["search_text"].strip(), f"{row['id']} has blank search_text"
