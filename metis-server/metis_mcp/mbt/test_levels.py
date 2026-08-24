"""
Test levels and existing coverage (spec REQ-METIS-PG-01; §6.2, P-12).

**Generation must be additive.** Before this module, the engine emitted one case
per transition regardless of what already existed. Measured against the pilot
estate: of six cases generated for one service, five duplicated an integration
test that was already passing. Generating a test that already exists is not
neutral -- it costs review time, it inflates a coverage figure, and it teaches
people that the generated suite is noise.

**The rule (REQ-METIS-PG-01): generation never fires for a layer already
covered.** A skipped transition is reported with its cause, never silently
dropped -- P-12's discipline, that the denominator is never quietly lowered.

**Covering an endpoint is not covering a transition, and this is the whole
subtlety.** A transition is `(state, trigger, outcome)`. An integration test that
calls `GET /{id}` and asserts 200 is evidence for the 200 transition and says
*nothing* about the 204 one. On the pilot estate that is exactly the situation:
every endpoint of the metric service is reached by a test, yet `GET /{id} -> 204`
-- the not-found path -- is asserted nowhere.

So each transition is graded into three, and the middle grade is the honest one:

    covered                            a test reaches it AND asserts its outcome
    endpoint_covered_outcome_unproven  a test reaches the endpoint; this outcome
                                       is not evidenced. Reported as a judgement
    uncovered                          nothing reaches it

Promoting the middle grade to `covered` would excuse real gaps, which is the
failure this module exists to prevent. Demoting it to `uncovered` would discard
real evidence. It stays its own grade and a human decides.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from metis_mcp.mbt.model import IMPLEMENTED, Model

# The six-value taxonomy (spec §8.5). A level is where a test sits in the
# pyramid, not what it asserts.
UNIT = "unit"
INTEGRATION = "integration"
API_FUNCTIONAL = "api_functional"
WEB_FUNCTIONAL = "web_functional"
E2E = "e2e"
PERFORMANCE = "performance"
LEVELS = (UNIT, INTEGRATION, API_FUNCTIONAL, WEB_FUNCTIONAL, E2E, PERFORMANCE)

# Grades.
COVERED = "covered"
OUTCOME_UNPROVEN = "endpoint_covered_outcome_unproven"
UNCOVERED = "uncovered"

# A status embedded in a state name: `NoContent204` -> 204.
_STATUS_IN_NAME = re.compile(r"([1-5]\d{2})")


@dataclass(frozen=True)
class ExistingTest:
    """One test that already exists, and what it reaches."""

    name: str
    owner: str
    level: str
    routes: tuple[tuple[str, str], ...]      # (verb, path)
    asserts: tuple[str, ...] = ()            # status literals found in the body
    anchor: str = ""
    service: str = ""                        # the module this test lives in

    def reaches(self, verb: str, paths: tuple[str, ...] | str) -> bool:
        wanted = (paths,) if isinstance(paths, str) else paths
        return any(v == verb and p in wanted for v, p in self.routes)


@dataclass
class Inventory:
    """What already exists, per service."""

    tests: list[ExistingTest] = field(default_factory=list)
    unresolved: list[tuple[str, str]] = field(default_factory=list)

    def reaching(self, verb: str, paths: tuple[str, ...] | str,
                 service: str = "") -> list[ExistingTest]:
        """Tests reaching a route, **scoped to the service that owns them**.

        Scoping is not tidiness. Feign clients declare bare paths -- git's test
        declares `GET /summary`, metric's declares `GET /metric/summary` -- so an
        unscoped match credited metric's `/summary` to `GitRepositoryControllerIT`
        and would have excused a genuinely untested endpoint using another
        service's test.
        """
        return [t for t in self.tests
                if t.reaches(verb, paths)
                and (not service or not t.service or t.service == service)]

    @property
    def levels_present(self) -> set[str]:
        return {t.level for t in self.tests}


# **The module a file belongs to is a fact about a repository, not about Métis.**
#
# This was a regex matching one estate's directory naming — a company
# convention compiled into the engine. Against any other layout it matched
# nothing and `--service` reported "this report covers nothing recognisable",
# which was true of the regex and false of the code.
#
# A project declares its own mapping in `.metis/project.json`
# (`code_analysis.project_profile`). With no profile the fallback is the first
# path segment — a plain reading of a monorepo, right for most layouts and
# never a guess dressed as a convention.
_resolver = None


def set_service_resolver(resolve) -> None:
    """Install the profile's mapping. `resolve(path) -> service`, or None to reset."""
    global _resolver
    _resolver = resolve


# Directories that are build layout, never a deployable's name. A single-module
# repository has paths starting `src/`, and returning "src" as the service was
# worse than returning nothing: `Inventory.reaching` treats "" as unscoped and
# still matches on the route, but a WRONG service name blocks every match. Three
# recovered tests graded eight transitions as `uncovered` that way.
_LAYOUT_DIRS = frozenset({"src", "main", "test", "java", "kotlin", "scala",
                          "resources", "target", "build", "out", "app"})


def service_of_path(path: str) -> str:
    """Which deployable a file belongs to, or "" when the layout does not say.

    `records-service/src/main/java/...` -> `records-service` by default, or
    whatever the loaded project profile says it is. A single-module repository
    yields "" — unknown, which is honest and harmless — rather than `src`.
    """
    if _resolver is not None:
        return _resolver(path or "")
    head = (path or "").replace("\\", "/").split("/", 1)[0]
    if not head or head.endswith(".java") or head in _LAYOUT_DIRS:
        return ""
    return head


def from_pack(report: dict) -> Inventory:
    """Build an inventory from `packs/jvm-test-inventory`'s output."""
    inv = Inventory()
    for t in report.get("tests", ()):
        anchor = t.get("anchor", {})
        file = anchor.get("file", "") if isinstance(anchor, dict) else ""
        inv.tests.append(ExistingTest(
            name=t["name"], owner=t.get("owner", ""), level=t.get("level", UNIT),
            routes=tuple((r["verb"], r["path"]) for r in t.get("routes", ())),
            asserts=tuple(t.get("asserts", ())),
            anchor=(f"{file.split('/')[-1]}:{anchor.get('line',0)}"
                    if isinstance(anchor, dict) else str(anchor)),
            service=service_of_path(file)))
    for u in report.get("unresolved", ()):
        inv.unresolved.append((u.get("name", ""), u.get("reason", "")))
    return inv


def _routes_of(transition, service: str) -> tuple[str, tuple[str, ...]] | None:
    """`GET /summary` on service `metric` -> `("GET", ("/summary", "/metric/summary"))`.

    **Every plausible form is returned, because the convention is not uniform.**
    Controllers are dual-mounted on `""` and `/<service>`, the gateway strips the
    prefix, and the Feign clients disagree with each other: metric declares
    `GET /metric/all` while core declares `GET /environment/all`. Normalising to
    one form graded core, git and kube as entirely uncovered when they have
    ControllerITs that do cover them.
    """
    parts = transition.trigger.split(None, 1)
    if not parts:
        return None
    verb = parts[0].upper()
    if not verb.isalpha():
        return None
    path = parts[1] if len(parts) > 1 else ""
    bare = re.sub(rf"^/{re.escape(service)}", "", path) if service else path
    candidates = {path or "/", bare or "/",
                  f"/{service}{path}" if service else path,
                  f"/{service}{bare}" if service else bare}
    return verb, tuple(sorted(c for c in candidates if c))


def expected_status(transition, model: Model) -> str | None:
    """The status a transition's target state represents, if it names one."""
    target = model.states.get(transition.target)
    name = target.name if target else transition.target
    m = _STATUS_IN_NAME.search(name or "")
    return m.group(1) if m else None


@dataclass(frozen=True)
class Grade:
    transition_id: str
    grade: str
    level: str = ""
    evidence: tuple[str, ...] = ()
    detail: str = ""

    @property
    def should_generate(self) -> bool:
        """REQ-METIS-PG-01. `OUTCOME_UNPROVEN` generates: the outcome is not
        evidenced, and treating unproven as proven is how a gap gets excused."""
        return self.grade != COVERED


def grade_transitions(model: Model, inventory: Inventory, service: str = "",
                      ) -> dict[str, Grade]:
    """Grade every implemented transition against what already exists."""
    service = service or _service_of(model)
    out: dict[str, Grade] = {}

    for tid in model.transition_ids():
        transition = model.transitions[tid]
        if transition.implementation_status != IMPLEMENTED:
            continue
        route = _routes_of(transition, service)
        if route is None:
            out[tid] = Grade(tid, UNCOVERED, detail="trigger is not an HTTP route")
            continue

        verb, paths = route
        reaching = inventory.reaching(verb, paths, service)
        if not reaching:
            out[tid] = Grade(tid, UNCOVERED,
                             detail=f"no existing test reaches {verb} {'|'.join(paths)}")
            continue

        status = expected_status(transition, model)
        proving = [t for t in reaching if status and status in t.asserts]
        if proving:
            out[tid] = Grade(
                tid, COVERED, level=proving[0].level,
                evidence=tuple(f"{t.owner}.{t.name}" for t in proving[:3]),
                detail=f"{verb} {paths[0]} reached, and {status} asserted")
        else:
            out[tid] = Grade(
                tid, OUTCOME_UNPROVEN, level=reaching[0].level,
                evidence=tuple(f"{t.owner}.{t.name}" for t in reaching[:3]),
                detail=(f"{verb} {paths[0]} is reached, but "
                        + (f"no existing test asserts {status}"
                           if status else "this outcome is not identifiable by status")
                        + " — evidence for the happy path only"))
    return out


def _service_of(model: Model) -> str:
    """The journey half of a `<journey>-<surface>` model id (M-1).

    Was a regex stripping a hardcoded company prefix as well as the surface.
    M-1 defines the id as `<journey>-<surface>` and says nothing about a prefix,
    so only the surface comes off.
    """
    return re.sub(r"-(api|ui)$", "", model.id)


def format_grades(grades: dict[str, Grade], model: Model) -> str:
    counts = {g: 0 for g in (COVERED, OUTCOME_UNPROVEN, UNCOVERED)}
    for grade in grades.values():
        counts[grade.grade] = counts.get(grade.grade, 0) + 1
    generate = sum(1 for g in grades.values() if g.should_generate)

    lines = [f"Existing coverage — {model.id}",
             f"  covered (outcome asserted):        {counts[COVERED]}",
             f"  endpoint covered, outcome unproven:{counts[OUTCOME_UNPROVEN]:>3}",
             f"  uncovered:                         {counts[UNCOVERED]}",
             "",
             f"  -> {generate} transition(s) would generate a case "
             f"(REQ-METIS-PG-01)"]
    for tid, grade in sorted(grades.items()):
        if grade.grade == COVERED:
            lines.append(f"    SKIP  {model.transitions[tid].trigger} -> "
                         f"{model.transitions[tid].target}")
            lines.append(f"          {grade.detail}; {', '.join(grade.evidence)}")
    lines += ["",
              "  'endpoint covered, outcome unproven' still GENERATES. A test that",
              "  calls an endpoint and asserts one status is not evidence for the",
              "  others; treating it as such is how a real gap gets excused."]
    return "\n".join(lines)
