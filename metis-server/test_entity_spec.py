"""
Business-entity specifications (application spec §4.6a, §18; D-8, D-13, F-12).

Free to run: `build` and `render_markdown` are pure, and the landing planner is
fully validated offline. Only execution needs Neo4j.

The properties that matter here are the ones a document can lose silently:
the round trip through `spec_kit`, determinism, idempotence, and whether a
`code_derived` criterion is still visible as one after rendering.
"""
import json

from metis_mcp.model_sources.spec_kit import _AC_HEADING
from metis_mcp.specgen import entity as E
from metis_mcp.specgen.documents import plan_entity_document

ENTITY = {
    "id": "record",
    "name": "record",
    "description": "A stored item a user can act on",
    "area": "records",
    "impact": ["archiving hides it from search but retains it for audit"],
    "properties_json": json.dumps([
        {"name": "status", "meaning": "where it is in its life",
         "values": ["active", "archived"]},
    ]),
}

CRITERIA = [
    {"id": "AC-1", "text": "Given the user has admin permission, when they archive "
                           "a record, then it is hidden from search",
     "provenance": "human_confirmed", "lifecycle_state": "Quarantine",
     "requirement_id": "REQ-1", "transition_ids": ["admin-api::t01"]},
    {"id": "AC-2", "text": "Given a non-admin user, when they archive a record, "
                           "then the request is refused",
     "provenance": "code_derived", "lifecycle_state": "Quarantine",
     "requirement_id": "REQ-1", "transition_ids": []},
]


def _spec(**kwargs):
    return E.build(ENTITY, CRITERIA, area_name="Records", **kwargs)


# --------------------------------------------------------------------------
# The glossary's two halves both survive into the document
# --------------------------------------------------------------------------

def test_impact_is_rendered_because_it_is_the_half_worth_writing_down():
    """A description says what a noun is; impact says what acting on it does,
    and no schema records that."""
    body = E.render_markdown(_spec())
    assert "What changes when you act on it" in body
    assert "archiving hides it from search but retains it for audit" in body


def test_properties_render_with_their_meaning_and_values():
    body = E.render_markdown(_spec())
    assert "**status**" in body
    assert "where it is in its life" in body
    assert "`active`" in body and "`archived`" in body


def test_a_property_with_no_name_is_dropped_rather_than_rendered_blank():
    entity = dict(ENTITY, properties_json=json.dumps([{"meaning": "orphan"}]))
    assert E.build(entity, []).properties == ()


def test_malformed_properties_json_does_not_take_the_document_down():
    """A document that cannot render is worse than one missing a section."""
    entity = dict(ENTITY, properties_json="{not json")
    spec = E.build(entity, CRITERIA)
    assert spec.properties == ()
    assert "## Properties" in E.render_markdown(spec)


# --------------------------------------------------------------------------
# §4.1 : coverage is not correctness, and the document must not blur it
# --------------------------------------------------------------------------

def test_a_code_derived_criterion_is_marked_as_one():
    """It was written from the code, so agreeing with the code proves nothing.
    Rendering it beside an intent criterion without the grade would present
    coverage as correctness."""
    spec = _spec()
    assert len(spec.code_derived_rules) == 1
    assert len(spec.intent_rules) == 1
    body = E.render_markdown(spec)
    assert "code-derived — coverage, not correctness" in body
    assert "1 of 2 rules are `code_derived`" in body


def test_an_all_intent_entity_carries_no_warning():
    criteria = [dict(c, provenance="human_confirmed") for c in CRITERIA]
    body = E.render_markdown(E.build(ENTITY, criteria))
    assert "code_derived" not in body


def test_provenance_defaults_to_the_weakest_grade():
    """Fail-closed, the same reason a model source lands at Quarantine (S-4)."""
    criteria = [{"id": "AC-9", "text": "something", "lifecycle_state": "Quarantine"}]
    assert E.build(ENTITY, criteria).rules[0].provenance == "code_derived"


def test_coverage_wording_never_claims_the_behaviour_works():
    body = E.render_markdown(_spec(), coverage_summary="1 of 2 rules covered.")
    assert "**tested**, not what is **working**" in body


# --------------------------------------------------------------------------
# The round trip stays closed (SP-1a)
# --------------------------------------------------------------------------

def test_the_document_parses_back_into_the_criteria_it_came_from():
    """A document whose headings nothing can parse is a dead end — the journey
    specification parsed back to *zero* criteria before its heading was stable.
    """
    spec = _spec()
    found = _AC_HEADING.findall(E.render_markdown(spec))
    assert {cid for cid, _ in found} == {r.criterion_id for r in spec.rules}


def test_a_criterion_id_without_the_prefix_still_renders_a_parseable_heading():
    """The heading is prefixed for the parser; `criterion_id` keeps the real id.

    They were briefly the same value, which meant a criterion whose real id is
    `records-spec-api-ac1` got cited as `AC-records-spec-api-ac1` — an id no node
    carries — and every `CITES` edge matched nothing.
    """
    criteria = [dict(CRITERIA[0], id="7")]
    spec = E.build(ENTITY, criteria)
    assert spec.rules[0].criterion_id == "7", "the node id must survive verbatim"
    assert spec.rules[0].heading_id == "AC-7"
    assert _AC_HEADING.findall(E.render_markdown(spec))


def test_cites_targets_the_real_node_id_not_the_heading():
    """A document heading has to be parseable; an edge has to be true."""
    criteria = [dict(CRITERIA[0], id="records-spec-api-ac1")]
    spec = E.build(ENTITY, criteria)
    plan = plan_entity_document(spec, episode_id="ep-1")
    cited = {e.to_id for e in plan.edges if e.rel_type == "CITES"}
    assert cited == {"records-spec-api-ac1"}
    assert "AC-records-spec-api-ac1" not in cited


def test_the_heading_carries_the_behaviour_not_the_id():
    """SP-1: an element id printed as a section title tells a stakeholder
    nothing. The id is a prefix, not a replacement."""
    heading = _spec().rules[0].heading
    assert heading.startswith("AC-1: ")
    assert "archive" in heading


# --------------------------------------------------------------------------
# D-8 : re-rendering unchanged input writes nothing
# --------------------------------------------------------------------------

def test_rendering_is_deterministic():
    assert E.render_markdown(_spec()) == E.render_markdown(_spec())


def test_the_content_hash_excludes_the_timestamp():
    """Hashing `generated_at` would make every regeneration a new document and
    defeat the MERGE that keeps this idempotent."""
    assert (_spec(generated_at="2020-01-01").content_hash
            == _spec(generated_at="2026-08-21").content_hash)


def test_the_content_hash_changes_when_the_entity_does():
    changed = E.build(dict(ENTITY, description="something else"), CRITERIA)
    assert changed.content_hash != _spec().content_hash


def test_the_content_hash_changes_when_a_criterion_changes():
    changed = E.build(ENTITY, [dict(CRITERIA[0], text="different"), CRITERIA[1]])
    assert changed.content_hash != _spec().content_hash


# --------------------------------------------------------------------------
# The landing plan (F-12 — the document is a node, not a file)
# --------------------------------------------------------------------------

def test_the_plan_is_legal_offline():
    plan = plan_entity_document(_spec(), episode_id="ep-1")
    assert plan.is_legal, plan.errors[:3]


def test_the_document_lands_at_quarantine():
    """S-4: generated is authored, never agreed. Nothing here decides that a
    specification has been accepted — G1 does, with a person."""
    plan = plan_entity_document(_spec(), episode_id="ep-1")
    node = next(n for n in plan.nodes if n.label == "EntityDocument")
    assert node.properties["lifecycle_state"] == "Quarantine"


def test_the_document_describes_its_entity_and_cites_its_criteria():
    """`CITES` is what makes the round trip checkable without parsing markdown."""
    spec = _spec()
    plan = plan_entity_document(spec, episode_id="ep-1")
    edges = {(e.rel_type, e.to_label, e.to_id) for e in plan.edges}
    assert ("DESCRIBES", "BusinessEntity", "record") in edges
    for rule in spec.rules:
        assert ("CITES", "AcceptanceCriterion", rule.criterion_id) in edges


def test_the_body_is_stored_on_the_node():
    """F-12: consumers query the graph, they never re-derive. A document that
    lands without its body would make every reader re-render it."""
    plan = plan_entity_document(_spec(), episode_id="ep-1")
    node = next(n for n in plan.nodes if n.label == "EntityDocument")
    assert "business entity" in node.properties["body_markdown"]
    assert node.properties["content_hash"] == _spec().content_hash


# --------------------------------------------------------------------------
# The specialisation trap, in the query this feature depends on
# --------------------------------------------------------------------------

def test_the_criteria_query_matches_specialised_transitions():
    """A classified transition carries `:ApiCall` INSTEAD of `:Transition`, so a
    hardcoded parent label matches nothing and reports no error."""
    from metis_mcp.mbt.graph_loader import ENTITY_CRITERIA_CYPHER

    assert "Transition|ApiCall|UiAction" in ENTITY_CRITERIA_CYPHER


def test_a_criterion_that_validates_nothing_cites_no_transition():
    """`collect(DISTINCT t.id)` yields `[null]` rather than `[]`, and a null
    would render as a citation to a transition that does not exist."""
    spec = E.build(ENTITY, [dict(CRITERIA[0], transition_ids=[None])])
    assert spec.rules[0].transition_ids == ()
    assert "Validates:" not in E.render_markdown(spec)


# --------------------------------------------------------------------------
# The journey document cites REAL criteria, not its own heading ids
# --------------------------------------------------------------------------

def test_a_spec_document_cites_acceptance_criteria_not_heading_ids():
    """`Rule.criterion_id` is synthetic — derived from the transition's natural
    key so the document round-trips through `spec_kit`. It names no node.

    Citing it planned an edge per rule against ids nothing carries, and `land`
    reported every one as unmatched. `Rule.acceptance_criteria` is the real
    thing: the AC ids that VALIDATE the transition the rule renders.
    """
    from metis_mcp.specgen.documents import plan_spec_document
    from metis_mcp.specgen.specification import Rule, Specification

    rule = Rule(
        transition_id="t01", criterion_id="AC-synthetic-heading-id",
        given="Given a user", when="they submit", and_guard="", guard_verbatim="",
        then="they are logged in", lifecycle_state="Quarantine",
        implementation_status="implemented",
        acceptance_criteria=("ac-real-1", "ac-real-2"),
    )
    spec = Specification(model_id="login-api", journey="login", rules=[rule])
    plan = plan_spec_document(spec, "cmp-1", "ep-1", "# body", spec.content_hash)

    cited = {e.to_id for e in plan.edges if e.rel_type == "CITES"}
    assert cited == {"ac-real-1", "ac-real-2"}
    assert "AC-synthetic-heading-id" not in cited


def test_a_rule_validated_by_nothing_cites_nothing():
    """A rule renders whether or not a criterion validates its transition, so
    the two counts differ and only the plan's is a fact about the graph."""
    from metis_mcp.specgen.documents import plan_spec_document
    from metis_mcp.specgen.specification import Rule, Specification

    rule = Rule(
        transition_id="t01", criterion_id="AC-x", given="g", when="w",
        and_guard="", guard_verbatim="", then="t", lifecycle_state="Quarantine",
        implementation_status="implemented", acceptance_criteria=(),
    )
    spec = Specification(model_id="m", journey="j", rules=[rule])
    plan = plan_spec_document(spec, "cmp-1", "ep-1", "# body", spec.content_hash)
    assert not [e for e in plan.edges if e.rel_type == "CITES"]
    assert len(spec.rules) == 1, "the rule still renders — only the citation is absent"


def test_the_spec_content_hash_excludes_the_timestamp():
    from metis_mcp.specgen.specification import Specification

    a = Specification(model_id="m", journey="j", generated_at="2020-01-01")
    b = Specification(model_id="m", journey="j", generated_at="2026-08-21")
    assert a.content_hash == b.content_hash


def test_the_spec_content_hash_changes_with_the_model():
    from metis_mcp.specgen.specification import Specification

    a = Specification(model_id="m", journey="j", commit="abc")
    b = Specification(model_id="m", journey="j", commit="def")
    assert a.content_hash != b.content_hash
