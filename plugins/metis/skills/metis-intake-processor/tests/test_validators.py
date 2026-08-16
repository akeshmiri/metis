"""Tests for UIF validators."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from validators import UIFValidator


def test_valid_uif():
    """Test validation of valid UIF."""
    validator = UIFValidator()
    
    uif = {
        "uif_version": "1.0.0",
        "scope": {
            "primary_id": "PROJ-1234",
            "primary_type": "story",
            "source_system": "jira",
            "created_at": "2024-01-01T00:00:00Z",
            "last_updated_at": "2024-01-01T00:00:00Z",
            "uif_generated_at": "2024-01-01T00:00:00Z"
        },
        "metadata": {
            "title": "Test Story",
            "status": {
                "approval_state": "draft",
                "automation_status": "not_started",
                "validation_status": "not_validated",
                "measurement_status": "not_measured",
                "freshness_status": "fresh",
                "summary_status": "draft"
            }
        },
        "links": [
            "jira:PROJ-1234"
        ]
    }
    
    is_valid, errors = validator.validate(uif)
    
    assert is_valid, f"Valid UIF failed validation: {errors}"
    print("✓ test_valid_uif passed")


def test_missing_required_fields():
    """Test validation fails for missing required fields."""
    validator = UIFValidator()
    
    # Missing uif_version
    uif_no_version = {
        "scope": {"primary_id": "PROJ-1234"},
        "metadata": {"title": "Test"},
        "links": []
    }
    
    is_valid, errors = validator.validate(uif_no_version)
    assert not is_valid
    assert any("uif_version" in e for e in errors)
    
    # Missing scope
    uif_no_scope = {
        "uif_version": "1.0.0",
        "metadata": {"title": "Test"},
        "links": []
    }
    
    is_valid, errors = validator.validate(uif_no_scope)
    assert not is_valid
    assert any("scope" in e for e in errors)
    
    # Missing links
    uif_no_trace = {
        "uif_version": "1.0.0",
        "scope": {"primary_id": "PROJ-1234"},
        "metadata": {"title": "Test"}
    }
    
    is_valid, errors = validator.validate(uif_no_trace)
    assert not is_valid
    assert any("links" in e for e in errors)
    
    print("✓ test_missing_required_fields passed")


def test_invalid_enum_values():
    """Test validation fails for invalid enum values."""
    validator = UIFValidator()
    
    uif = {
        "uif_version": "1.0.0",
        "scope": {
            "primary_id": "PROJ-1234",
            "primary_type": "invalid_type",
            "source_system": "jira",
            "created_at": "2024-01-01T00:00:00Z",
            "last_updated_at": "2024-01-01T00:00:00Z",
            "uif_generated_at": "2024-01-01T00:00:00Z"
        },
        "metadata": {
            "title": "Test",
            "status": {}
        },
        "links": ["jira:PROJ-1234"]
    }
    
    is_valid, errors = validator.validate(uif)
    assert not is_valid
    assert any("primary_type" in e for e in errors)
    
    print("✓ test_invalid_enum_values passed")


def test_empty_source_references():
    """Test validation fails for empty source_references."""
    validator = UIFValidator()
    
    uif = {
        "uif_version": "1.0.0",
        "scope": {
            "primary_id": "PROJ-1234",
            "primary_type": "story",
            "source_system": "jira",
            "created_at": "2024-01-01T00:00:00Z",
            "last_updated_at": "2024-01-01T00:00:00Z",
            "uif_generated_at": "2024-01-01T00:00:00Z"
        },
        "metadata": {
            "title": "Test",
            "status": {}
        },
        "links": []
    }
    
    is_valid, errors = validator.validate(uif)
    assert not is_valid
    assert any("source_references" in e for e in errors)
    
    print("✓ test_empty_source_references passed")


if __name__ == "__main__":
    test_valid_uif()
    test_missing_required_fields()
    test_invalid_enum_values()
    test_empty_source_references()
    print("\n✓ All validator tests passed!")
