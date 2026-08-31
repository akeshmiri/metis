"""
The intake declaration, checked against the code (spec §5.0, X-7a).

**This file is the difference between a declaration and a fiction.** Seven
manifests sit beside `intakes.json` describing sources Métis was designed to
ingest, against an `athena_internal_read` protocol and entity types the current
ontology does not have. Nothing ever loaded them, so nothing ever noticed.

So every claim in the new declaration is checked against something that would
break: the registered sources, the intake anchors, the label catalogue, and the
modules it names.

Free to run: reading a description of what may be read is not a read of anything.
"""
from __future__ import annotations

import importlib
import pathlib
import json
from pathlib import Path

import pytest

from metis_mcp import intakes
from metis_mcp.ontology.labels import KNOWN_LABELS, STAGED_OUT

SCHEMA = Path(__file__).resolve().parents[1] / "connectors" / "metis-intake-schema.json"


@pytest.fixture(scope="module")
def declared():
    return intakes.all_intakes()


# --------------------------------------------------------------------------
# X-7a — the rule the whole file exists for
# --------------------------------------------------------------------------

def test_no_intake_executes_against_the_system_under_test(declared):
    """Métis reads intake sources and writes its own graph. It does not call the
    API it models, drive the UI it models, or query the database it models.

    A database Métis reads is an intake source; the same database reached to
    check a test's outcome is the SUT. Same server, different act.
    """
    for intake in declared:
        assert intake["executes_against_sut"] is False, intake["id"]


def test_the_loader_refuses_a_declaration_that_claims_otherwise(tmp_path):
    """A constant in a schema is only a guarantee if something enforces it."""
    bad = tmp_path / "intakes.json"
    bad.write_text(json.dumps({
        "intake_version": intakes.INTAKES_VERSION,
        "intakes": [{"id": "rogue", "reads": "x", "access": "local_files",
                     "executes_against_sut": True, "produces": ["y"],
                     "lands": [], "status": "declared"}]}))
    intakes.load.cache_clear()
    with pytest.raises(intakes.IntakesRefused) as e:
        intakes.load(bad)
    assert "X-7a" in str(e.value)
    intakes.load.cache_clear()


def test_every_access_mode_is_read_only(declared):
    """There is deliberately no mode meaning "runs something". Adding one is the
    change that would need arguing for, and its absence is what makes the
    prohibition structural rather than remembered."""
    assert {i["access"] for i in declared} <= set(intakes.ACCESS_MODES)


def test_an_unknown_access_mode_is_refused(tmp_path):
    bad = tmp_path / "intakes.json"
    bad.write_text(json.dumps({
        "intake_version": intakes.INTAKES_VERSION,
        "intakes": [{"id": "rogue", "reads": "x", "access": "shell_command",
                     "executes_against_sut": False, "produces": ["y"],
                     "lands": [], "status": "declared"}]}))
    intakes.load.cache_clear()
    with pytest.raises(intakes.IntakesRefused) as e:
        intakes.load(bad)
    assert "read-only" in str(e.value)
    intakes.load.cache_clear()


# --------------------------------------------------------------------------
# The declaration must describe the code, not a plan
# --------------------------------------------------------------------------

def test_every_label_an_intake_claims_to_land_is_in_the_catalogue(declared):
    """The v1 manifests name `Repository`, which is staged out. A declaration
    against labels that do not exist is how one stops describing anything."""
    for intake in declared:
        for label in intake.get("lands", ()):
            assert label in KNOWN_LABELS, f"{intake['id']} lands {label!r}"
            assert label not in STAGED_OUT, (
                f"{intake['id']} lands {label!r}, which is staged out")


def test_every_reader_a_working_intake_names_can_be_imported(declared):
    """`status: working` is a claim that a reader exists. Naming a module that
    does not import is the cheapest possible way for that claim to be false."""
    for intake in declared:
        if intake["status"] == intakes.DECLARED:
            continue
        for module in intake["reader"].split(","):
            module = module.strip().replace("-", "_")
            if ".packs." in module:
                # A query pack is Scala, not a module — check the file instead.
                pack = module.rsplit(".", 1)[-1].replace("_", "-")
                assert (Path("code_analysis/packs") / pack / "query.sc").exists(), \
                    f"{intake['id']} names pack {pack!r}"
                continue
            importlib.import_module(module)


def test_a_registered_source_and_a_declared_intake_agree(declared):
    """A source the engine can run and no intake describes is a capability
    nobody can find; an intake naming a source that does not exist is the
    reverse. Both are the drift this test exists to catch."""
    from metis_mcp.model_sources import registered

    ids = {i["id"] for i in declared}
    for source in registered():
        assert source in ids, (
            f"`{source}` is a registered model source and no intake declares it")


def test_the_catalogue_reader_is_importable_without_any_driver():
    """The property that matters more than convenience: a suite that needs a
    database is a suite people stop running. No `psycopg`, no `oracledb`, no
    `mysqlclient` — and the module still imports and still reads a fixture."""
    import importlib
    import sys

    assert not {m for m in sys.modules if m.startswith(
        ("psycopg", "oracledb", "cx_Oracle", "MySQLdb", "pymysql"))}
    importlib.import_module("code_analysis.db_catalogue")


def test_a_partial_intake_names_what_it_does_not_recover(declared):
    """`partial` without `limits` is `working` with better manners."""
    for intake in declared:
        if intake["status"] == intakes.PARTIAL:
            assert intake.get("limits"), intake["id"]


def test_the_web_intake_records_that_a_selector_comes_from_code(declared):
    """It was briefly going to be authored, and that was the wrong source. The
    declaration carries the correction so the next person does not repeat it."""
    web = intakes.get("web")
    assert any("selector" in limit for limit in web["limits"])
    # The `structure` intake was the other half of this pair and went with the UI
    # structure layer. What the correction was ABOUT still holds: a selector is
    # recovered, never authored, and `web` is where that is declared.


# --------------------------------------------------------------------------
# The declaration validates against its own schema
# --------------------------------------------------------------------------

def test_the_declaration_satisfies_the_schema(declared):
    """Skipped rather than faked when `jsonschema` is absent: a validation that
    silently does not run is worse than one that says it did not."""
    jsonschema = pytest.importorskip("jsonschema")

    schema = json.loads(SCHEMA.read_text())
    jsonschema.validate(intakes.load(), schema)


def test_the_schema_forbids_executing_against_the_sut_structurally():
    """Not a convention — a `const` the validator rejects."""
    schema = json.loads(SCHEMA.read_text())
    prop = schema["$defs"]["intake"]["properties"]["executes_against_sut"]
    assert prop["const"] is False
    assert "executes_against_sut" in schema["$defs"]["intake"]["required"]


def test_the_capability_map_states_every_limit_not_just_the_working_parts(declared):
    """`describe()` is what somebody reads to decide what Métis can do for them.

    It asserted the "no reader" line until the database reader existed. Now every
    intake that is not `working` must still appear with its limits, because a map
    that lists only what works is the thing this whole file exists to prevent.
    """
    text = intakes.describe()
    for intake in declared:
        if intake["status"] != intakes.WORKING:
            assert intake["id"] in text, intake["id"]
            assert intake["limits"][0][:40] in text, intake["id"]
    assert "executes anything against the System Under Test" in text


# ---------------------------------------------------------------------------
# UIF conformance — refused at the door, with every reason
# ---------------------------------------------------------------------------

def _uif(**over):
    doc = {"uif_version": "1.0",
           "scope": {"source_system": "jira", "primary_id": "DEMO-1"},
           "metadata": {"title": "When a token has expired, the system shall "
                                 "reject the request."}}
    doc.update(over)
    return doc


def test_every_reason_a_document_is_refused_is_reported_at_once():
    """`load` raised on the FIRST problem, so a document with three took three
    round-trips to learn about all of them."""
    from metis_mcp.model_sources.intake_landing import conformance

    outcome = conformance({"uif_version": "9.0",
                           "scope": {"source_system": "notion"},
                           "metadata": {}})
    assert len(outcome.refusals) == 4
    assert not outcome.conformant


def test_an_unknown_source_system_is_caught_at_the_door_not_mid_plan():
    """It used to pass `load` and raise from `anchor_for` in the middle of
    planning — a stack trace where a sentence was wanted."""
    from metis_mcp.model_sources.intake_landing import conformance

    outcome = conformance(_uif(scope={"source_system": "notion",
                                      "primary_id": "N-1"}))
    assert any("no anchor label" in r for r in outcome.refusals)
    assert any("D-2" in r for r in outcome.refusals), "the fix is named"


def test_free_prose_is_an_advisory_and_not_a_refusal():
    """S-13: it lands, as a `Finding` pointing at knowledge-capture. That is
    correct behaviour and the most surprising thing this intake does, so it is
    said at the door rather than discovered by counting nodes afterwards."""
    from metis_mcp.model_sources.intake_landing import conformance

    outcome = conformance(_uif(metadata={"title": "MFA is broken again"}))
    assert outcome.conformant, "prose is legal"
    assert any("not EARS-conformant" in a for a in outcome.advisories)
    assert any("Finding" in a for a in outcome.advisories)


def test_claimed_acceptance_criteria_are_flagged_as_untrusted():
    """A criterion asserted by the document that raised the requirement is not
    independent evidence of it."""
    from metis_mcp.model_sources.intake_landing import conformance

    outcome = conformance(_uif(acceptance_criteria=[{"text": "a"}]))
    assert any("NOT be trusted" in a for a in outcome.advisories)


def test_a_conformant_document_still_loads():
    """The checker must not become a refusal machine."""
    from metis_mcp.model_sources.intake_landing import conformance

    assert conformance(_uif()).conformant
    assert conformance(_uif()).advisories == ()


# ---------------------------------------------------------------------------
# A declared command must exist — "no invoker" becomes a failure
# ---------------------------------------------------------------------------

def _command_is_invokable(command) -> bool:
    """Whether `metis <command> --help` parses.

    Asked by running it rather than by introspecting the parser: argparse exits
    0 for a command it knows and 2 for one it does not, and "the command runs"
    is the claim being made.
    """
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-m", "metis_mcp.mbt.cli", *command, "--help"],
        capture_output=True, text=True, cwd=pathlib.Path(__file__).parent)
    return out.returncode == 0


def test_every_declared_intake_command_is_a_command_the_cli_registers():
    """**This is the check that would have caught the data layer.**

    `data_landing`, `db_catalogue` and the scaffold renderer were built, tested
    and unreachable — no CLI command, no workflow stage — and every field in
    this declaration said the intake was fine. A reader that nothing calls is a
    capability nobody has, and until now no test could tell the difference.
    """
    from metis_mcp import intakes

    missing = []
    for intake in intakes.all_intakes():
        command = intake.get("command") or []
        if command and not _command_is_invokable(command):
            missing.append(f"{intake['id']}: declares `metis "
                           f"{' '.join(command)}` and the CLI has no such "
                           f"command")
    assert not missing, "\n  ".join(missing)


# ---------------------------------------------------------------------------
# The other direction: a pack that exists and no intake declares
# ---------------------------------------------------------------------------

def test_every_query_pack_is_declared_by_some_intake(declared):
    """**The gap that hid `jvm-test-inventory`.**

    `test_a_registered_source_and_a_declared_intake_agree` closes this direction
    for `model_sources`, and nothing closed it for the query packs. So
    `code_analysis/packs/jvm-test-inventory` — a real pack, named by
    `engine.TEST_INVENTORY`, consumed by `metis paths --inventory`, exercised by
    `test_extraction.py` and read by `test_levels.from_pack` — was absent from a
    declaration whose own README opens by claiming to list every kind of thing
    Métis ingests. It was found by comparing against a v1 connector manifest,
    which is not a maintainable way to find it.

    A pack is a reader. If no intake names it, the capability exists and nobody
    looking at the declaration can tell.
    """
    packs = {p.name for p in (pathlib.Path("code_analysis") / "packs").iterdir()
             if p.is_dir() and (p / "pack.yaml").exists()}
    assert packs, "no packs found — the path is wrong, not the declaration"

    readers = " ".join(i.get("reader", "") for i in declared)
    undeclared = sorted(p for p in packs if p not in readers)
    assert not undeclared, (
        "query packs no intake declares: " + ", ".join(undeclared)
        + ". Add them to connectors/intakes.json, or say why in its README.")


def test_the_test_inventory_intake_declares_that_it_lands_nothing(declared):
    """An empty `lands` is a real answer here and needs saying out loud, because
    every other intake writes to the graph. The inventory feeds *generation* —
    `test_levels.from_pack` grades transitions so a case is not proposed for
    behaviour a passing test already proves (REQ-METIS-PG-01)."""
    inventory = next(i for i in declared if i["id"] == "test-inventory")
    assert inventory["lands"] == []
    assert any("lands NOTHING" in limit for limit in inventory["limits"])
    assert any("JVM only" in limit for limit in inventory["limits"]), (
        "the v1 connector covered JUnit/TestNG/pytest/Playwright; this covers one")


# ---------------------------------------------------------------------------
# `lands_from` and `temporal` — taken from v1's manifest schema
# ---------------------------------------------------------------------------

def test_every_source_shape_names_a_label_the_intake_actually_lands(declared):
    """`lands_from` is checkable or it is decoration.

    v1's `entity_type_mapping` carried a `source_shape` for every entity a
    connector wrote — *"Jira issue (Story/Epic)" → Requirement*. v2 kept the
    labels and dropped the shapes, so `lands` says the database intake writes
    `Column` and nothing says a row of `information_schema.columns` is what
    produces one. That is the half a reader needs to know whether their own
    source will produce anything at all.
    """
    wrong = []
    for intake in declared:
        landed = set(intake.get("lands") or ())
        for mapping in intake.get("lands_from") or ():
            if mapping["label"] not in landed:
                wrong.append(f"{intake['id']}: lands_from names "
                             f"{mapping['label']!r}, which is not in `lands`")
    assert not wrong, "\n  ".join(wrong)


def test_a_source_shape_maps_to_a_label_in_the_ontology(declared):
    """The same check `lands` already gets. A shape producing a label the
    ontology does not have is a claim about a node that cannot exist."""
    from metis_mcp.ontology import labels

    for intake in declared:
        for mapping in intake.get("lands_from") or ():
            assert mapping["label"] in labels.LABELS, (
                f"{intake['id']}: {mapping['label']} is not in the ontology")


def test_the_intakes_that_can_say_where_a_timestamp_comes_from_do(declared):
    """Every `Episode` REQUIRES `t_recorded` and nothing recorded where it came
    from. `data_landing` defaults it to `datetime.now()`, so a re-ingest of
    six-month-old code produces a fact dated today.

    This does not fix that. It makes it **stated**, which is the precondition —
    and the database entry says outright that a catalogue read is undated by
    nature rather than implying a real timestamp exists.
    """
    have = {i["id"] for i in declared if i.get("temporal")}
    assert {"code", "openapi", "uif"} <= have


def test_the_temporal_pitfall_is_named_and_not_just_the_happy_path(declared):
    """A source without its failure mode reads as a guarantee. v1's example is
    still exactly right for the code intake, so it is carried over verbatim in
    substance: a squash loses the dates the anchor depends on."""
    code = next(i for i in declared if i["id"] == "code")
    assert "squash" in code["temporal"]["known_pitfalls"]

    # The `database` intake carried the second example — an extraction-time
    # default declared as such rather than as a date — and went with the
    # database layer. Every remaining intake that declares a temporal source
    # must still declare its pitfall, which is the general form of both.
    for intake in declared:
        temporal = intake.get("temporal") or {}
        if temporal.get("t_recorded_source"):
            assert temporal.get("known_pitfalls"), (
                f"{intake['id']} declares where its timestamp comes from and "
                f"not how that goes wrong")


# --------------------------------------------------------------------------
# The reader, the declaration and the CLI must name the same sources
# --------------------------------------------------------------------------
#
# **The drift this catches, which actually happened.** `ANCHORS` mapped
# `confluence -> ConfluenceItem` and a `ConfluenceExtractor` sat in a skill, so
# by every local check Confluence was supported. It was not: `tracker.ENDPOINTS`
# had no path for it, `--system` offered `jira` and `scale`, and `intakes.json`
# declared nothing. Three artefacts each individually consistent, and no way to
# fetch a page.
#
# Joined on the ANCHOR rather than the intake id, because the two deliberately
# differ: the intake is `zephyr` and its `source_system` is `scale`.

def _tracker_intakes(declared):
    return [i for i in declared if i.get("reader") == "code_analysis.tracker"]


def test_every_tracker_the_reader_can_fetch_is_a_declared_intake(declared):
    """A source the reader can reach and no intake declares is a capability
    that exists and cannot be found — `intakes.describe()` is the capability
    map, and a map missing a road is worse than one that admits the gap."""
    from code_analysis import tracker
    from metis_mcp.model_sources.intake_landing import ANCHORS

    anchored = {i["anchor"] for i in _tracker_intakes(declared)}
    for system in sorted(tracker.ENDPOINTS):
        assert system in ANCHORS, (
            f"`tracker.ENDPOINTS` can fetch {system!r} and `ANCHORS` has no "
            f"anchor label for it, so every item would land unattached")
        label = ANCHORS[system][0]
        assert label in anchored, (
            f"`tracker.ENDPOINTS` can fetch {system!r} (anchor {label}) and no "
            f"intake in intakes.json declares it. Add the declaration in the "
            f"same change as the endpoint.")


def test_every_declared_tracker_intake_can_actually_be_fetched(declared):
    """The reverse, and the one that would have failed loudest: an intake
    promising a source the reader cannot reach."""
    from code_analysis import tracker
    from metis_mcp.model_sources.intake_landing import ANCHORS

    fetchable = {ANCHORS[s][0] for s in tracker.ENDPOINTS if s in ANCHORS}
    for intake in _tracker_intakes(declared):
        assert intake["anchor"] in fetchable, (
            f"intake {intake['id']!r} names `code_analysis.tracker` and there "
            f"is no endpoint for its anchor {intake['anchor']!r}")


def test_the_cli_offers_every_source_the_reader_supports():
    """`--system`'s choices are derived from `tracker.ENDPOINTS` rather than
    hand-kept. This pins that they are derived: a literal list here is how a
    source becomes unreachable from the surface that is meant to be the
    fullest one."""
    from code_analysis import tracker
    from metis_mcp.mbt.cli import tracker_systems

    assert tracker_systems() == set(tracker.ENDPOINTS)


def test_these_guards_can_fail():
    """A consistency check that passes because it compares a thing to itself
    proves nothing. Introduce the exact drift and assert each guard catches it."""
    from code_analysis import tracker
    from metis_mcp.model_sources.intake_landing import ANCHORS

    # An endpoint with no anchor, which is the first assertion above.
    assert "nowhere" not in ANCHORS
    anchored = {i["anchor"] for i in _tracker_intakes(intakes.all_intakes())}
    assert anchored, "no intake names the tracker reader; the join is vacuous"

    # An anchor that exists but is declared by no intake — Confluence's exact
    # former state — must not be silently acceptable.
    assert ANCHORS["swagger"][0] not in anchored, (
        "this fixture assumes OpenApiItem is not a tracker intake")


# --------------------------------------------------------------------------
# A refusal must name a flag the command accepts
# --------------------------------------------------------------------------

def test_analyse_accepts_every_flag_its_own_refusals_name():
    """**Advice that cannot be followed is worse than none.**

    `metis analyse` is the one-command front end over `workflow run model-build`,
    and two stages it runs refuse with an instruction:

      extract  "... and no --service was given ... pass --service to scope it"
      validate "To proceed accepting that risk, pass --allow-unverifiable."

    Both flags existed only on `workflow run`, so `analyse` on a multi-module
    repository was a dead end: it printed what to do and rejected it. Worse for
    `--service`, `cmd_analyse` then hardcoded `args.service = ""`, so adding the
    flag alone would have left the refusal identical with the flag supplied.
    """
    import subprocess
    import sys

    help_text = subprocess.run(
        [sys.executable, "-m", "metis_mcp.mbt.cli", "analyse", "--help"],
        capture_output=True, text=True).stdout

    for flag in ("--service", "--allow-unverifiable"):
        assert flag in help_text, (
            f"a stage `analyse` runs tells the reader to pass {flag}, and "
            f"`analyse` does not accept it")


def test_analyse_does_not_discard_the_service_it_was_given():
    """The half a flag alone would not have fixed. `cmd_analyse` set
    `args.service = ""` after parsing, so the value never reached the stage."""
    import inspect

    from metis_mcp.mbt import cli

    source = inspect.getsource(cli.cmd_analyse)
    assert 'args.service = ""' not in source, (
        "the service is being overwritten after it was parsed")
    assert "args.service" in source, "the service must still be threaded through"
