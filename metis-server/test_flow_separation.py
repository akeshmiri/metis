"""
Starting a flow versus being a step in it (application spec M-5a, M-5f, C-1..C-3).

One edge used to carry two different claims, and the graph read as though the Web
and API flows merged. They do not: a page **starts** a call and then continues its
own flow, and a failing call frequently produces **no UI transition at all**.

Three measured consequences, each pinned below:

  * `graph_loader` stored the links in a `{ui: api}` dict. A page opening three
    panels kept one and **silently dropped two** — a dict does not complain about
    being overwritten;
  * `credit_indirect` credited an API transition whenever a UI path covered it,
    justified by C-3, which only holds for an outcome that was *observed*;
  * "the UI starts this call and can never render this result" was not a question
    the graph could answer.
"""
from __future__ import annotations

import sys

from metis_mcp.mbt.coverage import (
    COVERING_MECHANISMS,
    DIRECT,
    INDIRECT,
    INITIATED,
    Ledger,
    LedgerRow,
    credit_indirect,
    credit_initiated,
)
from metis_mcp.mbt.cross_surface import (
    UNHANDLED_OUTCOME,
    InvokesLink,
    LinkSet,
    divergences,
)
from metis_mcp.mbt.model import APPROVED, IMPLEMENTED, Model, State, Transition
from metis_mcp.ontology import LABELS, validate, validate_relationship


def _api_model() -> Model:
    states = {n: State(id=n, name=n, surface="api", is_initial=(n == "Ready"),
                       lifecycle_state=APPROVED)
              for n in ("Ready", "Ok200", "Error500")}
    return Model(id="svc-api", states=states, transitions={
        "ok": Transition(id="ok", source="Ready", trigger="GET /thing",
                         target="Ok200", lifecycle_state=APPROVED, outcome_status=200),
        "boom": Transition(id="boom", source="Ready", trigger="GET /thing",
                           target="Error500", guard="NOT (ok)",
                           lifecycle_state=APPROVED, outcome_status=500),
    })


def _ui_model() -> Model:
    states = {n: State(id=n, name=n, surface="ui", is_initial=(n == "Start"),
                       lifecycle_state=APPROVED)
              for n in ("Start", "Opened", "Shown")}
    return Model(id="svc-ui", states=states, transitions={
        "open": Transition(id="open", source="Start", trigger="open Page",
                           target="Opened", lifecycle_state=APPROVED),
        "render": Transition(id="render", source="Opened", trigger="data arrives",
                             target="Shown", lifecycle_state=APPROVED),
    })


def _links(**kw) -> LinkSet:
    links = LinkSet(journey="svc")
    links.triggers.append(InvokesLink("open", "ok", "pack", {}, kw.get("confirm", "rev")))
    links.triggers.append(InvokesLink("open", "boom", "pack", {}, kw.get("confirm", "rev")))
    links.links.append(InvokesLink("render", "ok", "pack", {}, kw.get("confirm", "rev")))
    return links


# --------------------------------------------------------------------------
# The two labels ride together.
# --------------------------------------------------------------------------

def test_a_specialisation_is_carried_alongside_transition_not_instead_of_it():
    """`MATCH (t:ApiCall)` reads unambiguously; `MATCH (t:Transition)` still
    finds everything, so the engine keeps one traversal and therefore one
    definition of what a flow is."""
    assert LABELS["ApiCall"].specialises == "Transition"
    assert LABELS["UiAction"].specialises == "Transition"


def test_the_specialisation_narrows_the_surface():
    base = {"id": "t", "source_episode_id": "e", "name": "n", "trigger": "GET /x",
            "guard_expression": "", "implementation_status": IMPLEMENTED}
    assert validate("ApiCall", {**base, "surface": "api"}).valid
    assert not validate("ApiCall", {**base, "surface": "ui"}).valid
    assert validate("UiAction", {**base, "surface": "ui"}).valid
    assert not validate("UiAction", {**base, "surface": "api"}).valid


def test_the_two_edges_are_separate_and_directional():
    assert validate_relationship("UiAction", "TRIGGERS", "ApiCall").valid
    assert validate_relationship("UiAction", "INVOKES", "ApiCall").valid
    # An API call does not start a UI flow.
    assert not validate_relationship("ApiCall", "TRIGGERS", "UiAction").valid


# --------------------------------------------------------------------------
# The fan-out that a dict was destroying.
# --------------------------------------------------------------------------

def test_a_trigger_fans_out_and_every_target_survives():
    """One page-open starts several calls. `as_map`'s one-to-one shape kept the
    last and lost the rest, invisibly."""
    triggered = _links().triggered_map()
    assert triggered == {"open": ["ok", "boom"]}
    assert len(_links().triggered_api_ids()) == 2


def test_an_observation_stays_one_to_one():
    assert _links().as_map() == {"render": "ok"}


def test_an_unconfirmed_link_is_a_proposal_and_acts_like_nothing():
    """M-5g/F-7 — the same gate the observation edge has always had."""
    proposals = _links(confirm="")
    assert proposals.triggered_map() == {}
    assert proposals.triggered_map(confirmed_only=False) == {"open": ["ok", "boom"]}


# --------------------------------------------------------------------------
# Coverage: starting a call is not covering its outcome.
# --------------------------------------------------------------------------

def test_starting_a_call_is_recorded_but_never_counted_as_covered():
    """Your "the call was genuinely made", kept honest. Crediting it would mark
    the 500 the page never handles as tested — the case worth finding."""
    api = _api_model()
    ledger = Ledger(model_id=api.id, criterion="all-transitions")
    initiated = credit_initiated(ledger, api, _links().triggered_map(), {"open"})

    assert set(initiated) == {"ok", "boom"}
    assert INITIATED not in COVERING_MECHANISMS
    assert ledger.summary()["covered"] == 0, "a trigger must not move the figure"
    assert ledger.summary()["initiated_not_covered"] == 2


def test_observing_an_outcome_still_credits_it():
    """C-2/C-3 unchanged: a UI transition that rendered an outcome necessarily
    satisfied that outcome's guard."""
    api = _api_model()
    ledger = Ledger(model_id=api.id, criterion="all-transitions")
    credited = credit_indirect(ledger, api, _links().as_map(), {"render"})

    assert credited == ["ok"]
    assert ledger.summary()["covered"] == 1
    assert INDIRECT in ledger.mechanisms_for("ok")


def test_a_directly_covered_transition_is_not_also_marked_initiated():
    api = _api_model()
    ledger = Ledger(model_id=api.id, criterion="all-transitions")
    ledger.rows.append(LedgerRow(transition_id="ok", surface="api",
                                 mechanism=DIRECT, criterion="all-transitions"))
    initiated = credit_initiated(ledger, api, _links().triggered_map(), {"open"})
    assert "ok" not in initiated, "already covered; 'was called' adds nothing"


# --------------------------------------------------------------------------
# The finding this makes answerable.
# --------------------------------------------------------------------------

def test_an_outcome_the_ui_starts_but_cannot_render_is_a_finding():
    """Your observation, as a query: the page fires the call and has no state
    for the failure. Previously inferred from a same-trigger heuristic, because
    one edge type could not tell "starts" from "rendered"."""
    findings = divergences(_ui_model(), _api_model(), _links())
    unhandled = [f for f in findings if f.kind == UNHANDLED_OUTCOME]
    assert [f.element_id for f in unhandled] == ["boom"], (
        "the 500 is started and never rendered; the 200 is rendered")
    assert "can never be rendered" in unhandled[0].detail


def test_a_triggered_outcome_is_not_also_reported_as_api_only():
    """One problem must not be reported as two: the UI does reach this call."""
    findings = divergences(_ui_model(), _api_model(), _links())
    api_only = {f.element_id for f in findings if f.kind == "api_only"}
    assert "boom" not in api_only and "ok" not in api_only


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
