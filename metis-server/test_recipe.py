"""
Call-recipe rendering (spec §7.4b, X-6e).

Free to run: the renderer is pure. What it renders comes from the demo corpus's
extraction, so the placeholders are the real constraints rather than a fixture's
idea of them.
"""
from __future__ import annotations

import json
import re

from metis_mcp.rendering import recipe as R


def _endpoint(structural, path: str) -> dict:
    return next(e for e in structural["endpoints"] if e["path"] == path)


def _payload(structural, type_name: str, nested: dict | None = None) -> dict:
    """The Class node's flat properties, as landing would write them."""
    from metis_mcp.model_sources.raw_landing import _field_properties
    from metis_mcp.model_sources.sources import _report_from_dict

    members = [m for m in _report_from_dict(structural).members
               if m.type_name == type_name]
    node = {"name": type_name, "fields": sorted(m.name for m in members),
            **_field_properties(members)}
    return R.expand_payload(node, nested)


# --------------------------------------------------------------------------
# The space, not a value
# --------------------------------------------------------------------------

def test_an_enum_field_renders_its_partitions(demo_structural):
    body = R.body_template(_payload(demo_structural, "RecordBatchDto"))
    assert body["mode"] == "<IMMEDIATE|DEFERRED|DRY_RUN>"


def test_a_bounded_string_renders_its_bounds(demo_structural):
    body = R.body_template(_payload(demo_structural, "RecordBatchDto"))
    assert body["submittedBy"] == "<string, length 3..40, required>"


def test_a_collection_renders_cardinality_not_length(demo_structural):
    """Forty characters and forty elements are different things to build."""
    body = R.body_template(_payload(demo_structural, "RecordBatchDto"))
    assert body["tags"] == "<list, 1..50 items>"


def test_a_pattern_is_carried_into_the_placeholder(demo_structural):
    body = R.body_template(_payload(demo_structural, "RecordBatchDto"))
    assert "matching [A-Z]{2}-[0-9]{4}" in body["reference"]


def test_no_literal_appears_that_was_not_recovered(demo_structural):
    """**T-9c, asserted rather than trusted.** A plausible-looking value is the
    failure this rule exists to prevent, so every string in a rendered body is
    either a placeholder or a name that came out of the graph."""
    body = R.body_template(_payload(demo_structural, "RecordBatchDto"))
    declared = {m["name"] for m in demo_structural["members"]}
    for name, value in body.items():
        assert name in declared, f"{name} is not a declared field"
        if isinstance(value, str):
            assert value.startswith("<") and value.endswith(">"), value


# --------------------------------------------------------------------------
# The nested payload
# --------------------------------------------------------------------------

def test_a_nested_type_renders_as_a_nested_body(demo_structural):
    """`records` is a `List<RecordDto>`, so the body a fixture builds is a list
    of the nested shape — not the string `java.util.List`."""
    nested = {"RecordDto": _payload(demo_structural, "RecordDto")}
    body = R.body_template(_payload(demo_structural, "RecordBatchDto", nested))
    assert isinstance(body["records"], list) and len(body["records"]) == 1
    assert "title" in body["records"][0]


def test_a_self_referential_payload_terminates():
    """A type that contains itself is legal Java and would otherwise recurse
    for ever."""
    loop = {"type": "Node", "fields": {"child": {"type": "Node"}}}
    loop["fields"]["child"]["__nested__"] = loop
    body = R.body_template(loop)
    assert body["child"] == {"__recursive__": "Node"}


# --------------------------------------------------------------------------
# What could not be recovered is marked, never guessed (T-9d)
# --------------------------------------------------------------------------

def test_an_absent_base_url_is_a_placeholder_with_its_reason(demo_structural):
    built = R.build(_endpoint(demo_structural, "/record"))
    assert built["base_url"] == "{base}"
    assert any(what == "base_url" for what, _ in built["unrecoverable"])


def test_a_declared_base_url_is_used(demo_structural):
    built = R.build(_endpoint(demo_structural, "/record"),
                    base_url="https://records.example")
    assert built["base_url"] == "https://records.example"
    assert not any(what == "base_url" for what, _ in built["unrecoverable"])


def test_no_declared_security_says_so_and_does_not_say_open(demo_structural):
    """The distinction that matters: extraction cannot see a filter chain or a
    gateway, so "nothing declared" is the only claim available."""
    built = R.build(_endpoint(demo_structural, "/record/page"))
    assert built["security"]["declared"] is False
    assert "not the same as open" in built["security"]["note"]


def test_declared_security_is_carried(demo_structural):
    """`@DemoSecured` is a project annotation — Métis ships no knowledge of it,
    and the profile declaring `role: security` is the only reason it is here."""
    built = R.build(_endpoint(demo_structural, "/record"),
                    )  # POST /record carries @DemoSecured({"records:write"})
    posts = [e for e in demo_structural["endpoints"]
             if e["path"] == "/record" and e["http_method"] == "POST"]
    assert posts[0]["security"], "the pack recovered it"


def test_an_assumed_content_type_is_stated_as_an_assumption(demo_structural):
    built = R.build(_endpoint(demo_structural, "/record"),
                    payload_types=(_payload(demo_structural, "RecordDto"),))
    assert built["content_type"] == "application/json"
    assert any(what == "content_type" for what, _ in built["unrecoverable"])


# --------------------------------------------------------------------------
# The rendered command
# --------------------------------------------------------------------------

def test_the_curl_is_shaped_like_something_you_can_run(demo_structural):
    built = R.build(_endpoint(demo_structural, "/record/{id}"),
                    base_url="https://records.example")
    text = R.as_curl(built)
    assert text.startswith("curl -X ")
    assert "https://records.example/record/{id}" in text


def test_every_rejection_is_named_beside_the_call(demo_structural):
    built = R.build(_endpoint(demo_structural, "/summary/{id}"),
                    rejections=(("422", "SummaryUnavailableException"),))
    assert "# 422 when SummaryUnavailableException" in R.as_curl(built)
