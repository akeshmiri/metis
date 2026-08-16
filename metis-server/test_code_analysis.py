"""
Query-pack contract and mapper tests (application spec §13.2, §13.4, X-5, X-6).

Free to run: the contract and mapper are pure. The pack's `query.sc` needs a
Joern install to author and verify, and is scaffold-only -- `pack.yaml` records
that rather than implying otherwise.
"""
import sys
from pathlib import Path

from code_analysis import (
    CONTRACT_VERSION,
    Anchor,
    CallFact,
    CheckFact,
    EndpointFact,
    ExtractionReport,
    LayerNotImplemented,
    MemberFact,
    MethodFact,
    OutcomeFact,
    map_report,
    plan_transitions,
    validate_report,
    verify_fields,
)

COMMIT = "a3f21c"


def _anchor(file="AuthController.java", line=42, commit=COMMIT):
    return Anchor(file=file, line=line, commit=commit)


def _report(**overrides) -> ExtractionReport:
    report = ExtractionReport(
        pack="jvm-structural", pack_version="0.1.0",
        engine="joern", engine_version="4.0.604",
        repo="athena-boot-git", commit=COMMIT, frontend="javasrc2cpg",
        layers=(1, 2, 3),
        methods=[
            MethodFact("m1", "login", "AuthController", "(String,String):Response", _anchor()),
            MethodFact("m2", "validate", "Validator", "(String):boolean",
                       _anchor("Validator.java", 10)),
        ],
        calls=[CallFact("m1", "m2", _anchor(line=45))],
        endpoints=[EndpointFact("e1", "POST", "/auth/login", "m1", _anchor(line=40))],
        members=[
            MemberFact("LoginRequest", "username", "java.lang.String",
                       _anchor("LoginRequest.java", 5)),
            MemberFact("LoginRequest", "password", "java.lang.String",
                       _anchor("LoginRequest.java", 6)),
        ],
        checks=[
            CheckFact("c1", "authenticated", 1, _anchor(line=20), "authentication"),
            CheckFact("c2", "hasRole('USER')", 2, _anchor(line=25), "authorization"),
        ],
        outcomes=[
            OutcomeFact("o1", "e1", "401/UNAUTHENTICATED", 401, "UNAUTHENTICATED", ("c1",)),
        ],
    )
    for key, value in overrides.items():
        setattr(report, key, value)
    return report


# --------------------------------------------------------------------------
# X-5 : a partial parse fails the run
# --------------------------------------------------------------------------

def test_valid_report_passes():
    assert validate_report(_report()) == []


def test_partial_parse_is_refused():
    """Under-reporting is indistinguishable from clean code — the worst failure."""
    errors = validate_report(_report(partial=True))
    assert any("partial parse" in e for e in errors)


def test_parse_errors_refuse_even_without_the_partial_flag():
    errors = validate_report(_report(parse_errors=["Foo.java: syntax error"]))
    assert any("partial parse" in e for e in errors)


def test_missing_provenance_is_refused():
    for field_name in ("pack", "engine_version", "repo", "commit", "frontend"):
        errors = validate_report(_report(**{field_name: ""}))
        assert any(field_name in e for e in errors), f"{field_name} should be required"


def test_unknown_contract_version_is_refused():
    errors = validate_report(_report(contract_version="metis.cpg-extract/99"))
    assert any("contract version" in e for e in errors)


# --------------------------------------------------------------------------
# X-6 / REQ-CGA-010 : anchors, and no external stubs
# --------------------------------------------------------------------------

def test_external_method_must_be_filtered_in_the_pack():
    report = _report()
    report.methods.append(
        MethodFact("ext", "println", "java.io.PrintStream", "(String):void",
                   _anchor("PrintStream.java", 1), is_external=True))
    errors = validate_report(report)
    assert any("external methods must be filtered" in e for e in errors)


def test_anchor_from_a_different_commit_is_refused():
    report = _report()
    report.methods[0] = MethodFact("m1", "login", "AuthController", "()",
                                   _anchor(commit="deadbeef"))
    errors = validate_report(report)
    assert any("different commit" in e for e in errors)


def test_call_to_an_unemitted_method_is_refused():
    report = _report()
    report.calls.append(CallFact("m1", "ghost", _anchor()))
    assert any("not an emitted method" in e for e in validate_report(report))


def test_endpoint_handler_must_be_an_emitted_method():
    report = _report()
    report.endpoints.append(EndpointFact("e2", "GET", "/x", "ghost", _anchor()))
    assert any("handler" in e for e in validate_report(report))


# --------------------------------------------------------------------------
# GD-9 : precedence must be unambiguous, or fail closed
# --------------------------------------------------------------------------

def test_duplicate_check_order_is_refused():
    """Spec GD-9: never guess an evaluation order."""
    report = _report()
    report.checks.append(CheckFact("c3", "valid(body)", 1, _anchor(), "validation"))
    errors = validate_report(report)
    assert any("precedence would be ambiguous" in e for e in errors)


def test_outcome_guard_must_reference_an_emitted_check():
    report = _report()
    report.outcomes.append(OutcomeFact("o2", "e1", "403/FORBIDDEN", 403, "FORBIDDEN", ("cX",)))
    assert any("guard check" in e for e in validate_report(report))


# --------------------------------------------------------------------------
# Mapping onto the ontology
# --------------------------------------------------------------------------

def test_map_produces_endpoints_and_registry():
    mapped = map_report(_report())
    assert mapped.is_usable, mapped.errors
    assert mapped.endpoints[0]["path"] == "/auth/login"
    assert mapped.endpoints[0]["anchor"].endswith(f"@{COMMIT}")
    assert set(mapped.registry["LoginRequest"].fields) == {"username", "password"}


def test_invalid_report_is_not_partially_consumed():
    mapped = map_report(_report(partial=True))
    assert not mapped.is_usable
    assert mapped.endpoints == [] and mapped.registry == {}


def test_absent_endpoints_are_reported_as_a_config_problem():
    """Spec X-4: an unrecognised framework is reported, never guessed."""
    mapped = map_report(_report(endpoints=[]))
    assert mapped.is_usable
    assert any("framework configuration" in n for n in mapped.notes)


# --------------------------------------------------------------------------
# REQ-TST-008 : the registry gate fails closed
# --------------------------------------------------------------------------

def test_verified_fields_pass():
    mapped = map_report(_report())
    ok, unverified = verify_fields(mapped, "LoginRequest", ["username", "password"])
    assert ok and unverified == []


def test_unverified_field_fails_the_gate():
    mapped = map_report(_report())
    ok, unverified = verify_fields(mapped, "LoginRequest", ["username", "captcha"])
    assert not ok and unverified == ["captcha"]


def test_unknown_type_fails_closed():
    """An unknown type is not evidence that its fields exist."""
    mapped = map_report(_report())
    ok, unverified = verify_fields(mapped, "GhostRequest", ["anything"])
    assert not ok and unverified == ["anything"]


# --------------------------------------------------------------------------
# §13 scope banner : Layer 4 is deferred, loudly
# --------------------------------------------------------------------------

def test_layer_4_raises_rather_than_returning_nothing():
    """An empty result would read as 'no behaviour found' — the ambiguity that
    let R4 be dropped once already."""
    try:
        plan_transitions(_report())
    except LayerNotImplemented as e:
        assert "not built yet" in str(e)
        assert "Analysis unit sufficient" in str(e), (
            "the failure must report whether guards would even be recoverable"
        )
        return
    raise AssertionError("Layer 4 must raise, not return an empty result")


def test_analysis_unit_detects_an_unresolved_cross_module_call():
    """Measured against the real pilot target: extracting one module left the
    response helper unresolved, so the guard selecting 200 from 204 was invisible."""
    from code_analysis.mapper import analysis_unit_is_sufficient
    report = _report()
    sufficient, reason = analysis_unit_is_sufficient(report)
    assert sufficient and reason == ""

    report.calls.append(CallFact("m1", "org.other.Utils.okOrNoContent", _anchor()))
    sufficient, reason = analysis_unit_is_sufficient(report)
    assert not sufficient
    assert "multi-module build" in reason, (
        "the warning must say what to do, not merely that something is missing"
    )


# --------------------------------------------------------------------------
# Pack manifest
# --------------------------------------------------------------------------

def test_pack_manifest_pins_the_engine_and_records_verification():
    """Spec X-3: the engine version is pinned per pack, not ranged.

    The manifest must also record what the pack was actually run against. A pack
    claiming to work without saying against what is the same unearned confidence
    the rest of this specification exists to prevent.
    """
    manifest = Path("code_analysis/packs/jvm-structural/pack.yaml").read_text()
    assert f"contract: {CONTRACT_VERSION}" in manifest
    assert 'version: "4.0.604"' in manifest, "spec X-3 requires a pinned engine version"
    assert "verified_against:" in manifest, "a working pack must say what it was run against"
    assert "known_limits:" in manifest, "limits are recorded, not discovered later"


def test_query_pack_exists_and_filters_external_methods():
    """REQ-CGA-010 is enforced in the pack, at the source of the data."""
    query = Path("code_analysis/packs/jvm-structural/query.sc").read_text()
    assert "isExternal(false)" in query, (
        "external methods must be filtered in the pack, never emitted as stubs"
    )
    assert "__unresolved__" in query, (
        "an unresolvable route must be marked, never guessed (spec T-9d)"
    )
    assert "partial" in query, "the pack must report unparsed files so X-5 can refuse"


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
