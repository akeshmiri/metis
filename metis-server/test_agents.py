"""
The client agents are a view, not a second source (§9.5, N-8).

**They had drifted completely.** All five agents under `.github/agents/` declared
MCP tools — `metis_get_context`, `metis_get_traceability`, `metis_check_coverage`
and nine more — and **not one existed**: twelve referenced, seven exposed, zero
overlap. Three of the six skills they documented had been deleted. The endpoint
was still `https://REPLACE-metis-host.example.com/mcp`.

`test_skills.py` has a guard for exactly this and could not see it, for two
reasons worth stating because they are the general lesson:

  * it scans `plugins/metis/skills/` only, and the agents are a **second surface**
    outside that path;
  * it checks a **hardcoded list of seven dead names**, so the five newer dead
    names would have passed even inside `skills/`.

So the tests below compare against what the code *actually exposes*, never
against a list someone has to remember to update.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from metis_mcp.agent_generator import (
    AGENT_TARGETS, AGENTS, exposed_tools, generate, read_skills, stale_agents,
)
from metis_mcp.workflow.stages import WORKFLOWS

_DECLARED = re.compile(r"^tools:\n((?:- .+\n)+)", re.M)


def _agent_files():
    return sorted(AGENTS.glob("*.agent.md"))


def _declared_tools(text: str) -> list[str]:
    block = _DECLARED.search(text)
    return ([line[2:].strip() for line in block.group(1).splitlines()]
            if block else [])


def test_every_tool_an_agent_declares_is_one_the_server_exposes():
    """Compared against `server.py` itself, so this cannot go stale.

    A hardcoded dead-list is what let twelve phantom tools survive: it only ever
    catches the names someone thought to write down.
    """
    real = set(exposed_tools())
    assert real, "no tools parsed from server.py — the parser is broken, not the agents"

    phantom = []
    for path in _agent_files():
        for tool in _declared_tools(path.read_text()):
            if tool not in real:
                phantom.append(f"{path.name}:{tool}")
    assert not phantom, (
        f"these declare tools the server does not expose: {', '.join(sorted(phantom))}. "
        f"Real surface: {', '.join(sorted(real))}")


def test_no_agent_mentions_a_v1_tool_name_anywhere_in_its_body():
    """Not just the frontmatter. Prose telling a user to "call
    `metis_mine_requirements`" fails exactly as hard as a declaration."""
    real = set(exposed_tools())
    offenders = []
    for path in _agent_files():
        for name in set(re.findall(r"\bmetis_[a-z_]+\b", path.read_text())):
            if name == "metis_mcp" or name in real:
                continue
            offenders.append(f"{path.name}:{name}")
    assert not offenders, (
        f"v1 tool names still referenced: {', '.join(sorted(offenders))}")


def test_every_agent_names_a_skill_that_exists():
    """Three agents documented skills that had been deleted."""
    names = {s.name for s in read_skills()}
    assert names, "no skills found"
    for path in _agent_files():
        assert path.name.replace(".agent.md", "") in names, (
            f"{path.name} has no corresponding skill")


def test_every_skill_has_an_agent():
    """The other direction. `metis-model-build` existed with no agent at all, so
    the one workflow that can actually run end to end was unreachable."""
    for skill in read_skills():
        assert (AGENTS / f"{skill.name}.agent.md").exists(), (
            f"{skill.name} has no agent")


def test_the_checked_in_agents_match_the_generator():
    """Same discipline as `test_ontology.py` asserting the schema matches
    `labels.py`: a generated artefact that has been hand-edited is a second
    source of truth, which is what drifted in the first place."""
    for filename, expected in generate().items():
        path = AGENTS / filename
        assert path.exists(), f"{filename} is missing — regenerate"
        assert path.read_text() == expected, (
            f"{filename} differs from the generator. Do not hand-edit; "
            f"run metis_mcp.agent_generator.write()")


def test_no_stale_agent_survives_a_regeneration():
    assert {p.name for p in _agent_files()} == set(generate()), (
        "an agent exists that the generator does not produce — a deleted skill "
        "leaves its agent behind unless the stale one is removed")


def test_the_placeholder_endpoint_is_gone():
    """`mcp_server: https://REPLACE-metis-host.example.com/mcp` shipped in
    `spec-aware.agent.md` — a fake host nobody replaced."""
    for path in _agent_files():
        assert "REPLACE-" not in path.read_text(), f"{path.name} has a placeholder"


def test_agents_state_what_the_build_cannot_do():
    """An agent advertising a capability it lacks fails in front of a user
    mid-task. The absent ones are named rather than quietly omitted."""
    for path in _agent_files():
        text = path.read_text()
        assert "does not have" in text
        for absent in ("impact analysis", "traceability", "read-only"):
            assert absent in text, f"{path.name} does not mention {absent}"


def test_every_workflow_is_listed_for_the_client():
    for path in _agent_files():
        text = path.read_text()
        for code in WORKFLOWS:
            assert code in text, f"{path.name} omits workflow {code}"


# --------------------------------------------------------------------------
# Every agent surface, not just the one somebody remembered
# --------------------------------------------------------------------------

def test_no_agent_surface_carries_a_file_no_skill_produces():
    """The rot this closes was real and invisible to both existing tests.

    `plugins/metis/agents/` held four agents for skills that had been deleted,
    naming twelve MCP tools the server does not expose, and linking to a
    `metis-onboarding/SKILL.md` that no longer exists. `test_skills.py` scans
    `skills/` and the router; this file scanned `.github/agents/`. The plugin's
    own agent directory was a third surface, generated by nothing and checked by
    nothing — while every file in it carried a "GENERATED … do not hand-edit"
    banner.
    """
    for target in AGENT_TARGETS:
        assert stale_agents(target) == [], (
            f"{target} carries agent file(s) no live skill produces: "
            f"{[p.name for p in stale_agents(target)]}. Regenerate with "
            f"agent_generator.write()")


def test_every_surface_has_an_agent_for_every_skill():
    for target in AGENT_TARGETS:
        for skill in read_skills():
            assert (target / f"{skill.name}.agent.md").exists(), (
                f"{skill.name} has no agent in {target}")


def test_the_surfaces_do_not_disagree():
    """One generator, one content. Two copies that differ are two answers."""
    for filename, content in generate().items():
        rendered = {t: (t / filename).read_text() for t in AGENT_TARGETS}
        assert len(set(rendered.values())) == 1, (
            f"{filename} differs between agent surfaces")
        for text in rendered.values():
            assert text == content, f"{filename} has drifted from the generator"


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
