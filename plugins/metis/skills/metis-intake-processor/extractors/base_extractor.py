"""Abstract base extractor for all UIF sources."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Iterable, Iterator
import json
import uuid


class BaseExtractor(ABC):
    """Abstract base class for all UIF extractors."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize extractor with optional config."""
        self.config = self._load_config(config_path) if config_path else {}
        self.extracted_at = datetime.now(timezone.utc).isoformat()
        self.extractor_name = self.__class__.__name__
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load YAML/JSON config for this extractor."""
        path = Path(config_path)
        if not path.exists():
            return {}
        
        try:
            with path.open() as f:
                if config_path.endswith('.json'):
                    return json.load(f)
                else:
                    import yaml
                    return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Could not load config from {config_path}: {e}")
            return {}
    
    @abstractmethod
    def extract(self, **kwargs) -> Dict[str, Any]:
        """Extract and return UIF object."""
        pass
    
    def _build_source_reference(
        self,
        source_system: str,
        source_id: str,
        source_url: Optional[str] = None,
        quote: Optional[str] = None,
        confidence: str = "direct",
        fields_extracted: Optional[list] = None
    ) -> Dict[str, Any]:
        """Build a standardized source_reference object."""
        return {
            "source_system": source_system,
            "source_id": source_id,
            "source_url": source_url,
            "quote": quote,
            "confidence": confidence,
            "extracted_at": self.extracted_at,
            "extracted_by": self.extractor_name,
            "fields_extracted": fields_extracted or []
        }
    
    def _build_normalized_status(
        self,
        approval_state: str = "draft",
        automation_status: str = "not_started",
        validation_status: str = "not_validated",
        measurement_status: str = "not_measured",
        freshness_status: str = "fresh",
        summary_status: str = "draft"
    ) -> Dict[str, Any]:
        """Build a normalized_status object."""
        return {
            "approval_state": approval_state,
            "automation_status": automation_status,
            "validation_status": validation_status,
            "measurement_status": measurement_status,
            "freshness_status": freshness_status,
            "summary_status": summary_status,
            "last_status_update": self.extracted_at
        }
    
    def _build_fact(
        self,
        name: str,
        value: Any,
        fact_type: str = "observation",
        source_ref: Optional[Dict] = None,
        unit: Optional[str] = None,
        confidence: str = "observed",
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Build a fact object."""
        return {
            "id": f"fact_{uuid.uuid4().hex[:8]}",
            "type": fact_type,
            "name": name,
            "description": description,
            "value": value,
            "unit": unit,
            "confidence": confidence,
            "source_ref": source_ref or {},
            "derived": False,
            "timestamp": self.extracted_at
        }
    
    def _build_acceptance_criterion(
        self,
        statement: str,
        criterion_type: str = "functional",
        priority: str = "must_have",
        verification_method: str = "manual",
        source_ref: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Build an acceptance_criterion object."""
        return {
            "id": f"ac_{uuid.uuid4().hex[:8]}",
            "statement": statement,
            "type": criterion_type,
            "priority": priority,
            "verification_method": verification_method,
            "test_case_ids": [],
            "automation_coverage": {},
            "status": "pending",
            "source_ref": source_ref or {},
            "derived": False
        }
    
    def _build_comment(
        self,
        text: str,
        author: str = "unknown",
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        source_ref: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Build a comment object."""
        return {
            "id": f"comment_{uuid.uuid4().hex[:8]}",
            "text": text,
            "author": author,
            "created_at": created_at or self.extracted_at,
            "updated_at": updated_at or self.extracted_at,
            "source_ref": source_ref or {},
            "derived": False
        }
    
    def _build_uif_scope(
        self,
        primary_id: str,
        primary_type: str,
        source_system: str,
        secondary_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Build UIF scope object."""
        now = datetime.now(timezone.utc).isoformat()
        return {
            "primary_id": primary_id,
            "primary_type": primary_type,
            "secondary_id": secondary_id,
            "source_system": source_system,
            "created_at": now,
            "last_updated_at": now,
            "uif_generated_at": now
        }
    
    def _build_uif(
        self,
        scope: Dict[str, Any],
        metadata: Dict[str, Any],
        facts: Optional[Dict[str, Any]] = None,
        specifications: Optional[Dict[str, Any]] = None,
        comments: Optional[list] = None,
        source_references: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Build minimal but valid UIF object with hard format constraints.
        
        UIF is a HARD FORMAT - no additional fields can be added by extractors.
        Any attempt to extend this contract must be reviewed and approved.
        """
        if not source_references:
            raise ValueError("At least one source_reference is required")
        
        # Build with ONLY allowed root fields (hard format)
        # Build links from provided source_references. Each link is a simple
        # href string referencing the upstream resource when possible.
        links = []
        for sr in source_references:
            if isinstance(sr, dict):
                href = sr.get("source_url") or f"{sr.get('source_system')}:{sr.get('source_id')}"
            else:
                href = str(sr)
            links.append(href)

        uif = {
            "uif_version": "1.0.0",
            "scope": scope,
            "metadata": metadata,
            "facts": facts or {},
            "specifications": specifications or {},
            "comments": comments or [],
            "api_contracts": [],
            "data_model": [],
            "error_handling": {},
            "open_questions": {},
            "links": links
        }
        
        # HARD FORMAT GUARD: Verify no additional fields are present
        allowed_root_fields = {
            "uif_version", "scope", "metadata", "facts", "specifications",
            "comments", "api_contracts", "data_model", "error_handling",
            "open_questions", "links"
        }
        actual_fields = set(uif.keys())
        if actual_fields != allowed_root_fields:
            unexpected = actual_fields - allowed_root_fields
            raise ValueError(f"HARD FORMAT VIOLATION: Attempted to add unexpected fields to UIF: {unexpected}")
        
        return uif

    def convert(self, raw: Dict[str, Any], identifier: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Convenience wrapper to convert a raw payload into a UIF object.

        Default implementation raises NotImplementedError and should be
        implemented by subclasses to map raw payloads to the appropriate
        `extract(...)` call (e.g. `raw_issue` -> `extract(key=..., raw_issue=...)`).
        """
        raise NotImplementedError("Subclasses should implement convert(raw, identifier, **kwargs)")

    def convert_many(self, items: Iterable[Dict[str, Any]], **kwargs) -> Iterator[Dict[str, Any]]:
        """
        Generator that converts an iterable of raw payloads into UIF objects
        by calling `convert()` for each item.
        """
        for item in items:
            yield self.convert(item, **kwargs)
