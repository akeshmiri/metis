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
        repo="archive-service", commit=COMMIT, frontend="javasrc2cpg",
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


def test_the_schema_role_carries_documentation_and_two_facts_that_are_not():
    """springdoc's `@Schema`, through the annotation table's `schema` role.

    71 of these in one service and not one read: `Class.description` was null on
    every node while the text sat in the source. Two of the fields are not
    documentation at all — `required` and `allowed_values` are test-design
    inputs, because an enum's values ARE its equivalence partitions.
    """
    from code_analysis.contract import MemberFact

    member = MemberFact(
        type_name="RecordDto", name="channel", type_full_name="java.lang.String",
        anchor=None, description="Delivery channel", required="true",
        allowed_values=("SMS", "VOICE"), owner_description="An RECORDS request")
    assert member.description == "Delivery channel"
    assert member.allowed_values == ("SMS", "VOICE")


def test_required_keeps_three_answers_not_two():
    """"Not stated" and "stated optional" are different facts about a payload.

    A boolean would collapse them, and a fixture built from the collapse would
    omit a field the API in fact requires.
    """
    from code_analysis.contract import MemberFact

    for raw, meaning in (("true", "stated required"), ("false", "stated optional"),
                         ("", "not stated")):
        m = MemberFact(type_name="T", name="f", type_full_name="java.lang.String",
                       anchor=None, required=raw)
        assert m.required == raw, meaning


def test_only_present_schema_facts_are_written():
    """An empty description stored as "" is a property every reader must test
    for. Absent says the same thing once."""
    from metis_mcp.model_sources.raw_landing import _present

    assert _present(description="x", required="") == {"description": "x"}
    assert _present(description="", required="") == {}


# --------------------------------------------------------------------------
# The manifests themselves
# --------------------------------------------------------------------------

def test_every_pack_manifest_is_valid_yaml_and_declares_its_pin():
    """**`react-ui/pack.yaml` was not valid YAML and nothing noticed** — a
    `known_limits` entry contained `\\'` inside a double-quoted scalar, which is an
    illegal escape. It went unseen because nothing parses these files: X-3's pin
    is read with a text scan, so a manifest can say anything at all and still
    appear to work. A file whose job is to record a claim has to be readable.
    """
    import yaml

    manifests = sorted(Path("code_analysis/packs").glob("*/pack.yaml"))
    assert len(manifests) == 5, "every pack carries one (X-3 pins per pack)"
    for path in manifests:
        data = yaml.safe_load(path.read_text())
        assert data["engine"]["version"], path
        assert data["status"] in {"working", "unwired", "scaffold"}, path
        assert data.get("verified_against"), f"{path}: an unverified pack claims nothing"


def test_no_manifest_names_a_private_repository():
    """A pack's claim has to be re-checkable by whoever reads it. Five manifests
    named five repositories a customer will never have, so every correctness claim
    in the extraction layer was unfalsifiable prose."""
    import yaml

    for path in sorted(Path("code_analysis/packs").glob("*/pack.yaml")):
        blob = yaml.safe_load(path.read_text())
        verified = str(blob.get("verified_against", ""))
        assert "demo_project" in verified, (
            f"{path}: verified_against must name the checked-in corpus")


# --------------------------------------------------------------------------
# Preflight diagnoses the environment, rather than blaming the install
#
# Both conditions below were met on a clean macOS box and both were reported as
# "check the install" -- the same shape as the test-inventory diagnosis that
# blamed unresolved dependencies and pointed at `--fetch-dependencies`, which
# would not have helped. Free to run: the parsing is pure.
# --------------------------------------------------------------------------

def test_the_launcher_names_the_tool_it_cannot_find():
    """Joern's macOS launcher shells out to `greadlink` (GNU coreutils). Without
    it `$(greadlink -f "$0")` is empty, `dirname ""` is `.`, and the launcher
    only works when the working directory IS joern-cli -- which surfaces as
    "version unreadable"."""
    from code_analysis.engine import launcher_fix, missing_launcher_tool

    stderr = "/Users/x/joern/joern-cli/joern: line 4: greadlink: command not found\n"
    assert missing_launcher_tool(stderr) == "greadlink"
    fix = launcher_fix(stderr)
    assert "greadlink" in fix and "brew install coreutils" in fix


def test_an_unexplained_probe_falls_back_rather_than_inventing_a_cause():
    """A wrong cause costs more than no cause. When stderr says nothing usable,
    the message must not name a tool."""
    from code_analysis.engine import launcher_fix, missing_launcher_tool

    assert missing_launcher_tool("") == ""
    assert missing_launcher_tool("some unrelated warning") == ""
    assert "check the install" in launcher_fix("some unrelated warning")


def test_a_shipped_astgen_under_the_wrong_name_is_a_mismatch_not_a_missing_install(
        tmp_path):
    """4.0.604's macOS-arm build ships `astgen-macos-arm`; `jssrc2cpg` looks for
    `astgen-macos`. Every JS pack then fails with "Local astgen binary not
    found", which reads like a broken install and is a naming mismatch. The
    check has to say which, and give the one-line repair."""
    from code_analysis.engine import astgen_check, astgen_expected_name

    directory = tmp_path / "frontends" / "jssrc2cpg" / "bin" / "astgen"
    directory.mkdir(parents=True)
    (directory / (astgen_expected_name() + "-arm")).write_text("binary")

    check = astgen_check(tmp_path)
    assert not check.ok
    assert astgen_expected_name() in check.detail
    assert "mismatch" in check.fix and "ln -s" in check.fix


def test_a_present_astgen_passes():
    from code_analysis.engine import astgen_check, astgen_expected_name
    import pathlib, tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        directory = root / "frontends" / "jssrc2cpg" / "bin" / "astgen"
        directory.mkdir(parents=True)
        (directory / astgen_expected_name()).write_text("binary")
        assert astgen_check(root).ok


def test_no_engine_is_reported_as_no_engine_not_as_a_missing_astgen():
    """Ordering matters in a preflight: the first true cause is the useful one."""
    from code_analysis.engine import astgen_check

    check = astgen_check(None)
    assert not check.ok and "no engine" in check.detail


# --------------------------------------------------------------------------
# Incremental review: which recovered behaviour a commit range could have moved
# --------------------------------------------------------------------------

def test_changed_files_are_relative_to_the_analysed_directory():
    """The path form has to match `Anchor.file`, or nothing lines up.

    `git -C <dir> diff --name-only` prints paths from the REPOSITORY root, so a
    service inside a monorepo comes back as `services/records/src/...` while its
    anchors say `src/...`. Every comparison then misses, `impact` reports nothing
    touched, and "no behaviour at risk" is indistinguishable from "the two sides
    never spoke the same language". `--relative` is what makes them agree.

    Asserted against this repository, which is itself a subdirectory of a git
    root — so the bug this guards against is reproducible here.
    """
    from code_analysis.engine import changed_files

    changed = changed_files(".", "HEAD~1")
    assert changed, "expected some change in the last commit"
    assert not [p for p in changed if p.startswith("metis-server/")], (
        "paths came back relative to the repository root, not to the analysed "
        "directory — they will not match any anchor")


def test_an_unanswerable_range_is_empty_rather_than_an_exception():
    """A missing commit, a shallow clone and a directory that is not a
    repository are all "I cannot tell you what changed".

    Empty rather than raising, matching `head_commit` — but the caller has to
    understand that this is NOT the same claim as "nothing changed". It is why
    the range is the caller's to choose.
    """
    from code_analysis.engine import changed_files

    assert changed_files(".", "not-a-real-commit") == []
    assert changed_files("/tmp", "HEAD~1") == []
    assert changed_files(".", "   ") == []
    assert changed_files(".", "HEAD", "HEAD") == []


def test_the_output_is_sorted_and_deduplicated():
    """It feeds `impact`, whose answer should not depend on git's ordering."""
    from code_analysis.engine import changed_files

    changed = changed_files(".", "HEAD~1")
    assert changed == sorted(set(changed))
