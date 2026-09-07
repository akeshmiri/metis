"""
Rendered test cases as a `.feature` file.

**Gherkin is specification, not code, which is the only reason this exists
here.** `rendering/__init__` states the rule the deleted `generators/` package
broke: Métis says what must be verified and whether it is covered, and
producing the implementation belongs to whatever executes the test. A feature
file is the first half of that — the steps are sentences, and the step
definitions that bind them to a system are written in Cucumber, Behave, SpecFlow
or whatever the team already runs. Nothing here emits any.

**Separate from `specgen/gherkin.py`, deliberately.** That module renders
*stated intent*: one `Requirement`, its `AcceptanceCriterion` children as
scenarios, each with exactly one `Given`. This renders *recovered behaviour*: a
path through the machine, whose setup is N steps and therefore N `Given`
clauses. The two are not the same artefact and must not round-trip into each
other — `feature read` turns a file into acceptance criteria, and reading these
back would file a recovered path as somebody's stated requirement, which is the
one confusion the whole intent/recovery split exists to prevent.

The Gherkin dialect itself is shared, so both emitters indent alike.
"""
from __future__ import annotations

from metis_mcp.rendering.test_case import INPUT, TestCase
from metis_mcp.specgen.gherkin import INDENT, STEP_INDENT, _wrap

# The sentence a reader needs before they wire anything up. Kept in the
# artefact rather than only in our docs: this file lands in somebody's test
# repository, where our documentation is not.
BOUNDARY_NOTE = (
    "These steps are specification, not code. The step definitions that bind "
    "them to a running system belong to your test framework — Métis does not "
    "generate them, and never executes anything against the system it models."
)

PROVENANCE_NOTE = (
    "Recovered from source by Métis. Every scenario is one path through the "
    "behaviour model and carries exactly one assertion (T-1a)."
)


def _tag(text: str) -> str:
    """A Gherkin tag: no whitespace, since a space starts a second tag."""
    return "@" + "-".join(str(text).split())


def scenario_lines(case: TestCase) -> list[str]:
    """One case as a `Scenario` block.

    Setup steps come before the state they establish, matching `format_case` —
    naming the state first and then the steps that produce it reads backwards.
    """
    lines = [f"{INDENT}{_tag(case.id)}",
             f"{INDENT}Scenario: {case.name}"]

    givens: list[tuple[str, str]] = [
        (step.description, step.guard_verbatim) for step in case.precondition_steps]
    givens.append((case.given or "the system is in the initial state", ""))

    for n, (text, guard) in enumerate(givens):
        lines.append(f"{STEP_INDENT}{'Given' if n == 0 else 'And'} {text}")
        if guard:
            lines.append(f"{STEP_INDENT}# condition as recovered: {guard}")

    lines.append(f"{STEP_INDENT}When {case.act_step.description}")
    if case.act_step.guard_verbatim:
        lines.append(
            f"{STEP_INDENT}# condition as recovered: {case.act_step.guard_verbatim}")

    lines.append(f"{STEP_INDENT}Then {case.act_step.expected_result}")

    # **Comments, not steps (T-5).** A guard is evidence of a condition the code
    # branches on; a data requirement is something to prepare. Neither is an
    # instruction to perform, and rendered as a step a reader would look for a
    # step definition binding `NOT credentials_valid` to an action. There is
    # none, and there should not be.
    inputs = [r for r in case.data_requirements if r.kind == INPUT]
    others = [r for r in case.data_requirements if r.kind != INPUT]
    for requirement in inputs:
        lines.append(f"{STEP_INDENT}# request data: {requirement.condition} "
                     f"({requirement.where})")
    for requirement in others:
        lines.append(f"{STEP_INDENT}# test data: {requirement.condition} "
                     f"({requirement.where})")
    if case.data_note:
        lines.append(f"{STEP_INDENT}# why this case: {case.data_note}")
    return lines


def feature_for(model, cases, *, criterion: str = "") -> str:
    """A `.feature` file for one model's rendered cases.

    Deterministic: same input, same bytes (TR-6/P-7). Cases are emitted in the
    order `render` produced them, which is itself ordered.
    """
    tags = [_tag("metis"), _tag(model.id)]
    if criterion:
        tags.append(_tag(criterion))

    lines: list[str] = [" ".join(tags), f"Feature: {model.id}"]
    lines += _wrap(PROVENANCE_NOTE)
    lines.append("")
    for wrapped in _wrap(BOUNDARY_NOTE):
        lines.append(f"{INDENT}# {wrapped.strip()}")
    lines.append("")

    for case in cases:
        lines += scenario_lines(case)
        lines.append("")

    # An empty suite is a real state — a model with nothing generatable — and
    # saying so beats a file that reads like a rendering failure. The same
    # choice `specgen.render_feature` makes for a requirement with no criteria.
    if not cases:
        lines.append(f"{INDENT}# No scenarios. Nothing in this model is both "
                     f"approved and generatable,")
        lines.append(f"{INDENT}# so there is no path to state as an example.")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
