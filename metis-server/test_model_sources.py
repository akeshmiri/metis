"""
Model-source and landing tests (application spec §4.2, S-4, S-17, D-8b).

Free to run: the planner is pure, so landing legality is provable offline.
"""
import json
import sys
import tempfile
from pathlib import Path

from metis_mcp.mbt.model import QUARANTINE
from metis_mcp.model_sources import (
    AC_MINED,
    HAND_AUTHORED,
    STATIC_ANALYSIS,
    availability,
    episode_id_for,
    get,
    land,
    plan_landing,
    registered,
)
from mbt_fixtures import login_model_source


def _authored(tmpdir: str):
    path = Path(tmpdir) / "login-api.json"
    path.write_text(json.dumps(login_model_source(), indent=2))
    return get("authored").produce(path=str(path), author="alice")


# --------------------------------------------------------------------------
# R9 : all three cases are registered
# --------------------------------------------------------------------------

def test_all_three_sources_are_registered():
    assert set(registered()) == {"authored", "code", "ac-mined"}


def test_unimplemented_sources_say_why_rather_than_being_absent():
    """Spec S-17/S-18: report what could produce a model; never choose silently.

    `ac-mined` used to be listed here as unavailable, "needs a gated model call".
    It does not: criteria written to EARS or Given/When/Then parse
    deterministically, and TR-4 prefers deterministic code to generated judgement.
    It is now genuinely available, which is what makes S-3's comparison possible
    without an LLM budget. Only the code source still needs an external engine.
    """
    report = dict((name, (ok, why)) for name, ok, why in availability())
    assert report["authored"][0] is True
    assert report["ac-mined"][0] is True, "deterministic mining needs no model call"

    available, why = report["code"]
    assert available is False
    assert why.strip(), "code extraction must state why it cannot run"


def test_two_sources_are_available_so_the_intent_comparison_is_possible():
    """S-3: a deployment running only code extraction gets coverage, not
    correctness. Two independent sources must be able to disagree."""
    available = {name for name, ok, _ in availability() if ok}
    assert {"authored", "ac-mined"} <= available


def test_unimplemented_source_raises_with_its_reason():
    try:
        get("code").produce()
    except NotImplementedError as e:
        assert "Joern" in str(e) or "code-property-graph" in str(e)
        return
    raise AssertionError("an unavailable source must raise, not return an empty model")


def test_extraction_methods_match_the_ontology_enum():
    from metis_mcp.ontology import LABELS
    allowed = LABELS["Transition"].enums["extraction_method"]
    assert set(allowed) == {HAND_AUTHORED, STATIC_ANALYSIS, AC_MINED}


# --------------------------------------------------------------------------
# The authored source
# --------------------------------------------------------------------------

def test_authored_source_produces_quarantine_elements():
    """Spec S-4: authoring is not approving."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _authored(tmp)
    assert result.extraction_method == HAND_AUTHORED
    assert all(s.lifecycle_state == QUARANTINE for s in result.model.states.values())
    assert all(t.lifecycle_state == QUARANTINE for t in result.model.transitions.values())


def test_authored_source_records_its_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        result = _authored(tmp)
    assert result.evidence["author"] == "alice"
    assert result.evidence["path"].endswith("login-api.json")


def test_dangling_transition_is_skipped_with_a_reason():
    with tempfile.TemporaryDirectory() as tmp:
        data = login_model_source()
        data["transitions"].append({"id": "tX", "source": "LoggedOut",
                                    "trigger": "go", "target": "Nowhere"})
        path = Path(tmp) / "m.json"
        path.write_text(json.dumps(data))
        result = get("authored").produce(path=str(path))
    assert ("tX", "source or target state not in this model") in result.skipped
    assert "tX" not in result.model.transitions


# --------------------------------------------------------------------------
# Landing: provenance, legality, idempotency
# --------------------------------------------------------------------------

def test_landing_plan_is_legal_offline():
    with tempfile.TemporaryDirectory() as tmp:
        plan = plan_landing(_authored(tmp), journey="login")
    assert plan.is_legal, plan.errors[:3]


def test_every_element_carries_the_episode_that_justifies_it():
    """Spec P1: no fact enters the graph without a traceable basis."""
    with tempfile.TemporaryDirectory() as tmp:
        plan = plan_landing(_authored(tmp), journey="login")
    for node in plan.nodes:
        if node.label == "Episode":
            assert "source_episode_id" not in node.properties, (
                "an Episode is the provenance record and cannot point at one"
            )
            continue
        assert node.properties["source_episode_id"] == plan.episode_id


def test_landing_plans_states_transitions_and_one_episode():
    with tempfile.TemporaryDirectory() as tmp:
        plan = plan_landing(_authored(tmp), journey="login")
    assert len(plan.by_label("Episode")) == 1
    assert len(plan.by_label("State")) == 10
    assert len(plan.by_label("Transition")) == 17
    when = [e for e in plan.edges if e.rel_type == "WHEN"]
    then = [e for e in plan.edges if e.rel_type == "THEN"]
    assert len(when) == 17 and len(then) == 17


def test_extraction_method_is_recorded_on_every_transition():
    """Spec M-13: provenance survives into the graph."""
    with tempfile.TemporaryDirectory() as tmp:
        plan = plan_landing(_authored(tmp), journey="login")
    for node in plan.by_label("Transition"):
        assert node.properties["extraction_method"] == HAND_AUTHORED


def test_journey_tag_is_applied_for_later_scoping():
    with tempfile.TemporaryDirectory() as tmp:
        plan = plan_landing(_authored(tmp), journey="login")
    for node in (*plan.by_label("State"), *plan.by_label("Transition")):
        assert node.properties["functional_areas"] == ["login"]


def test_episode_id_is_content_derived_so_relanding_is_a_no_op():
    with tempfile.TemporaryDirectory() as tmp:
        first = plan_landing(_authored(tmp), journey="login")
        second = plan_landing(_authored(tmp), journey="login")
    assert first.episode_id == second.episode_id


def test_a_changed_model_lands_under_a_different_episode():
    with tempfile.TemporaryDirectory() as tmp:
        before = plan_landing(_authored(tmp), journey="login").episode_id
        data = login_model_source()
        for t in data["transitions"]:
            if t["id"] == "t06":
                t["guard"] = "NOT credentials_valid AND attempts >= 5"
        path = Path(tmp) / "changed.json"
        path.write_text(json.dumps(data))
        result = get("authored").produce(path=str(path))
        after = plan_landing(result, journey="login").episode_id
    assert after != before, "a changed model is different evidence"


def test_illegal_plan_never_reaches_the_database():
    """Under Community the gate is the sole guarantee (spec D-8b)."""
    with tempfile.TemporaryDirectory() as tmp:
        plan = plan_landing(_authored(tmp), journey="login")
    plan.errors.append("injected")
    calls = []

    class Recorder:
        def run(self, *a, **k):
            calls.append(a)

    outcome = land(Recorder(), plan)
    assert not outcome.ok and calls == []


def test_landing_uses_merge_so_a_repeat_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        plan = plan_landing(_authored(tmp), journey="login")
    statements = []

    class Recorder:
        def run(self, cypher, **kwargs):
            statements.append(cypher)

    outcome = land(Recorder(), plan)
    assert outcome.ok
    assert all("MERGE" in s for s in statements)
    assert outcome.episode_id == plan.episode_id


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
