"""
The skill and router surface (application spec §9.2, §9.5).

**Why this file exists.** Every one of Métis's six skills was dead: they called
`metis_get_context`, `metis_check_coverage` and four siblings on
`metis_mcp.server`, a module that no longer exists, and three of them had lost
their implementations entirely. Nothing failed, because nothing checked — a
skill that names a command is prose until something asserts the command is real.

Atlas shows where that ends: four hand-maintained routing tables that contradict
each other, agent files naming ~25 skills with no directory behind them, and a
documented test script that does not exist.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from metis_mcp.workflow.routing import HEADER, render_router, route
from metis_mcp.workflow.stages import WORKFLOWS

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "metis"
SKILLS = PLUGIN / "skills"
ROUTER = PLUGIN / "agents" / "metis.agent.md"

# Commands a SKILL.md may tell the model to run, as `... cli <verb>`.
_CLI_CALL = re.compile(r"metis_mcp\.mbt\.cli\s+([a-z-]+)(?:\s+([a-z-]+))?")


def _cli_verbs() -> set[str]:
    """Every subcommand the real CLI exposes, read from the parser itself."""
    import contextlib
    import io

    from metis_mcp.mbt import cli

    # Read the verbs from `--help`, i.e. from what a user actually sees. A
    # hand-maintained list here would be a second place to keep in step, which
    # is the failure this whole file exists to catch.
    verbs: set[str] = set()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.suppress(SystemExit):
        cli.main(["--help"])
    text = buf.getvalue()
    match = re.search(r"\{([a-z,\-]+)\}", text)
    if match:
        verbs |= set(match.group(1).split(","))
    return verbs


def skill_files() -> list[Path]:
    return sorted(SKILLS.glob("*/SKILL.md"))


# --------------------------------------------------------------------------
# Skills must name real commands.
# --------------------------------------------------------------------------

def test_there_are_skills_at_all():
    assert skill_files(), "the plugin advertises skills; there must be some"


def test_every_command_a_skill_names_is_a_real_cli_verb():
    """The check that would have caught six dead skills on the day they died."""
    verbs = _cli_verbs()
    assert verbs, "could not read the CLI's own subcommand list"

    unknown: list[tuple[str, str]] = []
    for path in skill_files():
        for text in [path.read_text()] + [p.read_text() for p in
                                          sorted(path.parent.glob("steps/*.md"))]:
            for verb, _sub in _CLI_CALL.findall(text):
                if verb not in verbs:
                    unknown.append((path.parent.name, verb))
    assert not unknown, (
        "skills name CLI verbs that do not exist: "
        + ", ".join(f"{s}:{v}" for s, v in sorted(set(unknown))))


def test_no_skill_still_calls_a_tool_the_server_does_not_expose():
    """A skill calling a tool that does not exist cannot work.

    **This used to compare against a hardcoded list of seven dead names**, and
    that is precisely how twelve phantom tools survived in `.github/agents/`:
    five of them were never on the list, so they would have passed even here.
    It now compares against what `server.py` actually defines, which cannot go
    stale. The agents are covered by `test_agents.py`, a second surface this
    file deliberately does not reach into.
    """
    from metis_mcp.agent_generator import exposed_tools

    real = set(exposed_tools())
    assert real, "no tools parsed from server.py"

    offenders: list[str] = []
    for path in SKILLS.rglob("*.md"):
        text = path.read_text()
        for name in set(re.findall(r"\bmetis_[a-z_]+\b", text)):
            # `metis_mcp` is the python module, invoked as `python3 -m metis_mcp...`
            if name == "metis_mcp" or name in real:
                continue
            offenders.append(f"{path.relative_to(SKILLS)}:{name}")
    assert not offenders, (
        "these reference tools that do not exist: " + ", ".join(sorted(offenders)))


def test_every_skill_declares_a_name_and_a_description():
    for path in skill_files():
        head = path.read_text().split("---")[1] if "---" in path.read_text() else ""
        assert "name:" in head and "description:" in head, f"{path} lacks frontmatter"


# --------------------------------------------------------------------------
# The router is generated, so it cannot drift.
# --------------------------------------------------------------------------

def test_the_checked_in_router_matches_the_workflow_registry():
    """Atlas keeps four routing tables in sync by hand and they disagree."""
    assert ROUTER.exists(), f"{ROUTER} is missing"
    on_disk = ROUTER.read_text()
    assert HEADER in on_disk, "the router must declare that it is generated"
    body = render_router()
    assert body.strip() in on_disk.strip(), (
        "the checked-in router has drifted from the workflow registry — "
        "run metis_mcp.workflow.routing.write_router() rather than editing it "
        "by hand. (This said 'regenerate it' and named nothing that could, "
        "which left hand-editing as the only option the message forbade.)")


def test_every_workflow_appears_in_the_router():
    on_disk = ROUTER.read_text()
    for code in WORKFLOWS:
        assert f"`{code}`" in on_disk, f"workflow {code} is unroutable"


def test_the_router_names_no_workflow_that_does_not_exist():
    on_disk = ROUTER.read_text()
    for code in re.findall(r"\| `([a-z-]+)` \|", on_disk):
        if code in ("code",):
            continue
        assert code in WORKFLOWS or code.startswith("metis-"), (
            f"the router names {code!r}, which is neither a workflow nor a skill")


def test_routing_is_deterministic_and_refuses_to_guess():
    assert route("build a model for records")[0] == "model-build"
    assert route("generate test cases for x")[0] == "test-generate"
    # The important half: no match is an answer, not a fallback.
    assert route("make me a sandwich")[0] is None
    assert route("")[0] is None


def test_an_ambiguous_request_asks_rather_than_picking():
    """Two workflows matching equally well is exactly when a person should choose."""
    code, why = route("workflow")
    assert code is None, f"an ambiguous request routed to {code}"


# --------------------------------------------------------------------------
# Ported assets keep their provenance.
# --------------------------------------------------------------------------

def test_the_ported_design_gate_runs_and_is_not_atlas_coupled():
    script = SKILLS / "shared" / "scripts" / "check_design_sync.py"
    assert script.exists(), "the one genuinely enforcing gate Atlas had"
    text = script.read_text()
    # Functional coupling, not the word: the provenance note names `.atlas/`
    # deliberately, and erasing the credit to satisfy a crude grep would be the
    # wrong fix. What must not survive is the path being *used*.
    assert '".atlas"' not in text and "'.atlas'" not in text, (
        "the Atlas path must not be constructed any more")
    assert '".metis"' in text, "it must resolve under .metis/ instead"
    assert "--root" in text and "--atlas-root" not in text, "the flag is renamed"
    assert "Ported from Atlas" in text, "provenance is recorded, not erased"


def test_the_shared_knowledge_that_survives_is_the_knowledge_skills_cite():
    """What is in the skill tree must be reachable from a skill.

    The ISO/IEEE files and the two test-design templates were ported from Atlas
    and never rewired: nothing referenced them, and their own cross-references
    named a `test-designer` skill, a "Stage 08 Gate" and a `resources/templates/`
    path that do not exist here. They were retired to `docs/historical/`, and
    that directory has since been deleted along with the rest of the v1 material
    — so this test asserts only what SURVIVED the port, which is the half that
    was ever load-bearing.

    Métis does not render a test-design document from a template; it renders
    test cases from an approved model (`rendering/test_case.py`).
    """
    knowledge = SKILLS / "shared" / "knowledge"
    for expected in ("anti-hallucination-protocol.md",
                     "test-techniques-reference.md"):
        assert (knowledge / expected).exists(), f"{expected} did not survive the port"


def test_every_shared_knowledge_file_is_cited_by_a_skill():
    """The check that would have caught the port drifting in the first place.

    A reference file nothing points at is not a reference, and its own stale
    cross-references rot unnoticed.
    """
    knowledge = SKILLS / "shared" / "knowledge"
    skill_text = "\n".join(
        p.read_text() for p in SKILLS.rglob("*.md") if "shared" not in p.parts)
    for path in knowledge.glob("*.md"):
        assert path.name in skill_text, (
            f"{path.name} is in the skill tree and no skill references it — "
            f"either cite it from a skill or delete it"
        )


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
        except Exception as e:                                    # noqa: BLE001
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
