"""
The package's shape, checked against what the packaging and CI claim about it.

**Why this file exists.** Two claims about this tree were made in prose and
checked by nothing, and both were wrong at the same time:

  * `pyproject.toml` says *"`test_structure.py` now checks the entry point
    resolves"*. There was no `test_structure.py`. The console scripts were
    declared and nothing asserted they import.

  * `.github/workflows/ci.yml` split the suite into an engine-free job and an
    extraction job, and named the engine-dependent files in both — deliberately,
    so that adding one is a visible edit rather than a test that quietly stops
    running. Naming them turned out to be necessary and not sufficient. Both
    lists carried `test_data_layer.py` and `test_data_cli.py` for long after the
    engine rebuild deleted them, and the two jobs failed in opposite directions:

        engine-free   `--ignore` on a path that does not exist is IGNORED,
                      in silence. The job stayed green.
        extraction    a positional path that does not exist is `exit 4`.
                      The job ran NOTHING, for every commit.

    So the five query packs lost their only behavioural test, and the signal
    that they had was a job failing for a reason that looked like an
    infrastructure problem.

The rule both of those break is the one in CLAUDE.md: prefer a check that can
fail. A file list duplicated in two places is drift waiting to happen unless
something compares it to the filesystem.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

# The two steps that between them must account for every test file. Keyed by the
# step's `name:` because that is what a reader of the workflow sees, and matched
# exactly -- a renamed step should fail this loudly rather than silently drop the
# half of the suite it was running.
ENGINE_FREE_STEP = "Test suite (engine-free half)"
EXTRACTION_STEP = "Extraction suite"

_TEST_FILE = re.compile(r"\btest_[A-Za-z0-9_]+\.py\b")

CONFTEST = HERE / "conftest.py"
_FIXTURE = re.compile(
    r"@pytest\.fixture[^\n]*\)?\s*\ndef\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE)


def _engine_fixtures() -> set[str]:
    """Conftest fixtures that build a CPG, directly or through another one.

    Derived rather than listed. A hand-maintained set here would be a third copy
    of the same fact -- after the two CI lists -- and would drift for the same
    reason they did.
    """
    text = CONFTEST.read_text()
    fixtures = {name: [p.strip() for p in params.split(",") if p.strip()]
                for name, params in _FIXTURE.findall(text)}

    # The roots: a fixture whose own body calls `engine.extract`.
    roots = set()
    for name in fixtures:
        body = text.split(f"def {name}(", 1)[1]
        # Up to the next fixture definition, so a later fixture's call does not
        # attribute itself to this one.
        body = re.split(r"\n@pytest\.fixture", body, maxsplit=1)[0]
        if "engine.extract(" in body:
            roots.add(name)

    engine_dependent = set(roots)
    changed = True
    while changed:                       # transitive closure over fixture params
        changed = False
        for name, params in fixtures.items():
            if name not in engine_dependent and engine_dependent.intersection(params):
                engine_dependent.add(name)
                changed = True
    return engine_dependent


_TEST_SIGNATURE = re.compile(r"^def\s+(test_\w+)\s*\(([^)]*)\)", re.MULTILINE)


def _files_needing_the_engine() -> set[str]:
    """Test files that REQUEST a CPG-building fixture.

    Parsed from test signatures, not from mentions anywhere in the file. This
    file names `demo_api` and `demo_structural` in its own guard assertions and
    builds no CPG; a substring scan read that as a dependency and demanded
    Joern to run a YAML parser.
    """
    engine_fixtures = _engine_fixtures()
    needing = set()
    for path in HERE.glob("test_*.py"):
        for _, params in _TEST_SIGNATURE.findall(path.read_text()):
            requested = {p.split(":")[0].split("=")[0].strip()
                         for p in params.split(",") if p.strip()}
            if requested & engine_fixtures:
                needing.add(path.name)
                break
    return needing


def _steps() -> dict[str, str]:
    """Every `run:` script in the workflow, keyed by its step name."""
    workflow = yaml.safe_load(WORKFLOW.read_text())
    scripts: dict[str, str] = {}
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            name, run = step.get("name"), step.get("run")
            if name and run:
                scripts[name] = run
    return scripts


def _named_in(step: str) -> set[str]:
    scripts = _steps()
    assert step in scripts, (
        f"no step named {step!r} in {WORKFLOW.relative_to(REPO)}. Renaming a step "
        f"is fine; this list has to be updated with it, or the partition below "
        f"stops describing what CI runs."
    )
    return set(_TEST_FILE.findall(scripts[step]))


def _test_files() -> set[str]:
    return {p.name for p in HERE.glob("test_*.py")}


def test_every_test_file_runs_in_exactly_one_ci_job():
    """The two CI lists name the same files, they all exist, and they are exactly
    the files that build a CPG.

    The same names appear in both steps on purpose -- the engine-free job defers
    what the extraction job runs. So the invariant is not "no overlap", it is
    "the two lists are equal, and equal to what the fixtures say needs an
    engine". Reported as four separate failures because they need four different
    fixes and one combined message would hide which happened.
    """
    on_disk = _test_files()
    deferred = _named_in(ENGINE_FREE_STEP)      # named as `--ignore=...`
    extraction = _named_in(EXTRACTION_STEP)     # named as positional paths

    ghosts_in_ignore = sorted(deferred - on_disk)
    assert not ghosts_in_ignore, (
        f"{ENGINE_FREE_STEP!r} ignores files that do not exist: "
        f"{ghosts_in_ignore}. Harmless to that job -- pytest skips a missing "
        f"--ignore path in silence -- which is exactly why it goes unnoticed."
    )

    ghosts_in_extraction = sorted(extraction - on_disk)
    assert not ghosts_in_extraction, (
        f"{EXTRACTION_STEP!r} names files that do not exist: "
        f"{ghosts_in_extraction}. pytest exits 4 on a missing positional path, "
        f"so that job runs NOTHING until this is fixed."
    )

    assert deferred == extraction, (
        f"the two CI lists disagree. Deferred but not run: "
        f"{sorted(deferred - extraction)}; run but not deferred: "
        f"{sorted(extraction - deferred)}. Whatever the engine-free job skips "
        f"is exactly what the extraction job must pick up."
    )

    needs_engine = _files_needing_the_engine()
    assert extraction == needs_engine, (
        f"CI runs {sorted(extraction)} in the extraction job; the conftest "
        f"fixtures say the engine-dependent files are {sorted(needs_engine)}.\n"
        f"  unnamed but needs a CPG: {sorted(needs_engine - extraction)} "
        f"-- these run in the engine-free job, where conftest FAILS rather "
        f"than skips without Joern.\n"
        f"  named but needs no CPG: {sorted(extraction - needs_engine)} "
        f"-- these are deferred behind a 1.8GB download for no reason."
    )


def test_the_partition_check_can_actually_fail():
    """Guarding the guard.

    Either regex silently matching nothing would make every assertion above pass
    forever, which is the same shape as the bug this file exists to catch: a
    check whose pattern finds nothing proves nothing.
    """
    deferred = _named_in(ENGINE_FREE_STEP)
    extraction = _named_in(EXTRACTION_STEP)
    on_disk = _test_files()

    assert deferred, f"parsed no --ignore names out of {ENGINE_FREE_STEP!r}"
    assert extraction, f"parsed no test files out of {EXTRACTION_STEP!r}"
    assert deferred <= on_disk and extraction <= on_disk
    assert len(on_disk) > len(extraction), (
        "the extraction job claims to run every test file; it runs the "
        "engine-dependent subset"
    )

    # The fixture parser is the newer half and the easier one to get wrong: it
    # reads conftest with a regex, and a conftest reformat could quietly empty
    # it. An empty result would agree with an empty extraction list and pass.
    engine_fixtures = _engine_fixtures()
    assert "demo_api" in engine_fixtures, (
        "the conftest fixture parser found no CPG-building root; `demo_api` "
        "calls engine.extract and must be in the closure")
    assert "demo_structural" in engine_fixtures, (
        "the fixture closure is not transitive: `demo_structural` derives from "
        "`demo_api` and is reached by test files that never name `demo_api`")
    assert "demo_profile" not in engine_fixtures, (
        "`demo_profile` reads a JSON file and builds no CPG; a closure that "
        "includes it is matching too broadly")
    assert _files_needing_the_engine(), "no test file was found to need a CPG"


# `[project.scripts]`, which pyproject says this file checks. Both are declared
# in one place and resolving them is two imports, so there is no reason for the
# claim to have gone unbacked for as long as it did.
CONSOLE_SCRIPTS = {
    "metis": ("metis_mcp.mbt.cli", "main"),
    "metis-mcp-server": ("metis_mcp.server", "main"),
}


@pytest.mark.parametrize("script", sorted(CONSOLE_SCRIPTS))
def test_the_declared_console_scripts_resolve(script):
    """Each `[project.scripts]` target imports and is callable.

    The CLI was reachable only as `python -m metis_mcp.mbt.cli` for a long time
    while `engine.py`, `project_profile.py` and the CLI's own help all told
    people to run `metis doctor` -- four commands no install produced.
    """
    import importlib

    module_name, attribute = CONSOLE_SCRIPTS[script]
    module = importlib.import_module(module_name)
    entry = getattr(module, attribute, None)
    assert callable(entry), (
        f"`{script} = \"{module_name}:{attribute}\"` is declared in "
        f"pyproject.toml and {module_name}.{attribute} is not callable"
    )


def test_pyproject_declares_exactly_the_scripts_this_file_checks():
    """The list above may not drift from the packaging it claims to cover."""
    import tomllib

    data = tomllib.loads((HERE / "pyproject.toml").read_text())
    declared = data.get("project", {}).get("scripts", {})
    assert set(declared) == set(CONSOLE_SCRIPTS), (
        f"pyproject declares {sorted(declared)}; this file checks "
        f"{sorted(CONSOLE_SCRIPTS)}. A script nothing resolves is how the CLI "
        f"shipped unreachable."
    )
    for script, (module_name, attribute) in CONSOLE_SCRIPTS.items():
        assert declared[script] == f"{module_name}:{attribute}", (
            f"pyproject points `{script}` at {declared[script]!r}; this file "
            f"checks {module_name}:{attribute}"
        )


# ---------------------------------------------------------------------------
# The CLI's own failure surface
# ---------------------------------------------------------------------------
#
# `main()` caught four exception types and turned each into one actionable line.
# The neo4j driver's exceptions were not among them, so a database that was not
# running -- the single most common failure on a new machine -- came out of all
# forty-five verbs as a thirty-line traceback ending in `ServiceUnavailable`.
#
# The AuthError branch cannot be reached by running the CLI here: refusing a
# credential needs a server to do the refusing. It is exercised directly, which
# is the point of keeping the message a pure function of the exception.


def test_the_driver_exceptions_are_catchable_as_a_tuple():
    """`except _driver_failures()` has to be a tuple of exception classes."""
    from metis_mcp.mbt.cli import _driver_failures

    failures = _driver_failures()
    assert isinstance(failures, tuple) and failures, (
        "the neo4j driver is a hard dependency; this must not be the empty "
        "fallback tuple, which catches nothing")
    assert all(isinstance(f, type) and issubclass(f, BaseException)
               for f in failures)


def test_an_unreachable_database_names_the_repair():
    from neo4j.exceptions import ServiceUnavailable

    from metis_mcp.mbt.cli import _graph_failure_message

    message = _graph_failure_message(
        ServiceUnavailable("Couldn't connect to localhost:7687\nstack noise"))
    assert "Couldn't connect" in message
    assert "stack noise" not in message, "only the first line is the message"
    assert "Start the database" in message


def test_a_refused_credential_names_a_different_repair():
    """Two failures, two repairs. Telling someone to start a database that is
    already running is worse than saying nothing."""
    from neo4j.exceptions import AuthError

    from metis_mcp.mbt.cli import _graph_failure_message

    message = _graph_failure_message(AuthError("The client is unauthorized"))
    assert "METIS_NEO4J_PASSWORD" in message
    assert "Start the database" not in message


def test_an_unexpected_driver_error_still_gets_a_line():
    from neo4j.exceptions import Neo4jError

    from metis_mcp.mbt.cli import _graph_failure_message

    assert "metis doctor" in _graph_failure_message(Neo4jError("something else"))


# ---------------------------------------------------------------------------
# The Helm chart may not configure what nothing reads
# ---------------------------------------------------------------------------
#
# **Fourteen of the sixteen variables the chart set had no reader**, and four of
# the resulting defects each stopped the pod on its own:
#
#   MCP_TRANSPORT       the code reads METIS_MCP_TRANSPORT, so the container
#                       fell back to stdio -- waiting on a stdin nobody was
#                       attached to while publishing a port nothing listened on
#   (no host)           METIS_HTTP_HOST unset binds 127.0.0.1, which inside a
#                       pod is the pod, so the Service reached nothing
#   /healthz            is served by the HTTP API, not by the MCP server, which
#                       404s it -- so the liveness probe failed every time
#   literal password    in a secret volume Kubernetes mounts 0644, which
#                       graph_session refuses outright
#
# None of it was visible, because a variable nothing reads looks exactly like a
# variable something reads. This is the same closed-set discipline the ontology
# has, applied to deployment: the chart may name only variables that have a
# reader in the tree.

CHART = REPO / "metis-chart"

# Variables read by something other than the Python package: the container
# runtime, Kubernetes itself, or a subchart. Each needs its reason, exactly as
# `UNDEFINED_RULE_IDS` does -- an exemption list without reasons stops meaning
# anything.
_NOT_OURS: dict[str, str] = {}

_ENV_NAME = re.compile(r"^\s*-\s*name:\s*\"?([A-Z][A-Z0-9_]{2,})\"?\s*$", re.M)


def _chart_env_names() -> set[str]:
    """Environment variables the chart's own values declare.

    Read from `values.yaml` rather than from a rendered manifest, so this runs
    with no `helm` binary. The subchart's values (`neo4j:`) are excluded by
    reading only the blocks Métis owns.
    """
    text = (CHART / "values.yaml").read_text()
    # Everything before the Neo4j subchart block belongs to Métis; the subchart
    # configures itself and its variable names are its own business.
    metis_half = text.split("\nneo4j:", 1)[0] + text.split("\n# ---- Métis's own components ----", 1)[-1]
    return set(_ENV_NAME.findall(metis_half))


def _names_read_by_the_package() -> set[str]:
    names: set[str] = set()
    pattern = re.compile(r'"([A-Z][A-Z0-9_]{2,})"')
    for path in list((REPO / "metis-server" / "metis_mcp").rglob("*.py")) + \
            list((REPO / "metis-server" / "code_analysis").rglob("*.py")):
        names |= set(pattern.findall(path.read_text()))
    return names


def test_the_chart_configures_nothing_the_code_does_not_read():
    if not CHART.is_dir():
        return  # chart not in this checkout

    declared = _chart_env_names()
    assert declared, "parsed no environment variables out of the chart"

    read = _names_read_by_the_package()
    dead = sorted(n for n in declared if n not in read and n not in _NOT_OURS)
    assert not dead, (
        f"the chart sets {len(dead)} variable(s) no module reads: {dead}.\n"
        f"A variable nothing reads looks exactly like one something reads, "
        f"which is how `MCP_TRANSPORT` sat beside `METIS_MCP_TRANSPORT` and the "
        f"container ran the wrong transport. Delete it, correct the name, or "
        f"add it to _NOT_OURS with the reason something outside this package "
        f"reads it."
    )


def test_the_chart_sets_the_switches_that_decide_what_it_may_do():
    """Left unset, a deployment takes every default silently.

    `off` is the right default for all three and that is exactly why they are
    stated: it should be a choice somebody made, visible in the values file a
    reviewer reads, rather than an accident of omission.
    """
    if not CHART.is_dir():
        return

    declared = _chart_env_names()
    for switch in ("METIS_MCP_WRITE", "METIS_EXECUTE",
                   "METIS_ALLOW_EXTERNAL_WRITES", "METIS_MCP_TRANSPORT",
                   "METIS_HTTP_HOST", "METIS_NEO4J_PASSWORD"):
        assert switch in declared, (
            f"{switch} decides what this deployment may do and the chart never "
            f"sets it")


def test_the_mounted_config_names_a_variable_rather_than_holding_a_secret():
    """PLT-005, at the point the chart got it wrong.

    A literal password in a file Kubernetes mounts 0644 is refused outright by
    `graph_session._password_from_file` — so the chart could not authenticate at
    all. `password_env` removes the question rather than answering it.
    """
    if not CHART.is_dir():
        return

    config = (CHART / "files" / "metis-config.json").read_text()
    assert "password_env" in config
    assert '"password"' not in config, (
        "the mounted config holds a literal password again; a secret volume is "
        "world-readable by default and this file is committed")


def test_the_liveness_probe_does_not_ask_for_an_endpoint_this_process_lacks():
    """`/healthz` is on the HTTP API. `metis-mcp-server` 404s it.

    Verified by running the entrypoint, not by reading it: the probe failed on
    every pod and Kubernetes restarted them in a loop.
    """
    if not CHART.is_dir():
        return

    # The probe block, not the whole file: the comment above it explains the
    # defect by naming `/healthz`, and a raw substring scan read the explanation
    # as the thing it describes. Same mistake as the §8.7 guard, same fix —
    # check the structure, not the prose around it.
    values = yaml.safe_load((CHART / "values.yaml").read_text())
    probe = values["components"]["mcp-server"]["livenessProbe"]
    assert "httpGet" not in probe, (
        f"the chart probes {probe.get('httpGet', {}).get('path')!r} over HTTP. "
        f"`metis-mcp-server` serves /mcp and 404s /healthz, and /mcp itself "
        f"answers 406 without an Accept header — so an HTTP probe is either "
        f"wrong about the path or coupled to a protocol handshake. A tcpSocket "
        f"probe asserts only that the process is listening, which is what "
        f"liveness means.")
    assert "tcpSocket" in probe

# ---------------------------------------------------------------------------
# Stale copies of the package
# ---------------------------------------------------------------------------

#: The distributed packages. A build copies both, so both can go stale.
PACKAGES = ("metis_mcp", "code_analysis")

#: Directories that legitimately hold a second copy and are not ours to police.
NOT_OURS = {".git", ".venv", "node_modules", "site-packages", "__pycache__"}


def shadow_modules(repo: Path) -> list[tuple[Path, Path]]:
    """`(copied module, where the real one would be)` for every copy that has
    outlived its original.

    Content differing is NOT reported: a build directory is a snapshot and is
    expected to lag. What is reported is a module the real package no longer
    has at all, because that file is not a stale copy of anything -- it is a
    deleted module still sitting in the tree under an importable name.
    """
    real = repo / "metis-server"
    found = []
    for package in PACKAGES:
        for shadow in repo.rglob(package):
            if not shadow.is_dir() or shadow == real / package:
                continue
            if any(part in NOT_OURS for part in shadow.parts):
                continue
            base = shadow.parent
            for module in sorted(shadow.rglob("*.py")):
                original = real / module.relative_to(base)
                if not original.exists():
                    found.append((module, original))
    return found


def test_no_deleted_module_survives_in_a_copy_of_the_package():
    """A build directory that outlived the modules it holds.

    `metis-server/build/lib/` held a full copy of both packages including six
    modules the rebuild had deleted -- `model_sources/data_landing.py`,
    `model_sources/structure.py`, `resolution/`, `rendering/payload.py` and
    `rendering/scaffold.py`. It is gitignored, so nothing tracked it and nothing
    complained, and CLAUDE.md's rule that a search finding one of those names
    "has found a stale reference, not a file to read" was quietly false: the file
    was there and it opened.

    That is the same failure as `.github/agents/` -- a generated artefact that
    stopped being regenerated and stayed confidently wrong. The repair is
    `rm -rf metis-server/build`, and a build made after this passes, because a
    fresh copy holds exactly what the tree holds.
    """
    survivors = shadow_modules(REPO)

    assert not survivors, (
        "a copy of the package holds modules the real package no longer has:\n  "
        + "\n  ".join(f"{m.relative_to(REPO)} (no {o.relative_to(REPO)})"
                       for m, o in survivors)
        + "\n\nrun `rm -rf metis-server/build` — it is a build artefact, and a "
          "fresh build holds only what the tree holds."
    )


def test_the_shadow_check_can_actually_fail(tmp_path):
    """Guarding the guard.

    With `build/` removed this test file's other assertion passes over an empty
    set, which is exactly the shape of check this file exists to distrust. So
    the finder is run against a tree built to contain the failure.
    """
    real = tmp_path / "metis-server" / "metis_mcp"
    real.mkdir(parents=True)
    (real / "lives.py").write_text("")

    shadow = tmp_path / "build" / "lib" / "metis_mcp"
    shadow.mkdir(parents=True)
    (shadow / "lives.py").write_text("")
    (shadow / "deleted.py").write_text("")

    found = shadow_modules(tmp_path)

    assert [m.name for m, _ in found] == ["deleted.py"], found
    assert not shadow_modules(tmp_path / "nothing-here")


def test_a_copy_that_matches_the_tree_is_not_reported(tmp_path):
    """A build made right now must not fail the suite. Only a copy holding a
    module the tree lacks does -- content is allowed to lag."""
    real = tmp_path / "metis-server" / "metis_mcp"
    real.mkdir(parents=True)
    (real / "current.py").write_text("x = 1")

    shadow = tmp_path / "build" / "lib" / "metis_mcp"
    shadow.mkdir(parents=True)
    (shadow / "current.py").write_text("x = 0  # an older build")

    assert shadow_modules(tmp_path) == []

