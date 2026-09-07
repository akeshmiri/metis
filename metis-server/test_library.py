"""The document half of the MCP surface: skills as prompts, documents as resources.

The property under test throughout is that **nothing here is a second copy**.
Prompts and resources are discovered from `plugins/metis/skills/` and `docs/`;
a skill authored in one place must not be restated in the server, and a document
served here must be the file on disk rather than a snapshot of it.
"""
import asyncio

import pytest

from metis_mcp import library, server


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def docs():
    return library.documents()


# --------------------------------------------------------------------------
# Discovery is from the tree, not from a list in this repository's code.
# --------------------------------------------------------------------------

def test_every_skill_becomes_a_prompt(docs):
    """Thirteen skills, thirteen prompts. A skill that gained an agent and no
    prompt would be reachable from one client and not another."""
    from metis_mcp.agent_generator import read_skills

    skills = {s.name for s in read_skills()}
    prompts = {p.name for p in _run(server.mcp.list_prompts())}
    assert prompts == skills, (
        f"prompts and skills disagree: only skills {skills - prompts}, "
        f"only prompts {prompts - skills}")


def test_a_specialist_is_addressed_by_its_flat_name(docs):
    """Nesting is ownership, not addressing — the same rule the agents follow."""
    uris = {d.uri for d in docs}
    assert "metis://skill/metis-model-build-code" in uris
    assert "metis://skill/metis-model-build/specialists/code" not in uris


def test_steps_and_knowledge_are_resources_not_prompt_bodies(docs):
    """**Progressive disclosure is the thing this could most easily break.**

    `SKILL.md` is paid for every time; `steps/` one at a time; `knowledge/` only
    when a step cites it. A prompt that inlined a skill's whole directory would
    spend exactly the budget the folder tree exists to protect.
    """
    body = _run(server.mcp.get_prompt("metis-model-build", {})
                ).messages[0].content.text

    steps = [d for d in docs
             if d.uri.startswith("metis://skill/metis-model-build/steps/")]
    assert steps, "the fixture skill has no steps — this proves nothing"

    for step in steps:
        text = step.path.read_text()
        # The step's own body must not already be inside the prompt.
        longest = max(text.split("\n\n"), key=len).strip()
        assert longest not in body, (
            f"{step.uri} is inlined into the prompt, so its cost is paid "
            f"whether or not a reader needs it")


def test_the_generated_guide_and_the_academy_are_served(docs):
    uris = {d.uri for d in docs}
    assert "metis://guide/mcp-tools" in uris
    assert "metis://spec" in uris
    assert any(u.startswith("metis://academy/") for u in uris)


def test_every_document_resolves_to_a_file_that_exists(docs):
    for doc in docs:
        assert doc.path.is_file(), f"{doc.uri} points at nothing"


def test_uris_are_unique(docs):
    uris = [d.uri for d in docs]
    assert len(uris) == len(set(uris))


# --------------------------------------------------------------------------
# Reading through the protocol returns the file, not a copy of it.
# --------------------------------------------------------------------------

def test_a_resource_returns_the_file_on_disk(docs):
    doc = next(d for d in docs if d.uri == "metis://spec")
    served = list(_run(server.mcp.read_resource(doc.uri)))[0].content
    assert served == doc.path.read_text()


def test_a_prompt_returns_the_skill_and_carries_its_gate():
    text = _run(server.mcp.get_prompt("metis-model-build", {})
                ).messages[0].content.text
    assert text == (library.repo() / "plugins" / "metis" / "skills"
                    / "metis-model-build" / "SKILL.md").read_text()
    # The reason a skill is a prompt rather than a tool, asserted.
    assert "model-approval" in text or "G1" in text


def test_a_description_is_the_documents_own_first_heading(docs):
    step = next(d for d in docs if d.kind == "steps")
    heading = next(l[2:].strip() for l in step.path.read_text().splitlines()
                   if l.startswith("# "))
    assert step.description == heading


# --------------------------------------------------------------------------
# Absence is reported, never presented as an empty library.
# --------------------------------------------------------------------------

def test_a_deployment_without_the_repository_says_so(tmp_path, monkeypatch):
    """A `pip install` with no repository beside it has the tools and none of
    the procedure. Serving zero prompts silently is how a caller concludes a
    skill does not exist — the same distinction the UIF schema check draws."""
    monkeypatch.setattr(library, "repo", lambda: tmp_path)

    ok, why = library.available()
    assert not ok
    assert "plugins" in why or "docs" in why

    described = library.describe()
    assert described["available"] is False
    assert described["prompts"] == 0
    assert described["reason"]

    with pytest.raises(library.LibraryUnavailable):
        library.documents()


def test_describe_counts_match_what_is_registered(docs):
    described = library.describe()
    assert described["resources"] == len(docs)
    assert described["prompts"] == len(_run(server.mcp.list_prompts()))
    assert described["resources"] == len(_run(server.mcp.list_resources()))


def test_the_tool_reports_the_same_thing():
    import json

    from metis_mcp.agent_generator import read_skills

    # Derived, not hardcoded. This said `== 13` and became wrong the first time
    # a skill was added — which is the failure mode the count guards elsewhere in
    # the suite exist to catch, reproduced inside a test.
    expected = len(read_skills())
    assert expected > 1, "no skills discovered — this would pass as 0 == 0"
    payload = json.loads(server.describe_library())
    assert payload["available"] is True
    assert payload["prompts"] == expected
    assert payload["by_kind"]["skill"] == expected


# --------------------------------------------------------------------------
# N-8 survives the addition.
# --------------------------------------------------------------------------

def test_the_document_surface_reaches_no_write_path():
    """Prompts and resources are files. Nothing here may reach a decision."""
    import subprocess
    import sys
    from pathlib import Path

    probe = ("import os, sys; os.environ.pop('METIS_MCP_WRITE', None)\n"
             "import metis_mcp.library, metis_mcp.server\n"
             "bad = [m for m in sys.modules if m.startswith((\n"
             "    'metis_mcp.write', 'metis_mcp.decide',\n"
             "    'metis_mcp.review.decisions', 'metis_mcp.publishing'))]\n"
             "print(','.join(sorted(bad)))\n")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, cwd=Path(__file__).parent)
    assert out.stdout.strip() == "", out.stdout + out.stderr


def test_no_resource_is_a_uri_template():
    """Concrete resources only. A template over a caller-supplied path would
    put traversal on a read-only surface; a fixed list cannot."""
    templates = _run(server.mcp.list_resource_templates())
    assert not templates, f"a URI template is registered: {templates}"


# --------------------------------------------------------------------------
# Discoverability. The decorator does not exist, so something else must answer.
#
# `server.py`'s convention is that `grep '@mcp.tool'` enumerates the surface.
# Prompts and resources are discovered rather than declared, so that grep finds
# nothing for them — and a reader following the file's own stated convention
# concludes there are no prompts. That happened.
#
# Thirteen `@mcp.prompt` decorators would fix the grep and break the thing the
# grep is for: they would be a second copy of `plugins/metis/skills/`, stale the
# first time somebody adds a skill. So the inventory moved to the generated
# guide, and these tests are what stop it rotting there instead.
# --------------------------------------------------------------------------

def _guide_page() -> str:
    return (library.repo() / "docs" / "guide" / "mcp-tools.md").read_text()


def test_the_guide_names_every_prompt():
    """The enumeration `grep '@mcp.prompt'` cannot provide."""
    page = _guide_page()
    prompts = [p.name for p in _run(server.mcp.list_prompts())]
    assert prompts, "no prompts registered — this proves nothing"
    missing = [name for name in prompts if f"`{name}`" not in page]
    assert not missing, (
        f"docs/guide/mcp-tools.md is the inventory now, and it does not name "
        f"{missing}. Run `metis guide`.")


def test_the_guide_names_no_prompt_that_does_not_exist():
    """The other direction — the failure the plugin README shipped with."""
    import re

    from metis_mcp.agent_generator import read_skills

    page = _guide_page()
    section = page[page.index("### The prompts"):]
    named = set(re.findall(r"^- `([a-z-]+)`", section, re.M))
    real = {s.name for s in read_skills()}
    assert named <= real, f"the guide names prompts that do not exist: {named - real}"


def test_a_reader_who_greps_for_the_absent_decorator_lands_on_the_reason():
    """**The specific failure, guarded.**

    Someone searched `@mcp.prompt`, found nothing, and reasonably concluded the
    server had no prompts. The string has to appear in the file that would have
    carried the decorator, attached to the reason it does not.
    """
    source = (library.repo() / "metis-server" / "metis_mcp"
              / "server.py").read_text()

    # It must not actually be a decorator — that would mean a hand-written list.
    assert "\n@mcp.prompt" not in source, (
        "a prompt is declared by hand, which restates the skill tree in Python")

    assert "@mcp.prompt" in source, (
        "server.py never mentions `@mcp.prompt`, so a reader who greps for it "
        "finds nothing and concludes there are no prompts")

    where = source.index("@mcp.prompt")
    nearby = source[max(0, where - 500):where + 1500]
    assert "docs/guide/mcp-tools.md" in nearby, (
        "the explanation does not say where the inventory actually lives")
