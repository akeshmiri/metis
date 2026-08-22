"""
React UI synthesis — the Web surface pattern (spec §5.2, M-2, M-3, M-17).

What this replaces: six UI models of **two states each** (`PageLoaded`, `Ready`),
every transition unguarded, hand-derived off-pipeline because
`ui_synthesis.synthesise` had zero callers and nothing at all read the react-ui
facts. Twenty-two `error` states and twenty-two `loading` states were recovered
by the pack and discarded — the error path was not in the graph.
"""
from __future__ import annotations

import sys

from code_analysis.react_ui_synthesis import (
    ERROR,
    INITIAL_STATE,
    LOADING,
    READY,
    region_of,
    synthesise_react_ui,
)
from metis_mcp.mbt.validation import validate


def facts(**overrides) -> dict:
    base = {
        "pack": "react-ui", "pack_version": "0.1.0", "repo": "f", "commit": "c",
        "ui_states": [
            {"id": "u1", "screen": "MetricPage", "setter": "setSummaryStatus",
             "value": v, "anchor": {"file": "a.jsx", "line": 1, "commit": "c"}}
            for v in (LOADING, READY, ERROR)
        ],
        "api_calls": [{"id": "c1", "screen": "MetricPage", "endpoint": "/metric/summary"}],
        "unresolved_calls": [],
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Naming and regions.
# --------------------------------------------------------------------------

def test_the_region_name_is_the_codes_own_convention():
    """X-7 tier 2 — nothing is invented, the setter is read."""
    assert region_of("setSummaryStatus") == "summary"
    assert region_of("setTrendStatus") == "trend"
    assert region_of("setStatus") == "page"


def test_error_states_are_first_class():
    """The whole point: 22 of these were recovered and thrown away."""
    result = synthesise_react_ui(facts(), journey="m")
    conditions = {s.condition for s in result.model.states.values()}
    assert "summary=error" in conditions
    assert "summary=ready" in conditions


def test_a_state_knows_the_page_it_belongs_to():
    result = synthesise_react_ui(facts(), journey="m")
    shown = [s for s in result.model.states.values() if s.page]
    assert shown, "a ui state belongs to a screen (M-2)"
    assert all(s.page == "MetricPage" for s in shown)


# --------------------------------------------------------------------------
# The two things that make the model well-formed rather than merely bigger.
# --------------------------------------------------------------------------

def test_opening_a_page_is_one_transition_not_one_per_region():
    """Opening a page starts every region loading *at once* — concurrency, not a
    choice. One `open` per region made three siblings share one trigger, which
    the determinism check correctly called ambiguous: the model was claiming the
    page picks a panel to load."""
    many = facts(ui_states=[
        {"id": f"u{i}", "screen": "MetricPage", "setter": setter, "value": v,
         "anchor": {"file": "a.jsx", "line": 1, "commit": "c"}}
        for i, (setter, v) in enumerate(
            [(s, v) for s in ("setStatus", "setSummaryStatus", "setTrendStatus")
             for v in (LOADING, READY, ERROR)])
    ])
    result = synthesise_react_ui(many, journey="m")
    opens = [t for t in result.model.transitions.values() if t.source == INITIAL_STATE]
    assert len(opens) == 1, "three regions, one page-open"
    assert validate(result.model).blocking == [], "and therefore no ambiguity"


def test_the_two_outcomes_of_a_load_are_guarded_and_complementary():
    """The UI surface has never had a guard: `ui_synthesis` writes `""`
    unconditionally and all six estate models had zero.

    Prose ("the request succeeded") is unparseable, so M-17 flags it
    unverifiable and blocks — correct, and useless when every UI guard is prose.
    A negated literal is recognised as mutually exclusive by structure.
    """
    from metis_mcp.behavior_model import guards_conflict

    result = synthesise_react_ui(facts(), journey="m")
    pair = [t for t in result.model.transitions.values() if t.source.endswith(".opened")]
    assert len(pair) == 2
    assert all(t.guard for t in pair), "both outcomes carry a guard"
    conflicts, why = guards_conflict(pair[0].guard, pair[1].guard)
    assert not conflicts, why
    assert "complementary" in why


def test_a_model_from_real_shaped_facts_is_well_formed():
    result = synthesise_react_ui(facts(), journey="m")
    outcome = validate(result.model)
    assert outcome.blocking == [], [f.describe() for f in outcome.blocking]
    assert outcome.unverifiable == [], [f.describe() for f in outcome.unverifiable]


def test_the_page_load_becomes_a_real_setup_step():
    """Was 0 of 91 paths with setup across the whole Web estate."""
    from dataclasses import replace

    from metis_mcp.mbt.model import APPROVED, Model
    from metis_mcp.mbt.path_generation import generate

    m = synthesise_react_ui(facts(), journey="m").model
    app = Model(id=m.id,
                states={k: replace(v, lifecycle_state=APPROVED) for k, v in m.states.items()},
                transitions={k: replace(v, lifecycle_state=APPROVED)
                             for k, v in m.transitions.items()})
    paths = generate(app, "all-transitions", 10).paths
    assert any(p.setup_length for p in paths), "reaching an outcome costs a page open"


# --------------------------------------------------------------------------
# Honesty about limits.
# --------------------------------------------------------------------------

def test_a_region_with_no_loading_value_is_reported_not_invented():
    """Without a recovered "not resolved yet" there is no entry point, and
    inventing one would create a precondition no test can establish (§5.8)."""
    result = synthesise_react_ui(facts(ui_states=[
        {"id": "u1", "screen": "MetricPage", "setter": "setStatus", "value": READY,
         "anchor": {"file": "a.jsx", "line": 1, "commit": "c"}}]), journey="m")
    assert result.unresolved
    assert "no 'loading' state recovered" in result.unresolved[0]


def test_an_empty_report_says_which_kind_of_empty_it_is():
    result = synthesise_react_ui({"pack": "react-ui"}, journey="m")
    assert not result.ok
    assert "not evidence that the pages have no states" in result.errors[0]


def test_no_click_or_submit_action_is_invented():
    """react-ui states plainly that JSX handler bindings are not structurally
    recoverable. A fabricated `click` no test can bind to is worse than none."""
    result = synthesise_react_ui(facts(), journey="m")
    triggers = " ".join(t.trigger for t in result.model.transitions.values())
    for invented in ("click", "submit", "type ", "select"):
        assert invented not in triggers.lower(), f"{invented!r} was not recovered"


def test_screens_scope_the_model_the_way_service_scopes_the_api_side():
    two = facts(ui_states=facts()["ui_states"] + [
        {"id": "x", "screen": "OtherPage", "setter": "setStatus", "value": v,
         "anchor": {"file": "b.jsx", "line": 1, "commit": "c"}}
        for v in (LOADING, READY)])
    result = synthesise_react_ui(two, journey="m", screens={"MetricPage"})
    assert set(result.pages) == {"MetricPage"}


def test_the_endpoint_hint_is_evidence_not_invention():
    """Where the pack recovered a call whose path matches the region name, the
    trigger says so. Where it did not, the trigger stays silent."""
    result = synthesise_react_ui(facts(), journey="m")
    summary = [t for t in result.model.transitions.values() if "summary" in t.trigger]
    assert any("/metric/summary" in t.trigger for t in summary)

    without = synthesise_react_ui(facts(api_calls=[]), journey="m")
    assert not any("/" in t.trigger for t in without.model.transitions.values())


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
