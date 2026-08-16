"""Tests for Jira extractor."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from extractors.jira_extractor import JiraExtractor


def test_jira_extraction_minimal():
    """Test minimal Jira extraction."""
    extractor = JiraExtractor()
    
    # Mock Jira issue
    raw_issue = {
        "key": "PROJ-1234",
        "fields": {
            "summary": "Test Story",
            "description": "Test description",
            "issuetype": {"name": "Story"},
            "status": {"name": "To Do"},
            "priority": {"name": "High"},
            "labels": ["test"],
            "created": "2024-01-01T00:00:00Z",
            "updated": "2024-01-01T00:00:00Z"
        }
    }
    
    uif = extractor.extract(key="PROJ-1234", raw_issue=raw_issue)
    
    # Assertions
    assert uif["uif_version"] == "1.0.0"
    assert uif["scope"]["primary_id"] == "PROJ-1234"
    assert uif["scope"]["primary_type"] == "story"
    assert uif["scope"]["source_system"] == "jira"
    assert uif["metadata"]["title"] == "Test Story"
    assert uif["metadata"]["priority"] == "high"
    assert "links" in uif
    assert len(uif["links"]) > 0
    
    print("✓ test_jira_extraction_minimal passed")


def test_jira_acceptance_criteria_parsing():
    """Test Jira acceptance criteria parsing."""
    extractor = JiraExtractor()
    
    description = """
Given I am on the login page
When I enter valid credentials
Then I should see the dashboard
"""
    
    criteria = extractor._parse_acceptance_criteria(description)
    
    assert len(criteria) == 3
    assert any("login page" in c["statement"] for c in criteria)
    assert any("dashboard" in c["statement"] for c in criteria)
    
    print("✓ test_jira_acceptance_criteria_parsing passed")


def test_jira_status_normalization():
    """Test Jira status normalization."""
    extractor = JiraExtractor()
    
    assert extractor._normalize_status("To Do") == "draft"
    assert extractor._normalize_status("In Progress") == "active"
    assert extractor._normalize_status("Done") == "completed"
    assert extractor._normalize_status("Unknown") == "draft"
    
    print("✓ test_jira_status_normalization passed")


def test_jira_priority_normalization():
    """Test Jira priority normalization."""
    extractor = JiraExtractor()
    
    assert extractor._normalize_priority("Blocker") == "critical"
    assert extractor._normalize_priority("High") == "high"
    assert extractor._normalize_priority("Medium") == "medium"
    assert extractor._normalize_priority("Trivial") == "low"
    
    print("✓ test_jira_priority_normalization passed")


def test_jira_issue_type_normalization():
    """Test Jira issue type normalization."""
    extractor = JiraExtractor()
    
    assert extractor._normalize_issue_type("Epic") == "epic"
    assert extractor._normalize_issue_type("Story") == "story"
    assert extractor._normalize_issue_type("Task") == "task"
    assert extractor._normalize_issue_type("Bug") == "defect"
    assert extractor._normalize_issue_type("Unknown") == "task"
    
    print("✓ test_jira_issue_type_normalization passed")


def test_jira_comments_extraction():
    """Test Jira comments extraction."""
    extractor = JiraExtractor()
    
    # Mock Jira issue with comments
    raw_issue = {
        "key": "PROJ-5678",
        "fields": {
            "summary": "Test Story with Comments",
            "description": "Test description",
            "issuetype": {"name": "Story"},
            "status": {"name": "In Progress"},
            "priority": {"name": "Medium"},
            "labels": [],
            "created": "2024-01-01T00:00:00Z",
            "updated": "2024-01-02T00:00:00Z",
            "comment": {
                "comments": [
                    {
                        "id": "comment1",
                        "body": "This is the first comment",
                        "author": {"displayName": "John Doe"},
                        "created": "2024-01-01T10:00:00Z",
                        "updated": "2024-01-01T10:00:00Z"
                    },
                    {
                        "id": "comment2",
                        "body": "This is the second comment",
                        "author": {"displayName": "Jane Smith"},
                        "created": "2024-01-01T11:00:00Z",
                        "updated": "2024-01-01T11:30:00Z"
                    }
                ]
            }
        }
    }
    
    uif = extractor.extract(key="PROJ-5678", raw_issue=raw_issue)
    
    # Assertions for comments
    assert "comments" in uif
    assert len(uif["comments"]) == 2
    
    # Check first comment
    comment1 = uif["comments"][0]
    assert comment1["text"] == "This is the first comment"
    assert comment1["author"] == "John Doe"
    assert comment1["created_at"] == "2024-01-01T10:00:00Z"
    assert "comment_" in comment1["id"]
    assert "source_ref" in comment1
    
    # Check second comment
    comment2 = uif["comments"][1]
    assert comment2["text"] == "This is the second comment"
    assert comment2["author"] == "Jane Smith"
    assert comment2["created_at"] == "2024-01-01T11:00:00Z"
    
    print("✓ test_jira_comments_extraction passed")


if __name__ == "__main__":
    test_jira_extraction_minimal()
    test_jira_acceptance_criteria_parsing()
    test_jira_status_normalization()
    test_jira_priority_normalization()
    test_jira_issue_type_normalization()
    test_jira_comments_extraction()
    print("\n✓ All Jira extractor tests passed!")
