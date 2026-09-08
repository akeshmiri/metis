"""The sibling-practice comparison (`metis_mcp/parity.py`), asserted both ways.

**The failure this prevents.** "Have we compared Métis against the practice it
was ported from?" was answerable only by doing the comparison again, and every
answer was somebody's recollection. A registry fixes that only if something
checks it — otherwise it is one more hand-maintained index, which
`docs/academy/10-where-a-thing-belongs.md` says twice is the thing that rots.

So: every `covered` entry must name a Métis surface that exists on disk or in
the server, every entry must carry a reason, and every `open` entry must carry
the condition that would close it — because an open item with no condition is a
complaint rather than a plan.
"""
from __future__ import annotations

import re
from pathlib import Path

from metis_mcp import parity

ROOT = Path(__file__).resolve().parent
SKILLS = ROOT.parent / "plugins" / "metis" / "skills"
ENGINE = ROOT / "metis_mcp"


def test_there_are_entries_to_check():
    """The guard on the guard."""
    assert len(parity.ENTRIES) >= 20, "the register has been emptied"


def test_every_verdict_is_one_of_the_three():
    for entry in parity.ENTRIES:
        assert entry.verdict in parity.VERDICTS, (
            f"{entry.name} carries an unknown verdict: {entry.verdict!r}")


def test_every_entry_says_why():
    """A verdict with no reason is a vote.

    Especially a `refused` one: a refusal that does not say why is
    indistinguishable, six months later, from something nobody got to.
    """
    for entry in parity.ENTRIES:
        assert len(entry.because) > 60, (
            f"{entry.name} gives no real reason: {entry.because!r}")


def test_every_open_entry_carries_the_condition_that_would_close_it():
    """The property that keeps `open` from becoming a permanent grievance."""
    for entry in parity.entries_with(parity.OPEN):
        assert entry.condition.strip(), (
            f"{entry.name} is open and states no condition for closing it")
        assert len(entry.condition) > 30, (
            f"{entry.name}'s condition says too little to act on")


def test_only_covered_entries_name_a_surface():
    """A refusal or a gap naming an owner would read as covered."""
    for entry in parity.ENTRIES:
        if entry.verdict == parity.COVERED:
            assert entry.answered_by, f"{entry.name} is covered by nothing"
        else:
            assert not entry.answered_by, (
                f"{entry.name} is {entry.verdict} and names {entry.answered_by}")


def test_only_open_entries_carry_a_condition():
    for entry in parity.ENTRIES:
        if entry.verdict != parity.OPEN:
            assert not entry.condition, (
                f"{entry.name} is {entry.verdict} and carries a close condition")


# --------------------------------------------------------------------------
# The half that can actually go stale: what `covered` points at.
# --------------------------------------------------------------------------

def _skill_names() -> set[str]:
    names = set()
    for path in SKILLS.rglob("SKILL.md"):
        head = path.read_text().split("---")
        match = re.search(r"^name:\s*(\S+)", head[1] if len(head) > 1 else "", re.M)
        if match:
            names.add(match.group(1))
    return names


def _tool_names() -> set[str]:
    from metis_mcp.agent_generator import exposed_tools

    # Write- and outward-tier tools are real and absent at the default policy,
    # so they are parsed from the source rather than taken from the read list.
    source = (ENGINE / "server.py").read_text()
    gated = set(re.findall(r"(?:write|decide|flow|read|outward_tools)\.(\w+)",
                           source))
    return set(exposed_tools()) | gated


def test_the_surface_scan_is_not_vacuous():
    assert len(_skill_names()) > 10, "no skills discovered"
    assert len(_tool_names()) > 30, "no tools discovered"


def test_every_covered_entry_names_something_that_exists():
    """The assertion that makes this a check rather than a claim.

    A `covered` entry naming a renamed or deleted skill is how a comparison
    quietly becomes wrong while still reading as complete.
    """
    skills, tools = _skill_names(), _tool_names()
    offenders: list[str] = []
    for entry in parity.entries_with(parity.COVERED):
        for surface in entry.answered_by:
            if surface in skills or surface in tools:
                continue
            # A path or a CLI verb: assert the path exists, or that the verb
            # appears in the CLI parser.
            if surface.endswith("/"):
                if (ROOT.parent / surface).exists() or (ENGINE / surface).exists():
                    continue
            if surface.startswith("metis "):
                if surface.split(" ", 1)[1] in (ENGINE / "mbt" / "cli.py").read_text():
                    continue
            if "." in surface:  # a dotted module attribute, e.g. publishing.TRANSPORTS
                module, _, attribute = surface.rpartition(".")
                path = ENGINE / (module.replace(".", "/") + ".py")
                if path.exists() and attribute in path.read_text():
                    continue
                package = ENGINE / module.replace(".", "/") / "__init__.py"
                if package.exists():
                    continue
            if surface in (ENGINE / "ontology" / "labels.py").read_text():
                continue
            offenders.append(f"{entry.name} -> {surface}")
    assert not offenders, (
        "these covered entries name a surface that does not exist: "
        + ", ".join(offenders))


def test_the_two_unreachable_modules_are_recorded_as_open():
    """`risk/verdict.py` and `rendering/fidelity.py` have no importer.

    This asserts the register keeps saying so **while it is true**, and — the
    part that matters — stops saying so when it stops being true: wiring either
    module up makes this test demand the entry be closed, rather than leaving a
    stale `open` behind.
    """
    for module, entry_name in (("risk/verdict.py", "release-verdict"),
                               ("rendering/fidelity.py", "source-fidelity")):
        dotted = module.replace("/", ".").removesuffix(".py")
        importers = [
            path for path in ENGINE.rglob("*.py")
            if path != ENGINE / module
            and re.search(rf"\b{re.escape(dotted)}\b|import {dotted.split('.')[-1]}\b",
                          path.read_text())]
        entry = parity.entry_for(entry_name)
        assert entry is not None, f"{entry_name} is not in the register"
        if importers:
            assert entry.verdict == parity.COVERED, (
                f"{module} now has importers {[p.name for p in importers]} — "
                f"close the {entry_name!r} entry instead of leaving it open")
        else:
            assert entry.verdict == parity.OPEN, (
                f"{module} still has no importer and {entry_name!r} is not open")


def test_a_closed_entry_names_a_surface_the_engine_actually_reaches():
    """The specific regression the register exists to prevent.

    Three entries were closed by wiring a module that had no importer. If any of
    those wires is removed, the entry must reopen rather than keep claiming
    coverage — which is the same bidirectional property the two-unreachable test
    has, applied to the ones that are now reached.
    """
    wired = {
        "release-verdict": ("risk.verdict", "risk import verdict"),
        "source-fidelity": ("rendering.fidelity", "rendering import fidelity"),
        "bug-reporter": ("defects.classify", "defects import classify"),
    }
    for name, needles in wired.items():
        entry = parity.entry_for(name)
        assert entry is not None, f"{name} left the register"
        importers = [
            path for path in ENGINE.rglob("*.py")
            if any(re.search(re.escape(n).replace(r"\ ", r"\s+"), path.read_text())
                   for n in needles)
            and "parity.py" not in path.name]
        if entry.verdict == parity.COVERED:
            assert importers, (
                f"{name} is recorded as covered and nothing in metis_mcp/ "
                f"imports what closed it")


def test_describe_serves_the_counts_and_states_what_it_does_not_claim():
    served = parity.describe()
    assert served["entries"]
    assert sum(served["counts"].values()) == len(parity.ENTRIES)
    assert "does_not_claim" in served
    assert "equivalently" in served["does_not_claim"], (
        "the register must not read as a claim that covered means equivalent")
