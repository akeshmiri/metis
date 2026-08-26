"""
The project profile: what is true of ONE repository (spec X-4, §5.8).

**Métis ships framework knowledge; a project ships its own.**
"Spring MVC builds responses with `ResponseEntity.ok(...)`" is true of every
Spring project and lives in `framework_config`. "This repo's `records-service`
module is the `demo_project/records-service` service" is true of one repository and lives here.

Profiles are kept in **`$METIS_HOME/profiles/<project>.json`** — `~/.metis` by
default, the same directory the graph configuration already uses and the one the
chart mounts. Métis's own source tree carries none of them: what it knows about
your estate lives beside your credentials, not in this repository.

That split is not tidiness. Three of this engine's assumptions were one estate's
directory convention compiled into it:

    test_levels._SERVICE_IN_PATH   a regex naming one estate's directories
    test_levels._service_of        a regex stripping one estate's prefix
    cross_surface._service_of      the same strip, again

Every one of them silently produced a wrong answer for any other repository —
`--service demo_project/records-service` reported "this report covers nothing recognisable",
which is true of the regex and false of the code. A profile makes that a
declared fact rather than a guess that happens to be right at one company.

Validated the way `framework_config` validates: **rejected with a reason, never
silently empty**. A profile that contributes nothing produces an extraction that
finds nothing and reports "no behaviour", which §5.8 says must never happen.
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path

PROFILE_VERSION = "metis.project-profile/1"
SURFACES = ("api", "ui")

HOME_ENV = "METIS_HOME"


def metis_home() -> Path:
    """`$METIS_HOME`, or `~/.metis`.

    The same directory `graph_session` reads configuration from and the chart
    mounts, so there is one place a machine's Métis state lives rather than two.
    """
    import os

    configured = os.environ.get(HOME_ENV, "").strip()
    return Path(configured) if configured else Path.home() / ".metis"


def profiles_dir() -> Path:
    return metis_home() / "profiles"


def project_name_for(repo: str | Path) -> str:
    """The directory's own name, which is what `init` defaults to."""
    return Path(repo).resolve().name


class ProfileInvalid(ValueError):
    """Raised when a profile cannot be used as written."""


class ProfileMissing(FileNotFoundError):
    """Raised when a repository has no profile and one is required."""


@dataclass(frozen=True)
class JourneySpec:
    """One model this repository produces: `<journey>-<surface>` (M-1).

    `modules` is the answer to "which directories are this deployable", and it
    replaces a regex over somebody's naming convention. It is a list because a
    service is regularly more than one Maven module, and it is required because
    the alternative -- infer it -- is what produced a model wearing one service's
    name for an entire monorepo.
    """

    journey: str
    surface: str
    modules: tuple[str, ...]
    exclude: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.journey:
            raise ProfileInvalid("a journey needs a name (M-1)")
        if self.surface not in SURFACES:
            raise ProfileInvalid(
                f"{self.journey}: surface {self.surface!r} is not one of {SURFACES}")
        if not self.modules:
            raise ProfileInvalid(
                f"{self.journey}-{self.surface}: no modules. Without them every "
                f"file in the repository belongs to this journey, which is how a "
                f"monorepo becomes one model wearing one service's name")

    @property
    def model_id(self) -> str:
        return f"{self.journey}-{self.surface}"

    def owns(self, path: str) -> bool:
        """Whether a file path belongs to this journey."""
        p = (path or "").replace("\\", "/")
        if any(fnmatch.fnmatch(p, pattern) for pattern in self.exclude):
            return False
        return any(p == m or p.startswith(m.rstrip("/") + "/") for m in self.modules)


@dataclass
class ProjectProfile:
    version: str = PROFILE_VERSION
    project: str = ""
    language: str = ""
    framework: str = ""
    journeys: list[JourneySpec] = field(default_factory=list)
    # Where it was read from, for messages that have to tell someone which file
    # to edit. Not part of the document.
    path: str = ""
    # Things worth saying about how this profile was resolved — a stray file
    # that was ignored, most usefully. Carried rather than printed so the caller
    # decides where they go (the MCP surface has no stdout to print to).
    notes: list = field(default_factory=list)
    # Which checkout it was written for. Recorded so a profile can say it
    # describes somewhere else, which is otherwise invisible.
    repo: str = ""
    # This project's own annotations, on the same closed role vocabulary the
    # framework uses. `@ProjectSecured` means nothing to Métis until a profile says
    # which role it plays; before this it was simply invisible.
    annotations: dict = field(default_factory=dict)

    def journey(self, journey: str = "", surface: str = "") -> JourneySpec:
        """One journey, or a refusal naming what is declared."""
        matches = [j for j in self.journeys
                   if (not journey or j.journey == journey)
                   and (not surface or j.surface == surface)]
        if len(matches) == 1:
            return matches[0]
        declared = ", ".join(sorted(j.model_id for j in self.journeys)) or "none"
        if not matches:
            raise ProfileInvalid(
                f"{self.path or '<profile>'} declares no journey matching "
                f"{journey or '<any>'}-{surface or '<any>'}. Declared: {declared}")
        raise ProfileInvalid(
            f"{journey or '<any>'}-{surface or '<any>'} matches {len(matches)} "
            f"declared journeys ({declared}); name one. Picking for you is how a "
            f"run lands in the wrong model and reports success")

    def service_of(self, path: str) -> str:
        """Which journey owns this file, or "" when none does.

        Replaces `test_levels.service_of_path`'s regex. Returning "" for an
        unowned file is a fact, not a failure: build files, shared libraries and
        generated sources genuinely belong to no journey.
        """
        for spec in self.journeys:
            if spec.owns(path):
                return spec.journey
        return ""


def _journey(entry: dict) -> JourneySpec:
    return JourneySpec(
        journey=entry.get("journey", ""),
        surface=entry.get("surface", "api"),
        modules=tuple(entry.get("modules", ())),
        exclude=tuple(entry.get("exclude", ())),
    )


def load(data: dict, path: str = "") -> ProjectProfile:
    """Validate and build. Rejects with a reason rather than degrading."""
    version = data.get("version", "")
    if version != PROFILE_VERSION:
        raise ProfileInvalid(
            f"unknown profile version {version!r}; expected {PROFILE_VERSION}")

    for required in ("project", "language", "framework"):
        if not data.get(required):
            raise ProfileInvalid(
                f"{path or '<profile>'}: {required!r} is required. It is a "
                f"judgement about this repository, and X-4 says an undeclared "
                f"framework is reported, never guessed")
    if str(data.get("framework", "")).startswith("REPLACE"):
        # `metis init` leaves these markers on every judgement. Running against
        # one means the scaffold was never filled in, and the honest failure is
        # here rather than in an extraction that quietly finds nothing.
        raise ProfileInvalid(
            f"{path or '<profile>'} still has a REPLACE marker on 'framework'. "
            f"`metis init` fills in what is mechanically knowable and leaves the "
            f"judgements to a person; this is one of them")

    journeys = [_journey(e) for e in data.get("journeys", ())]
    if not journeys:
        raise ProfileInvalid(
            f"{path or '<profile>'}: no journeys declared, so there is nothing "
            f"to extract. A profile that contributes nothing produces an "
            f"extraction that finds nothing and reports 'no behaviour' (§5.8)")
    ids = [j.model_id for j in journeys]
    if len(ids) != len(set(ids)):
        raise ProfileInvalid(
            f"duplicate journey/surface pairs: which one wins would be an "
            f"accident of file order")

    from code_analysis import annotations as _annotations

    return ProjectProfile(
        version=version, project=data["project"], language=data["language"],
        framework=data["framework"], journeys=journeys, path=path,
        repo=data.get("repo", ""),
        annotations=_annotations.load(data.get("annotations"),
                                      where=path or "profile"))


def profile_path(project: str) -> Path:
    """`~/.metis/profiles/<project>.json`."""
    return profiles_dir() / f"{project}.json"


def list_profiles() -> list[str]:
    directory = profiles_dir()
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))


def load_project(project: str) -> ProjectProfile:
    """One profile by name, or a refusal listing what is there."""
    p = profile_path(project)
    if not p.exists():
        known = ", ".join(list_profiles()) or "none"
        raise ProfileMissing(
            f"no profile {project!r} in {profiles_dir()} (have: {known}). "
            f"Run `metis init <repo>` to scaffold one, then fill in the "
            f"judgements it marks REPLACE.")
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        raise ProfileInvalid(f"{p} is not valid JSON: {e}") from e
    return load(data, path=str(p))


def load_for(repo: str | Path, project: str = "") -> ProjectProfile:
    """The profile describing this checkout.

    Named explicitly, or the repository's directory name. A profile left in the
    repository by an earlier build is **reported**, never read: two locations
    for one fact is two answers that can disagree, and the one being ignored is
    exactly the one somebody just edited.
    """
    name = project or project_name_for(repo)
    profile = load_project(name)
    if stray.exists():
        # F-10: what was found and not used is named.
        profile.notes.append(
            f"{stray} exists and was ignored — the profile in use is "
            f"{profile.path}. Delete the stray one so there is a single answer.")
    return profile


def format_profile(profile: ProjectProfile) -> str:
    lines = [f"Project profile ({profile.version})", "",
             f"  project   {profile.project}",
             f"  language  {profile.language}",
             f"  framework {profile.framework}", "", "  JOURNEYS"]
    for j in profile.journeys:
        lines.append(f"    {j.model_id:<20} modules: {', '.join(j.modules)}")
        if j.exclude:
            lines.append(f"    {'':<20} exclude: {', '.join(j.exclude)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scaffolding — `metis init`
# ---------------------------------------------------------------------------

# What a build system implies about the frontend. Mechanically knowable, so it
# is detected. The FRAMEWORK is not in here on purpose: X-4 says an unrecognised
# framework is reported, never guessed, and "there is a pom.xml" does not tell
# you whether the surface is Spring MVC, JAX-RS or a batch job with no surface
# at all.
_BUILD_MARKERS = (
    ("pom.xml", "javasrc"),
    ("build.gradle", "javasrc"),
    ("build.gradle.kts", "javasrc"),
    ("package.json", "jssrc"),
    ("go.mod", "golang"),
    ("pyproject.toml", "pythonsrc"),
    ("Cargo.toml", "rust"),
)

REPLACE = "REPLACE: "

# Never a module, and never worth walking into.
_IGNORED_DIRS = {"target", "build", "node_modules", "dist", "venv", "site"}


def detect_language(repo: str | Path) -> str:
    """The frontend a build file implies, from the root or one level down.

    One level, because a build file in a subdirectory is the ordinary shape —
    Métis's own `pyproject.toml` is in `metis-server/`, and looking only at the
    root reported "no language" for the repository the tool lives in. Deeper
    than that would be a guess about somebody's nesting.
    """
    root = Path(repo)
    for marker, language in _BUILD_MARKERS:
        if (root / marker).exists():
            return language
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        if child.name.startswith(".") or child.name in _IGNORED_DIRS:
            continue
        for marker, language in _BUILD_MARKERS:
            if (child / marker).exists():
                return language
    return ""


def detect_modules(repo: str | Path) -> list[str]:
    """Top-level directories that look like source modules.

    A directory containing a build file, or a `src/`. Deliberately shallow: a
    guess about nesting would be a guess about somebody's layout, which is the
    whole class of assumption this module exists to remove.
    """
    root = Path(repo)
    out = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        if child.name.startswith(".") or child.name in _IGNORED_DIRS:
            continue
        if (child / "src").exists() or any(
                (child / m).exists() for m, _ in _BUILD_MARKERS):
            out.append(child.name)
    return out


def scaffold(repo: str | Path, project: str = "") -> dict:
    """A profile with what is knowable filled in and judgements marked REPLACE.

    The same discipline `.metis/config.yaml` already uses: a marker left where a
    person has to decide, rather than a plausible default that nobody revisits.
    """
    root = Path(repo)
    modules = detect_modules(root)
    language = detect_language(root)
    return {
        "version": PROFILE_VERSION,
        "project": project or root.name,
        # Which checkout this describes. A profile lives in ~/.metis and the
        # repository it is about is otherwise unrecoverable from the file.
        "repo": str(root.resolve()),
        "language": language or f"{REPLACE}source language, e.g. javasrc",
        "framework": f"{REPLACE}declared framework, e.g. spring-mvc — "
                     f"run `metis frameworks` for what is supported (X-4)",
        "journeys": [
            {
                "journey": f"{REPLACE}one feature name, e.g. records (M-1)",
                "surface": "api",
                "modules": modules or [f"{REPLACE}the directories of this deployable"],
                "exclude": ["**/src/test/**"],
            }
        ],
        # Declared empty rather than omitted: a key that is visibly there and
        # visibly empty invites the question "what goes in here", where a
        # missing one invites nothing.
        "annotations": {},
        # Where this service answers. **Not recoverable from source** — a base
        # URL lives in deployment config, not in a controller — so a recipe
        # emits `{base}` and says why when this is empty. Stating a guess here
        # would produce a curl that looks runnable and is not.
        "base_url": "",
        # Inert accessors and generated boilerplate are dropped before anything
        # downstream reads them -- on a real 12-endpoint service that was 189 of
        # 389 methods. Set false if this codebase's getters carry logic; the count
        # dropped is reported either way, never silently.
        "drop_noise": True,
        "_notes": [
            "Lives in $METIS_HOME/profiles (default ~/.metis/profiles). Métis's "
            "own source tree carries no profiles.",
            "modules: which directories are ONE deployable. Without them a "
            "monorepo becomes one model wearing one service's name.",
            "base_url: where this service answers, for generated call recipes. "
            "Not recoverable from source; empty means a recipe emits a "
            "placeholder rather than a guess.",
            "drop_noise: true drops getX/setX/isX methods that have a matching "
            "field, are short, and contain no branch, throw or call — plus "
            "equals/hashCode/toString. Never by visibility: a private method can "
            "guard an endpoint and raise the exception its handler maps.",
            "annotations: your own Java annotations, mapped onto Métis's roles "
            "(entry_point, route_prefix, outcome_status, exception_mapping, "
            "security, validation, schema, outbound_client, ignore). Anything "
            "not declared here or by the framework is invisible to extraction.",
            "exclude: glob patterns. A @FeignClient package is worth excluding — "
            "its mappings are calls this service MAKES, not endpoints it serves.",
        ],
    }
