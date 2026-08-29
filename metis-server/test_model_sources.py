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

def test_every_source_is_registered():
    """Five, and two of them exist because provenance was being misreported.

    `web` exists because **neither UI synthesiser was reachable from anywhere** —
    `ui_synthesis.synthesise` had zero callers and the react-ui facts had no
    consumer at all, so the six landed UI models were hand-derived off-pipeline
    and recorded `hand_authored`: the same provenance defect the code source had.

    `openapi` is the fifth, and it is a separate source rather than a flag on
    `code` for the same reason. Its output flows through the identical
    `contract.ExtractionReport`, so `synthesise` needed no change — but a
    published contract is not static analysis of code. One records what the
    system *does*, the other what it *declares*, and where they differ that is
    the finding (§4.1). It is invisible if both arrive wearing `static_analysis`.
    """
    assert set(registered()) == {"authored", "code", "ac-mined", "web", "openapi"}


def test_every_source_reports_its_availability_rather_than_being_absent():
    """Spec S-17/S-18: report what could produce a model; never choose silently.

    Both of the sources once listed here as unavailable now run. `ac-mined`
    never needed a model call -- criteria written to EARS or Given/When/Then
    parse deterministically, and TR-4 prefers deterministic code to generated
    judgement. `code` reads a query pack's already-validated report rather than
    driving Joern itself, and while it was unavailable its real output was being
    landed through the *authored* source -- so thirteen statically-analysed
    models recorded `hand_authored`, claiming a person wrote what a machine
    inferred (M-13).
    """
    report = dict((name, (ok, why)) for name, ok, why in availability())
    assert report["authored"][0] is True
    assert report["ac-mined"][0] is True, "deterministic mining needs no model call"
    assert report["code"][0] is True, "code extraction reads pack output, not Joern"


def test_two_sources_are_available_so_the_intent_comparison_is_possible():
    """S-3: a deployment running only code extraction gets coverage, not
    correctness. Two independent sources must be able to disagree."""
    available = {name for name, ok, _ in availability() if ok}
    assert {"authored", "ac-mined"} <= available


def test_the_code_source_refuses_without_a_pack_report():
    """It reads what a pack emitted; it does not invent an empty model."""
    try:
        get("code").produce()
    except ValueError as e:
        assert "behaviour pack" in str(e)
        return
    raise AssertionError("a source with no input must raise, not return an empty model")


def test_the_code_source_refuses_to_merge_several_services_into_one_model():
    """A monorepo report unscoped is worse than a failure — it looks like a result.

    The pilot estate's single report carries 405 outcomes across seven services.
    Synthesising them together produced one 145-transition model wearing one
    service's name.
    """
    import json, tempfile, pathlib
    from code_analysis.contract import CONTRACT_VERSION

    report = {
        "contract_version": CONTRACT_VERSION, "pack": "p", "pack_version": "1",
        "engine": "e", "engine_version": "1", "repo": "r", "commit": "c",
        "frontend": "javasrc2cpg", "layers": [4],
        "checks": [], "methods": [], "endpoints": [], "members": [],
        "outcomes": [
            {"id": "o1", "endpoint_id": "e1", "signature": "s", "status": 200,
             "discriminator": "", "guarding_check_ids": [], "guard_sense": "",
             "link": "declared",
             "anchor": {"file": "records-service/A.java", "line": 1, "commit": "c"}},
            {"id": "o2", "endpoint_id": "e2", "signature": "s", "status": 200,
             "discriminator": "", "guarding_check_ids": [], "guard_sense": "",
             "link": "declared",
             "anchor": {"file": "archive-service/B.java", "line": 1, "commit": "c"}},
        ],
        "parse_errors": [], "partial": False,
    }
    with tempfile.TemporaryDirectory() as d:
        path = pathlib.Path(d) / "r.json"
        path.write_text(json.dumps(report))
        try:
            get("code").produce(path=str(path), journey="records")
        except ValueError as e:
            assert "spans 2 services" in str(e) and "--service" in str(e)
            return
    raise AssertionError("an unscoped multi-service report must refuse")


def test_extraction_methods_match_the_ontology_enum():
    """A method the ontology does not allow is refused at landing, so a source
    can only report provenance the graph can actually store."""
    from metis_mcp.model_sources.base import DECLARED_CONTRACT
    from metis_mcp.ontology import LABELS
    allowed = LABELS["Transition"].enums["x_extraction_method"]
    assert set(allowed) == {HAND_AUTHORED, STATIC_ANALYSIS, AC_MINED, DECLARED_CONTRACT}


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
    # `login-api` is an api-surface model, so its transitions land as `ApiCall`.
    # The generic `Transition` label is reserved for transitions whose surface
    # nothing established — a worklist, not a synonym for all of them.
    assert len(plan.by_label("ApiCall")) == 17
    assert len(plan.by_label("Transition")) == 0
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


# --------------------------------------------------------------------------
# A specialisation replaces its parent -- as a property, not as a comment
# --------------------------------------------------------------------------

def _plan_for(surface: str):
    """Landing derives the surface from the model id's suffix (`login-api` ->
    `api`), so the id is what selects the label."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        source = login_model_source()
        source["id"] = f"login-{surface}"
        for state in source["states"]:
            state["surface"] = surface
        path = Path(tmp) / "m.json"
        path.write_text(json.dumps(source, indent=2))
        result = get("authored").produce(path=str(path), author="alice")
        return plan_landing(result, journey="login", job_id="j1")


def test_a_classified_transition_carries_exactly_one_label():
    """`:ApiCall` is written INSTEAD of `:Transition`, never alongside it.

    Both `ontology/labels.py` and the application spec's §8.2 said the opposite
    for a long time, and nothing contradicted them because nothing asserted the
    property. It is the one semantic that fails silently: an edge planned
    against `:Transition` passes the ontology check -- `is_allowed` walks the
    specialisation chain -- and then merges nothing, because no node carries
    that label. Both stages report success and the chain is broken.
    """
    for surface, expected in (("api", "ApiCall"), ("ui", "UiAction")):
        plan = _plan_for(surface)
        classified = [n for n in plan.nodes if n.label == expected]
        assert classified, f"no {expected} nodes were planned for surface={surface}"
        for node in classified:
            assert node.also == (), (
                f"{expected} carries extra labels {node.also!r} -- a "
                f"specialisation replaces its parent, it does not accompany it"
            )
        assert not [n for n in plan.nodes if n.label == "Transition"], (
            "a classified transition was also planned as a generic :Transition"
        )


def test_the_generic_transition_label_is_left_meaning_unclassified():
    """Which is what makes `MATCH (t:Transition)` a worklist rather than a
    synonym for every transition in the graph."""
    from metis_mcp.model_sources.landing import transition_label_for

    assert transition_label_for("api") == "ApiCall"
    assert transition_label_for("ui") == "UiAction"
    assert transition_label_for("") == "Transition"
    assert transition_label_for("something-new") == "Transition"


def test_matching_any_transition_needs_the_label_expression():
    """The documented way to get it right, asserted so the docs cannot drift
    from it."""
    from metis_mcp.ontology.labels import label_expression

    expression = label_expression("Transition")
    for label in ("Transition", "ApiCall", "UiAction"):
        assert label in expression, f"{label} would not match {expression}"


# --------------------------------------------------------------------------
# What a source could not model reaches the graph
# --------------------------------------------------------------------------
#
# `react_ui_synthesis` detects the real limit precisely — "no 'loading' state
# recovered; its ['error','ready'] state(s) have no recovered entry", because
# `setStatus(record ? "ready" : "error")` is a ternary and not a control
# structure the pack can traverse. That reason was PRINTED by `metis land` and
# persisted nowhere, so M-18 later reported the same states as "unreachable — a
# dead state, or a transition into it is missing", sending a reader to look for
# a modelling mistake instead of a recall limit.

def _landed_findings(skipped):
    from metis_mcp.mbt.model import Model, State, Transition
    from metis_mcp.model_sources.base import SourceResult
    from metis_mcp.model_sources.landing import plan_landing

    model = Model(
        id="probe-ui",
        states={"A": State(id="A", name="A", surface="ui", is_initial=True),
                "B": State(id="B", name="B", surface="ui")},
        transitions={"t": Transition(id="t", source="A", target="B",
                                     trigger="click go", guard="")})
    plan = plan_landing(
        SourceResult(model=model, extraction_method="static_analysis",
                     source_connector="react-ui", skipped=list(skipped)),
        journey="probe")
    assert not plan.errors, plan.errors
    return [n for n in plan.nodes if n.label == "Finding"]


def test_what_a_source_could_not_model_lands_as_a_finding():
    findings = _landed_findings([
        ("SummaryPage.summary", "SummaryPage.summary: no 'loading' state recovered")])
    assert len(findings) == 1
    assert findings[0].properties["finding_type"] == "unmodelled"
    assert findings[0].properties["resolution"] == "open"
    assert "no 'loading' state recovered" in findings[0].properties["detail"]


def test_the_reason_is_not_stuttered_when_it_already_names_the_element():
    """`react-ui` splits its own message to produce an element id, and passes
    the whole message as both for a finding. Prefixing again reads badly."""
    one = _landed_findings([("A.page", "A.page: no entry recovered")])[0]
    assert one.properties["detail"] == "A.page: no entry recovered"
    same = _landed_findings([("whole message", "whole message")])[0]
    assert same.properties["detail"] == "whole message"


def test_nothing_skipped_lands_no_finding():
    """Silence where there is nothing to report — a Finding per landing would
    train a reader to ignore the label."""
    assert not _landed_findings([])
