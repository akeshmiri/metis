"""
OpenAPI → the extraction contract (application spec §5.2; X-2, X-5, X-6, GD-2).

Free to run: pure parsing and mapping. No Neo4j, no model calls, no network —
`$ref` resolution is local-only by design.
"""
import json
import sys
from pathlib import Path

from code_analysis.contract import (
    CONTRACT_VERSION,
    IN_BODY,
    IN_COOKIE,
    IN_HEADER,
    IN_PATH,
    IN_QUERY,
    LINK_DECLARED,
    validate_report,
)
from code_analysis.openapi import (
    OpenAPIRefused,
    constraints_of,
    load,
    to_dict,
    to_report,
)
from metis_mcp.model_sources import get as get_source
from metis_mcp.model_sources.base import DECLARED_CONTRACT

FIXTURE = Path(__file__).parent / "test_fixtures" / "records-openapi.json"


def _spec() -> dict:
    return json.loads(FIXTURE.read_text())


def _report():
    return to_report(_spec(), repo="records-api", document="records-api.json")


def _endpoint(report, method, path):
    return next(e for e in report.endpoints
                if e.http_method == method and e.path == path)


# --------------------------------------------------------------------------
# The contract it produces
# --------------------------------------------------------------------------

def test_the_report_passes_the_same_gate_a_pack_output_does():
    """X-5. A human-written document gets no exemption for being human-written."""
    result = _report()
    assert validate_report(result.report) == []
    assert result.report.contract_version == CONTRACT_VERSION


def test_the_version_comes_from_the_document_when_no_commit_is_given():
    """M-14: every element names the exact version it came from."""
    assert _report().report.commit == "2.4.1"


def test_a_document_with_no_version_and_no_commit_is_refused():
    spec = _spec()
    spec["info"].pop("version")
    try:
        to_report(spec, repo="r")
    except OpenAPIRefused as e:
        assert "M-14" in str(e)
    else:
        raise AssertionError("an element with no version cannot be anchored")


def test_something_that_is_not_an_openapi_document_is_refused():
    try:
        to_report({"paths": {}}, repo="r", commit="1")
    except OpenAPIRefused as e:
        assert "openapi" in str(e).lower()
    else:
        raise AssertionError("a mapping with `paths` is not necessarily OpenAPI")


def test_every_anchor_resolves_to_a_json_pointer():
    """X-6. A YAML document has no line number, so the pointer is the locator —
    and it is a real one a reviewer can open, not an invented line."""
    endpoint = _endpoint(_report().report, "GET", "/record/{id}")
    assert endpoint.anchor.file == "records-api.json#/paths/~1record~1{id}/get"
    assert endpoint.anchor.line == 0
    assert endpoint.anchor.commit == "2.4.1"


# --------------------------------------------------------------------------
# What it recovers
# --------------------------------------------------------------------------

def test_path_level_parameters_apply_to_every_operation_on_that_path():
    """OpenAPI 3 §4.8.9. Missing this drops the id from DELETE entirely."""
    report = _report().report
    for method in ("GET", "DELETE"):
        names = [p.name for p in _endpoint(report, method, "/record/{id}").parameters]
        assert "id" in names, f"{method} lost its path parameter"


def test_a_parameter_carries_its_location_and_its_constraints():
    endpoint = _endpoint(_report().report, "GET", "/record/{id}")
    by_name = {p.name: p for p in endpoint.parameters}
    assert by_name["id"].location == IN_PATH and by_name["id"].required
    assert "minimum: 1" in by_name["id"].constraints
    assert by_name["expand"].location == IN_QUERY
    assert not by_name["expand"].required


def test_a_request_body_becomes_a_body_parameter_with_its_schema_name():
    endpoint = _endpoint(_report().report, "POST", "/record")
    body = next(p for p in endpoint.parameters if p.location == IN_BODY)
    assert body.type_name == "RecordDto", "the $ref must resolve to a type name"
    assert endpoint.validated, "a declared request schema is OpenAPI's @Valid"


def test_an_operation_security_requirement_overrides_the_document_default():
    delete = _endpoint(_report().report, "DELETE", "/record/{id}")
    assert delete.security[0].roles == ("records:admin",)


def test_constraints_use_openapis_own_vocabulary_never_a_java_annotation():
    """Rewriting `maxLength: 120` into `@Size(max=120)` would claim the document
    said something it did not."""
    constraints = constraints_of({"maxLength": 120, "enum": ["a", "b"]}, required=True)
    assert constraints == ("required", "maxLength: 120", "enum: a|b")


def test_the_type_registry_carries_gd3s_variants():
    """The data requirements a fixture must violate to reach a rejection."""
    members = {(m.type_name, m.name): m for m in _report().report.members}
    title = members[("RecordDto", "title")]
    assert "required" in title.constraints
    assert "maxLength: 120" in title.constraints
    assert "enum: Draft|Active|Archived" in members[("RecordDto", "state")].constraints


def test_every_outcome_is_declared_never_constructed():
    """X-11: a document saying a 403 exists is not evidence any path builds one."""
    assert all(o.link == LINK_DECLARED for o in _report().report.outcomes)


# --------------------------------------------------------------------------
# GD-2 — the guards the document actually grounds
# --------------------------------------------------------------------------

def _guards(report):
    checks = {c.id: c for c in report.checks}
    return {o.id.rsplit("::", 1)[1]: checks[o.guarding_check_ids[0]].expression
            for o in report.outcomes if o.guarding_check_ids
            and o.endpoint_id.startswith("archiveRecord")}


def test_a_rejection_is_guarded_by_its_prefix_and_its_own_negation():
    """GD-2: guard(k) = (dimensions 1..k-1 pass) AND (dimension k fails)."""
    guards = _guards(_report().report)
    assert guards["403"] == "authenticated AND NOT authorized"
    assert guards["204"] == "authenticated AND authorized"


def test_the_pair_is_mutually_exclusive_by_construction():
    """GD-4: precedence-ordered guards satisfy determinism structurally."""
    from metis_mcp.behavior_model import guards_conflict

    guards = _guards(_report().report)
    overlaps, _ = guards_conflict(guards["204"], guards["403"])
    assert not overlaps


def test_a_status_the_document_does_not_explain_is_left_unguarded():
    """A 404 is declared and never conditioned. Reporting it is the tool working;
    inventing `record_exists` is what S-13 forbids."""
    report = _report().report
    not_found = next(o for o in report.outcomes
                     if o.endpoint_id.startswith("getRecordById") and o.status == 404)
    assert not_found.guarding_check_ids == ()


def test_a_dimension_the_document_never_declares_is_never_asserted():
    """No security on the operation and none at the document level means
    `authenticated` is a word nobody wrote."""
    spec = _spec()
    spec.pop("security")
    spec["paths"]["/record"]["post"].pop("requestBody")
    report = to_report(spec, repo="r").report
    assert all(not o.guarding_check_ids for o in report.outcomes
               if o.endpoint_id.startswith("createRecord"))


def test_check_orders_are_unique_or_precedence_would_be_ambiguous():
    """GD-9, and `validate_report` enforces it."""
    orders = [c.order for c in _report().report.checks]
    assert len(orders) == len(set(orders))


# --------------------------------------------------------------------------
# `in: cookie` — one of OpenAPI 3.0's four locations, mapped like any other
# --------------------------------------------------------------------------

def test_a_cookie_parameter_lands_like_any_other():
    """It used to be intercepted and dropped: an optional one became a note, a
    required one refused the whole document. The reasoning for not folding it
    into `header` was right and still holds — a cookie and a header are
    different claims about where the value rides — but the fix for a real
    position missing from the vocabulary is to add it, not to keep reporting it.
    """
    result = _report()
    assert result.report.parse_errors == []
    assert not any("cookie" in n for n in result.notes), (
        "a mapped location should not be disclosed as unmappable")

    endpoint = _endpoint(result.report, "GET", "/record/{id}")
    session = next((p for p in endpoint.parameters if p.name == "session"), None)
    assert session is not None, "the cookie parameter was dropped"
    assert session.location == IN_COOKIE


def test_a_required_cookie_no_longer_refuses_the_document():
    """It blocked because the value could not be represented. It can now, so a
    request generated for this endpoint carries it and X-5 has nothing to
    refuse."""
    spec = _spec()
    for parameter in spec["paths"]["/record/{id}"]["get"]["parameters"]:
        if parameter["name"] == "session":
            parameter["required"] = True
    result = to_report(spec, repo="r")
    assert result.report.parse_errors == []
    assert not validate_report(result.report)


def test_a_cookie_is_still_never_folded_into_a_header():
    """The distinction that mattered all along: a generated request has to
    construct one or the other."""
    endpoint = _endpoint(_report().report, "GET", "/record/{id}")
    session = next(p for p in endpoint.parameters if p.name == "session")
    assert session.location != IN_HEADER



# --------------------------------------------------------------------------
# The source, and its provenance
# --------------------------------------------------------------------------

def test_the_source_records_what_it_is_not_static_analysis():
    """M-13. A code model says what the system does; this says what its contract
    declares, and a reviewer weighs those differently."""
    out = get_source("openapi").produce(path=str(FIXTURE), journey="records",
                                        surface="api", repo="records-api")
    assert out.extraction_method == DECLARED_CONTRACT
    assert out.extraction_method != "static_analysis"


def test_the_model_carries_the_inputs_the_document_declared():
    """The join this catches was silent: `synthesise` recovers the handler with
    `endpoint_id.rsplit("::", 1)[0]`, so an id in any other shape matched no
    endpoint and every recovered parameter was dropped — while the model still
    built and `check_callability` reported bodies this had in hand as missing."""
    out = get_source("openapi").produce(path=str(FIXTURE), journey="records",
                                        surface="api", repo="records-api")
    post = next(t for t in out.model.transitions.values()
                if t.trigger.startswith("POST"))
    assert [p["name"] for p in post.inputs] == ["body"]
    assert post.is_callable


def test_the_report_is_the_packs_own_json_shape():
    """X-2: one contract, two producers. The existing `code` source reads this
    with no change, which is the whole integration."""
    from metis_mcp.model_sources.sources import _report_from_dict

    data = to_dict(_report().report)
    assert _report_from_dict(data).endpoints[0].parameters[0].name


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


def _report_with_parameter_location(location: str):
    """A real adapter report with one parameter's location overridden.

    Built from the adapter rather than hand-assembled, so the report is valid in
    every other respect and the only thing under test is the location.
    """
    import dataclasses

    report = _report().report
    endpoint = next(e for e in report.endpoints if e.parameters)
    parameters = list(endpoint.parameters)
    parameters[0] = dataclasses.replace(parameters[0], location=location)
    patched = dataclasses.replace(endpoint, parameters=tuple(parameters))
    return dataclasses.replace(
        report,
        endpoints=tuple(patched if e is endpoint else e for e in report.endpoints))


def test_a_location_outside_the_vocabulary_is_refused():
    """`contract.PARAMETER_LOCATIONS` is what the adapter maps into. It used to
    be checked against `Parameter.location`'s enum — two lists for one fact, and
    `cookie` was added to the first and not the second, so a document the adapter
    read cleanly was refused at landing.

    `Parameter` was staged out (its content is the transition's `c_inputs`), so
    there is one list now and it is enforced where the fact enters. Without this
    the vocabulary would be declared and checked by nothing at all.
    """
    import dataclasses

    from code_analysis.contract import PARAMETER_LOCATIONS, validate_report

    report = _report_with_parameter_location("cookie")
    assert validate_report(report) == [], "cookie IS in the vocabulary"

    bad = _report_with_parameter_location("teapot")
    problems = validate_report(bad)
    assert any("teapot" in p and "not one of" in p for p in problems), problems
    assert "cookie" in PARAMETER_LOCATIONS
