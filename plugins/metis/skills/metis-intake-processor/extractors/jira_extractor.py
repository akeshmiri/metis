"""Jira to UIF extractor."""

from typing import Any, Dict, Optional
import re
from .base_extractor import BaseExtractor


class JiraExtractor(BaseExtractor):
    """Extract UIF from Jira tickets."""
    
    def extract(self, key: str, jira_client: Optional[Any] = None, raw_issue: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Extract UIF from Jira ticket.
        
        Args:
            key: Jira issue key (e.g., "PROJ-1234")
            jira_client: Optional Jira client instance
            raw_issue: Optional raw Jira issue dict (for testing without client)
        
        Returns:
            Minimal UIF object with facts and specifications
        """
        if not raw_issue and not jira_client:
            raise ValueError("Either raw_issue or jira_client must be provided")
        
        # Fetch issue if not provided
        if not raw_issue:
            try:
                raw_issue = jira_client.issue(key).raw
            except Exception as e:
                raise RuntimeError(f"Failed to fetch Jira ticket {key}: {e}")
        
        # Extract fields
        fields = raw_issue.get("fields", {})
        summary = fields.get("summary", "")
        description = fields.get("description", "")
        issue_type = fields.get("issuetype", {}).get("name", "task")
        status = fields.get("status", {}).get("name", "unknown")
        priority = fields.get("priority", {}).get("name", "medium")
        labels = fields.get("labels", [])
        created = fields.get("created", "")
        updated = fields.get("updated", "")
        
        # Parse acceptance criteria from description
        acceptance_criteria = self._parse_acceptance_criteria(description)
        
        # Extract comments
        comments = self._extract_comments(raw_issue, key)
        
        # Build UIF
        source_ref = self._build_source_reference(
            source_system="jira",
            source_id=key,
            source_url=f"https://jira.example.com/browse/{key}",
            fields_extracted=["summary", "description", "issuetype", "status", "priority", "labels", "comment"]
        )
        
        scope = self._build_uif_scope(
            primary_id=key,
            primary_type=self._normalize_issue_type(issue_type),
            source_system="jira"
        )
        
        metadata = {
            "title": summary,
            # Full description, not truncated. The Atlas original capped this at
            # 200 characters, which silently destroyed requirements: a Jira
            # description listing acceptance criteria as bullets lost every
            # bullet past the cap, mid-word. The schema sets no maxLength, and
            # in this pipeline the description IS the primary evidence that gets
            # mined into Requirements.
            "description": description or "",
            "status": self._build_normalized_status(
                approval_state="draft",
                summary_status=self._normalize_status(status)
            ),
            "priority": self._normalize_priority(priority),
            "tags": labels
        }
        
        # Build specifications with acceptance criteria
        specifications = {}
        if acceptance_criteria:
            specifications["acceptance_criteria"] = acceptance_criteria
        
        # Build UIF
        uif = self._build_uif(
            scope=scope,
            metadata=metadata,
            specifications=specifications,
            comments=comments,
            source_references=[source_ref]
        )
        
        return uif
    
    def _parse_acceptance_criteria(self, description: str) -> list:
        """Parse acceptance criteria from description text."""
        if not description:
            return []
        
        criteria = []
        # Look for lines starting with "Given", "When", "Then" (BDD format)
        lines = description.split("\n")
        
        current_criterion = []
        for line in lines:
            line = line.strip()
            if line.startswith("Given") or line.startswith("When") or line.startswith("Then"):
                if current_criterion:
                    criteria.append(self._build_acceptance_criterion(
                        statement=" ".join(current_criterion),
                        criterion_type="functional",
                        priority="must_have",
                        verification_method="manual"
                    ))
                    current_criterion = []
                current_criterion.append(line)
            elif line and current_criterion:
                current_criterion.append(line)
        
        # Add last criterion if any
        if current_criterion:
            criteria.append(self._build_acceptance_criterion(
                statement=" ".join(current_criterion),
                criterion_type="functional",
                priority="must_have",
                verification_method="manual"
            ))
        
        return criteria
    
    def _extract_comments(self, raw_issue: Dict[str, Any], key: str) -> list:
        """Extract comments from Jira ticket."""
        comments = []
        
        # Access comments from Jira fields
        fields = raw_issue.get("fields", {})
        comment_data = fields.get("comment", {})
        comment_list = comment_data.get("comments", [])
        
        # Build comment objects from Jira comments
        for jira_comment in comment_list:
            comment_text = jira_comment.get("body", "")
            author = jira_comment.get("author", {}).get("displayName", "unknown")
            created_at = jira_comment.get("created")
            updated_at = jira_comment.get("updated")
            
            # Build source reference for this comment
            comment_source_ref = self._build_source_reference(
                source_system="jira",
                source_id=f"{key}#{jira_comment.get('id', 'unknown')}",
                source_url=f"https://jira.example.com/browse/{key}?focusedCommentId={jira_comment.get('id', '')}",
                quote=comment_text[:100] if comment_text else "",
                fields_extracted=["body", "author", "created", "updated"]
            )
            
            # Build comment object
            comment_obj = self._build_comment(
                text=comment_text,
                author=author,
                created_at=created_at,
                updated_at=updated_at,
                source_ref=comment_source_ref
            )
            comments.append(comment_obj)
        
        return comments
    
    def _normalize_issue_type(self, issue_type: str) -> str:
        """Normalize Jira issue type to UIF primary_type."""
        mapping = {
            "Epic": "epic",
            "Story": "story",
            "Feature": "feature",
            "Task": "task",
            "Bug": "defect",
            "Defect": "defect"
        }
        return mapping.get(issue_type, "task")
    
    def _normalize_status(self, jira_status: str) -> str:
        """Normalize Jira status to UIF summary_status."""
        mapping = {
            "To Do": "draft",
            "In Progress": "active",
            "In Review": "active",
            "Done": "completed",
            "Closed": "completed"
        }
        return mapping.get(jira_status, "draft")
    
    def _normalize_priority(self, jira_priority: str) -> str:
        """Normalize Jira priority to UIF priority."""
        mapping = {
            "Blocker": "critical",
            "Critical": "critical",
            "High": "high",
            "Medium": "medium",
            "Low": "low",
            "Trivial": "low"
        }
        return mapping.get(jira_priority, "medium")

    def convert(self, raw: Dict[str, Any], identifier: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Convert a raw Jira payload (or similar dict) into a UIF object.

        If `identifier` (ticket key) is not provided, attempt to infer it
        from common fields in the raw payload.
        """
        key = identifier or raw.get("key") or raw.get("id") or raw.get("key")
        if not key:
            raise ValueError("Could not infer ticket key from raw payload; provide `identifier` or include `key` in raw data")
        return self.extract(key=key, raw_issue=raw)
