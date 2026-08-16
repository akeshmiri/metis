"""
Framework configuration (application spec RD-6; X-4, X-10b, X-10c, X-10d).

Two things §5 makes configuration rather than code, and the distinction matters:

  * **X-4 -- which frameworks are supported is *declared*.** An unrecognised
    framework is **reported, never guessed**. A fabricated UI model is worse than
    no model, because it looks authoritative. This is the one place that decides
    whether extraction runs at all for a given repository.
  * **X-10b -- dimension classes are configuration**, matched against recovered
    checks. But **order is a code fact** (X-10a): configuration says what *kind*
    of check something is, never when it runs. Nothing here can set an order, and
    that is deliberate -- a config file that could would let someone assert a
    precedence the code does not have, which GD-9 exists to prevent.

The schema is validated rather than trusted. A config that names a dimension class
with no match patterns, or declares a framework with no entry-point markers, is
**rejected with the reason** rather than silently contributing nothing -- the
failure mode of a silently-empty config is an extraction that finds nothing and
reports "no behaviour", which §5.8 says must never happen.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from metis_mcp.mbt.dimensions import CROSS_CUTTING, DimensionClass

CONFIG_VERSION = "metis.framework-config/1"

# Surfaces a framework may serve (spec M-2).
API = "api"
UI = "ui"
SURFACES = (API, UI)


class ConfigInvalid(ValueError):
    """Raised when a configuration cannot be used as written."""


class FrameworkUnsupported(Exception):
    """Raised when extraction is attempted against an undeclared framework (X-4)."""


@dataclass(frozen=True)
class FrameworkSpec:
    """One declared framework (spec X-4).

    `entry_point_markers` are what the query pack looks for to find a trigger --
    annotations, decorators, route-registration calls. `outcome_markers` are what
    it looks for to find an observable outcome. Both are *required*: a framework
    declared without them would pass the support check and then recover nothing,
    which is indistinguishable from a clean codebase.
    """

    name: str
    language: str
    surface: str
    entry_point_markers: tuple[str, ...]
    outcome_markers: tuple[str, ...]
    pack: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.surface not in SURFACES:
            raise ConfigInvalid(
                f"{self.name}: surface {self.surface!r} is not one of {SURFACES}")
        if not self.entry_point_markers:
            raise ConfigInvalid(
                f"{self.name}: no entry_point_markers. A framework declared without "
                f"them passes the support check and then recovers nothing, which is "
                f"indistinguishable from a clean codebase (§5.8)")
        if not self.outcome_markers:
            raise ConfigInvalid(
                f"{self.name}: no outcome_markers. Triggers with no recoverable "
                f"outcome produce transitions with no target state")


@dataclass
class FrameworkConfig:
    version: str = CONFIG_VERSION
    frameworks: list[FrameworkSpec] = field(default_factory=list)
    dimension_classes: list[DimensionClass] = field(default_factory=list)

    def supports(self, name: str, surface: str = "") -> bool:
        return any(f.name == name and (not surface or f.surface == surface)
                   for f in self.frameworks)

    def get(self, name: str, surface: str = "") -> FrameworkSpec:
        """Spec X-4: an unrecognised framework is reported, never guessed."""
        for framework in self.frameworks:
            if framework.name == name and (not surface or framework.surface == surface):
                return framework
        declared = ", ".join(sorted(f"{f.name} ({f.surface})" for f in self.frameworks))
        raise FrameworkUnsupported(
            f"{name!r} is not a declared framework"
            + (f" for the {surface!r} surface" if surface else "")
            + f". Declared: {declared or 'none'}.\n"
            f"Extraction is NOT attempted against an undeclared framework: a "
            f"fabricated model is worse than no model, because it looks "
            f"authoritative (X-4). Declare it in the framework config, with real "
            f"entry-point and outcome markers, or extract a surface that is "
            f"supported.")

    def classes(self) -> tuple[DimensionClass, ...]:
        return tuple(self.dimension_classes)


def _dimension_class(entry: dict) -> DimensionClass:
    name = entry.get("class") or entry.get("name") or ""
    if not name:
        raise ConfigInvalid("a dimension class needs a name")
    matches = tuple(m.lower() for m in entry.get("matches", ()))
    if not matches:
        raise ConfigInvalid(
            f"dimension class {name!r} has no match patterns, so it can never "
            f"classify anything. An empty class silently leaves every check "
            f"unclassified (X-10c) while appearing to be configured")
    if "order" in entry or "precedence" in entry:
        # X-10a/X-10d: order is a code fact, recovered from the framework chain
        # and control flow. Letting configuration set it would allow someone to
        # assert a precedence the code does not have -- exactly what GD-9's
        # fail-closed rule exists to prevent.
        raise ConfigInvalid(
            f"dimension class {name!r} declares an order. Configuration says what "
            f"KIND of check something is; it never says when it runs. Order is "
            f"recovered from the framework chain and control flow, never from "
            f"config and never from source line position (X-10a, X-10d)")

    cross_cutting = bool(entry.get("cross_cutting", name in CROSS_CUTTING))
    return DimensionClass(name=name, cross_cutting=cross_cutting, matches=matches)


def load(data: dict) -> FrameworkConfig:
    """Validate and build. Rejects with a reason rather than degrading."""
    version = data.get("version", CONFIG_VERSION)
    if version != CONFIG_VERSION:
        raise ConfigInvalid(
            f"unknown config version {version!r}; expected {CONFIG_VERSION}. "
            f"The engine and its query packs are pinned and versioned together "
            f"(X-3); a config from another version is not assumed compatible")

    frameworks = []
    seen: set[tuple[str, str]] = set()
    for entry in data.get("frameworks", ()):
        spec = FrameworkSpec(
            name=entry["name"], language=entry.get("language", ""),
            surface=entry.get("surface", API),
            entry_point_markers=tuple(entry.get("entry_point_markers", ())),
            outcome_markers=tuple(entry.get("outcome_markers", ())),
            pack=entry.get("pack", ""), notes=entry.get("notes", ""))
        key = (spec.name, spec.surface)
        if key in seen:
            raise ConfigInvalid(
                f"{spec.name} is declared twice for the {spec.surface!r} surface; "
                f"which one wins would be an accident of file order")
        seen.add(key)
        frameworks.append(spec)

    classes = [_dimension_class(e) for e in data.get("dimension_classes", ())]
    names = [c.name for c in classes]
    if len(names) != len(set(names)):
        raise ConfigInvalid("duplicate dimension class names")

    return FrameworkConfig(version=version, frameworks=frameworks,
                           dimension_classes=classes)


def load_file(path: str | Path) -> FrameworkConfig:
    p = Path(path)
    if not p.exists():
        raise ConfigInvalid(
            f"{p} does not exist. Extraction requires a declared framework "
            f"configuration; there is no default, because a default would mean "
            f"guessing a framework (X-4)")
    return load(json.loads(p.read_text()))


# The shipped starting point. Java/Spring only, because that is the frontend
# §5's own X-1a rationale calls most mature and the only one this build has run
# against for real. Every other framework is absent rather than aspirational --
# listing one that has no verified query pack would make X-4's support check
# report support that does not exist.
DEFAULT_CONFIG: dict = {
    "version": CONFIG_VERSION,
    "frameworks": [
        {
            "name": "spring-mvc",
            "language": "java",
            "surface": API,
            "pack": "jvm-structural + jvm-behaviour",
            "entry_point_markers": [
                "RequestMapping", "GetMapping", "PostMapping", "PutMapping",
                "DeleteMapping", "PatchMapping",
            ],
            "outcome_markers": [
                "ResponseEntity.ok", "ResponseEntity.status", "ResponseEntity.noContent",
                "ResponseEntity.created", "ResponseEntity.badRequest",
                "ResponseEntity.notFound", "ApiResponse",
            ],
            "notes": "Verified against athena-git: 149 methods, 6 endpoints, "
                     "22 outcomes recovered.",
        },
        {
            "name": "dom-events",
            "language": "javascript",
            "surface": UI,
            "pack": "js-ui",
            "entry_point_markers": ["addEventListener"],
            "outcome_markers": [
                "classList.add", "classList.remove", "classList.toggle",
                "setAttribute", "hidden", "pushState", "replaceState",
            ],
            "notes": "Verified against atlas-site (jssrc2cpg, Joern 4.0.604): "
                     "199 methods, 11 handlers, 8 outcomes, 0 API calls. Handler "
                     "bodies resolve through inline closures and named references; "
                     "anything else is reported unresolved rather than attributed "
                     "to the enclosing module.",
        },
    ],
    "dimension_classes": [
        {
            "class": "authentication",
            "cross_cutting": True,
            "matches": ["isauthenticated", "principal", "securitycontext",
                        "preauthorize", "jwt", "token_valid", "api_key"],
        },
        {
            "class": "authorization",
            "cross_cutting": True,
            "matches": ["hasrole", "hasauthority", "permission", "granted",
                        "isowner", "canaccess"],
        },
        {
            "class": "validation",
            "cross_cutting": False,
            "matches": ["valid", "notnull", "isempty", "notblank", "length",
                        "matches", "required", "format"],
        },
    ],
}


def default() -> FrameworkConfig:
    return load(DEFAULT_CONFIG)


def format_config(config: FrameworkConfig) -> str:
    lines = [f"Framework configuration ({config.version})", "", "  DECLARED FRAMEWORKS"]
    for framework in config.frameworks:
        lines.append(f"    {framework.name:<16} {framework.language:<8} "
                     f"{framework.surface:<4} pack: {framework.pack or '—'}")
        if framework.notes:
            lines.append(f"        {framework.notes}")
    if not config.frameworks:
        lines.append("    none")
    lines += ["", "  DIMENSION CLASSES (X-10b: classification is configuration; "
                  "order is a code fact)"]
    for declared in config.dimension_classes:
        cc = " [cross-cutting]" if declared.cross_cutting else ""
        lines.append(f"    {declared.name:<16}{cc}  {len(declared.matches)} pattern(s)")
    lines += ["",
              "  Any framework not listed above is UNSUPPORTED. Extraction against it",
              "  is refused, not attempted: a fabricated model looks authoritative",
              "  and is worse than none (X-4)."]
    return "\n".join(lines)
