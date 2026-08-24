"""
Spec Kit reader tests (application spec §4.5; S-12, S-13, S-14; R5).

Free to run: parsing is pure.
"""
import sys
import tempfile
from pathlib import Path

from metis_mcp.model_sources.spec_kit import (
    SpecCriterion,
    format_specs,
    parse_spec,
    read_specs,
)

SPEC = """# Spec: metric-derived-quality-actions

> Status: **IMPLEMENTED** — 100% feature-complete

## Acceptance Criteria

### AC-1: Metric Append-Only Save

**Given** a `POST /metric` request with a `RecordDto`
**When** the request is processed
**Then** a new metric record is always created
**And** `201 Created` is returned

**Code reference**: `MetricServiceImpl.save()` → `metricRepository.saveAndFlush(metric)`

---

### AC-4: Metric Point Query

**Given** a `GET /metric/{id}` request
**When** a metric with the given id exists
**Then** the `RecordDto` is returned with `200 OK`

**When** no metric exists with the given id
**Then** `204 No Content` is returned

**Code reference**: `RecordController.getActionById()`

---

### AC-9: A readiness gate exists

- Before a module ships it must have a documented readiness result.
- Verified by: a readiness matrix in the feature package.
"""


def _parse(text=SPEC, name="metric-derived-quality-actions"):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / name / "spec.md"
        p.parent.mkdir(parents=True)
        p.write_text(text)
        return parse_spec(p)


# --------------------------------------------------------------------------
# Reading what is written
# --------------------------------------------------------------------------

def test_the_feature_and_status_are_read():
    f = _parse()
    assert f.name == "metric-derived-quality-actions"
    assert f.status == "IMPLEMENTED"


def test_a_given_when_then_criterion_becomes_one_behavioural_rule():
    rule = next(c for c in _parse().criteria if c.id == "AC-1")
    assert rule.is_behavioural
    assert rule.given.startswith("a POST /metric request")
    assert "201 Created is returned" in rule.text
    assert rule.code_reference.startswith("MetricServiceImpl.save()")


def test_backticks_are_stripped_so_a_matcher_sees_what_a_reader_sees():
    rule = next(c for c in _parse().criteria if c.id == "AC-1")
    assert "`" not in rule.text
    assert "POST /metric" in rule.text


# --------------------------------------------------------------------------
# One Given, several When/Then -- the real shape in these files
# --------------------------------------------------------------------------

def test_nested_when_then_pairs_become_separate_rules():
    """AC-4 states two outcomes of one request. Those are two transitions."""
    ids = [c.id for c in _parse().criteria]
    assert "AC-4.1" in ids and "AC-4.2" in ids
    assert "AC-4" not in ids, "the block itself is not a rule; its pairs are"


def test_a_nested_rule_inherits_the_shared_given():
    rules = {c.id: c for c in _parse().criteria}
    assert rules["AC-4.1"].given == rules["AC-4.2"].given
    assert "GET /metric/{id}" in rules["AC-4.1"].given


def test_each_nested_rule_keeps_its_own_outcome():
    rules = {c.id: c for c in _parse().criteria}
    assert "200 OK" in rules["AC-4.1"].then
    assert "204 No Content" in rules["AC-4.2"].then


def test_a_single_rule_keeps_the_plain_ac_id():
    rules = {c.id: c for c in _parse().criteria}
    assert "AC-1" in rules, "no sub-id when there is only one rule"


def test_and_clauses_between_when_and_then_become_guard_text():
    rule = next(c for c in _parse().criteria if c.id == "AC-1")
    assert "and a new metric record is always created" in rule.text


# --------------------------------------------------------------------------
# S-13 : a narrative criterion is real, and is NOT a transition
# --------------------------------------------------------------------------

def test_a_narrative_criterion_is_kept_but_marked_non_behavioural():
    """37 of 66 criteria on the real estate are readiness gates and
    architectural constraints. Dropping them would hide most of the spec;
    forcing them into a transition would invent behaviour."""
    narrative = [c for c in _parse().criteria if not c.is_behavioural]
    assert [c.id for c in narrative] == ["AC-9"]
    assert narrative[0].text.startswith("A readiness gate")


def test_the_report_says_how_many_are_not_transitions():
    text = format_specs([_parse()])
    assert "narrative" in text
    assert "never forced" in text


# --------------------------------------------------------------------------
# S-14 : traceability back to the file
# --------------------------------------------------------------------------

def test_every_criterion_records_its_feature_and_file():
    for c in _parse().criteria:
        assert c.feature == "metric-derived-quality-actions"
        assert c.source_file.endswith("spec.md")


def test_a_criterion_converts_to_the_shape_the_miner_consumes():
    rule = next(c for c in _parse().criteria if c.id == "AC-4.1")
    criterion = rule.to_criterion()
    assert criterion.id == "AC-4.1"
    assert criterion.requirement_id == "metric-derived-quality-actions"
    assert criterion.text == rule.text


# --------------------------------------------------------------------------
# Directory reading
# --------------------------------------------------------------------------

def test_reading_a_directory_is_ordered_and_skips_features_with_no_spec():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for name in ("b-feature", "a-feature"):
            (root / name).mkdir()
            (root / name / "spec.md").write_text(SPEC)
        (root / "c-no-spec").mkdir()
        features = read_specs(root)
    assert [f.name for f in features] == ["a-feature", "b-feature"]


def test_a_missing_directory_says_what_to_point_at():
    try:
        read_specs("/nonexistent/specs")
    except FileNotFoundError as e:
        assert "Spec Kit" in str(e)
        return
    raise AssertionError("a missing spec root must be reported")


def test_a_spec_with_no_criteria_yields_none_rather_than_failing():
    f = _parse("# Spec: empty\n\nNothing here.\n", name="empty")
    assert f.criteria == []


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


# --------------------------------------------------------------------------
# A spec document -> a Requirement (§4.5; S-13, S-19, §4.1)
# --------------------------------------------------------------------------

def _feature():
    from metis_mcp.model_sources.spec_kit import SpecCriterion, SpecFeature

    return SpecFeature(name="Archive a record", criteria=[
        SpecCriterion(id="AC-1", title="hides it", feature="Archive a record",
                      text="Given admin, when they archive a record, then it is hidden",
                      is_behavioural=True),
        SpecCriterion(id="AC-2", title="a narrative note", feature="Archive a record",
                      text="Verified by an e2e suite", is_behavioural=False),
    ])


EARS = "When a user archives a record, the system shall hide it from search."


def test_only_behavioural_criteria_become_entries():
    """A readiness gate or an architectural constraint is a genuine criterion
    and genuinely not a state transition — it must not be forced into a shape it
    does not have (S-13)."""
    from metis_mcp.model_sources.spec_kit import requirement_from_spec

    knowledge = requirement_from_spec(_feature(), EARS)
    assert [e.id for e in knowledge.entries] == ["AC-1"]


def test_the_statement_is_carried_onto_every_entry():
    """Each criterion claims to formalise it, and a claim nobody can check
    against its source is not evidence."""
    from metis_mcp.model_sources.spec_kit import requirement_from_spec

    knowledge = requirement_from_spec(_feature(), EARS)
    assert all(e.source_statement == EARS for e in knowledge.entries)


def test_the_requirement_carries_the_ears_statement_not_the_feature_name():
    """A feature is named "Archive a record"; a requirement is a sentence.
    Composing one from the other is composition, not extraction (S-13)."""
    from metis_mcp.model_sources.spec_kit import requirement_from_spec

    knowledge = requirement_from_spec(_feature(), EARS)
    assert knowledge.requirement.text == EARS
    assert knowledge.requirement.ears.pattern == "EventDriven"


def test_a_non_ears_statement_is_reported_by_the_existing_validator():
    """Not reimplemented here: `knowledge.validate` already refuses it, and one
    definition of the rule is the point of routing through that writer."""
    from metis_mcp.model_sources.knowledge import validate
    from metis_mcp.model_sources.spec_kit import requirement_from_spec

    problems = validate(requirement_from_spec(_feature(), "Archive a record"))
    assert any(p.kind == "requirement_not_ears" for p in problems)


def test_every_criterion_lands_at_the_weakest_grade():
    """§4.1: a spec rendered from the code model, parsed back into a
    requirement, then used to check that code proves only that the code does
    what the code does. Nothing here upgrades a grade — `promotion_for` does,
    on a real edit or an explicit affirmation.
    """
    from metis_mcp.model_sources.spec_kit import requirement_from_spec

    knowledge = requirement_from_spec(_feature(), EARS)
    assert all(e.provenance == "code_derived" for e in knowledge.entries)


def test_edited_by_hand_is_not_read_as_consent():
    """It says the wording changed, not that a person affirmed the claim."""
    import dataclasses

    from metis_mcp.model_sources.spec_kit import requirement_from_spec

    feature = _feature()
    feature.criteria = [dataclasses.replace(feature.criteria[0], edited_by_hand=True),
                        feature.criteria[1]]
    knowledge = requirement_from_spec(feature, EARS)
    assert knowledge.entries[0].provenance == "code_derived"


def test_landing_goes_through_the_one_requirement_writer():
    """`knowledge.plan_documentation` is the only writer of `Requirement`. A
    second one is how two halves of a graph disagree about what `Approved`
    means."""
    from metis_mcp.model_sources.knowledge import plan_documentation
    from metis_mcp.model_sources.spec_kit import requirement_from_spec

    plan = plan_documentation(requirement_from_spec(_feature(), EARS), "ep-1")
    assert plan.is_legal, plan.errors[:3]
    labels = [n.label for n in plan.nodes]
    assert labels.count("Requirement") == 1
    assert labels.count("AcceptanceCriterion") == 1
    assert ("Requirement", "HAS_AC", "AcceptanceCriterion") in {
        (e.from_label, e.rel_type, e.to_label) for e in plan.edges}
