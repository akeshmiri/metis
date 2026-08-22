"""
The specification as Gherkin, and the glossary behind its nouns
(application spec §18, §4.6a; D-13, S-13, S-19, §7.8).

Free to run: pure rendering and parsing. No Neo4j, no model calls.
"""
import sys

from metis_mcp.model_sources.glossary import (
    MISSING_DESCRIPTION,
    MISSING_IMPACT,
    UNKNOWN_AREA,
    BAD_PROPERTY,
    BusinessArea,
    BusinessEntity,
    EntityProperty,
    Glossary,
    plan_glossary,
)
from metis_mcp.model_sources.glossary import validate as validate_glossary
from metis_mcp.model_sources.knowledge import (
    INFERRED_COMPLEMENT,
    NEGATIVE,
    KnowledgeEntry,
    KnowledgeFile,
    KnowledgeRequirement,
)
from metis_mcp.model_sources.knowledge import validate as validate_knowledge
from metis_mcp.ontology.labels import CODE_DERIVED
from metis_mcp.specgen.gherkin import (
    PARSE_NO_FEATURE,
    PARSE_UNSUPPORTED,
    build_feature,
    parse_feature,
    render_feature,
    to_knowledge,
    verbatim_clauses,
)

STATEMENT = "if user has admin permission then it should be able to archive a record"
REQUIREMENT_TEXT = ("When a user has admin permission, the system shall permit "
                    "the requested action.")


def _entry(eid, text, **kwargs):
    kwargs.setdefault("source_statement", STATEMENT)
    return KnowledgeEntry(id=eid, text=text, requirement_id="REQ-ADMIN-01", **kwargs)


def _knowledge() -> KnowledgeFile:
    return KnowledgeFile(
        model_id="admin-api",
        requirement=KnowledgeRequirement("REQ-ADMIN-01", REQUIREMENT_TEXT),
        statement=STATEMENT,
        entries=[
            _entry("AC-001", "Given the user has admin permission, when they "
                             "archive a record, then the record is archived."),
            _entry("AC-002", "Given the user is logged in, when they archive a "
                             "record, and they have admin permission, then the "
                             "record is archived."),
            _entry("AC-004", "Given the user does not have admin permission, when "
                             "they archive a record, then the request is rejected.",
                   polarity=NEGATIVE, derived=INFERRED_COMPLEMENT,
                   complement_of="AC-001"),
        ])


def _glossary() -> Glossary:
    return Glossary(
        areas=[BusinessArea(id="records", name="Records",
                            description="Stored business documents")],
        entities=[BusinessEntity(
            id="record", name="Record", area="records",
            description="a stored business document owned by one user",
            impact=("archiving is reversible for 30 days",),
            properties=(EntityProperty("state", "where it sits in its lifecycle",
                                       ("Draft", "Active", "Archived")),))])


def _rendered(**kwargs) -> str:
    knowledge = _knowledge()
    return render_feature(build_feature(
        knowledge.requirement.id, knowledge.requirement.text, knowledge.entries,
        **kwargs))


# --------------------------------------------------------------------------
# One Requirement, one Feature; one criterion, one Scenario
# --------------------------------------------------------------------------

def test_a_requirement_is_a_feature_and_each_criterion_is_a_scenario():
    text = _rendered()
    assert text.count("Feature:") == 1
    assert text.count("  Scenario:") == 3


def test_the_feature_title_is_the_requirement_not_its_id():
    """SP-1: an element id printed as a heading tells a stakeholder nothing."""
    text = _rendered()
    assert "Feature: When a user has admin permission" in text
    assert "Feature: REQ-ADMIN-01" not in text


def test_traceability_rides_in_tags_because_a_tag_survives_the_round_trip():
    """§7.8 — a comment would not come back."""
    text = _rendered(area="records")
    assert "@requirement:REQ-ADMIN-01" in text
    assert "@area:records" in text
    assert "@ac:AC-001" in text


def test_an_inferred_criterion_is_tagged_as_inferred_on_the_page():
    text = _rendered()
    assert "@inferred" in text
    assert "@complement_of:AC-001" in text
    assert "NOT stated by anyone" in text, (
        "a reader must not have to know what the tag means"
    )


def test_every_scenario_carries_its_s19_grade():
    assert _rendered().count(f"@{CODE_DERIVED}") == 3


def test_rendering_is_deterministic():
    """P-7/TR-6: same input, same bytes."""
    assert _rendered(area="records") == _rendered(area="records")


def test_a_requirement_with_no_criteria_says_so_rather_than_rendering_empty():
    text = render_feature(build_feature("REQ-X", "The system shall do a thing.", []))
    assert "No acceptance criteria" in text
    assert "unspecified" in text


def test_an_unparseable_criterion_is_reported_never_reshaped_into_steps():
    """S-13 in a renderer: fluent well-formedness is what a fabrication is."""
    text = render_feature(build_feature(
        "REQ-X", "The system shall do a thing.",
        [_entry("AC-9", "admins can do stuff")]))
    assert "could not be read" in text
    assert "Scenario:" not in text


# --------------------------------------------------------------------------
# The author's own words
# --------------------------------------------------------------------------

def test_the_criterion_is_rendered_in_the_words_it_was_written_in():
    """The defect this catches was silent and changed a person's sentence.

    `ac_mining._parse` strips `the`, `user is` and `they` on purpose — the state
    it mines is `slug(given)`, and `LoggedOut` is the right id where
    `TheUserIsLoggedOut` is not. Rendering from those groups turned "Given the
    user has admin permission, when they archive a record" into "Given user has
    admin permission, when archive a record". Parse to check; slice to render.
    """
    text = _rendered()
    assert "Given the user has admin permission" in text
    assert "When they archive a record" in text
    assert "Given user has admin permission" not in text


def test_verbatim_clauses_returns_none_for_prose_it_cannot_split():
    assert verbatim_clauses("admins can do stuff") is None


# --------------------------------------------------------------------------
# The round trip — a .feature is a source, not only an output
# --------------------------------------------------------------------------

def test_a_feature_reads_back_into_the_same_criteria():
    original = _knowledge()
    parsed = parse_feature(_rendered(area="records"))
    assert parsed.problems == []
    assert parsed.requirement_id == "REQ-ADMIN-01"
    assert parsed.area == "records"

    rebuilt = to_knowledge(parsed, model_id="admin-api", statement=STATEMENT)
    assert [e.id for e in rebuilt.entries] == [e.id for e in original.entries]
    for before, after in zip(original.entries, rebuilt.entries):
        assert after.text == before.text, "the author's sentence must survive"
        assert after.polarity == before.polarity
        assert after.derived == before.derived


def test_the_rebuilt_file_still_validates():
    """The check that caught a real loss: `complement_of` was not tagged, so an
    inferred criterion came back ungrounded and `knowledge.validate` refused it."""
    rebuilt = to_knowledge(parse_feature(_rendered()), model_id="admin-api",
                           statement=STATEMENT)
    assert validate_knowledge(rebuilt) == []
    inferred = next(e for e in rebuilt.entries if e.is_inferred)
    assert inferred.complement_of == "AC-001"


def test_a_second_render_is_byte_identical():
    first = _rendered(area="records")
    rebuilt = to_knowledge(parse_feature(first), model_id="admin-api",
                           statement=STATEMENT)
    second = render_feature(build_feature(
        rebuilt.requirement.id, rebuilt.requirement.text, rebuilt.entries,
        area="records"))
    assert second == first


def test_unsupported_gherkin_is_refused_not_skipped():
    """Skipping `Examples:` would drop every row and report a clean read."""
    parsed = parse_feature(
        "@requirement:REQ-X\nFeature: X\n\n  Scenario Outline: p\n"
        "    Given <a>\n\n  Examples:\n    | a |\n    | 1 |\n")
    assert any(p.kind == PARSE_UNSUPPORTED for p in parsed.problems)


def test_a_feature_with_no_requirement_tag_is_refused():
    """Without it the scenarios land with nothing above them."""
    parsed = parse_feature("Feature: X\n\n  Scenario: y\n    Given a\n"
                           "    When b\n    Then c\n")
    assert any(p.kind == PARSE_NO_FEATURE for p in parsed.problems)


def test_a_scenario_missing_a_clause_is_reported():
    parsed = parse_feature("@requirement:REQ-X\nFeature: X\n\n"
                           "  @ac:AC-1\n  Scenario: y\n    Given a\n    When b\n")
    assert parsed.problems and "then" in parsed.problems[0].detail


# --------------------------------------------------------------------------
# The glossary — what the nouns mean
# --------------------------------------------------------------------------

def test_a_clean_glossary_validates():
    assert validate_glossary(_glossary()) == []


def test_an_entity_must_say_what_acting_on_it_changes():
    """The half a schema cannot tell you, and the half an author needs."""
    glossary = _glossary()
    glossary.entities = [BusinessEntity(
        id="record", name="Record", area="records", description="a document")]
    assert any(p.kind == MISSING_IMPACT for p in validate_glossary(glossary))


def test_an_entity_must_be_described():
    glossary = _glossary()
    glossary.entities = [BusinessEntity(
        id="record", name="Record", area="records", description="  ",
        impact=("x",))]
    assert any(p.kind == MISSING_DESCRIPTION for p in validate_glossary(glossary))


def test_a_property_whose_name_is_its_only_explanation_is_rejected():
    glossary = _glossary()
    glossary.entities = [BusinessEntity(
        id="record", name="Record", area="records", description="a document",
        impact=("x",), properties=(EntityProperty("status", ""),))]
    assert any(p.kind == BAD_PROPERTY for p in validate_glossary(glossary))


def test_an_entity_in_an_undefined_area_is_caught():
    glossary = _glossary()
    glossary.entities = [BusinessEntity(
        id="record", name="Record", area="nowhere", description="a document",
        impact=("x",))]
    assert any(p.kind == UNKNOWN_AREA for p in validate_glossary(glossary))


def test_the_glossary_lands_through_the_ontology_gate():
    plan = plan_glossary(_glossary(), "ep-1")
    assert plan.is_legal, plan.errors
    labels = [n.label for n in plan.nodes]
    assert labels.count("BusinessArea") == 1
    assert labels.count("BusinessEntity") == 1
    assert [e.rel_type for e in plan.edges] == ["BELONGS_TO"]


def test_properties_land_as_json_not_as_nodes():
    """D-13, on `Transition.inputs`' reasoning: the reader renders them all and
    nothing queries one. Promote when something does."""
    plan = plan_glossary(_glossary(), "ep-1")
    entity = next(n for n in plan.nodes if n.label == "BusinessEntity")
    assert "state" in entity.properties["properties_json"]
    assert not any(n.label == "EntityProperty" for n in plan.nodes)


def test_the_glossary_appears_beside_the_scenarios_that_touch_it():
    text = _rendered(glossary=_glossary(),
                     entity_ids={"AC-001": ["record"]})
    assert "Record — a stored business document" in text
    assert "state (Draft | Active | Archived)" in text
    assert "impact: archiving is reversible for 30 days" in text
    assert "@entity:record" in text


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
        except Exception as e:
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
