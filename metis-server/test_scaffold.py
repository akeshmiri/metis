"""
The handoff to a generator outside Métis (R8, X-6e, T-9c).

The manifest exists so that R8 can hold while somebody still gets code out the
other end. These assert the two properties that make that true: it carries no
framework, and it carries no values.
"""
from __future__ import annotations

import json

from metis_mcp.mbt.criteria import DEFAULT_CRITERION
from metis_mcp.mbt.path_generation import generate
from metis_mcp.rendering import render
from metis_mcp.scaffold import KNOWN_TARGETS, flow_manifest, flow_manifests
from test_publishing import _cases


def _built(target="generic"):
    model, cases = _cases()
    return model, cases, flow_manifests(model, cases, target=target)


# --------------------------------------------------------------------------
# Framework-neutral by construction
# --------------------------------------------------------------------------

def _without_target_fields(document: dict) -> str:
    """The manifest with `target` and `translation_rules` removed.

    Those two legitimately name a framework — that is their whole job. Checking
    for leaks without stripping them first is a test that cannot fail for the
    one term most likely to leak, which is how a guard ends up guarding nothing.
    """
    body = json.loads(json.dumps(document))
    body.pop("target", None)
    body.pop("translation_rules", None)
    for flow in body.get("flows", []):
        flow.pop("target", None)
        flow.pop("translation_rules", None)
    return json.dumps(body).lower()


def test_the_manifest_names_no_library_or_annotation():
    """**The property R8 rests on.** The moment a framework name appears in the
    payload itself, the framework knowledge has moved back inside Métis."""
    _m, _c, document = _built("locust")
    body = _without_target_fields(document)
    for leak in ("locust", "junit", "pytest", "playwright", "restassured",
                 "@task", "@test", "@beforeeach", "fasthttpuser",
                 "taskset", "import "):
        assert leak not in body, f"{leak!r} leaked into the manifest"


def test_the_leak_check_would_actually_catch_one():
    """The guard on the guard: strip the two fields that may name a framework,
    then plant one somewhere else and confirm it is seen."""
    _m, _c, document = _built("locust")
    document["flows"][0]["name"] = "a FastHttpUser task"
    assert "fasthttpuser" in _without_target_fields(document)


def test_naming_a_target_does_not_change_what_is_emitted():
    """`target` selects which lesson a reader is pointed at. If it changed the
    output, the seam would be in the wrong place — and a second framework would
    need a second manifest."""
    model, cases = _cases()
    generic = flow_manifests(model, cases, target="generic")
    locust = flow_manifests(model, cases, target="locust")

    def _stripped(d):
        body = json.loads(json.dumps(d))
        body.pop("target", None)
        body.pop("translation_rules", None)
        for flow in body.get("flows", []):
            flow.pop("target", None)
            flow.pop("translation_rules", None)
        return body

    assert _stripped(generic) == _stripped(locust)


def test_every_known_target_points_at_a_lesson_that_exists():
    """A translation rule nobody can read is not a translation rule."""
    import pathlib

    repo = pathlib.Path(__file__).resolve().parent.parent
    for target, lesson in KNOWN_TARGETS.items():
        assert (repo / lesson).exists(), f"{target} points at a missing {lesson}"


# --------------------------------------------------------------------------
# The accepted space, never a value
# --------------------------------------------------------------------------

def test_the_manifest_carries_no_sample_values():
    """X-6e / T-9c. One valid value is one case; the space is what a case is
    chosen from. A manifest carrying an example teaches a generator to emit that
    example forever — and to stop generating the boundaries worth having."""
    _m, _c, document = _built()
    for flow in document["flows"]:
        for name, shape in flow["payloads"].items():
            body = json.dumps(shape)
            assert "example" not in body.lower(), name
            assert "sample" not in body.lower(), name


def test_data_requirements_say_where_each_condition_bites():
    """T-9: grouped, not repeated per step, and each still naming its steps —
    otherwise a builder cannot tell setup data from act data."""
    _m, _c, document = _built()
    for flow in document["flows"]:
        for requirement in flow["data_requirements"]:
            assert requirement["condition"]
            assert isinstance(requirement["steps"], list)


# --------------------------------------------------------------------------
# What lets a generator write a good suite rather than a repetitive one
# --------------------------------------------------------------------------

def test_shared_setup_is_reported_so_a_generator_can_hoist_it():
    """Métis knows which cases share a precondition group; a generator reading
    one case at a time cannot, and emits N copies of the same fixture."""
    _m, _c, document = _built()
    assert "shared_setup" in document
    for group in document["shared_setup"]:
        assert group["cases"], "a group with no cases is not a group"


def test_the_flow_is_ordered_with_the_act_distinguished():
    """Setup is arrangement; exactly one step is the act (T-1a). A generator
    that cannot tell them apart writes an assertion into a fixture."""
    model, cases = _cases()
    flow = flow_manifest(model, cases[0])
    assert flow["act"]["ordinal"] == 0
    for i, step in enumerate(flow["setup"], start=1):
        assert step["ordinal"] == i


def test_a_manifest_states_what_it_is_and_is_not():
    """It lands in somebody else's repository, where our documentation is not."""
    _m, _c, document = _built()
    assert "R8" in document["means"]
    assert "specification, not code" in document["flows"][0]["means"]
