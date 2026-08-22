"""
Building the declared layer from a specification's contracts (§5.2, M-13; X-5).

**What this closes.** `Endpoint -[:IMPLEMENTS]-> Specification` and
`Action -[:IMPLEMENTS]-> Specification` are in the catalogue and nothing wrote
them, so §4.1's comparison at the `Specification` node had only one side: intent
arrived, and the code never did.

A specification names the **published contracts** it is stated in — an OpenAPI
document, a structure file — and this builds the declared layer from those and
links each artefact back.

**Why this is not circular, and the distinction is the whole point.** A
specification does not generate an endpoint from its own prose. It names a
document, and the *document* is parsed. `openapi.to_report` reads what the
service promises; `structure.load` reads what a screen presents. Neither asks
the specification's sentence anything.

That leaves three separable accounts of the same system, which is more than
Métis had before:

    intent          somebody said it should behave this way
    declared        the published contract says it behaves this way
    code            static analysis says the code does this

`M-13` already keeps the second and third apart -- `declared_contract` is a
distinct extraction method precisely because "the document says this" and "the
code does this" are weighed differently by a reviewer. A disagreement between
any pair is a finding, and folding them into one would destroy the only thing
worth having here.

**Nothing is invented for a contract that will not parse.** X-5's gate is
unchanged: a report with parse errors stops the run rather than landing a
partial view of an endpoint set. A human-written OpenAPI document gets no
exemption.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from metis_mcp.model_sources.intent import CONTRACT_OPENAPI, CONTRACT_STRUCTURE


@dataclass
class BuildResult:
    """What was built, from which contract, and what refused."""

    endpoints: int = 0
    pages: int = 0
    actions: int = 0
    linked: int = 0
    # F-10: a contract that could not be read is named with its reason, never
    # skipped into silence.
    refused: list[tuple[str, str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.refused


def build_openapi(spec_id: str, path: str, journey: str, episode_id: str):
    """One OpenAPI document → the declared endpoint layer, linked to its spec.

    Returns `(plan, notes)`. Raises `ValueError` when the contract does not
    parse -- X-5's gate, which a caller reports rather than swallows.
    """
    from code_analysis.contract import validate_report
    from code_analysis.openapi import load as load_spec
    from code_analysis.openapi import to_report
    from metis_mcp.model_sources.raw_landing import plan_raw_landing

    adapter = to_report(load_spec(path), repo=journey or "openapi",
                        commit="", document=str(path))
    errors = validate_report(adapter.report)
    if errors:
        raise ValueError(f"failed the contract ({len(errors)} error(s)): {errors[0]}")

    plan = plan_raw_landing(adapter.report, journey=journey, repo=journey or "openapi")

    # The link back. Planned against every endpoint the document declared, so a
    # reader can ask "which behaviour is this entry point an implementation of"
    # and get an answer rather than a join through prose.
    _link(plan, "Endpoint", _ids(plan, "Endpoint"), spec_id)
    return plan, list(adapter.notes)


def build_structure(spec_id: str, path: str, journey: str, episode_id: str):
    """One structure file → pages, elements and actions, linked to its spec.

    Same signature as `build_openapi` even though `journey` is unused here: the
    two are dispatched from one table, and two arities meant the dispatcher
    crashed on whichever it happened to call second.
    """
    from metis_mcp.model_sources.structure import format_problems, load, plan_structure
    from metis_mcp.model_sources.structure import validate as validate_structure

    structure = load(path)
    problems = validate_structure(structure)
    if problems:
        raise ValueError(format_problems(problems, structure).splitlines()[0])

    # `journey` is the deployable these screens belong to, so the pages are
    # created here rather than assumed. Without it `Page` cannot be written at
    # all -- the label requires a `component` -- and every HAS_ELEMENT edge came
    # back unmatched on a graph where no model source had landed first.
    plan = plan_structure(structure, episode_id, component=journey)
    # `Action` is the affordance a person invokes -- the thing a test clicks --
    # so it is the element worth linking. The containers around it (Page, Form,
    # Row) reach the specification through it.
    _link(plan, "Action", _ids(plan, "Action"), spec_id)
    return plan, []


def _ids(plan, label: str) -> list[str]:
    return [n.properties["id"] for n in plan.nodes if n.label == label]


def _link(plan, label: str, ids: list[str], spec_id: str) -> None:
    """Add `(<label>)-[:IMPLEMENTS]->(Specification)` for each id.

    Validated through the same ontology gate as everything else in the plan, so
    an edge the catalogue forbids is an error before anything is written rather
    than a statement that merges nothing.
    """
    from metis_mcp.model_sources.landing import PlannedEdge
    from metis_mcp.ontology.validation import validate_relationship

    outcome = validate_relationship(label, "IMPLEMENTS", "Specification")
    if not outcome.valid:
        plan.errors.extend(outcome.errors)
        return
    for element_id in ids:
        plan.edges.append(
            PlannedEdge(label, element_id, "IMPLEMENTS", "Specification", spec_id))


def format_build(result: BuildResult) -> str:
    lines = [f"Declared layer — {result.endpoints} endpoint(s), "
             f"{result.pages} page(s), {result.actions} action(s), "
             f"{result.linked} linked to a specification", ""]
    if result.notes:
        lines.append("  Disclosed, and not invalidating (M-17's third outcome):")
        lines += [f"    {n}" for n in result.notes[:8]]
        lines.append("")
    if result.refused:
        lines.append("  Refused — X-5: a contract that does not parse stops the run "
                     "rather than landing a partial view:")
        for spec_id, path, why in result.refused:
            lines.append(f"    {spec_id} → {path}")
            lines.append(f"        {why}")
        lines.append("")
    lines.append("  lifecycle: Quarantine — a declared contract is evidence, "
                 "not agreement (S-4)")
    return "\n".join(lines)


def contract_errors() -> tuple:
    """Every way a contract can refuse to be read.

    `OpenAPIRefused` and `StructureRefused` derive from `Exception`, not from
    `ValueError` — so a caller catching `(OSError, ValueError)` let a malformed
    document crash the command instead of reporting it. X-5 says an unparseable
    contract stops its own run; it does not say the run should traceback.
    """
    from code_analysis.openapi import OpenAPIRefused
    from metis_mcp.model_sources.structure import StructureRefused

    return (OSError, ValueError, OpenAPIRefused, StructureRefused)


CONTRACT_BUILDERS = {
    CONTRACT_OPENAPI: build_openapi,
    CONTRACT_STRUCTURE: build_structure,
}
