"""
Routing: turning a request into a workflow (application spec §9.2).

**Generated from the workflow registry, never hand-maintained.** Atlas keeps four
overlapping routing tables in prose and they already contradict each other about
where `analyze <KEY>` goes; its executable router is illustrative pseudocode in a
markdown file, and the test script its docs tell you to run does not exist. The
failure mode is not that routing is hard — it is that a table nobody generates
drifts from the thing it routes to, silently.

So the table is emitted from `stages.WORKFLOWS`, and `test_skills.py` asserts the
checked-in file matches. A workflow added without a routing entry, or an entry
naming a workflow that no longer exists, fails the build.

**No match asks.** Tier order resolves the common cases; anything else prints the
menu and stops. Guessing which workflow a request meant is how a run lands in the
wrong place and produces a confident, wrong artefact.
"""
from __future__ import annotations

import re

from metis_mcp.agent_generator import read_skills
from metis_mcp.workflow.stages import WORKFLOWS, Workflow

HEADER = "<!-- generated from metis_mcp/workflow/stages.py — do not edit by hand -->"

# Tier order. Explicit beats inferred, and a named workflow beats a keyword,
# because the cost of guessing wrong rises as the signal gets weaker.
TIER_EXPLICIT = "explicit workflow name"
TIER_PATTERN = "entry pattern"
TIER_NONE = "no match — ask"


def _use_when(description: str) -> str:
    """The "Use when ..." clause a skill description already carries.

    Every skill states its own trigger; restating it here in different words is
    how the two come to disagree. Falls back to the first sentence for a
    description that does not follow the convention -- reported by being visibly
    generic, rather than by inventing a trigger.
    """
    match = re.search(r"\bUse when\b(.*?)(?:\.|$)", description, re.S)
    if match:
        clause = " ".join(match.group(1).split()).strip()
        return (clause[:1].upper() + clause[1:]) if clause else description
    return " ".join(re.split(r"(?<=[.!?])\s+", description.strip(), maxsplit=1)[0].split())


def _keywords(workflow: Workflow) -> list[str]:
    """The distinctive words of a workflow's entry patterns, minus placeholders."""
    words: list[str] = []
    for pattern in workflow.entry_patterns:
        for token in re.findall(r"[a-z]+", pattern.lower()):
            if token not in ("a", "the", "for", "of", "to") and token not in words:
                words.append(token)
    return words


def route(request: str) -> tuple[str | None, str]:
    """`(workflow_code, why)`. Returns `None` when nothing matches — never a guess."""
    text = (request or "").lower().strip()
    if not text:
        return None, TIER_NONE

    for code in sorted(WORKFLOWS):
        if code in text:
            return code, TIER_EXPLICIT

    # Score by how many of a workflow's distinctive words appear. A tie is not
    # broken arbitrarily: it is reported as no match, because two workflows
    # matching equally well is exactly when a person should choose.
    scores = {code: sum(1 for w in _keywords(wf) if w in text)
              for code, wf in WORKFLOWS.items()}
    best = max(scores.values(), default=0)
    if best == 0:
        return None, TIER_NONE
    winners = [c for c, s in scores.items() if s == best]
    if len(winners) > 1:
        return None, TIER_NONE
    return winners[0], TIER_PATTERN


def render_router() -> str:
    """The routing table, as the agent file's body."""
    lines = [
        HEADER,
        "",
        "# Métis — Workflow Router",
        "",
        "Every request to Métis runs a **defined workflow**: an ordered set of",
        "stages with explicit gates, rather than a set of commands somebody has to",
        "remember the order of. This table is generated from the workflow registry",
        "(`metis_mcp/workflow/stages.py`); a test fails if it drifts.",
        "",
        "## Quick Routing",
        "",
        "| Ask for | Workflow | What it does |",
        "|---|---|---|",
    ]
    for code, workflow in sorted(WORKFLOWS.items()):
        asks = " / ".join(f"\"{p}\"" for p in workflow.entry_patterns) or "—"
        lines.append(f"| {asks} | `{code}` | {workflow.summary} |")

    lines += [
        "",
        "## What each workflow stops for",
        "",
        "| Workflow | Stages | Gate |",
        "|---|---|---|",
    ]
    for code, workflow in sorted(WORKFLOWS.items()):
        stages = " → ".join(s.name for s in workflow.ordered)
        gates = ", ".join(s.name for s in workflow.ordered if s.is_gate) or "none"
        lines.append(f"| `{code}` | {stages} | {gates} |")

    lines += [
        "",
        "## Running one",
        "",
        "```",
        "python3 -m metis_mcp.mbt.cli workflow list",
        "python3 -m metis_mcp.mbt.cli workflow run <code> --scope <scope> [...]",
        "python3 -m metis_mcp.mbt.cli workflow status <code>--<scope>",
        "python3 -m metis_mcp.mbt.cli workflow resume <code> --scope <scope> [...]",
        "```",
        "",
        "Exit `0` complete · **`5` blocked on a human decision, not a failure** ·",
        "anything else failed.",
        "",
        "## Preconditions are checked, not remembered",
        "",
    ]
    for code, workflow in sorted(WORKFLOWS.items()):
        if workflow.preconditions:
            lines.append(f"- `{code}` requires: "
                         + ", ".join(f"`{p}`" for p in workflow.preconditions))
    lines += [
        "",
        "These are registered predicates evaluated before the first stage runs —",
        "so \"this workflow needs that one to have happened first\" is enforced,",
        "not documented.",
        "",
        "## No match",
        "",
        "If a request matches nothing above, or matches two workflows equally,",
        "**ask which one the user wants**. Do not guess: a run started in the",
        "wrong workflow produces a confident artefact about the wrong thing.",
        "",
        "## Skills",
        "",
        "| Skill | Use when |",
        "|---|---|",
    ]
    # Read from the skills' own frontmatter, not from a list kept here by hand.
    # This table WAS hand-maintained, in the one module whose docstring says the
    # failure mode is "a table nobody generates drifts from the thing it routes
    # to" -- and it had already drifted: a fifth skill existed and was not listed.
    lines += [f"| `{skill.name}` | {_use_when(skill.description)} |"
              for skill in read_skills()]
    lines += [
        "",
        "Direct CLI verbs (`paths`, `render`, `report`, `spec`, `coverage-gap`,",
        "`drift`, `publish`) remain available for single steps and automation;",
        "they are stages, and running one by hand skips the ordering the workflow",
        "enforces.",
    ]
    return "\n".join(lines) + "\n"


def write_router(target=None) -> list:
    """Write the router surface, preserving its frontmatter.

    **The gap this closes.** `render_router` produced the body and nothing wrote
    it, so `test_the_checked_in_router_matches_the_workflow_registry` told a
    reader to "regenerate it rather than editing it by hand" while offering no
    way to regenerate it — leaving hand-editing as the only option the failure
    message forbade. `agent_generator.write` skips this file deliberately
    (it comes from the workflow registry, not from a skill), which is correct
    and is why the writer belongs here instead.

    The frontmatter is kept rather than regenerated: `name` and `description`
    are what a client dispatches on, they are authored, and no part of them is
    derived from the registry.
    """
    from pathlib import Path

    from metis_mcp.agent_generator import AGENT_TARGETS

    body = render_router().strip() + "\n"
    targets = ([Path(target)] if target
               else [directory / "metis.agent.md" for directory in AGENT_TARGETS])

    # A target directory that carries no router is not an error: agents are
    # published to more than one place and only the plugin surface ships the
    # router. Writing to ALL of them and finding NONE is the error.
    present = [path for path in targets if path.exists()]
    if not present:
        raise FileNotFoundError(
            f"no router found at any of {[str(t) for t in targets]}. This "
            f"rewrites the generated body of an existing router and does not "
            f"invent its frontmatter.")

    written = []
    for path in present:
        existing = path.read_text()
        head, marker, _ = existing.partition(HEADER)
        if not marker:
            raise ValueError(
                f"{path} carries no generated marker, so there is no boundary "
                f"between its authored frontmatter and its generated body")
        path.write_text(head + HEADER + "\n\n" + body)
        written.append(path)
    return written
