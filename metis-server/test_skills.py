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

# Commands a SKILL.md may tell the model to run.
#
# **Both spellings, and the second one is the whole point.** This matched only
# `python -m metis_mcp.mbt.cli <verb>` and *no skill has ever used that form* --
# every one of them writes `metis <verb>`, which is what the console script is.
# So the check iterated over an empty set and passed for as long as it existed,
# while `metis data` sat in metis-intake-processor naming a verb the CLI has
# never registered. A test that cannot fail is not a test; the vacuity guard
# below is what stops it silently becoming one again.
#
# Matching bare `metis <word>` anywhere -- prose included -- is deliberate and
# is safe here for a reason worth writing down: the product is spelled `Métis`
# in prose and `metis` only ever names the console script. Anchoring to a
# backtick instead was measured and finds 5 of the 44 real calls, because the
# skills put their commands in fenced blocks rather than inline spans.
_CLI_CALL = re.compile(
    r"(?:metis_mcp\.mbt\.cli|\bmetis)\s+([a-z][a-z-]*)(?:\s+([a-z][a-z-]*))?")


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


def _named_commands() -> list[tuple[str, str]]:
    """Every `(skill, verb)` a SKILL.md or one of its steps tells anyone to run."""
    found: list[tuple[str, str]] = []
    for path in skill_files():
        for text in [path.read_text()] + [p.read_text() for p in
                                          sorted(path.parent.glob("steps/*.md"))]:
            for verb, _sub in _CLI_CALL.findall(text):
                found.append((path.parent.name, verb))
    return found


def test_the_command_scan_is_not_vacuous():
    """The guard on the guard.

    `test_every_command_a_skill_names_is_a_real_cli_verb` cannot fail if it
    finds nothing to check, which is exactly how it passed while naming a dead
    verb. Asserting the scan matched something means the next time the spelling
    of a command changes, this fails loudly instead of quietly checking nothing.
    """
    assert _named_commands(), (
        "no skill names any `metis <verb>` command -- either the skills stopped "
        "naming commands, or _CLI_CALL no longer matches how they spell them. "
        "The second is the failure this test exists for.")


def test_every_command_a_skill_names_is_a_real_cli_verb():
    """The check that would have caught six dead skills on the day they died."""
    verbs = _cli_verbs()
    assert verbs, "could not read the CLI's own subcommand list"

    unknown = [(skill, verb) for skill, verb in _named_commands()
               if verb not in verbs]
    assert not unknown, (
        "skills name CLI verbs that do not exist: "
        + ", ".join(f"{s}:{v}" for s, v in sorted(set(unknown))))


# A tool call as a skill writes one: `design_sections()` in an inline span. This
# is deliberately narrower than the CLI scan above, because a bare word is a
# word -- `coverage` and `impact` are English -- while `` `coverage(` `` is
# unambiguously a call.
_TOOL_CALL = re.compile(r"`(\w+)\(")


def _cited_tools(directory: Path) -> set[str]:
    """Every tool a skill's own prose tells the model to call.

    `SKILL.md` plus the `steps/` and `knowledge/` files that belong to it. A
    nested specialist has its own frontmatter and is scanned as its own skill,
    so its directory is not walked from the parent.
    """
    files = [directory / "SKILL.md"]
    files += sorted(directory.glob("steps/*.md"))
    files += sorted(directory.glob("knowledge/*.md"))
    cited: set[str] = set()
    for path in files:
        if path.exists():
            cited |= set(_TOOL_CALL.findall(path.read_text()))
    return cited


def test_no_skill_still_calls_a_tool_the_server_does_not_expose():
    """A skill calling a tool that does not exist cannot work.

    **This used to compare against a hardcoded list of seven dead names**, and
    that is precisely how twelve phantom tools survived in `.github/agents/`:
    five of them were never on the list, so they would have passed even here.
    It now compares against what `server.py` actually defines, which cannot go
    stale. The agents are covered by `test_agents.py`, a second surface this
    file deliberately does not reach into.

    **The `metis_*` scan it used to do was vacuous and stayed that way through
    the rebuild.** Every tool on the surface is unprefixed now, so a regex for
    `\bmetis_[a-z_]+\b` matched nothing a skill could get wrong -- it could only
    ever have caught a v1 name, and `test_agents.py` already owns that. Scanning
    the call form instead is what makes it capable of failing again.
    """
    from metis_mcp.agent_generator import exposed_tools, read_skills

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


def test_every_tool_a_skill_cites_is_one_it_is_granted():
    """A skill telling the model to call a tool its frontmatter denies.

    `allowed-tools:` is what `agent_generator` turns into the generated agent's
    tool grant, so a tool cited in prose and missing from that list is
    **unreachable**: the skill reads correct, and the agent cannot execute it.
    Nothing caught this class before, because the only tool check asked whether
    the *server* exposed a name -- never whether *this skill* was granted it.

    It found `metis-test-design` telling the model to call `design_standards()`
    while granting fifteen other tools and not that one. The `compliance`
    section it renders was therefore unreachable from the skill that owns it.
    """
    from metis_mcp.agent_generator import exposed_tools, read_skills

    real = set(exposed_tools())
    offenders: list[str] = []
    for skill in read_skills():
        granted = set(skill.tools)
        if not granted:
            # A skill declaring no tools gets the whole surface (see
            # `agent_generator`), so there is nothing to deny.
            continue
        for name in sorted(_cited_tools(skill.directory) & real):
            if name not in granted:
                offenders.append(f"{skill.name} cites {name}() but does not grant it")
    assert not offenders, "\n".join(offenders)


def test_the_granted_tool_scan_is_not_vacuous():
    """The guard on the guard, and this file's own convention.

    The scan above is only meaningful while skills actually write tool calls in
    the form it matches. If the prose style changes, it must fail here rather
    than start passing everywhere.
    """
    from metis_mcp.agent_generator import exposed_tools, read_skills

    real = set(exposed_tools())
    seen = set()
    for skill in read_skills():
        seen |= _cited_tools(skill.directory) & real
    assert len(seen) > 10, (
        f"only {len(seen)} tool calls found in the whole skill tree — the "
        "`name(` form the scan depends on is no longer how skills write them")


def test_every_relative_path_a_skill_writes_resolves():
    """A path written as a path must lead somewhere.

    **Scoped to `../` deliberately.** A backtick span like `steps/01-plan.md`
    is prose naming a file in another skill's tree, and resolving it from the
    citing file would be wrong. A span that opens with `../` is unambiguously a
    relative path from *this* file, so it is checkable and was worth checking:
    it found 24 of them, three hand-written and **21 generated** by
    `knowledge_gen.render_index`, which emitted a specialist's hop count as a
    top-level skill's. A wrong path reproduced into 21 files is the failure
    `docs/academy/10-where-a-thing-belongs.md` warns about from the other side —
    generation does not make a path right, it makes a wrong one uniform.

    Markdown links (`[x](y.md)`) are checked by the same rule and were all
    already sound; the breakage was entirely in backticked spans, which nothing
    had ever looked at.
    """
    offenders: list[str] = []
    for path in SKILLS.rglob("*.md"):
        text = path.read_text()
        written = set(re.findall(r"`(\.\.?/[^`\s]+)`", text))
        written |= {c for c in re.findall(r"\]\(([^)#\s]+)\)", text)
                    if c.startswith(".") and "<" not in c}
        for ref in written:
            if not (path.parent / ref).resolve().exists():
                offenders.append(f"{path.relative_to(SKILLS)} -> {ref}")
    assert not offenders, (
        "these relative paths lead nowhere:\n  " + "\n  ".join(sorted(offenders)))


def test_the_relative_path_scan_is_not_vacuous():
    """The guard on the guard: skills must still be writing relative paths."""
    found = 0
    for path in SKILLS.rglob("*.md"):
        found += len(re.findall(r"`(\.\.?/[^`\s]+)`", path.read_text()))
    assert found > 20, (
        f"only {found} relative paths in the skill tree — the scan above is "
        "no longer looking at anything")


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


def test_no_skill_tells_anyone_to_run_the_unwired_design_gate():
    """A gate with no producer must not be presented as a step.

    `check_design_sync.py` compares a high-level design against its detailed
    form using `SG-xx` group ids and an `overview-source-hash` marker. **Métis
    produces none of those** — `design/document.py` renders one document — so
    the script returns `Missing high-level overview artifact` for every scope,
    every time. `metis-test-generate/SKILL.md` said "run it before the gate",
    which is a guaranteed failure dressed as a procedure: worse than a dead
    reference, because it teaches a reader to ignore a gate that does block.

    The check is conditional rather than absolute, so **wiring it up makes this
    pass instead of having to be deleted**: if anything in `metis_mcp/` starts
    emitting the marker, a skill may instruct running it again.
    """
    engine = Path(__file__).resolve().parent / "metis_mcp"
    produced = any(
        "overview-source-hash" in path.read_text(errors="ignore")
        for path in engine.rglob("*.py"))
    if produced:
        return

    offenders = []
    for path in SKILLS.rglob("*.md"):
        text = path.read_text()
        if "check_design_sync" not in text:
            continue
        # Naming it while saying it is unwired is exactly right; instructing a
        # run is what must not survive. **Quoted spans are stripped first** --
        # the corrected text quotes the instruction it removed in order to say
        # why, and a check that cannot tell a quotation from a directive would
        # forbid explaining the fix.
        prose = re.sub(r'"[^"]*"', "", text)
        # A negated instruction is the correct state, so "do not run it" and
        # "never run it" are not offenders -- only a bare directive is.
        if re.search(r"(?<!do not )(?<!never )\brun it\b", prose, re.I):
            offenders.append(str(path.relative_to(SKILLS)))
    assert not offenders, (
        "nothing in metis_mcp/ emits an `overview-source-hash`, so "
        "check_design_sync.py cannot pass — yet these instruct running it: "
        + ", ".join(offenders))


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
    survivors = (
        SKILLS / "shared" / "knowledge" / "anti-hallucination-protocol.md",
        # Moved out of `shared/knowledge/` and it has now moved once more.
        # `docs/academy/10-where-a-thing-belongs.md` asks two questions and this
        # file answers both against where it sits: ISO/IEC/IEEE 29119-4 "would
        # still be true if Métis were deleted", so it is `references/` rather
        # than `knowledge/` -- a surface the rule defined and the tree had no
        # instance of until this file.
        #
        # **It was skill-local, and the premise of that changed.** The promotion
        # rule counts consumers: one citer means the file belongs to that skill,
        # two or more mean `shared/`. `metis-test-design-technique` is the
        # second citer -- choosing between techniques is exactly what it does --
        # so the file moved to `shared/references/` rather than being copied,
        # which is the outcome the rule exists to prevent.
        SKILLS / "shared" / "references" / "test-techniques-reference.md",
    )
    for expected in survivors:
        assert expected.exists(), f"{expected.name} did not survive the port"


def test_every_shared_knowledge_file_is_cited_by_a_skill():
    """The check that would have caught the port drifting in the first place.

    A reference file nothing points at is not a reference, and its own stale
    cross-references rot unnoticed.
    """
    skill_text = "\n".join(
        p.read_text() for p in SKILLS.rglob("*.md") if "shared" not in p.parts)

    # **Every kind of shared asset, not just the prose.** This globbed
    # `knowledge/*.md` alone, so it guarded a third of the directory: the
    # 830-line UIF schema and the 124-line design-sync gate — together about
    # half the skill tree by volume — were cited by no skill at all, and held
    # alive only by tests. An orphan a test keeps is still an orphan.
    shared = SKILLS / "shared"
    assets = sorted(
        list((shared / "knowledge").glob("*.md"))
        + list((shared / "schemas").glob("*.json"))
        + list((shared / "scripts").glob("*.py"))
        # `references/` too, wherever it appears. The rule defines the surface
        # and until now nothing in the tree used it, so an orphan there would
        # have been invisible to exactly the guard written to catch orphans.
        + [p for p in SKILLS.rglob("references/*.md") if "shared" not in p.parts]
        + list((shared / "references").glob("*.md")))
    assert assets, "no shared assets found — the glob is checking nothing"

    for path in assets:
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


# --------------------------------------------------------------------------
# The plugin manifests.
#
# **Nothing generated or checked these, and all three had gone wrong.** They
# claimed "Five skills" and "Twelve read-only tools", named twelve tools by hand
# — missing `impact`, `describe_policy` and the five authoring tools — and were
# the first thing anyone installing the plugin reads. A count in prose is a
# second place to state a fact, which is exactly what the generated surfaces
# exist to avoid; these tests are the cheapest available substitute for
# generating them.
# --------------------------------------------------------------------------

MANIFESTS = (
    PLUGIN / ".claude-plugin" / "plugin.json",
    PLUGIN.parent / "metis-mcp" / ".claude-plugin" / "plugin.json",
    PLUGIN.parent.parent / ".claude-plugin" / "marketplace.json",
)


def _manifest_text() -> str:
    return "\n".join(p.read_text() for p in MANIFESTS if p.exists())


def test_every_manifest_exists_and_is_valid_json():
    import json

    for path in MANIFESTS:
        assert path.exists(), f"{path} is missing"
        json.loads(path.read_text())


# Enough to read any count a manifest is likely to write out. The map exists to
# PARSE what a manifest says, not to enumerate what it may say -- the previous
# version of these tests carried a hardcoded set of wrong numbers and checked
# only those, so `.claude-plugin/marketplace.json` claiming 22 read-only tools
# passed while there were 28. A guard that only catches the mistakes somebody
# already thought of is the dead-list failure `test_agents.py` was written
# against, reproduced inside the guard.
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "twenty-one": 21, "twenty-two": 22, "twenty-three": 23, "twenty-four": 24,
    "twenty-five": 25, "twenty-six": 26, "twenty-seven": 27,
    "twenty-eight": 28, "twenty-nine": 29, "thirty": 30, "thirty-one": 31,
    "thirty-two": 32, "thirty-three": 33, "thirty-four": 34, "thirty-five": 35,
    "forty": 40, "fifty": 50,
}


def _stated_counts(noun: str) -> list:
    """Every count a manifest states next to `noun`, as (phrase, number).

    Digits and written-out words both, because both forms have drifted here.
    """
    text = _manifest_text().lower()
    found = []
    for match in re.finditer(rf"\b([a-z]+(?:-[a-z]+)?|\d+)\s+{noun}\b", text):
        token = match.group(1)
        if token.isdigit():
            found.append((match.group(0), int(token)))
        elif token in _NUMBER_WORDS:
            found.append((match.group(0), _NUMBER_WORDS[token]))
    return found


def test_no_manifest_states_a_skill_count_that_is_wrong():
    """A written-out number is the form these drifted in last time."""
    from metis_mcp.agent_generator import read_skills

    actual = len(read_skills())
    for phrase, stated in _stated_counts("skills"):
        assert stated == actual, (
            f"a manifest says {phrase!r} and there are {actual} skills")


def test_no_manifest_states_a_tool_count_that_is_wrong():
    from metis_mcp.agent_generator import exposed_tools

    actual = len(exposed_tools())
    for phrase, stated in _stated_counts("read-only tools"):
        assert stated == actual, (
            f"a manifest says {phrase!r} and there are {actual} read-only tools")


def test_the_count_scan_is_not_vacuous():
    """Both guards above pass trivially if the regex matches nothing.

    That is how a manifest could drop its counts entirely and still look
    guarded. At least one count has to be found for the assertions to mean
    anything.
    """
    assert _stated_counts("skills") or _stated_counts("read-only tools"), (
        "no manifest states a skill or tool count -- the scan found nothing, "
        "so the two guards above assert over an empty list")


def test_no_manifest_names_a_tool_the_server_does_not_expose():
    """The mcp manifest listed twelve tools by hand. Naming them at all is the
    problem; naming ones that do not exist is the symptom."""
    import re

    from metis_mcp.agent_generator import exposed_tools

    real = set(exposed_tools())
    text = _manifest_text()
    # Only flag snake_case identifiers, which is how a tool is written.
    named = {m for m in re.findall(r"\b[a-z]+_[a-z_]+\b", text)}
    # Words that look like tools and are not: manifest keys and env vars.
    ignored = {"claude_plugin", "metis_mcp_write", "read_only"}
    unknown = {n for n in named - real - ignored if not n.startswith("metis_")}
    assert not unknown, (
        f"a manifest names identifiers the server does not expose: "
        f"{sorted(unknown)}")


# --------------------------------------------------------------------------
# Specialists.
#
# Nesting is **ownership, not addressing**: a specialist lives under its parent
# on disk and is a flat peer everywhere else — in discovery, in the agent
# surface, in the router. The failure to avoid is a specialist nothing routes to,
# which is the orphan problem in a new place.
# --------------------------------------------------------------------------

def _specialists():
    from metis_mcp.agent_generator import read_skills

    return [s for s in read_skills() if s.parent]


def test_there_are_specialists_to_check():
    """A guard on the guard: the tests below pass trivially if the glob that
    finds specialists ever stops matching."""
    assert _specialists(), "no specialists discovered — check the glob"


def test_every_specialist_is_routed_to_by_its_parent():
    """A specialist nobody routes to is a skill with no way in."""
    for skill in _specialists():
        parent = SKILLS / skill.parent / "SKILL.md"
        assert parent.exists(), f"{skill.name} names a parent that does not exist"
        assert skill.name in parent.read_text(), (
            f"{skill.parent} does not route to {skill.name}")


def test_a_specialist_states_what_its_parent_already_enforces():
    """Ported from Atlas, where each specialist opens by restating the parent's
    rules as satisfied preconditions. Without it a reader cannot tell which rules
    are in force, and the specialist grows a second, drifting copy of them."""
    for skill in _specialists():
        text = (skill.directory / "SKILL.md").read_text()
        assert "Prerequisites, from the parent" in text, (
            f"{skill.name} does not say what its parent already enforces")


def test_a_specialist_is_a_complete_skill_not_a_fragment():
    """Its own frontmatter, its own steps, its own refusals — the property that
    lets it be invoked directly when the family is already known."""
    for skill in _specialists():
        assert skill.tools, f"{skill.name} declares no tools"
        assert list(skill.directory.glob("steps/*.md")), f"{skill.name} has no steps"
        text = (skill.directory / "SKILL.md").read_text()
        assert "## What this skill must not do" in text, (
            f"{skill.name} states no refusals of its own")


def test_a_specialist_name_is_flat():
    """Discovery, the agent surface and the router see a peer. A name carrying a
    path separator would make the nesting an address."""
    for skill in _specialists():
        assert "/" not in skill.name and "\\" not in skill.name


# --------------------------------------------------------------------------
# A plugin README may not hand-list the tools.
#
# `plugins/metis-mcp/README.md` carried a table of twelve while the server
# exposed thirty-one — the whole authoring surface missing — and it is the first
# thing somebody installing the plugin reads. Both existing guards let it
# through: the manifest scan above covers the three `.json` files, and
# `test_documentation_sync` matched a count only when the word "tools" followed
# the phrase, which "Twelve, all read-only:" does not.
#
# So this guards the disease rather than that one symptom. The rule is already
# written in `test_no_manifest_names_a_tool_the_server_does_not_expose`'s own
# docstring: *naming them at all is the problem.* A prose mention of one or two
# tools is useful and stays legal; an enumeration is a second copy of a
# generated fact, and `docs/guide/mcp-tools.md` is the first.
# --------------------------------------------------------------------------

# Naming a few tools in prose is fine — "`list_workflows` is the cheapest check"
# tells a reader something. Five distinct names in list or table rows is an
# inventory, and an inventory drifts.
_INVENTORY = 5


def _tools_enumerated(text: str) -> set:
    """Real tool names appearing in table rows or list items."""
    from metis_mcp.agent_generator import exposed_tools

    real = set(exposed_tools())
    named = set()
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith(("|", "-", "*", "+")):
            continue
        named |= {m for m in re.findall(r"`([a-z_]+)`", stripped) if m in real}
    return named


def test_no_plugin_readme_hand_lists_the_tools():
    readmes = sorted((PLUGIN.parent).glob("*/README.md"))
    assert readmes, "no plugin READMEs found — the glob is checking nothing"

    for path in readmes:
        enumerated = _tools_enumerated(path.read_text())
        assert len(enumerated) < _INVENTORY, (
            f"{path.relative_to(PLUGIN.parent.parent)} enumerates "
            f"{len(enumerated)} tools by hand. That list is a second copy of "
            f"what `metis guide` generates into docs/guide/mcp-tools.md, and it "
            f"is the copy nothing checks. Point at the generated page instead: "
            f"{sorted(enumerated)}")


def test_the_inventory_scan_recognises_a_dead_list():
    """Guarding the guard, against the exact table that was there."""
    from metis_mcp.agent_generator import exposed_tools

    real = sorted(exposed_tools())[:6]
    table = "\n".join(f"| `{t}` | what it answers | yes |" for t in real)
    assert len(_tools_enumerated(table)) == 6

    # And prose naming a tool must stay legal, or the guard is unusable.
    assert _tools_enumerated(
        "Restart your client. `list_workflows` is the cheapest check.") == set()


def test_a_skill_directory_is_named_for_the_skill_it_holds():
    """`risk-manager/` held `metis-risk-manager`, and it was the only one.

    The mismatch is not cosmetic. A specialist records its parent as the
    DIRECTORY name while its own `name:` is the flat agent name, so anything
    joining the two on `name` matched nothing for that one family — silently,
    rendering a parent with an empty specialist list rather than failing.
    """
    for path in SKILLS.glob("*/SKILL.md"):
        block = re.search(r"^name:\s*(.+)$", path.read_text(), re.M)
        assert block, f"{path} declares no name"
        assert block.group(1).strip() == path.parent.name, (
            f"{path.parent.name}/ holds a skill named "
            f"{block.group(1).strip()!r} — name the directory for the skill")


def test_every_specialist_resolves_to_a_real_parent_skill():
    """The join the routing actually depends on.

    A specialist records its parent as the DIRECTORY it sits under, and the
    parent's agent is generated by looking that directory up. If it resolves to
    nothing the parent renders with an empty specialist list and no error — the
    specialist becomes unreachable while every file still looks correct.

    Deliberately NOT asserted: that a specialist's name carries its parent's as
    a prefix. Six of seven do; `metis-release-readiness` under
    `metis-coverage-report/` does not, because it reads as a capability in its
    own right. That is a naming choice, and the join does not rest on it.
    """
    from metis_mcp.agent_generator import read_skills

    skills = read_skills()
    directories = {s.directory.name for s in skills if s.directory and not s.parent}
    specialists = [s for s in skills if s.parent]
    assert specialists, "no specialists found — this would pass vacuously"

    for skill in specialists:
        assert skill.parent in directories, (
            f"{skill.name} records parent {skill.parent!r}, which is not a "
            f"parent skill directory: {sorted(directories)}")
