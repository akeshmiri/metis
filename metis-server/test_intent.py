"""
The intent spine: Intent, Specification, and the Feature Métis derives (§4.1).

Free to run: the file gate and the derivation are both pure.

The properties that matter are the ones that would let intent quietly become
something nobody authored — a specification graded as evidence about the code,
a need with nothing to check it against, or a capability invented by clustering
words.
"""
import json

import pytest

from metis_mcp.model_sources import feature as F
from metis_mcp.model_sources import intent as I


def _doc(**overrides):
    base = {
        "intent_version": I.FILE_VERSION,
        "area": "records",
        "intents": [{"id": "i-archive", "statement": "Users should be able to archive a record"}],
        "specifications": [{
            "id": "spec-hides", "intent": "i-archive",
            "provenance": "independently_authored",
            "statement": "When a user archives a record, it no longer appears in search",
            "entities": ["record"],
        }],
    }
    base.update(overrides)
    return base


def _load(tmp_path, doc):
    p = tmp_path / "intent.json"
    p.write_text(json.dumps(doc))
    return I.load(p)


# --------------------------------------------------------------------------
# The file gate
# --------------------------------------------------------------------------

def test_a_well_formed_file_has_no_problems(tmp_path):
    assert I.validate(_load(tmp_path, _doc())) == []


def test_an_unknown_version_is_refused(tmp_path):
    p = tmp_path / "i.json"
    p.write_text(json.dumps(dict(_doc(), intent_version="metis.intent/99")))
    with pytest.raises(I.IntentFileRefused) as e:
        I.load(p)
    assert "99" in str(e.value)


def test_an_intent_nobody_specified_is_refused(tmp_path):
    """A need nobody has said the behaviour of is a wish, and landing it would
    put a node in the graph that nothing can ever be checked against."""
    doc = _doc(intents=[{"id": "i-archive", "statement": "archive"},
                        {"id": "i-wish", "statement": "it should be nice"}])
    problems = I.validate(_load(tmp_path, doc))
    assert any(p.kind == I.NO_SPECIFICATION and p.entry_id == "i-wish" for p in problems)


def test_a_specification_cannot_float_free_of_an_intent(tmp_path):
    doc = _doc(specifications=[dict(_doc()["specifications"][0], intent="i-nonexistent")])
    problems = I.validate(_load(tmp_path, doc))
    assert any(p.kind == I.UNKNOWN_INTENT for p in problems)


def test_an_authored_specification_cannot_claim_code_derived(tmp_path):
    """§4.1: that grade means Métis decoded it from an endpoint. Claiming it in a
    hand-written file would make an authored sentence look like evidence about
    the code — the one claim this platform must never make."""
    doc = _doc(specifications=[dict(_doc()["specifications"][0], provenance="code_derived")])
    problems = I.validate(_load(tmp_path, doc))
    assert any(p.kind == I.CODE_DERIVED_AUTHORED for p in problems)


def test_an_unknown_provenance_is_refused(tmp_path):
    doc = _doc(specifications=[dict(_doc()["specifications"][0], provenance="probably_fine")])
    problems = I.validate(_load(tmp_path, doc))
    assert any(p.kind == I.BAD_PROVENANCE for p in problems)


@pytest.mark.parametrize("statement", [
    "The system should handle archiving appropriately",
    "Archiving works correctly",
    "A robust archiving flow",
    "Archiving integrates seamlessly",
])
def test_an_unfalsifiable_statement_is_reported(tmp_path, statement):
    """Matched on the word stem, because "appropriate" has to catch
    "appropriately" — the form people actually write. A trailing word boundary
    matched the adjective and missed every adverb."""
    doc = _doc(specifications=[dict(_doc()["specifications"][0], statement=statement)])
    problems = I.validate(_load(tmp_path, doc))
    assert any(p.kind == I.VAGUE_STATEMENT for p in problems), statement


def test_a_measurable_statement_is_not_flagged(tmp_path):
    doc = _doc(specifications=[dict(_doc()["specifications"][0],
                                    statement="An archived record is removed from search within 5 seconds")])
    assert not [p for p in I.validate(_load(tmp_path, doc)) if p.kind == I.VAGUE_STATEMENT]


# --------------------------------------------------------------------------
# Landing: what it plans, and what it deliberately does not
# --------------------------------------------------------------------------

def test_landing_plans_intent_and_specification_but_never_a_feature(tmp_path):
    """A feature is a grouping, and a grouping is a claim Métis derives from
    evidence — not one an author restates by hand."""
    plan = I.plan_intent(_load(tmp_path, _doc()))
    labels = {n.label for n in plan.nodes}
    assert {"Intent", "Specification"} <= labels
    assert "Feature" not in labels


def test_everything_lands_at_quarantine(tmp_path):
    plan = I.plan_intent(_load(tmp_path, _doc()))
    for node in plan.nodes:
        state = node.properties.get("lifecycle_state")
        if state is not None:
            assert state == "Quarantine"


def test_entities_are_normalised_through_the_shared_key(tmp_path):
    """I-2: a specification and the glossary must agree about what `api spec` is,
    or the same noun lands twice."""
    doc = _doc(specifications=[dict(_doc()["specifications"][0], entities=["API Spec"])])
    plan = I.plan_intent(_load(tmp_path, doc))
    spec = next(n for n in plan.nodes if n.label == "Specification")
    assert spec.properties["entities"] == ["api-spec"]


def test_the_episode_id_is_content_derived(tmp_path):
    a = _load(tmp_path, _doc())
    assert I.episode_id_for(a) == I.episode_id_for(_load(tmp_path, _doc()))
    changed = _load(tmp_path, _doc(intents=[{"id": "i-archive", "statement": "different"}]))
    assert I.episode_id_for(changed) != I.episode_id_for(a)


# --------------------------------------------------------------------------
# Derivation: evidence, never wording
# --------------------------------------------------------------------------

def test_specifications_naming_one_noun_become_one_feature():
    result = F.derive(
        [{"id": "s1", "entities": ["record"]}, {"id": "s2", "entities": ["record"]}],
        known_entities={"record"})
    assert len(result.features) == 1
    assert result.features[0].basis == F.BY_ENTITY
    assert result.features[0].specification_ids == ("s1", "s2")


def test_a_noun_the_glossary_never_defined_is_reported_not_grouped():
    """An undefined noun is a glossary gap. Grouping on it would bury that."""
    result = F.derive([{"id": "s1", "entities": ["widget"]}], known_entities={"record"})
    assert result.features == []
    assert result.ungrouped and F.ENTITY_UNDEFINED in result.ungrouped[0][1]


def test_a_specification_with_no_evidence_is_left_for_a_person():
    """S-18: a model is never derived silently. Clustering the statement text
    would produce a feature that reads plausibly and answers to nobody."""
    result = F.derive([{"id": "s1", "entities": []}], known_entities={"record"})
    assert result.features == []
    assert F.NO_EVIDENCE in result.ungrouped[0][1]


def test_component_grouping_is_the_weaker_fallback():
    result = F.derive([{"id": "s1", "entities": []}], known_entities=set(),
                      implementations={"s1": "athena-spec-api"})
    assert result.features[0].basis == F.BY_COMPONENT
    assert result.features[0].key == "athena-spec-api"


def test_derivation_is_deterministic():
    """P-7's discipline: two derivations of one estate are comparable."""
    specs = [{"id": "s2", "entities": ["record"]}, {"id": "s1", "entities": ["record"]}]
    a = F.derive(specs, known_entities={"record"})
    b = F.derive(list(reversed(specs)), known_entities={"record"})
    assert [f.id for f in a.features] == [f.id for f in b.features]
    assert a.features[0].specification_ids == b.features[0].specification_ids


def test_the_feature_id_is_content_derived():
    """D-8/TR-6: re-deriving an unchanged estate is a no-op."""
    a = F.derive([{"id": "s1", "entities": ["record"]}], known_entities={"record"})
    b = F.derive([{"id": "s1", "entities": ["record"]}], known_entities={"record"})
    assert a.features[0].id == b.features[0].id


def test_the_feature_records_why_metis_says_it_is_one():
    """A grouping is a claim, so the evidence rides on the node."""
    result = F.derive([{"id": "s1", "entities": ["record"]}], known_entities={"record"})
    plan = F.plan_features(result, "ep-1")
    node = next(n for n in plan.nodes if n.label == "Feature")
    assert node.properties["basis"] == F.BY_ENTITY
    assert node.properties["grouped_on"] == "record"
    assert node.properties["lifecycle_state"] == "Quarantine"


def test_the_edge_comes_from_the_specification_not_the_criterion():
    """This planned `AcceptanceCriterion` edges using specification ids, and
    every one matched nothing — a specification is not a criterion and the ids
    never overlap. `land`'s unmatched reporting is why that was visible."""
    result = F.derive([{"id": "spec-1", "entities": ["record"]}], known_entities={"record"})
    plan = F.plan_features(result, "ep-1")
    edges = {(e.from_label, e.rel_type, e.to_label) for e in plan.edges}
    assert ("Specification", "REALISED_BY", "Feature") in edges
    assert not [e for e in plan.edges if e.from_label == "AcceptanceCriterion"]


def test_the_implementations_query_matches_specialised_components():
    """A Component is written `:RestServer` or `:WebServer` when its surface is
    known, so a hardcoded `:Component` matches only the unclassified ones."""
    from metis_mcp.mbt.graph_loader import SPEC_IMPLEMENTATIONS_CYPHER

    assert "RestServer" in SPEC_IMPLEMENTATIONS_CYPHER
    assert "WebServer" in SPEC_IMPLEMENTATIONS_CYPHER


# --------------------------------------------------------------------------
# Building the declared layer from a specification's contracts (§5.2, M-13)
# --------------------------------------------------------------------------

def test_a_contract_kind_nobody_implements_is_reported(tmp_path):
    doc = _doc(specifications=[dict(
        _doc()["specifications"][0],
        contracts=[{"kind": "carrier-pigeon", "path": str(tmp_path)}])])
    problems = I.validate(_load(tmp_path, doc))
    assert any(p.kind == I.UNKNOWN_CONTRACT for p in problems)


def test_a_contract_file_that_does_not_exist_is_reported(tmp_path):
    """A specification that names a contract nobody can read is a claim about a
    document, not a link to one."""
    doc = _doc(specifications=[dict(
        _doc()["specifications"][0],
        contracts=[{"kind": "openapi", "path": "/nope/absent.json"}])])
    problems = I.validate(_load(tmp_path, doc))
    assert any(p.kind == I.MISSING_CONTRACT for p in problems)


def test_the_contracts_are_recorded_on_the_node(tmp_path):
    """F-12: the graph says what a behaviour was built from, without anybody
    re-reading the file to find out."""
    fixture = tmp_path / "api.json"
    fixture.write_text("{}")
    doc = _doc(specifications=[dict(
        _doc()["specifications"][0],
        contracts=[{"kind": "openapi", "path": str(fixture)}])])
    plan = I.plan_intent(_load(tmp_path, doc))
    spec = next(n for n in plan.nodes if n.label == "Specification")
    assert json.loads(spec.properties["contracts_json"])[0]["kind"] == "openapi"


def test_the_contract_changes_the_content_hash(tmp_path):
    fixture = tmp_path / "api.json"
    fixture.write_text("{}")
    plain = _load(tmp_path, _doc())
    linked = _load(tmp_path, _doc(specifications=[dict(
        _doc()["specifications"][0],
        contracts=[{"kind": "openapi", "path": str(fixture)}])]))
    assert I.episode_id_for(plain) != I.episode_id_for(linked)


def test_a_refusing_contract_is_caught_not_raised():
    """`OpenAPIRefused` and `StructureRefused` derive from `Exception`, not
    `ValueError` — a caller catching `(OSError, ValueError)` let a malformed
    document crash the whole command instead of reporting it and continuing
    with the others. X-5 stops a run; it does not traceback."""
    from code_analysis.openapi import OpenAPIRefused
    from metis_mcp.model_sources.spec_build import contract_errors
    from metis_mcp.model_sources.structure import StructureRefused

    caught = contract_errors()
    assert OpenAPIRefused in caught and StructureRefused in caught


def test_both_builders_share_one_signature():
    """They are dispatched from one table, and two arities meant the dispatcher
    crashed on whichever it called second."""
    import inspect

    from metis_mcp.model_sources.spec_build import CONTRACT_BUILDERS

    signatures = {name: list(inspect.signature(fn).parameters)
                  for name, fn in CONTRACT_BUILDERS.items()}
    assert len(set(map(tuple, signatures.values()))) == 1, signatures


def test_the_endpoint_links_back_to_its_specification(tmp_path):
    """`IMPLEMENTS` is the code side of §4.1's comparison, and nothing wrote it
    before this."""
    from metis_mcp.model_sources.spec_build import build_openapi

    plan, _ = build_openapi("spec-1", "test_fixtures/records-openapi.json",
                            "records", "ep-1")
    links = [e for e in plan.edges if e.rel_type == "IMPLEMENTS"]
    assert links, "no endpoint was linked to its specification"
    assert all(e.to_id == "spec-1" and e.to_label == "Specification" for e in links)
    assert {e.from_label for e in links} == {"Endpoint"}


def test_the_specification_prose_builds_nothing():
    """The specification names a document; the DOCUMENT is parsed. Nothing here
    reads the specification's sentence, which is what keeps building an endpoint
    off a specification from being circular (§4.1)."""
    import inspect

    from metis_mcp.model_sources import spec_build

    source = inspect.getsource(spec_build.build_openapi)
    assert "statement" not in source, (
        "the builder reads the specification's prose — an endpoint must come "
        "from the contract, never from the sentence describing it")


# --------------------------------------------------------------------------
# The last hop: which walks demonstrate a capability
# --------------------------------------------------------------------------

def test_the_criterion_path_is_preferred_over_the_implementation_path():
    """A criterion explicitly VALIDATES the transition — somebody said this
    behaviour is what the capability means. An implementation link only says the
    code and the contract line up."""
    result = F.link_scenarios(
        [{"id": "f1"}],
        {"f1": ["sc1", "sc2"]},
        {"f1": ["sc2", "sc3"]})
    bases = {scenario: basis for _, scenario, basis in result.links}
    assert bases["sc1"] == F.BY_CRITERION
    assert bases["sc2"] == F.BY_CRITERION, "the stronger evidence must win"
    assert bases["sc3"] == F.BY_IMPLEMENTATION


def test_a_feature_nothing_demonstrates_is_reported():
    """The actionable half: a capability with no walk behind it is exactly what
    the coverage question exists to surface."""
    result = F.link_scenarios([{"id": "f1"}], {}, {})
    assert result.links == []
    assert F.NO_SCENARIO in result.undemonstrated[0][1]


def test_a_scenario_is_never_linked_twice():
    result = F.link_scenarios([{"id": "f1"}], {"f1": ["sc1", "sc1"]}, {"f1": ["sc1"]})
    assert [s for _, s, _ in result.links] == ["sc1"]


def test_both_paths_match_specialised_transitions():
    """A classified transition carries `:ApiCall`, so a hardcoded `:Transition`
    in either query would find nothing."""
    from metis_mcp.mbt.graph_loader import (
        FEATURE_SCENARIOS_BY_CRITERION_CYPHER as A,
        FEATURE_SCENARIOS_BY_IMPLEMENTATION_CYPHER as B,
    )

    for query in (A, B):
        assert "Transition|ApiCall|UiAction" in query


def test_a_knowledge_file_can_name_the_specification_it_formalises():
    """`Specification -[:HAS_AC]-> AcceptanceCriterion` was in the catalogue with
    no writer, so the intent path from a Feature to its Scenarios could never
    fire — the criteria existed and nothing said which specified behaviour they
    belonged to."""
    import sys

    sys.path.insert(0, ".")
    from test_knowledge import _admin_file

    from metis_mcp.model_sources.knowledge import plan_documentation

    k = _admin_file()
    k.specification_id = "spec-1"
    plan = plan_documentation(k, "ep-1")
    edges = {(e.from_label, e.rel_type) for e in plan.edges}
    assert ("Specification", "HAS_AC") in edges
    assert ("Requirement", "HAS_AC") in edges, "both are real; neither replaces the other"


def test_validates_uses_the_idempotent_namespacing():
    """A mapping built from ids read OUT of the graph already carries the
    namespace, and prefixing twice produced `m::m::t` — an id no node has, so
    every VALIDATES edge matched nothing."""
    import sys

    sys.path.insert(0, ".")
    from test_knowledge import _admin_file

    from metis_mcp.model_sources.knowledge import plan_documentation

    k = _admin_file()
    already = f"{k.model_id}::t01"
    plan = plan_documentation(k, "ep-1",
                              criterion_transitions={k.entries[0].id: [already]})
    validates = [e for e in plan.edges if e.rel_type == "VALIDATES"]
    assert validates and validates[0].to_id == already
    assert f"{k.model_id}::{k.model_id}::" not in validates[0].to_id
