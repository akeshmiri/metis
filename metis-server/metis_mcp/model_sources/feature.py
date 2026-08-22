"""
Features, derived rather than authored (§4.6a, D-13; S-13, S-18).

**A feature is a grouping, and a grouping is a claim.** "Archiving" is a feature
because several specifications are about the same business noun, or because they
are implemented by the same component — not because somebody typed the word. So
this module derives features from evidence Métis already holds and **reports
what it cannot derive** rather than inventing a grouping nobody chose.

Two deterministic groupings, in order of how much they are worth:

    by business entity   Specifications that name the same noun (`record`,
                         `api spec`) are about one capability. This is the
                         strongest signal, because the glossary is a human
                         artefact -- somebody decided that noun exists.

    by component         Specifications whose implementing endpoints or actions
                         belong to one deployable. Weaker: a component boundary
                         is a deployment fact, not a business one, and two
                         unrelated capabilities routinely share a service.

**Nothing is grouped by guessing at the words.** Clustering statement text would
produce features that read plausibly and answer to nobody, which is the failure
`ac_mining` refuses by blocking free prose (S-13, TR-4). A specification that
matches neither grouping is returned as `ungrouped`, with the reason, for a
person to decide -- which is S-18's rule that a model is never derived silently.

**A derived feature lands at Quarantine like everything else** (S-4). Deriving is
not deciding.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from metis_mcp.identity.keys import business_entity_key
from metis_mcp.mbt.model import QUARANTINE

BY_ENTITY = "business_entity"
BY_COMPONENT = "component"

NO_EVIDENCE = "no_entity_and_no_implementation"
ENTITY_UNDEFINED = "entity_not_in_glossary"


@dataclass(frozen=True)
class DerivedFeature:
    """One capability, and why Métis says it is one."""

    id: str
    name: str
    basis: str
    # The specification ids that make it up. A feature with one specification is
    # legitimate -- a capability can be small -- but it is worth seeing.
    specification_ids: tuple[str, ...]
    # What the grouping was keyed on: the entity id, or the component id.
    key: str = ""

    @property
    def is_singleton(self) -> bool:
        return len(self.specification_ids) == 1


@dataclass
class DerivationResult:
    features: list[DerivedFeature] = field(default_factory=list)
    # F-10: what was left out is named, with the reason, rather than being
    # quietly absent from the result.
    ungrouped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def singletons(self) -> list[DerivedFeature]:
        return [f for f in self.features if f.is_singleton]


def _feature_id(basis: str, key: str) -> str:
    """Content-derived (D-8), so re-deriving an unchanged estate is a no-op."""
    return "feat-" + hashlib.sha256(f"{basis}|{key}".encode()).hexdigest()[:12]


def derive(specifications: list[dict], *, known_entities: set[str] | None = None,
           implementations: dict[str, str] | None = None) -> DerivationResult:
    """Group specifications into features from evidence, not from wording.

    `specifications` are rows as the loader returns them: `id`, `statement`,
    `entities`. `known_entities` is the glossary's own key set, so a noun nobody
    defined does not silently become a capability. `implementations` maps a
    specification id to the component that implements it, from `IMPLEMENTS`.

    Pure: no session, no model call, and the same inputs give the same features
    in the same order (P-7's discipline, applied here so two derivations are
    comparable).
    """
    known = known_entities if known_entities is not None else set()
    implementations = implementations or {}

    by_entity: dict[str, list[str]] = {}
    result = DerivationResult()
    remaining: list[dict] = []

    for spec in sorted(specifications, key=lambda s: s.get("id", "")):
        spec_id = spec.get("id", "")
        entities = [business_entity_key(e) for e in (spec.get("entities") or [])]
        defined = [e for e in entities if e in known]

        if defined:
            for entity in defined:
                by_entity.setdefault(entity, []).append(spec_id)
            continue

        if entities and not defined:
            # Named a noun, and the glossary has never heard of it. Reported
            # rather than grouped: an undefined noun is a glossary gap, and
            # grouping on it would bury that.
            result.ungrouped.append((
                spec_id,
                f"{ENTITY_UNDEFINED}: names {', '.join(entities)}, which the "
                f"glossary does not define. Add it with `glossary land`, or "
                f"correct the specification"))
            continue

        remaining.append(spec)

    for entity in sorted(by_entity):
        ids = tuple(sorted(by_entity[entity]))
        result.features.append(DerivedFeature(
            id=_feature_id(BY_ENTITY, entity), name=entity.replace("-", " "),
            basis=BY_ENTITY, specification_ids=ids, key=entity))

    by_component: dict[str, list[str]] = {}
    for spec in remaining:
        spec_id = spec.get("id", "")
        component = implementations.get(spec_id, "")
        if component:
            by_component.setdefault(component, []).append(spec_id)
        else:
            result.ungrouped.append((
                spec_id,
                f"{NO_EVIDENCE}: names no defined business entity and nothing "
                f"implements it, so there is no evidence of what capability it "
                f"belongs to. A person decides this one (S-18)"))

    for component in sorted(by_component):
        ids = tuple(sorted(by_component[component]))
        result.features.append(DerivedFeature(
            id=_feature_id(BY_COMPONENT, component), name=component,
            basis=BY_COMPONENT, specification_ids=ids, key=component))

    return result


def plan_features(result: DerivationResult, episode_id: str):
    """`Feature` nodes and the edges from what they group.

    A feature is reached from its acceptance criteria and its requirements
    (`REALISED_BY`), which is how the catalogue defines it. Those edges are
    planned per specification, so a feature that groups three specifications
    carries the criteria of all three.
    """
    from metis_mcp.model_sources.landing import LandingPlan, PlannedEdge, PlannedNode
    from metis_mcp.ontology.validation import validate as validate_node
    from metis_mcp.ontology.validation import validate_relationship

    plan = LandingPlan(episode_id=episode_id)

    def add_node(label: str, props: dict) -> bool:
        outcome = validate_node(label, props)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return False
        plan.nodes.append(PlannedNode(label=label, properties=props))
        return True

    def add_edge(from_label: str, from_id: str, rel: str, to_label: str, to_id: str) -> None:
        outcome = validate_relationship(from_label, rel, to_label)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        plan.edges.append(PlannedEdge(from_label, from_id, rel, to_label, to_id))

    for feature in result.features:
        if not add_node("Feature", {
            "id": feature.id, "source_episode_id": episode_id,
            "name": feature.name,
            "basis": feature.basis,
            "grouped_on": feature.key,
            "specification_count": len(feature.specification_ids),
            "lifecycle_state": QUARANTINE,
        }):
            continue
        # From the SPECIFICATION, because that is what was grouped. This planned
        # `AcceptanceCriterion` edges with specification ids at first and every
        # one matched nothing -- a specification is not a criterion, and the ids
        # never overlap. `land`'s unmatched reporting is the only reason that
        # was visible rather than a feature silently connected to nothing.
        for spec_id in feature.specification_ids:
            add_edge("Specification", spec_id, "REALISED_BY", "Feature", feature.id)

    return plan


def format_derivation(result: DerivationResult) -> str:
    """What was derived, on what evidence, and what still needs a person."""
    lines = [f"Features — {len(result.features)} derived, "
             f"{len(result.ungrouped)} left for a person", ""]
    for basis, title in ((BY_ENTITY, "By business entity (the glossary decided this noun exists)"),
                         (BY_COMPONENT, "By component (a deployment fact, not a business one)")):
        group = [f for f in result.features if f.basis == basis]
        if not group:
            continue
        lines.append(f"  {title}")
        for feature in group:
            mark = "  (single specification)" if feature.is_singleton else ""
            lines.append(f"    {feature.name:<24} {len(feature.specification_ids)} "
                         f"specification(s){mark}")
        lines.append("")

    if result.ungrouped:
        lines.append("  Not grouped — reported rather than guessed at (S-18):")
        for spec_id, why in result.ungrouped:
            lines.append(f"    {spec_id}")
            lines.append(f"        {why}")
        lines.append("")

    lines.append("  lifecycle: Quarantine — deriving is not deciding (S-4)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Feature → Scenario: which walks demonstrate this capability
# ---------------------------------------------------------------------------

BY_CRITERION = "criterion"
BY_IMPLEMENTATION = "implementation"

NO_SCENARIO = "no_scenario_demonstrates_it"


@dataclass
class LinkResult:
    """Which scenarios demonstrate which feature, and on what evidence."""

    links: list[tuple[str, str, str]] = field(default_factory=list)
    # F-10 again: a feature nothing demonstrates is the actionable half of this
    # report, so it is named rather than being absent from the links list.
    undemonstrated: list[tuple[str, str]] = field(default_factory=list)

    @property
    def by_criterion(self) -> list[tuple[str, str, str]]:
        return [l for l in self.links if l[2] == BY_CRITERION]


def link_scenarios(features: list[dict], by_criterion: dict, by_implementation: dict
                   ) -> LinkResult:
    """Join features to the scenarios that demonstrate them, on evidence.

    Two paths, and the stronger one wins where both apply:

        criterion       a criterion of this feature's specification explicitly
                        VALIDATES the transition the scenario asserts. Somebody
                        said this behaviour is what the capability means.

        implementation  the transition merely derives from an entry point that
                        implements the specification. True, and weaker: it says
                        the code and the contract line up, not that anybody
                        agreed what the capability is.

    A feature no scenario demonstrates is reported, never invented. That is the
    gap worth acting on -- a capability with no walk behind it is exactly what
    the coverage question exists to surface.
    """
    result = LinkResult()
    for feature in features:
        fid = feature.get("id", "")
        strong = list(dict.fromkeys(by_criterion.get(fid, [])))
        weak = [s for s in dict.fromkeys(by_implementation.get(fid, []))
                if s not in strong]

        for scenario_id in strong:
            result.links.append((fid, scenario_id, BY_CRITERION))
        for scenario_id in weak:
            result.links.append((fid, scenario_id, BY_IMPLEMENTATION))

        if not strong and not weak:
            result.undemonstrated.append((
                fid,
                f"{NO_SCENARIO}: no scenario covers a transition this feature's "
                f"specifications reach — through a criterion that validates one, "
                f"or through an entry point that implements one. Either the "
                f"behaviour is not modelled yet, or nothing generates a path to "
                f"it"))
    return result


def plan_scenario_links(result: LinkResult, episode_id: str):
    """`Feature -[:HAS_SCENARIO]-> Scenario`, carrying why."""
    from metis_mcp.model_sources.landing import LandingPlan, PlannedEdge
    from metis_mcp.ontology.validation import validate_relationship

    plan = LandingPlan(episode_id=episode_id)
    outcome = validate_relationship("Feature", "HAS_SCENARIO", "Scenario")
    if not outcome.valid:
        plan.errors.extend(outcome.errors)
        return plan

    for feature_id, scenario_id, basis in result.links:
        plan.edges.append(PlannedEdge(
            "Feature", feature_id, "HAS_SCENARIO", "Scenario", scenario_id))
    return plan


def format_links(result: LinkResult) -> str:
    strong = len(result.by_criterion)
    lines = [f"Feature → Scenario — {len(result.links)} link(s): "
             f"{strong} on a criterion, {len(result.links) - strong} on an "
             f"implementation", ""]
    if result.undemonstrated:
        lines.append("  Demonstrated by nothing — the gap worth acting on:")
        for feature_id, why in result.undemonstrated:
            lines.append(f"    {feature_id}")
            lines.append(f"        {why}")
        lines.append("")
    return "\n".join(lines)
