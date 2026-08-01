"""
Tests for Layer 2 structural validation (REQ-METIS-GRD-02) -- each test is
written against a specific behavior, not generic code coverage, matching
test_classification_gate.py's convention.
"""
from metis_mcp.structural_validation import StructuralValidator, KNOWN_LABELS


def _validator(known_episodes=frozenset()):
    return StructuralValidator(episode_exists=lambda eid: eid in known_episodes)


def test_unknown_label_rejected_with_specific_reason():
    validator = _validator()
    result = validator.validate("NotARealEntityType", {"id": "x", "source_episode_id": "e1"})
    assert not result.valid
    assert any("Unknown entity type 'NotARealEntityType'" in r for r in result.reasons)


def test_missing_id_rejected_with_specific_reason():
    validator = _validator(known_episodes={"e1"})
    result = validator.validate("Class", {"source_episode_id": "e1"})
    assert not result.valid
    assert any("Missing required property 'id'" in r for r in result.reasons)


def test_missing_source_episode_id_rejected_with_specific_reason():
    validator = _validator()
    result = validator.validate("Class", {"id": "x"})
    assert not result.valid
    assert any("Missing required property 'source_episode_id'" in r for r in result.reasons)


def test_requirement_missing_ears_pattern_rejected_with_specific_reason():
    validator = _validator(known_episodes={"e1"})
    result = validator.validate(
        "Requirement", {"id": "REQ-1", "source_episode_id": "e1", "revision": 1}
    )
    assert not result.valid
    assert any("Missing required property 'ears_pattern'" in r for r in result.reasons)


def test_dangling_source_episode_id_rejected_not_autocreated():
    """The core REQ-METIS-GRD-02 clause: a reference to a nonexistent
    Episode is a rejection, never a trigger to fabricate a stub Episode."""
    validator = _validator(known_episodes=set())  # no episodes exist
    result = validator.validate("Class", {"id": "x", "source_episode_id": "nonexistent-ep"})
    assert not result.valid
    assert any("does not reference an existing Episode" in r for r in result.reasons)
    assert any("not auto-created" in r for r in result.reasons)


def test_valid_entity_passes_with_no_reasons():
    validator = _validator(known_episodes={"e1"})
    result = validator.validate("Class", {"id": "x", "source_episode_id": "e1"})
    assert result.valid
    assert result.reasons == []


def test_valid_requirement_with_all_required_fields_passes():
    validator = _validator(known_episodes={"e1"})
    result = validator.validate(
        "Requirement",
        {"id": "REQ-1", "source_episode_id": "e1", "ears_pattern": "Ubiquitous", "revision": 1,
         "corroboration_count": 1},
    )
    assert result.valid


def test_requirement_missing_corroboration_count_rejected_with_specific_reason():
    """Real bug caught building the bmad-method connector: schema-02's
    requirement_corroboration_count existence constraint was never checked
    here until something actually tried to write a real :Requirement node."""
    validator = _validator(known_episodes={"e1"})
    result = validator.validate(
        "Requirement",
        {"id": "REQ-1", "source_episode_id": "e1", "ears_pattern": "Ubiquitous", "revision": 1},
    )
    assert not result.valid
    assert any("Missing required property 'corroboration_count'" in r for r in result.reasons)


def test_all_schema_labels_are_in_known_labels():
    """Sanity check that the closed ontology list wasn't hand-typo'd --
    every real label from the schema is present."""
    assert "Requirement" in KNOWN_LABELS
    assert "Repository" in KNOWN_LABELS
    assert "Class" in KNOWN_LABELS
    assert "Method" in KNOWN_LABELS
    assert len(KNOWN_LABELS) == 51  # Session 10: +Intent, +TestDesign


if __name__ == "__main__":
    import sys
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
