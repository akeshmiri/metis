"""
The CPG engine: preflight, invocation, and a cache (spec X-1a, X-3, X-5).

**`CodeExtractedSource` still does not run Joern, and that boundary is kept on
purpose.** Its docstring argues that a source whose `available` depended on a
working engine install "would report unavailable for reasons that have nothing
to do with Métis", and that is right. This module runs the engine and hands the
source what it already accepts: validated `metis.cpg-extract/1` reports. The
source is unchanged and stays usable with reports produced any other way.

Three things it owns:

  * **Preflight.** Checked BEFORE a forty-second CPG build, not discovered
    inside one. X-3 pins the engine because Joern's 2.x→4.x storage change broke
    packs silently, so a version mismatch is reported against the pin rather
    than shrugged at.
  * **Invocation.** `joern-parse`, then each pack, with the parameters the packs
    declare. Nobody should need to know four `--param` names to extract a repo.
  * **A cache**, keyed on everything that can change the answer:
    `(repo, commit, engine version, pack version, language)`. A hit is
    REPORTED, never silent — a stale artefact presented as fresh is the same
    class of lie as a fabricated path.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PACKS_DIR = Path(__file__).parent / "packs"
STRUCTURAL = "jvm-structural"
BEHAVIOUR = "jvm-behaviour"
# REQ-METIS-PG-01: generation is additive. Without this pack Métis emits a case
# per transition regardless of what already passes — on the pilot target 5 of 6
# generated cases duplicated an integration test that was already green.
TEST_INVENTORY = "jvm-test-inventory"

# `pack.yaml` is read with a regex rather than a YAML parser. `pyproject.toml`
# lists only what is imported, `openapi.py` already refuses rather than assume a
# yaml module is present, and one pinned version does not justify a dependency.
# Scoped to the `engine:` block so a `version:` elsewhere in the file cannot
# match.
_ENGINE_VERSION = re.compile(r"^engine:\s*$.*?^\s+version:\s*\"?([0-9.]+)\"?",
                             re.M | re.S)
_JOERN_VERSION = re.compile(r"(\d+\.\d+\.\d+)")


class EngineUnavailable(Exception):
    """Raised when the CPG engine cannot be used, with what to do about it."""


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""

    def describe(self) -> str:
        mark = "ok  " if self.ok else "FAIL"
        line = f"  [{mark}] {self.name:<18} {self.detail}"
        return line + (f"\n         -> {self.fix}" if self.fix and not self.ok else "")


@dataclass
class Preflight:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def describe(self) -> str:
        lines = ["Preflight", ""] + [c.describe() for c in self.checks]
        if not self.ok:
            lines += ["", "  Refusing before the slow path rather than inside it:",
                      "  a CPG build is minutes long and fails for reasons that",
                      "  have nothing to do with the code being analysed."]
        return "\n".join(lines)

    def require(self, ignore: tuple[str, ...] = ()) -> None:
        """Refuse unless every check passes, minus the ones named.

        `ignore` exists because not every check gates every caller. Extraction is
        database-free — building a CPG and running a query pack touches no graph —
        so a stopped Neo4j is irrelevant to it, while `doctor` should absolutely
        still report it. Coupling the two made "can I extract" answerable only on
        a machine with a database running.
        """
        failed = [c for c in self.checks if not c.ok and c.name not in ignore]
        if failed:
            raise EngineUnavailable(
                f"{len(failed)} preflight check(s) failed:\n" +
                "\n".join(c.describe() for c in failed))


# Two diagnostics for failures that are NOT Métis's and NOT the analysed code's.
#
# Both were met on a clean macOS install and both were reported as "check the
# install", which is the same unhelpful shape the test-inventory diagnosis once
# had: it blamed unresolved dependencies and pointed at `--fetch-dependencies`,
# which reaches Maven Central and would not have helped. A preflight that names
# the wrong cause costs more than one that says nothing.

# The launcher shells out to a tool it does not ship. On Darwin it calls
# `greadlink` (GNU coreutils); with that missing, `$(greadlink -f "$0")` is empty,
# `dirname ""` is `.`, and the launcher resolves its own directory to the CWD --
# so `joern` works when run from inside joern-cli and fails everywhere else. The
# version probe then reports "version unreadable", sending the reader to debug
# Joern rather than to install coreutils.
_MISSING_TOOL = re.compile(r"([A-Za-z0-9_.\-]+): command not found")


def missing_launcher_tool(stderr: str) -> str:
    """The tool Joern's own launcher needs and cannot find, or "".

    Pure, so it is tested without an engine: the string is the evidence.
    """
    found = _MISSING_TOOL.search(stderr or "")
    return found.group(1) if found else ""


def launcher_fix(stderr: str) -> str:
    """What to actually do, when the probe's stderr says what went wrong."""
    tool = missing_launcher_tool(stderr)
    if not tool:
        return "the launcher did not report a version; check the install"
    hint = ("brew install coreutils" if tool.startswith("g")
            else f"install {tool} and put it on PATH")
    return (f"Joern's launcher calls `{tool}`, which is not on PATH. Without it "
            f"the launcher resolves its own directory to `.`, so it only works "
            f"when the working directory IS joern-cli. Fix: {hint}")


# The JavaScript frontend shells out to a per-platform `astgen` binary, and
# 4.0.604's macOS-arm distribution ships `astgen-macos-arm` while `jssrc2cpg`
# looks for `astgen-macos`. Every JS pack then fails with "Local astgen binary
# not found", which reads like a broken install and is a naming mismatch.
_ASTGEN_DIR = ("frontends", "jssrc2cpg", "bin", "astgen")


def astgen_expected_name() -> str:
    """What `jssrc2cpg` will look for on this platform."""
    if sys.platform == "darwin":
        return "astgen-macos"
    if sys.platform.startswith("win"):
        return "astgen-win.exe"
    return "astgen-linux"


def astgen_check(home: Path | None) -> Check:
    """Whether the JS frontend can run at all.

    Not folded into the `joern` check: a JVM-only project does not need it, and
    `require(ignore=("astgen",))` is how such a caller says so. Reported either
    way, because "the JS packs recovered nothing" and "the JS packs could not
    start" are different facts.
    """
    if home is None:
        return Check("astgen", False, "no engine", "install Joern first")
    directory = home.joinpath(*_ASTGEN_DIR)
    expected = directory / astgen_expected_name()
    if expected.exists():
        return Check("astgen", True, str(expected))
    if not directory.is_dir():
        return Check("astgen", False, f"no {directory}",
                     "this Joern distribution ships no JS frontend; JVM packs are "
                     "unaffected, so `require(ignore=(\"astgen\",))` if that is fine")
    # The usual case: it IS shipped, under a name the frontend does not ask for.
    siblings = sorted(p.name for p in directory.iterdir() if p.name.startswith("astgen"))
    near = [n for n in siblings if n.startswith(expected.name)]
    if near:
        return Check(
            "astgen", False,
            f"{expected.name} missing; {', '.join(near)} present",
            f"a naming mismatch in the distribution, not a broken install. "
            f"Fix: ln -s {near[0]} {expected}")
    return Check("astgen", False, f"{expected.name} missing; found {siblings or 'nothing'}",
                 "set ASTGEN_BIN to a working astgen, or reinstall the frontend")


def pinned_version(pack: str = STRUCTURAL) -> str:
    """The engine version this pack was verified against (X-3)."""
    manifest = PACKS_DIR / pack / "pack.yaml"
    if not manifest.exists():
        return ""
    found = _ENGINE_VERSION.search(manifest.read_text())
    return found.group(1) if found else ""


def joern_home() -> Path | None:
    """Where joern lives: `METIS_JOERN_HOME`, then PATH, then the usual install."""
    import os

    def usable(candidate: Path) -> bool:
        # The launcher has to be THERE. A configured-but-wrong path that is
        # returned anyway fails later as "version unreadable", which sends
        # someone to debug their Joern install instead of their env var.
        return (candidate / "joern").exists() and (candidate / "joern-parse").exists()

    configured = os.environ.get("METIS_JOERN_HOME", "").strip()
    if configured:
        candidate = Path(configured)
        return candidate if usable(candidate) else None
    found = shutil.which("joern")
    if found and usable(Path(found).parent):
        return Path(found).parent
    default = Path.home() / "joern" / "joern-cli"
    return default if usable(default) else None


def installed_version(home: Path | None = None) -> str:
    """Joern's own reported version, or "".

    Read from the `joern` launcher's banner. There is no `--version` flag: it
    drops into the REPL, which is why this asks the REPL and exits rather than
    parsing a help string that does not carry it.
    """
    home = home or joern_home()
    if home is None:
        return ""
    out = _probe_launcher(home)
    if out is None:
        return ""
    found = _JOERN_VERSION.search(out.stdout or "")
    return found.group(1) if found else ""


@lru_cache(maxsize=4)
def _probe_launcher(home: Path):
    """Run the launcher once and keep the result, stderr included.

    Cached because `preflight` needs the stdout (for the version) AND the stderr
    (for WHY there is no version), and each call starts a JVM -- asking twice
    doubled the cost of a preflight that is meant to be the cheap step.

    The first launch on a cold install can exceed even this timeout; that is why
    a timeout is reported as "unreadable" with the launcher's own words rather
    than as a missing engine.
    """
    try:
        return subprocess.run([str(home / "joern"), "--nocolors"],
                              input="println(version)\n:exit\n", text=True,
                              capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None


def preflight(check_engine_version: bool = True) -> Preflight:
    """Is this machine able to finish an extraction?"""
    result = Preflight()
    pin = pinned_version()

    home = joern_home()
    if home is None:
        result.checks.append(Check(
            "joern", False, "not found",
            f"install Joern {pin} and put it on PATH, or set METIS_JOERN_HOME. "
            f"Release: https://github.com/joernio/joern/releases/tag/v{pin}"))
    else:
        version = installed_version(home) if check_engine_version else pin
        if not version:
            probe = _probe_launcher(home)
            stderr = (probe.stderr or "") if probe is not None else ""
            result.checks.append(Check(
                "joern", False, f"found at {home}, version unreadable",
                launcher_fix(stderr)))
        elif version != pin:
            # X-3: pinned, not a range. Reported as a failure rather than a
            # warning because the 2.x->4.x storage change broke packs SILENTLY,
            # and a silent break is the one this project refuses to risk.
            result.checks.append(Check(
                "joern", False, f"{version} at {home}, but the packs pin {pin}",
                f"install {pin}, or re-verify the packs against {version} and "
                f"move the pin deliberately (X-3)"))
        else:
            result.checks.append(Check("joern", True, f"{version} at {home}"))

    java = shutil.which("java")
    result.checks.append(Check(
        "jdk", bool(java), java or "not found",
        "javasrc2cpg needs a JDK on PATH"))

    # The JS frontend's own dependency. Reported always, gated by nobody: a
    # JVM-only caller passes `ignore=("astgen",)`, which is a decision it makes
    # explicitly rather than a failure it never hears about.
    result.checks.append(astgen_check(home))

    # Every pack, and every pack's OWN pin. X-3 pins the engine per pack, and
    # four of the five had no manifest — so this compared the install against
    # jvm-structural's pin and applied it to all of them. A pack verified
    # against a different build would have said nothing.
    for pack in sorted(d.name for d in PACKS_DIR.iterdir() if d.is_dir()):
        query = PACKS_DIR / pack / "query.sc"
        if not query.exists():
            result.checks.append(Check(f"pack:{pack}", False,
                                       f"{query} is missing"))
            continue
        own = pinned_version(pack)
        if not own:
            result.checks.append(Check(
                f"pack:{pack}", False, "declares no engine version",
                "add a pack.yaml with an `engine.version` — X-3 pins per pack"))
        elif pin and own != pin:
            result.checks.append(Check(
                f"pack:{pack}", False, f"pins {own}, others pin {pin}",
                "one estate cannot run two engine builds; reconcile the pins"))
        else:
            result.checks.append(Check(f"pack:{pack}", True, f"pinned {own}"))

    try:
        from metis_mcp.mbt.graph_session import GraphNotConfigured, resolve

        config = resolve()
        result.checks.append(Check(
            "graph", True, f"{config.redacted} (password from "
            f"{config.password_source})"))
    except Exception as e:  # GraphNotConfigured, or a driver problem
        result.checks.append(Check(
            "graph", False, str(e).splitlines()[0],
            "landing needs a graph; file-based commands do not"))

    return result


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _exclude_regex(patterns) -> str:
    """Profile globs -> one `--exclude-regex` alternation.

    The profile speaks globs (`**/src/test/**`) because that is what a person
    writes and what `fnmatch` already reads elsewhere; `joern-parse` speaks
    regex. Translating here keeps one vocabulary in the profile rather than
    asking an author to know which tool consumes their pattern.

    Deliberately small: `**` becomes "anything", `*` becomes "anything but a
    separator", `?` one character, and everything else is escaped. A pattern it
    cannot express would silently widen what is parsed, so nothing else is
    interpreted.
    """
    import re

    out = []
    for pattern in patterns:
        built, i = [], 0
        while i < len(pattern):
            if pattern.startswith("**/", i):
                # ZERO or more directories. `.*/ ` would require at least one,
                # so `**/.history/**` matched `a/.history/x` and missed
                # `.history/x` at the repository root — which is exactly where
                # an editor puts it.
                built.append("(?:.*/)?")
                i += 3
            elif pattern.startswith("**", i):
                built.append(".*")
                i += 2
            elif pattern[i] == "*":
                built.append("[^/]*")
                i += 1
            elif pattern[i] == "?":
                built.append("[^/]")
                i += 1
            else:
                built.append(re.escape(pattern[i]))
                i += 1
        out.append("".join(built))
    return "(" + "|".join(out) + ")"


def cache_key(repo: Path, commit: str, language: str, engine_version: str) -> str:
    import hashlib

    material = "|".join([str(Path(repo).resolve()), commit, language,
                         engine_version, pinned_version() or "?",
                         _pack_versions()])
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def _pack_versions() -> str:
    """Pack versions, so editing a pack invalidates what it produced.

    Without this a fixed pack returns yesterday's wrong answer from the cache,
    which is exactly how a fix appears not to work.
    """
    import hashlib

    # **Every pack, not just the two.** This listed only STRUCTURAL and BEHAVIOUR,
    # so editing `jvm-test-inventory` left the key unchanged and the next run
    # returned the previous pack's output from the cache — a fix that appears not
    # to work, which is the exact failure this function exists to prevent.
    # Globbed rather than enumerated so a new pack is covered by existing.
    out = []
    for query in sorted(PACKS_DIR.glob("*/query.sc")):
        out.append(query.parent.name + ":" +
                   hashlib.sha256(query.read_bytes()).hexdigest()[:8])
    return ",".join(out)


# How many builds to keep per project. Each is a CPG plus three reports —
# ~1 MB for a small service, and one per commit AND per pack edit, because the
# key includes the pack contents. Nine had accumulated for one project during a
# day's work on the packs, and nothing was ever going to remove them.
#
# Two rather than one: the previous build is what makes flipping back to an
# earlier commit cheap, which is exactly what someone comparing two revisions
# does.
KEEP_CACHED_BUILDS = 2


def _evict(directory: Path, keep: int, current: str) -> int:
    """Drop all but the `keep` most recent builds. Returns how many went.

    Never touches `current`: it has just been created and is about to be
    written into.
    """
    import shutil

    if not directory.exists():
        return 0
    builds = [d for d in directory.iterdir() if d.is_dir() and d.name != current]
    if len(builds) < keep:
        return 0
    builds.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    gone = 0
    for stale in builds[keep - 1:]:
        try:
            shutil.rmtree(stale)
            gone += 1
        except OSError:
            # A build somebody is reading is a build worth leaving alone.
            pass
    return gone


def cache_dir(project: str) -> Path:
    """`$METIS_HOME/cache/<project>` — never inside the analysed repository.

    It used to be `<repo>/.metis/cache`, which meant Métis wrote build artefacts
    into somebody else's source tree: a directory to gitignore, a surprise in
    `git status`, and a cache that disappears when the repo is cleaned. Profiles
    live in `$METIS_HOME` for the same reason, and one location beats two.
    """
    from code_analysis.project_profile import metis_home

    return metis_home() / "cache" / project


# ---------------------------------------------------------------------------
# Invocation
# ---------------------------------------------------------------------------

@dataclass
class Extraction:
    """What an extraction produced, and whether the engine actually ran."""

    cpg: Path
    # `pack name -> report`, for whichever packs the framework declares. The
    # two JVM ones are named below for the callers that want them by name; a UI
    # framework has neither and `structural`/`behaviour` are then None.
    reports: dict
    structural: Path | None
    behaviour: Path | None
    # Absent when the pack could not run — an inventory that failed is reported,
    # never quietly treated as "no existing tests", which would make every
    # transition look uncovered and generate a case for each.
    inventory: Path | None
    commit: str
    from_cache: bool = False
    log: list[str] = field(default_factory=list)


def _run(command: list[str], what: str, timeout: int = 3600) -> None:
    completed = subprocess.run(command, capture_output=True, text=True,
                               timeout=timeout)
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise EngineUnavailable(
            f"{what} failed (exit {completed.returncode}):\n  " +
            "\n  ".join(tail[-8:] or ["no output"]))


def head_commit(repo: str | Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def changed_files(repo: str | Path, since: str, until: str = "HEAD") -> list[str]:
    """Repo-relative paths that differ between two commits.

    The missing half of an incremental review. `metis_mcp.impact` already answers
    "which recovered behaviour do these files touch" and its docstring says to
    pass what `git diff --name-only` prints — this is the step that produces that
    list, so the question can be asked about two commits instead of about a set
    of paths somebody assembled by hand.

    **Reporting, not extraction.** A CPG is whole-program: call graphs and type
    resolution are global, so there is no meaningful per-file rebuild and this
    does not make one. What it makes cheaper is the REVIEW — re-extraction still
    reads everything, and this says which of the results could possibly have
    moved.

    Repo-relative on purpose: that is the form anchors are stored in
    (`Anchor.file`), so the output can be compared against them without either
    side normalising paths and the two disagreeing about what a path is.

    Returns `[]` on any git failure rather than raising. A missing commit, a
    shallow clone or a directory that is not a repository are all "I cannot tell
    you what changed", and the caller distinguishes that from "nothing changed"
    by having asked for a range it believes in — the same shape `head_commit`
    already uses.
    """
    if not since.strip():
        return []
    try:
        out = subprocess.run(
            # `--relative` is load-bearing, not tidiness. Without it git prints
            # paths from the REPOSITORY root, so analysing a service inside a
            # monorepo returns `services/records/src/...` while its anchors say
            # `src/...` — every path fails to match, `impact` reports nothing
            # touched, and "no behaviour at risk" is indistinguishable from "the
            # comparison never lined up". Measured against this repo: without it,
            # paths came back prefixed with `metis-server/`.
            ["git", "-C", str(repo), "diff", "--name-only", "--relative",
             since, until],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    return sorted({line.strip() for line in out.stdout.splitlines() if line.strip()})


def annotation_table(framework: str, project_annotations: dict | None) -> str:
    """The merged `name -> role` table the packs read.

    Métis ships the framework's; the project adds its own and wins on conflict.
    An undeclared framework is a halt rather than an empty table: extraction
    against one recovers nothing and reports "no behaviour", which §5.8 forbids.
    """
    from code_analysis import annotations as _annotations
    from code_analysis.framework_config import default as default_frameworks

    declared = default_frameworks()
    spec = next((f for f in declared.frameworks if f.name == framework), None)
    # A profile's `annotations` block is raw JSON; `merge` and `to_pack_table`
    # both want parsed specs. Handing the raw dicts straight through raised
    # `AttributeError: 'dict' object has no attribute 'name'` the moment a
    # project declared a single annotation -- so the whole project-annotation
    # feature worked only for a profile that used none of it. `load` is also
    # where an unknown role is refused, naming the nine that exist.
    # Both shapes reach here: a profile's `annotations` block is raw JSON, while
    # a caller holding parsed specs passes those. Handing raw dicts straight
    # through raised `AttributeError: 'dict' object has no attribute 'name'`, so
    # the whole project-annotation feature worked only for a profile that used
    # none of it. `load` is also where an unknown role is refused, naming the
    # nine that exist.
    given = project_annotations or {}
    if any(isinstance(v, _annotations.AnnotationSpec) for v in given.values()):
        project = dict(given)
    else:
        project = _annotations.load(given, where="project profile")
    return _annotations.to_pack_table(_annotations.merge(
        dict(spec.annotations) if spec else {}, project))


# The directory names javasrc2cpg's frontend ignores. Not configurable: x2cpg
# hardcodes the list, `--exclude`/`--exclude-regex` can only ignore MORE, and no
# include-override exists. Measured: a `src/test/java` tree with no imports at all
# is still dropped, and rooting the parse at `src` does not help either — the
# match is on any path segment, not the top level.
TEST_ROOTS = ("src/test/java", "src/test/kotlin", "src/it/java", "src/test")


def test_roots(repo: Path) -> list[Path]:
    """The test source directories to parse as their own input roots.

    Rooting the parse INSIDE the ignored directory is what gets these into a CPG:
    relative to `<repo>/src/test/java` the paths are `com/example/...` and carry
    no ignored segment. Deepest-first, and a root already covered by an earlier
    one is skipped, so `src/test` does not duplicate `src/test/java`.
    """
    found: list[Path] = []
    for name in TEST_ROOTS:
        candidate = repo / name
        if not candidate.is_dir() or not any(candidate.rglob("*.java")):
            continue
        # Either direction: `src/test` is an ANCESTOR of `src/test/java`, so
        # checking only for a descendant reported it as a second, unparsed root
        # and warned about coverage that was already covered.
        if any(candidate == prior or prior in candidate.parents
               or candidate in prior.parents for prior in found):
            continue
        found.append(candidate)
    return found


def _inventory_note(target: Path, repo: Path, parsed: bool = True) -> str:
    """Say whether an empty inventory means "no tests" or "tests unreadable".

    **The two are not the same and the difference is dangerous.** An empty
    inventory read as "nothing is covered" makes every transition look
    uncovered, so generation proposes a case for behaviour a real test already
    proves — the exact opposite of REQ-METIS-PG-01's intent.

    This used to blame dependency resolution and point at `--fetch-dependencies`.
    **That was a misdiagnosis**, and the remedy it recommended would not have
    worked: measured against a `src/test/java` tree containing a file with no
    imports whatsoever, javasrc2cpg dropped it too. The frontend ignores test
    directories by NAME. `test_roots` is the fix, and it needs no network.
    """
    import json

    try:
        found = len(json.loads(target.read_text()).get("tests", []))
    except (OSError, ValueError):
        return "  test inventory: unreadable — treat coverage as UNKNOWN"
    if found:
        return f"  test inventory: {found} existing test(s)"

    on_disk = sum(1 for _ in Path(repo).rglob("src/test/**/*.java"))
    if on_disk and not parsed:
        return (f"  test inventory: EMPTY but {on_disk} test file(s) exist on "
                f"disk and none was parsed — javasrc2cpg ignores test "
                f"directories by name, and no test-rooted CPG was built. "
                f"Coverage is UNKNOWN, not zero: do not read generation as "
                f"additive on this run")
    if on_disk:
        return (f"  test inventory: EMPTY though {on_disk} test file(s) were "
                f"parsed — no test resolved to a declared route, so no existing "
                f"coverage could be attributed. Coverage is UNKNOWN, not zero")
    return "  test inventory: no test sources found"


def packs_for(framework: str) -> tuple[str, ...]:
    """Which packs this framework's extraction runs.

    Read from the framework declaration rather than hardcoded. `engine` used to
    run jvm-structural and jvm-behaviour whatever the profile said, so a
    `surface: ui` journey built a CPG and ran a Java pack against JavaScript —
    recovering nothing, and reporting "no behaviour" rather than "wrong pack".
    """
    from code_analysis.framework_config import default as default_frameworks

    spec = next((f for f in default_frameworks().frameworks if f.name == framework),
                None)
    if spec is None or not spec.packs:
        return (STRUCTURAL, BEHAVIOUR)
    packs = list(spec.packs)
    # The inventory rides with the JVM packs: it answers "what do the existing
    # tests cover", which is a question about the same sources.
    if STRUCTURAL in packs and TEST_INVENTORY not in packs:
        packs.append(TEST_INVENTORY)
    return tuple(packs)


def constructor_param(framework: str) -> str:
    """`expr:status,...` — how this framework builds a response.

    Both packs need it now: the behaviour pack to recognise a constructed
    outcome, the structural pack to read the status of an @ExceptionHandler that
    builds its response instead of annotating one.
    """
    from code_analysis.framework_config import default as default_frameworks

    spec = next((f for f in default_frameworks().frameworks if f.name == framework),
                None)
    if spec is None:
        return ""
    return ",".join(f"{expr}:{code}" for expr, code in spec.response_constructors)


def extract(repo: str | Path, *, language: str, project: str,
            framework: str = "", project_annotations: dict | None = None,
            commit: str = "", refresh: bool = False,
            skip_preflight: bool = False, drop_noise: bool = True,
            exclude: tuple[str, ...] = ()) -> Extraction:
    """Build a CPG and run both packs, or reuse what is already cached."""
    repo = Path(repo).resolve()
    if not skip_preflight:
        # Not the graph: nothing below this line opens a connection.
        preflight().require(ignore=("graph",))

    home = joern_home()
    if home is None:
        raise EngineUnavailable("no engine; run `metis doctor`")

    commit = commit or head_commit(repo) or "unknown"
    # `drop_noise` folded in: without it, flipping the flag returned the previous
    # build from the cache and the change looked like it had no effect.
    # `exclude` folded in for the reason `drop_noise` is: a profile that stopped
    # excluding `.history` returned the previous build from the cache, reported
    # "repo, commit, engine and packs all unchanged" — true, and incomplete —
    # and the change looked like it had done nothing.
    excludes = tuple(sorted(x for x in exclude if x))
    key = cache_key(repo, commit + ("" if drop_noise else "+all")
                    + ("" if not excludes else "+x:" + "|".join(excludes)),
                    language, installed_version(home))
    out = cache_dir(project) / key
    cpg = out / "cpg.bin"
    packs = packs_for(framework)
    reports = {pack: out / f"{pack}.json" for pack in packs}
    structural = reports.get(STRUCTURAL)
    behaviour = reports.get(BEHAVIOUR)
    inventory = reports.get(TEST_INVENTORY)

    if not refresh and cpg.exists() and all(p.exists() for p in reports.values()):
        # Reported, never silent.
        return Extraction(cpg, dict(reports), structural, behaviour,
                          inventory if inventory and inventory.exists() else None,
                          commit, from_cache=True,
                          log=[f"cache hit {key} — repo, commit {commit}, engine "
                               f"and packs all unchanged; nothing was re-run"])

    out.mkdir(parents=True, exist_ok=True)
    log = [f"cache miss {key} — building"]
    evicted = _evict(cache_dir(project), keep=KEEP_CACHED_BUILDS, current=key)
    if evicted:
        log.append(f"  cache: evicted {evicted} older build(s), keeping "
                   f"{KEEP_CACHED_BUILDS}")

    # The merged annotation table, written beside the CPG and handed to every
    # pack. Framework first, project on top. Written as a file rather than a
    # `--param` string because nine roles over thirty-odd annotations is past
    # what a command line should carry, and a file can be read when an
    # extraction surprises somebody.
    table = out / "annotations.tsv"
    table.write_text(annotation_table(framework, project_annotations))
    log.append(f"annotations: {len(table.read_text().splitlines()) - 1} declared")

    # **Excluded at PARSE time, which is the only place it works.** The profile's
    # `exclude` globs were read only by `project_profile.Journey.owns`, when
    # deciding which journey a file belongs to — long after the CPG existed. So
    # an editor's local history was parsed, and every snapshot of a controller
    # produced its own endpoint: 462 nodes on Athena anchored in
    # `.history/…/VersionController_20260514114505.java`, 330 of the 870
    # Endpoint nodes. Adding `**/.history/**` to the profile changed nothing.
    #
    # `--exclude-regex` can only ignore MORE (see TEST_ROOTS above), which is
    # exactly the semantics wanted: it narrows what is parsed and can never
    # widen it.
    parse = [str(home / "joern-parse"), str(repo), "--language", language,
             "--output", str(cpg)]
    if excludes:
        # **After `--frontend-args`, because `joern-parse` has no such option.**
        # Its own flags are `--output/--language/--namespaces`; exclusion belongs
        # to the x2cpg frontend, and `joern-parse` passes everything after this
        # separator to it verbatim. Passing `--exclude-regex` directly exits 1
        # with a Scala stack trace.
        parse += ["--frontend-args", "--exclude-regex", _exclude_regex(excludes)]
        log.append(f"excluding {len(excludes)} pattern(s) at parse time")
    _run(parse, "joern-parse")
    log.append(f"cpg: {cpg.stat().st_size // 1024} KB")

    # **A second CPG, rooted inside the test tree.** Every pack used to receive
    # the main CPG, which structurally cannot contain a test — so the inventory
    # pack was asked "what do the existing tests cover" against a graph with no
    # tests in it, and answered "nothing" every time.
    roots = test_roots(repo)
    test_cpg = out / "tests-cpg.bin"
    if inventory is not None and roots:
        _run([str(home / "joern-parse"), str(roots[0]), "--language", language,
              "--output", str(test_cpg)], "joern-parse (tests)")
        log.append(f"test cpg: {test_cpg.stat().st_size // 1024} KB "
                   f"rooted at {roots[0].relative_to(repo)}")
        if len(roots) > 1:
            # Named, not silently dropped: one input root per parse is all
            # joern-parse takes, so a second test tree is real lost coverage.
            log.append(f"  NOTE: {len(roots) - 1} further test root(s) not "
                       f"parsed ({', '.join(str(r.relative_to(repo)) for r in roots[1:])}) "
                       f"— coverage from them is UNKNOWN, not zero")
    elif inventory is not None:
        log.append("  no test source root found; the inventory will be empty "
                   "because there is nothing to read, not because nothing is covered")

    for pack, target in reports.items():
        graph = test_cpg if (pack == TEST_INVENTORY and test_cpg.exists()) else cpg
        command = [str(home / "joern"), "--script", str(PACKS_DIR / pack / "query.sc"),
                   "--param", f"cpgPath={graph}", "--param", f"commit={commit}",
                   "--param", f"repo={project}", "--param", f"out={target}"]
        # Only what the script declares: an undeclared `--param` is refused
        # outright with "Unknown arguments", so this cannot be a blanket list.
        declared = (PACKS_DIR / pack / "query.sc").read_text()
        if "annotations: String" in declared:
            command += ["--param", f"annotations={table}"]
        if "constructors: String" in declared:
            command += ["--param", f"constructors={constructor_param(framework)}"]
        if "dropNoise: String" in declared:
            # Declared per project, because "is a getter noise" is a fact about a
            # codebase. A project whose getters carry logic sets
            # `"drop_noise": false` and gets every method; the count that was
            # dropped is reported either way.
            command += ["--param", f"dropNoise={'yes' if drop_noise else 'no'}"]
        if "pathPrefix: String" in declared and graph is test_cpg:
            # The anchors must stay repo-relative even though the parse was
            # rooted inside the repo; see the pack header for what breaks
            # otherwise.
            command += ["--param", f"pathPrefix={roots[0].relative_to(repo)}"]
        _run(command, pack)
        log.append(f"{pack}: {target.stat().st_size // 1024} KB")
        if pack == TEST_INVENTORY:
            log.append(_inventory_note(target, repo, parsed=test_cpg.exists()))

    return Extraction(cpg, dict(reports), structural, behaviour,
                      inventory if inventory and inventory.exists() else None,
                      commit, from_cache=False, log=log)
