"""
Automation emitters: one resolved payload, several runners.

**Declared, and an undeclared target is refused.** This is the same rule X-4
already applies to extraction frameworks (`code_analysis/framework_config.py`):
Métis refuses a framework it has not been verified against rather than
attempting one, because a fabricated artefact looks authoritative and is worse
than none. A generator asked for `cypress` must say "not supported" and not emit
something Playwright-shaped with the words changed.

**Why a registry rather than one generator with flags.** The runners differ in
language, not only in syntax — Playwright is TypeScript, REST Assured is Java —
so there is no shared template to parameterise. What IS shared is the input:
every emitter consumes `metis.resolved-payload/1` and nothing else, so a new
runner is a new module and never a change to the model, the payload, or the
join.

**What an emitter may not do.** It may not invent a value. A field the payload
still marks `__unrecoverable__` is emitted as a TODO carrying the hint or
condition beside it, so the gap is visible in the generated file rather than
guessed into it (X-6e, T-9c). An emitter that filled one in would move the
fabrication one layer further from where anybody would look for it.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

GENERATOR_VERSION = "metis.generator-config/1"

API = "api"
UI = "ui"


class TargetUnsupported(Exception):
    """A runner Métis has not been verified against. Refused, not attempted."""


@dataclass(frozen=True)
class GeneratorSpec:
    """One runner, and what it is verified to produce."""

    name: str
    surface: str
    language: str
    extension: str
    notes: str = ""


# The declared set. Adding one means adding its emitter AND a condition in
# `test_generators.py` that asserts what it produces — the same bar
# `framework_config` sets for an extraction framework.
DECLARED: tuple[GeneratorSpec, ...] = (
    GeneratorSpec(
        name="playwright", surface=UI, language="typescript", extension=".spec.ts",
        notes="Emits a test per case. Selectors come from the payload — which "
              "means from extracted literals or from an authored fixture — and "
              "an unresolved one is a TODO, never a guessed locator."),
    GeneratorSpec(
        name="rest-assured", surface=API, language="java", extension=".java",
        notes="One JUnit 5 class per model, a @Test method per case — Java "
              "requires the file to be named after the class. Method and path "
              "come from the transition's trigger; an unrecovered status is a "
              "TODO rather than an invented expectation."),
)

# Named here so the refusal can say what WOULD be accepted. These are runners a
# user is likely to ask for and that nothing has been verified against; listing
# them is more useful than a bare "unsupported".
KNOWN_UNSUPPORTED = {
    "selenium": UI,
    "cypress": UI,
    "feign": API,
    "restassured": API,   # the common misspelling of `rest-assured`
}


def declared_for(surface: str) -> tuple[GeneratorSpec, ...]:
    return tuple(g for g in DECLARED if g.surface == surface)


def get(name: str) -> GeneratorSpec:
    """The spec for a target, or a refusal naming what is available."""
    wanted = (name or "").strip().lower()
    for spec in DECLARED:
        if spec.name == wanted:
            return spec

    available = ", ".join(sorted(g.name for g in DECLARED))
    if wanted in KNOWN_UNSUPPORTED:
        raise TargetUnsupported(
            f"{wanted!r} is a real runner and Métis has not been verified "
            f"against it, so it is refused rather than approximated (X-4). "
            f"Declared: {available}. Adding it means an emitter plus a test "
            f"asserting what it produces.")
    raise TargetUnsupported(
        f"unknown target {wanted!r}. Declared: {available}")


def _module(spec: GeneratorSpec):
    from metis_mcp.rendering.generators import playwright, rest_assured

    return {"playwright": playwright, "rest-assured": rest_assured}[spec.name]


def emit(name: str, resolved: dict) -> str:
    """Render one resolved payload with the named emitter."""
    return _module(get(name)).emit(resolved)


def _safe_stem(case_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(case_id))


def emit_files(name: str, documents: Sequence[dict]) -> dict[str, str]:
    """Filename -> source for a whole run. **The emitter owns the layout.**

    It has to. A caller that named files itself wrote sixteen `tc-<hash>.java`
    each declaring `public class LoginApiTest`, which `javac` rejects on sight —
    Java requires a public class to live in a file named after it. That is a
    fact about the target language, not about Métis, so it belongs beside the
    emitter that knows the language rather than in the CLI.

    An emitter defining `emit_files` decides both grouping and names. One that
    does not gets the default: a file per case, named by case id, which is right
    wherever a file is not also a declaration (TypeScript).
    """
    spec = get(name)
    module = _module(spec)
    if hasattr(module, "emit_files"):
        return module.emit_files(documents)

    out: dict[str, str] = {}
    for index, document in enumerate(documents):
        payload = document.get("resolved", document)
        stem = _safe_stem(payload.get("case_id", f"case{index}"))
        out[f"{stem}{spec.extension}"] = module.emit(document)
    return out


def surface_of(document: dict) -> str:
    """The surface the case exercises, from the act step that defines it."""
    payload = document.get("resolved", document)
    act = payload.get("act") or {}
    return str(act.get("surface", ""))


def select_for(spec: GeneratorSpec, documents: Sequence[dict]):
    """`(matching, skipped)` for one target, split on surface.

    **Why filter rather than emit everything.** `GeneratorSpec.surface` was
    declared and never read, so `--target playwright` against an API model
    emitted a browser test whose every step was a TODO — an artefact that reads
    as a modelling gap and is a target mismatch. Filtering rather than refusing
    outright because a model may legitimately hold both surfaces: the UI cases
    are Playwright's, the API cases are REST Assured's, and each target takes
    its own half and says how much it left.
    """
    matching = [d for d in documents if surface_of(d) == spec.surface]
    skipped = [d for d in documents if surface_of(d) != spec.surface]
    return matching, skipped


def describe() -> str:
    """What can be generated, and what is deliberately refused."""
    lines = [f"Generator configuration ({GENERATOR_VERSION})", "",
             "  DECLARED TARGETS"]
    for spec in DECLARED:
        lines.append(f"    {spec.name:14} {spec.language:11} {spec.surface:4} {spec.extension}")
        lines.append(f"        {spec.notes}")
    lines += ["", "  REFUSED (real runners, not verified here)"]
    for name, surface in sorted(KNOWN_UNSUPPORTED.items()):
        lines.append(f"    {name:14} {surface}")
    lines += ["",
              "  An undeclared target is refused, not attempted: a fabricated",
              "  artefact looks authoritative and is worse than none (X-4)."]
    return "\n".join(lines)
