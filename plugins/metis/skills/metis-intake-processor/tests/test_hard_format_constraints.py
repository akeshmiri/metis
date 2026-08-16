"""Test UIF hard format constraints - no additional fields allowed."""

import pytest
from validators import UIFValidator


def test_rejects_additional_root_fields():
    """Verify UIF rejects any additional root fields."""
    validator = UIFValidator()
    
    uif = {
        "uif_version": "1.0.0",
        "scope": {
            "primary_id": "PROJ-123",
            "primary_type": "story",
            "source_system": "jira",
            "created_at": "2024-01-01T00:00:00Z",
            "last_updated_at": "2024-01-01T00:00:00Z",
            "uif_generated_at": "2024-01-01T00:00:00Z"
        },
        "metadata": {"title": "Test", "status": "draft"},
        "links": ["jira:PROJ-123"],
        "custom_field": "should_be_rejected"  # HARD FORMAT VIOLATION
    }
    
    is_valid, errors = validator.validate(uif)
    assert not is_valid, "UIF with extra root field should be invalid"
    assert any("HARD FORMAT VIOLATION" in err for err in errors), \
        "Should report hard format violation"
    assert any("custom_field" in err for err in errors), \
        "Should mention the custom field"


def test_rejects_additional_scope_fields():
    """Verify UIF rejects any additional scope fields."""
    validator = UIFValidator()
    
    uif = {
        "uif_version": "1.0.0",
        "scope": {
            "primary_id": "PROJ-123",
            "primary_type": "story",
            "source_system": "jira",
            "created_at": "2024-01-01T00:00:00Z",
            "last_updated_at": "2024-01-01T00:00:00Z",
            "uif_generated_at": "2024-01-01T00:00:00Z",
            "custom_scope_field": "not_allowed"  # HARD FORMAT VIOLATION
        },
        "metadata": {"title": "Test", "status": "draft"},
        "links": ["jira:PROJ-123"]
    }
    
    is_valid, errors = validator.validate(uif)
    assert not is_valid, "UIF with extra scope field should be invalid"
    assert any("scope" in err and "HARD FORMAT VIOLATION" in err for err in errors), \
        "Should report scope hard format violation"


def test_rejects_additional_metadata_fields():
    """Verify UIF rejects any additional metadata fields."""
    validator = UIFValidator()
    
    uif = {
        "uif_version": "1.0.0",
        "scope": {
            "primary_id": "PROJ-123",
            "primary_type": "story",
            "source_system": "jira",
            "created_at": "2024-01-01T00:00:00Z",
            "last_updated_at": "2024-01-01T00:00:00Z",
            "uif_generated_at": "2024-01-01T00:00:00Z"
        },
        "metadata": {
            "title": "Test",
            "status": "draft",
            "custom_meta": "not_allowed"  # HARD FORMAT VIOLATION
        },
        "links": ["jira:PROJ-123"]
    }
    
    is_valid, errors = validator.validate(uif)
    assert not is_valid, "UIF with extra metadata field should be invalid"
    assert any("metadata" in err and "HARD FORMAT VIOLATION" in err for err in errors), \
        "Should report metadata hard format violation"


def test_allows_all_defined_fields():
    """Verify UIF accepts all defined fields in hard format."""
    validator = UIFValidator()
    
    uif = {
        "uif_version": "1.0.0",
        "scope": {
            "primary_id": "PROJ-123",
            "primary_type": "story",
            "source_system": "jira",
            "secondary_id": "PROJ-456",
            "created_at": "2024-01-01T00:00:00Z",
            "last_updated_at": "2024-01-01T00:00:00Z",
            "uif_generated_at": "2024-01-01T00:00:00Z"
        },
        "metadata": {
            "title": "Test",
            "status": "draft",
            "priority": "high"
        },
        "facts": {"fact1": "value1"},
        "specifications": {"spec1": "value1"},
        "comments": [],
        "api_contracts": [],
        "data_model": [],
        "error_handling": {},
        "open_questions": {},
        "links": ["jira:PROJ-123"]
    }
    
    is_valid, errors = validator.validate(uif)
    assert is_valid, f"Valid UIF should be accepted, but got errors: {errors}"
