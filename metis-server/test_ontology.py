"""
Twelve-label ontology tests (application spec §8, D-1, D-2, ONT-001, ONT-002).

Includes the **four-place governance check**: the schema, the validator, the
catalogue and the specification document must agree, and CI must fail when they
do not (ONT-001). Two of the four are generated from one source, so this test
covers the two that are prose.

Free to run: no Neo4j needed. Applying the DDL against a live instance is
verified separately by test_ontology_live.py.
"""
import re
import sys
from pathlib import Path

from metis_mcp.ontology import (
    ALLOWED_RELATIONSHIPS,
    ANY_LABEL,
    KNOWN_LABELS,
    LABELS,
    RELATIONSHIP_TYPES,
    STAGED_OUT,
    validate,
    validate_relationship,
    validate_update,
    wildcard_relationships,
)
from metis_mcp.ontology.labels import PROVENANCE_GRADES
from metis_mcp.ontology.schema import (
    FILES,
    constraints_cypher,
    relationships_cypher,
    statements,
)

SPEC = Path("../docs/metis-application-spec.md")


# --------------------------------------------------------------------------
# D-1 : every label earns its place
# --------------------------------------------------------------------------

def test_exactly_twelve_labels():
    assert len(KNOWN_LABELS) == 12, (
        f"the ontology is twelve labels (spec D-1); found {len(KNOWN_LABELS)}: "
        f"{sorted(KNOWN_LABELS)}"
    )


def test_acceptance_criterion_can_store_its_s19_grade():
    """Spec D-9b. A grade the graph cannot hold is a grade that does not exist.

    `review/decisions.py:promotion_for` computed the promoted grade correctly
    from the day it was written, and `AcceptanceCriterion` had no property to put
    it in — so every promotion was discarded and "0 intent-backed criteria" was a
    structural fact, not a review backlog.
    """
    spec = LABELS["AcceptanceCriterion"]
    assert "provenance" in spec.enums, "S-19's grade must be a declared enum"
    assert spec.enums["provenance"] == PROVENANCE_GRADES
    assert "provenance" in spec.indexed, (
        "the question this answers is a filter — 'which criteria here are still "
        "code_derived' — not a lookup")


def test_the_grade_enum_has_one_definition_shared_with_the_matcher():
    """D-2: two places that cannot drift beat two kept in step by discipline."""
    from metis_mcp.reconciliation import matching
    assert matching.PROVENANCE_GRADES is PROVENANCE_GRADES


def test_a_partial_update_is_gated_on_enums_without_demanding_required_props():
    """`SET n.provenance = ...` must be checkable (D-10, ONT-012).

    `validate` rightly demands the whole required set for a *candidate node*, so
    running an update through it fails on properties the node already has. That
    mismatch is why every `SET` in this codebase skipped the gate entirely.
    """
    assert validate_update("AcceptanceCriterion",
                           {"provenance": "human_confirmed"}).valid
    bad = validate_update("AcceptanceCriterion", {"provenance": "vouched_for"})
    assert not bad.valid
    assert "vouched_for" in bad.errors[0]
    # The distinction from `validate` is the point of the function existing.
    assert not validate("AcceptanceCriterion", {"provenance": "human_confirmed"}).valid


def test_a_partial_update_still_refuses_an_unknown_label():
    assert not validate_update("Sprint", {"name": "x"}).valid


def test_staged_out_labels_each_name_their_return_trigger():
    """Spec D-11: the exclusion list is a staging plan, not a rejection."""
    assert STAGED_OUT, "the excluded labels must be recorded, not merely absent"
    for label, trigger in STAGED_OUT.items():
        assert label not in KNOWN_LABELS, f"{label} is both staged out and active"
        assert trigger.strip(), f"{label} has no trigger for its return"


def test_every_label_has_a_purpose():
    for label, spec in LABELS.items():
        assert spec.purpose.strip(), f"{label} has no stated purpose"


# --------------------------------------------------------------------------
# ONT-002 : rejection, never auto-creation
# --------------------------------------------------------------------------

def test_unknown_label_is_rejected():
    result = validate("Goal", {"id": "g1", "source_episode_id": "e1", "name": "Goal"})
    assert not result.valid
    assert "closed" in result.errors[0]


def test_missing_required_property_is_rejected():
    result = validate("Transition", {"id": "t1", "source_episode_id": "e1", "name": "t1"})
    assert not result.valid
    missing = " ".join(result.errors)
    for prop in ("trigger", "guard_expression", "implementation_status", "surface"):
        assert prop in missing, f"{prop} should be reported missing"


def test_empty_string_counts_as_missing():
    result = validate("JiraItem", {"id": "j1", "source_episode_id": "e1",
                                   "name": "PROJ-1", "jira_key": "  ", "issue_type": "Story"})
    assert not result.valid
    assert "jira_key" in result.errors[0]


def test_enum_membership_is_enforced_by_the_gate_not_the_schema():
    """Spec ONT-012: the schema guarantees presence, this gate guarantees membership."""
    base = {"id": "t1", "source_episode_id": "e1", "name": "t1", "trigger": "click",
            "guard_expression": "", "implementation_status": "implemented"}
    assert validate("Transition", {**base, "surface": "api"}).valid
    bad = validate("Transition", {**base, "surface": "cli"})
    assert not bad.valid and "surface" in bad.errors[0]


def test_episode_is_exempt_from_source_episode_id():
    """An Episode is the provenance record; it cannot point at one."""
    result = validate("Episode", {"id": "e1", "name": "ep", "t_recorded": "2026-01-01",
                                  "source_connector": "jira", "job_id": "j1"})
    assert result.valid, result.errors
    assert "source_episode_id" not in LABELS["Episode"].all_required


def test_valid_node_passes():
    assert validate("TestPath", {
        "id": "p1", "source_episode_id": "e1", "name": "path",
        "criterion": "all-transitions", "generator_version": "1",
    }).valid


# --------------------------------------------------------------------------
# Relationship catalogue
# --------------------------------------------------------------------------

def test_catalogued_relationship_is_allowed():
    assert validate_relationship("State", "WHEN", "Transition").valid
    assert validate_relationship("Transition", "THEN", "State").valid
    assert validate_relationship("AcceptanceCriterion", "VALIDATES", "Transition").valid


def test_uncatalogued_triple_is_rejected_with_the_permitted_set():
    result = validate_relationship("Transition", "WHEN", "State")
    assert not result.valid
    assert "(State)-[:WHEN]->(Transition)" in result.errors[0], (
        "the error should name what IS permitted, not merely what is not"
    )


def test_testcase_cannot_link_directly_to_a_requirement():
    """Spec D-4: traceability always routes through an AcceptanceCriterion."""
    assert not validate_relationship("TestCase", "VERIFIES", "Requirement").valid


def test_unknown_relationship_type_is_rejected():
    result = validate_relationship("State", "TRACES_TO", "Transition")
    assert not result.valid
    assert "closed" in result.errors[0]


def test_only_two_wildcard_relationships_exist():
    """Both are documented exceptions, not unenforced holes."""
    assert set(wildcard_relationships()) == {"HAS_REVISION", "ABOUT"}


def test_invokes_is_transition_to_transition():
    """Spec M-5a: cross-surface invocation links two transitions."""
    assert validate_relationship("Transition", "INVOKES", "Transition").valid


# --------------------------------------------------------------------------
# D-2 / ONT-001 : the four places agree
# --------------------------------------------------------------------------

def test_generated_schema_covers_every_label():
    cypher = constraints_cypher()
    for label in KNOWN_LABELS:
        assert f"(n:{label})" in cypher, f"{label} has no constraint in the generated schema"


def test_generated_schema_covers_every_relationship_type():
    cypher = relationships_cypher()
    for rel_type in RELATIONSHIP_TYPES:
        assert f"[x:{rel_type}]" in cypher, f"{rel_type} has no index (spec ONT-011)"


def test_generated_schema_has_no_duplicate_index_names():
    names = re.findall(r"CREATE (?:INDEX|CONSTRAINT) (\w+)",
                       constraints_cypher() + relationships_cypher())
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates, f"duplicate schema object names: {duplicates}"


def test_checked_in_schema_matches_the_generator():
    """A hand-edit to the generated file is exactly the drift generation prevents."""
    for name, generator in FILES.items():
        path = Path("schema") / name
        assert path.exists(), f"{path} missing — run: python3 -m metis_mcp.ontology.schema --write"
        assert path.read_text() == generator(), (
            f"{path} differs from the generator. Do not hand-edit; regenerate."
        )


def test_specification_document_lists_the_same_labels():
    """ONT-001's fourth place: the prose catalogue in §8.2."""
    if not SPEC.exists():
        return  # spec not adjacent in this checkout; the other three still agree
    text = SPEC.read_text()
    section = text[text.index("### 8.2 Labels"):text.index("### 8.3 Relationships")]
    for label in KNOWN_LABELS:
        assert f"`{label}`" in section, (
            f"{label} is in the code but not in §8.2 of the specification (ONT-001)"
        )


def test_specification_document_lists_the_same_relationships():
    if not SPEC.exists():
        return
    text = SPEC.read_text()
    section = text[text.index("### 8.3 Relationships"):text.index("### 8.4 Versioning")]
    for spec in ALLOWED_RELATIONSHIPS:
        assert f"`{spec.rel_type}`" in section, (
            f"{spec.rel_type} is in the code but not in §8.3 (ONT-001)"
        )


def test_statements_split_cleanly():
    stmts = statements(constraints_cypher())
    assert stmts and all(s.endswith(";") for s in stmts)
    assert not any(s.lstrip().startswith("//") for s in stmts)


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
