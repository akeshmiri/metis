"""
`model_id` on every element of a model.

**What it adds, and what it does not.** The value is already the first half of
the namespaced id (`{model_id}::{element_id}`) for states AND transitions alike
— `graph_transition_id` namespaces both — so this adds no information. It adds
QUERYABILITY: "every element of this model" was a `STARTS WITH` on the id, which
no index serves, and which breaks on any id containing `::` for another reason.

I first justified this by claiming a transition's id was a bare natural key with
no model in it. That is wrong, and the test below now pins the opposite: both
encodings exist and must agree.

It is REQUIRED rather than optional because `landing` is the only writer of these
(asserted in `test_independence.py`), so a second writer that omitted it is
refused at the gate instead of quietly producing elements that belong to no
model.

Free to run: planning is pure.
"""
from __future__ import annotations

import pytest

from metis_mcp.model_sources import get, plan_landing
from metis_mcp.ontology.validation import validate

MODEL_LABELS = {"State", "ApiCall", "UiAction", "Transition"}


def _plan():
    result = get("authored").produce(
        path="demo_data/models/records-api.json", journey="records")
    return plan_landing(result, journey="records", job_id="t"), result


def test_every_model_element_carries_its_model():
    plan, result = _plan()
    assert plan.errors == []
    elements = [n for n in plan.nodes if n.label in MODEL_LABELS]
    assert elements, "no model elements planned — the fixture stopped proving anything"
    for node in elements:
        assert node.properties.get("model_id") == result.model.id, node.properties["id"]


def test_the_value_agrees_with_the_namespace_in_the_id():
    """Two encodings of one fact must not disagree — that is worse than one."""
    plan, _ = _plan()
    for node in plan.nodes:
        if node.label != "State":
            continue
        prefix, sep, _ = node.properties["id"].partition("::")
        assert sep, f"{node.properties['id']} is not namespaced"
        assert prefix == node.properties["model_id"]


def test_a_transition_id_is_namespaced_too_and_the_two_agree():
    """The correction. A transition's id is `{model_id}::{natural_key}`, so the
    property duplicates the prefix — and a duplicate that can disagree is worse
    than no duplicate at all."""
    plan, result = _plan()
    transitions = [n for n in plan.nodes if n.label in {"ApiCall", "UiAction"}]
    assert transitions
    for node in transitions:
        prefix, sep, rest = node.properties["id"].partition("::")
        assert sep and rest, f"{node.properties['id']} is not namespaced"
        assert prefix == node.properties["model_id"] == result.model.id


@pytest.mark.parametrize("label", ["State", "Transition", "ApiCall"])
def test_the_gate_refuses_an_element_with_no_model(label):
    base = {"id": "x", "source_episode_id": "e", "name": "n", "b_surface": "api",
            "b_is_initial": False, "lifecycle_state": "Quarantine",
            "c_trigger": "GET /x", "b_guard_expression": "",
            "b_implementation_status": "implemented"}
    assert validate(label, {**base, "model_id": "m"}).valid
    refused = validate(label, base)
    assert not refused.valid
    assert "model_id" in refused.errors[0]


def test_two_models_are_separable_without_string_matching():
    """The point of the property: a filter, not a prefix scan."""
    api, _ = _plan()
    ui_result = get("authored").produce(
        path="demo_data/models/login-api.json", journey="login")
    ui = plan_landing(ui_result, journey="login", job_id="t")

    ids = {n.properties["model_id"]
           for plan in (api, ui)
           for n in plan.nodes if n.label in MODEL_LABELS}
    assert len(ids) == 2, f"models are not distinguishable: {ids}"
