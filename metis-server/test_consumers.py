"""Who reads what a behaviour produces, and the refusal where nothing says.

**The failure this guards.** The practice this was ported from detects consumers
by reading ticket prose — `REPORT` because somebody wrote "report" — and attaches
a confidence level to the guess. That is inference from wording, which X-6
forbids: a route called `/export` is a name, and a handler declaring `text/csv`
is a fact.

So every assertion below is about the same property from one side or the other:
a classification arrives with the recovered fact behind it, or it does not arrive.
"""
from __future__ import annotations

import sys

from metis_mcp.analysis import consumers
from metis_mcp.mbt.model import Model, State, Transition

_STATES = {"A": State(id="A", name="A", surface="api", is_initial=True),
           "B": State(id="B", name="B", surface="api")}


def _transition(**kwargs) -> Transition:
    """A transition with a deliberately uninformative trigger.

    `trigger` is overridable because one test's whole point is that a
    *suggestive* route name changes nothing — and it cannot show that if the
    helper fixes the trigger.
    """
    kwargs.setdefault("trigger", "GET /thing")
    return Transition(id="t", source="A", target="B", **kwargs)


def _model(*transitions) -> Model:
    return Model(id="c-api", states=_STATES,
                 transitions={t.id: t for t in transitions})


# --------------------------------------------------------------------------
# Every kind arrives with its evidence.
# --------------------------------------------------------------------------

def test_the_vocabulary_is_closed_and_excludes_what_cannot_be_recovered():
    """`SCHEDULED_JOB` and `AUDIT` are detectable only from prose. Carrying a
    kind Métis can never emit would make the vocabulary a promise it does not
    keep."""
    assert consumers.KINDS == ("REPORT", "EXPORT", "GRID", "INTEGRATION",
                               "NOTIFICATION")
    assert "SCHEDULED_JOB" not in consumers.KINDS
    assert "AUDIT" not in consumers.KINDS


def test_a_download_media_type_says_export():
    found = consumers.classify(_transition(media_types=("text/csv",)))
    assert [c.kind for c in found] == ["EXPORT"]
    assert "text/csv" in found[0].because


def test_an_event_stream_says_notification():
    found = consumers.classify(_transition(media_types=("text/event-stream",)))
    assert consumers.NOTIFICATION in {c.kind for c in found}


def test_paging_over_a_collection_says_grid():
    found = consumers.classify(_transition(
        response_body="PageDto<ItemDto>",
        inputs=({"name": "page"}, {"name": "size"})))
    kinds = {c.kind for c in found}
    assert consumers.GRID in kinds
    assert consumers.REPORT not in kinds, (
        "a paged listing is read a screen at a time, not taken whole")


def test_a_collection_with_no_paging_says_report():
    found = consumers.classify(_transition(response_body="List<ItemDto>"))
    assert consumers.REPORT in {c.kind for c in found}


def test_a_machine_readable_type_says_integration():
    found = consumers.classify(_transition(media_types=("application/json",)))
    assert consumers.INTEGRATION in {c.kind for c in found}


def test_every_classification_carries_the_fact_behind_it():
    """A classification a reader cannot audit is one they must take on trust —
    the objection T-9a makes about an unanchored guard."""
    found = consumers.classify(_transition(
        media_types=("application/json",), response_body="PageDto<X>",
        inputs=({"name": "page"},)))
    assert found
    for consumer in found:
        assert consumer.because.strip(), f"{consumer.kind} names no evidence"


def test_several_kinds_at_once_is_not_a_contradiction():
    """A paged JSON listing plausibly feeds a grid and an integration. Collapsing
    to one would be a choice nothing supports."""
    found = consumers.classify(_transition(
        media_types=("application/json",), response_body="PageDto<X>",
        inputs=({"name": "page"},)))
    assert {c.kind for c in found} >= {consumers.GRID, consumers.INTEGRATION}


# --------------------------------------------------------------------------
# The refusal, which is most of the value.
# --------------------------------------------------------------------------

def test_no_signal_yields_unknown_and_names_the_better_source():
    """**The route name is right there and must not be used.** `GET /thing`
    tells you nothing; a stated consumer is a better fact than an inferred one,
    so the refusal points at the intake rather than at more analysis."""
    described = consumers.describe_one(_transition())
    assert described["consumers"] == [consumers.UNKNOWN]
    assert described["because"] == []
    assert "X-6" in described["means"]
    assert "intake" in described["means"]


def test_a_suggestive_route_name_changes_nothing():
    """The sabotage check for the rule this module exists for."""
    plain = consumers.classify(_transition(trigger="GET /thing"))
    suggestive = consumers.classify(_transition(trigger="GET /export/report"))
    assert plain == suggestive == []


def test_an_empty_classification_is_not_an_unknown_member():
    """`classify` returns nothing; `describe_one` renders `unknown`. Keeping the
    two apart in code means *no kind fired* and *a kind called unknown fired*
    stay distinguishable."""
    assert consumers.classify(_transition()) == []
    assert consumers.UNKNOWN not in consumers.KINDS


def test_the_model_summary_reports_what_it_could_not_name():
    """A consumer map listing only what it could name would read as complete —
    the overstatement `coverage_report`'s `unmeasured` field exists to prevent."""
    described = consumers.describe(_model(
        _transition(media_types=("text/csv",)),
        Transition(id="u", source="A", trigger="GET /other", target="B")))
    assert described["unknown"] == 1
    assert described["distribution"][consumers.EXPORT] == 1
    assert "1 of 2" in described["means"]


def test_no_model_is_not_zero_unknowns():
    described = consumers.describe(None)
    assert described["by_transition"] == {}
    assert described["unknown"] == 0
    assert "no model" in described["means"]


# --------------------------------------------------------------------------
# The fifth reading.
# --------------------------------------------------------------------------

def test_the_consumer_aspect_is_registered_and_owned():
    from metis_mcp.analysis import areas, gaps

    assert gaps.CONSUMER in gaps.ASPECTS
    assert areas.owner_of(gaps.CONSUMER) == "metis-business-analyst-scope"


def test_the_consumer_gap_reports_and_never_blocks():
    """An unnamed consumer makes the design less specific. It does not make the
    claim unrepresentable, and only unrepresentable refuses an import."""
    from metis_mcp.analysis import gaps

    found = gaps.from_consumers("scope", unknown=52, total=56)
    assert found and not any(g.blocks_import for g in found)
    assert gaps.readiness(found)["status"] == gaps.READY


def test_no_gap_is_raised_when_every_consumer_is_named():
    from metis_mcp.analysis import gaps

    assert gaps.from_consumers("scope", unknown=0, total=56) == []
    assert gaps.from_consumers("scope", unknown=0, total=0) == []


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
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
