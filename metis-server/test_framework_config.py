"""
Framework configuration tests (application spec RD-6; X-3, X-4, X-10a..X-10d).

Free to run: validation is pure.
"""
import json
import sys
import tempfile
from pathlib import Path

from code_analysis.framework_config import (
    API,
    CONFIG_VERSION,
    DEFAULT_CONFIG,
    UI,
    ConfigInvalid,
    FrameworkUnsupported,
    default,
    format_config,
    load,
    load_file,
)
from metis_mcp.mbt.dimensions import AUTHENTICATION, VALIDATION, classify


def _minimal(**over):
    entry = {"name": "spring-mvc", "language": "java", "surface": API,
             "entry_point_markers": ["GetMapping"], "outcome_markers": ["ResponseEntity.ok"]}
    entry.update(over)
    return {"version": CONFIG_VERSION, "frameworks": [entry]}


# --------------------------------------------------------------------------
# X-4 : support is declared; an unrecognised framework is reported, never guessed
# --------------------------------------------------------------------------

def test_x4_a_declared_framework_resolves():
    config = default()
    assert config.supports("spring-mvc", API)
    assert config.get("spring-mvc").language == "java"


def test_x4_an_undeclared_framework_is_refused_with_the_reason():
    try:
        default().get("react", UI)
    except FrameworkUnsupported as e:
        assert "not a declared framework" in str(e)
        assert "worse than no model" in str(e)
        assert "spring-mvc" in str(e), "it names what IS declared"
        return
    raise AssertionError("X-4: extraction must not be attempted against a guess")


def test_x4_a_framework_declared_for_another_surface_does_not_satisfy_this_one():
    config = default()
    assert not config.supports("spring-mvc", UI)
    try:
        config.get("spring-mvc", UI)
    except FrameworkUnsupported as e:
        assert "'ui' surface" in str(e)
        return
    raise AssertionError("a UI surface needs a UI framework")


def test_the_shipped_config_declares_only_what_has_actually_been_run():
    """Listing an unverified framework would make X-4's support check report
    support that does not exist.

    Both declared frameworks have been run against real code with a real CPG:
    `spring-mvc` against athena-git (javasrc2cpg), `dom-events` against
    atlas-site (jssrc2cpg). The rule enforced here is not the *count* but the
    evidence: every declaration must name what it was verified against.
    """
    config = default()
    assert {f.name for f in config.frameworks} == {"spring-mvc", "dom-events"}
    for framework in config.frameworks:
        assert "Verified against" in framework.notes, framework.name
        assert framework.pack, f"{framework.name} names no query pack"


def test_both_surfaces_are_now_declared():
    """M-2's two surfaces each have a verified extraction path."""
    config = default()
    assert config.supports("spring-mvc", API)
    assert config.supports("dom-events", UI)


def test_an_unverified_framework_is_still_refused():
    config = default()
    try:
        config.get("react", UI)
    except FrameworkUnsupported as e:
        assert "dom-events" in str(e), "it names the UI framework that IS declared"
        return
    raise AssertionError("declaring one UI framework does not imply support for all")


# --------------------------------------------------------------------------
# A silently-empty config is the failure mode this validation prevents
# --------------------------------------------------------------------------

def test_a_framework_with_no_entry_point_markers_is_rejected():
    try:
        load(_minimal(entry_point_markers=[]))
    except ConfigInvalid as e:
        assert "indistinguishable from a clean codebase" in str(e)
        return
    raise AssertionError("it would pass the support check and recover nothing")


def test_a_framework_with_no_outcome_markers_is_rejected():
    try:
        load(_minimal(outcome_markers=[]))
    except ConfigInvalid as e:
        assert "no target state" in str(e)
        return
    raise AssertionError("triggers with no recoverable outcome are not transitions")


def test_an_unknown_surface_is_rejected():
    try:
        load(_minimal(surface="cli"))
    except ConfigInvalid as e:
        assert "not one of" in str(e)
        return
    raise AssertionError("only api and ui exist (M-2)")


def test_a_duplicate_declaration_is_rejected_rather_than_resolved_by_file_order():
    data = _minimal()
    data["frameworks"].append(dict(data["frameworks"][0]))
    try:
        load(data)
    except ConfigInvalid as e:
        assert "accident of file order" in str(e)
        return
    raise AssertionError("which one wins must not be an accident")


# --------------------------------------------------------------------------
# X-10a / X-10d : configuration classifies; it never orders
# --------------------------------------------------------------------------

def test_x10a_a_dimension_class_may_not_declare_an_order():
    data = _minimal()
    data["dimension_classes"] = [
        {"class": "authentication", "matches": ["isauthenticated"], "order": 1}]
    try:
        load(data)
    except ConfigInvalid as e:
        assert "never says when it runs" in str(e)
        assert "X-10a" in str(e) and "X-10d" in str(e)
        return
    raise AssertionError("config that could set order would let someone assert a "
                         "precedence the code does not have (GD-9)")


def test_x10a_precedence_is_refused_under_either_spelling():
    data = _minimal()
    data["dimension_classes"] = [
        {"class": "authorization", "matches": ["hasrole"], "precedence": 2}]
    try:
        load(data)
    except ConfigInvalid:
        return
    raise AssertionError("'precedence' is the same claim as 'order'")


def test_a_class_with_no_patterns_is_rejected():
    """An empty class silently leaves every check unclassified while appearing
    to be configured."""
    data = _minimal()
    data["dimension_classes"] = [{"class": "business", "matches": []}]
    try:
        load(data)
    except ConfigInvalid as e:
        assert "never classify anything" in str(e)
        return
    raise AssertionError("an empty class must be rejected")


def test_duplicate_class_names_are_rejected():
    data = _minimal()
    data["dimension_classes"] = [
        {"class": "authentication", "matches": ["a"]},
        {"class": "authentication", "matches": ["b"]}]
    try:
        load(data)
    except ConfigInvalid as e:
        assert "duplicate" in str(e)
        return
    raise AssertionError("two classes with one name is ambiguous")


# --------------------------------------------------------------------------
# X-10b : the classes actually drive classification
# --------------------------------------------------------------------------

def test_x10b_the_configured_classes_classify_real_checks():
    classes = default().classes()
    assert classify("isAuthenticated()", classes) == AUTHENTICATION
    assert classify("payload.isValid()", classes) == VALIDATION


def test_x10c_an_unmatched_check_stays_unclassified():
    assert classify("account.balance > threshold", default().classes()) is None


def test_cross_cutting_defaults_from_the_class_name_but_can_be_overridden():
    data = _minimal()
    data["dimension_classes"] = [
        {"class": "authentication", "matches": ["x"]},                 # implied True
        {"class": "business", "matches": ["y"], "cross_cutting": True}]
    config = load(data)
    by_name = {c.name: c for c in config.classes()}
    assert by_name["authentication"].cross_cutting
    assert by_name["business"].cross_cutting, "explicit wins"


# --------------------------------------------------------------------------
# X-3 : the engine and its config are pinned together
# --------------------------------------------------------------------------

def test_x3_a_config_from_another_version_is_not_assumed_compatible():
    try:
        load({"version": "metis.framework-config/99", "frameworks": []})
    except ConfigInvalid as e:
        assert "pinned and versioned together" in str(e)
        return
    raise AssertionError("an unknown version must be refused")


# --------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------

def test_a_missing_file_says_there_is_no_default():
    try:
        load_file("/nonexistent/framework-config.json")
    except ConfigInvalid as e:
        assert "no default" in str(e)
        assert "guessing a framework" in str(e)
        return
    raise AssertionError("a default config would mean guessing a framework")


def test_the_shipped_config_round_trips_through_a_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "framework-config.json"
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
        config = load_file(path)
    assert config.supports("spring-mvc", API)
    assert len(config.classes()) == 3


def test_the_report_states_that_anything_unlisted_is_unsupported():
    text = format_config(default())
    assert "spring-mvc" in text
    assert "UNSUPPORTED" in text
    assert "order is a code fact" in text


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
