"""
Layer 4 synthesis tests (application spec §2.1, §5.2, M-2, M-3; R4).

Free to run: synthesis is pure.
"""
import sys

from code_analysis.contract import Anchor, CheckFact, ExtractionReport, OutcomeFact
from code_analysis.synthesis import INITIAL_STATE, state_name, synthesise

COMMIT = "a3f21c"


def _anchor(line=10):
    return Anchor("CommitController.java", line, COMMIT)


def _behaviour(outcomes, checks=None) -> ExtractionReport:
    return ExtractionReport(
        pack="jvm-behaviour", pack_version="0.1.0", engine="joern",
        engine_version="4.0.604", repo="athena-git", commit=COMMIT,
        frontend="javasrc2cpg", layers=(4,),
        checks=checks or [], outcomes=outcomes,
    )


def _outcome(endpoint, status, disc, checks=(), sense=""):
    return OutcomeFact(id=f"{endpoint}::{status}", endpoint_id=endpoint,
                       signature=f"{status}/{disc}", status=status, discriminator=disc,
                       guarding_check_ids=tuple(checks), guard_sense=sense,
                       link="name-match", anchor=_anchor())


# `handler_method_id` is the field name the structural pack actually emits. An
# earlier version of this fixture said `handler`, which no pack has ever
# produced -- so these tests passed against a shape that does not exist. Keep
# this aligned with packs/jvm-structural/query.sc.
ENDPOINTS = [
    {"id": "e1", "http_method": "GET", "path": "/commit",
     "handler_method_id": "h1", "anchor": "x"},
    {"id": "e2", "http_method": "GET", "path": "/commit/{id}",
     "handler_method_id": "h2", "anchor": "x"},
    {"id": "e3", "http_method": "GET", "path": "/repo",
     "handler_method_id": "h3", "anchor": "x"},
]


def test_the_fixture_matches_the_field_the_real_pack_emits():
    """Guards the mismatch above: if the pack renames this field, these tests
    must fail rather than keep passing against an imaginary shape."""
    import json
    import pathlib as _p
    pack = _p.Path("code_analysis/packs/jvm-structural/query.sc").read_text()
    assert '"handler_method_id"' in pack
    assert all("handler_method_id" in e for e in ENDPOINTS)


# --------------------------------------------------------------------------
# M-2 / M-3 : outcome states are shared across endpoints
# --------------------------------------------------------------------------

def test_the_same_response_condition_is_one_state_across_all_endpoints():
    """For an API surface a state IS the observable response condition (M-2).

    204-with-no-body is indistinguishable to a client whichever endpoint produced
    it, so all four converge on one node. Minting a per-endpoint state would
    claim a distinction the caller cannot observe, which M-3 forbids -- and it
    would hide that four endpoints share one behaviour.
    """
    check = CheckFact("c1", "t.isEmpty()", 1, _anchor())
    outcomes = []
    for handler in ("h1", "h2", "h3"):
        outcomes.append(_outcome(f"{handler}::GET", 204, "noContent", ("c1",)))
        outcomes.append(_outcome(f"{handler}::GET", 200, "ok", ("c1",), sense="!"))

    result = synthesise(_behaviour(outcomes, [check]), ENDPOINTS, journey="athena-git")
    assert result.ok, result.errors

    model = result.model
    assert set(model.states) == {INITIAL_STATE, "NoContent204", "Ok200"}, (
        f"expected three shared states, got {sorted(model.states)}"
    )
    to_204 = [t for t in model.transitions.values() if t.target == "NoContent204"]
    assert len(to_204) == 3, "every endpoint returning 204 targets the same node"
    assert len({t.trigger for t in to_204}) == 3, "but each keeps its own trigger"


def test_state_naming_is_endpoint_independent():
    """The name comes from status + helper, never from the route — which is what
    makes sharing happen naturally rather than by a merge step."""
    assert state_name(204, "noContent") == "NoContent204"
    assert state_name(200, "ok") == "Ok200"
    assert state_name(201, "created") == "Created201"


def test_transitions_stay_distinct_even_when_they_share_a_target():
    check = CheckFact("c1", "t.isEmpty()", 1, _anchor())
    outcomes = [_outcome("h1::GET", 204, "noContent", ("c1",)),
                _outcome("h2::GET", 204, "noContent", ("c1",))]
    model = synthesise(_behaviour(outcomes, [check]), ENDPOINTS, journey="g").model
    assert len(model.transitions) == 2, "shared target must not collapse two transitions"
    assert {t.trigger for t in model.transitions.values()} == {"GET /commit", "GET /commit/{id}"}


# --------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------

def test_guard_sense_produces_the_negation():
    check = CheckFact("c1", "t.isEmpty()", 1, _anchor())
    outcomes = [_outcome("h1::GET", 204, "noContent", ("c1",), sense=""),
                _outcome("h1::GET", 200, "ok", ("c1",), sense="!")]
    model = synthesise(_behaviour(outcomes, [check]), ENDPOINTS, journey="g").model
    guards = {t.target: t.guard for t in model.transitions.values()}
    assert guards["NoContent204"] == "t.isEmpty()"
    assert guards["Ok200"] == "NOT (t.isEmpty())"


def test_an_unguarded_outcome_is_reported_not_invented():
    outcomes = [_outcome("h1::GET", 201, "created")]
    result = synthesise(_behaviour(outcomes), ENDPOINTS, journey="g")
    assert result.model.transitions
    assert result.unguarded, "an outcome with no recovered guard must be reported"
    assert all(t.guard == "" for t in result.model.transitions.values())


# --------------------------------------------------------------------------
# §5.8 : absence is reported as a cause, never as 'no behaviour'
# --------------------------------------------------------------------------

def test_no_outcomes_names_the_likely_cause():
    result = synthesise(_behaviour([]), ENDPOINTS, journey="g")
    assert not result.ok
    assert any("analysis unit" in e or "framework config" in e for e in result.errors)
    assert any("not evidence that the service has no behaviour" in e for e in result.errors)


def test_declared_versus_constructed_is_triage_not_a_defect_claim():
    """A status declared but not constructed in the handler is most often a
    framework exception handler elsewhere — claiming a defect would manufacture
    one out of a recovery limitation."""
    check = CheckFact("c1", "t.isEmpty()", 1, _anchor())
    outcomes = [
        _outcome("h1::POST", 201, "created", ("c1",)),
        OutcomeFact("d1", "h1::POST", "400/declared", 400, "declared",
                    (), "", "declared", _anchor()),
        OutcomeFact("d2", "h1::POST", "201/declared", 201, "declared",
                    (), "", "declared", _anchor()),
    ]
    result = synthesise(_behaviour(outcomes, [check]), ENDPOINTS, journey="g")
    assert result.findings
    finding = result.findings[0]
    assert "Needs triage" in finding
    assert "exception handler" in finding
    assert "disagree" not in finding, "must not assert a contradiction it cannot establish"


def test_declared_outcomes_do_not_become_transitions():
    """Declared statuses are evidence, not behaviour this pack recovered."""
    outcomes = [OutcomeFact("d1", "h1::GET", "200/declared", 200, "declared",
                            (), "", "declared", _anchor())]
    result = synthesise(_behaviour(outcomes), ENDPOINTS, journey="g")
    assert result.model.transitions == {}


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------

def test_every_transition_starts_at_the_initial_state():
    """The synthesised API model is a one-hop star: Ready -> outcome.

    Honest consequence: every generated path has zero setup, so path *chaining*
    is not exercised by this model shape. A resource lifecycle would exercise it,
    but deriving one needs REST-convention inference, which §5.8 excludes.
    """
    check = CheckFact("c1", "t.isEmpty()", 1, _anchor())
    outcomes = [_outcome("h1::GET", 204, "noContent", ("c1",)),
                _outcome("h2::GET", 200, "ok", ("c1",), sense="!")]
    model = synthesise(_behaviour(outcomes, [check]), ENDPOINTS, journey="g").model
    assert all(t.source == INITIAL_STATE for t in model.transitions.values())
    assert model.states[INITIAL_STATE].is_initial


def test_elements_land_at_quarantine():
    check = CheckFact("c1", "t.isEmpty()", 1, _anchor())
    outcomes = [_outcome("h1::GET", 204, "noContent", ("c1",))]
    model = synthesise(_behaviour(outcomes, [check]), ENDPOINTS, journey="g").model
    assert all(s.lifecycle_state == "Quarantine" for s in model.states.values())
    assert all(t.lifecycle_state == "Quarantine" for t in model.transitions.values())


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
        except Exception as e:
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
