"""UIF validators using JSON Schema."""

from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path
import json


class UIFValidator:
    """Validate UIF objects against schema."""
    
    def __init__(self, schema_path: Optional[str] = None):
        """Initialize validator with schema."""
        if not schema_path:
            # **This skill's own tree, and only its own tree.**
            #
            # It used to try `.agents/skills/shared/schemas/...` FIRST -- the
            # sibling project's layout -- and fall back to Métis's copy only if
            # that missed. Run from an Atlas checkout, Métis validated its
            # intake against Atlas's schema, silently, with the foreign one
            # winning on precedence. Porting a schema and then preferring the
            # original is not a port.
            possible_paths = [
                Path(__file__).parent.parent / "shared" / "schemas" / "unified-intake-format.schema.json",
            ]
            for p in possible_paths:
                if p.exists():
                    schema_path = str(p)
                    break
            if not schema_path:
                schema_path = str(possible_paths[0])  # Use first as fallback
        
        self.schema_path = Path(schema_path)
        self.schema = self._load_schema()
    
    def _load_schema(self) -> Dict[str, Any]:
        """Load schema from file."""
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Schema not found: {self.schema_path}")
        
        with self.schema_path.open() as f:
            return json.load(f)
    
    def validate(self, uif: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate UIF object against hard format constraints.
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        # STRICT: Check for additional/unexpected root properties
        allowed_root_fields = {
            "uif_version", "scope", "metadata", "facts", "specifications",
            "comments", "api_contracts", "data_model", "error_handling",
            "open_questions", "links"
        }
        unexpected_fields = set(uif.keys()) - allowed_root_fields
        if unexpected_fields:
            errors.append(f"UIF contains unexpected root fields (HARD FORMAT VIOLATION): {sorted(unexpected_fields)}")
        
        # Check required root properties
        if "uif_version" not in uif:
            errors.append("Missing required field: uif_version")
        elif uif["uif_version"] != "1.0.0":
            errors.append(f"Invalid uif_version: {uif['uif_version']}, expected 1.0.0")
        
        if "scope" not in uif:
            errors.append("Missing required field: scope")
        else:
            scope_errors = self._validate_scope(uif["scope"])
            errors.extend(scope_errors)
        
        if "metadata" not in uif:
            errors.append("Missing required field: metadata")
        else:
            metadata_errors = self._validate_metadata(uif["metadata"])
            errors.extend(metadata_errors)
        
        if "links" not in uif:
            errors.append("Missing required field: links")
        else:
            links_errors = self._validate_links(uif["links"])
            errors.extend(links_errors)
        
        return len(errors) == 0, errors
    
    def _validate_scope(self, scope: Dict[str, Any]) -> List[str]:
        """Validate scope object with strict field enforcement."""
        errors = []
        required = ["primary_id", "primary_type", "source_system", "created_at", "last_updated_at", "uif_generated_at"]
        
        # STRICT: Check for additional scope fields
        allowed_scope_fields = set(required) | {"secondary_id"}
        unexpected = set(scope.keys()) - allowed_scope_fields
        if unexpected:
            errors.append(f"scope: Contains unexpected fields (HARD FORMAT VIOLATION): {sorted(unexpected)}")
        
        for field in required:
            if field not in scope:
                errors.append(f"scope: Missing required field '{field}'")
        
        if "primary_type" in scope:
            valid_types = ["epic", "story", "feature", "task", "page", "test_case", "defect"]
            if scope["primary_type"] not in valid_types:
                errors.append(f"scope.primary_type: Invalid value '{scope['primary_type']}'")
        
        if "source_system" in scope:
            valid_systems = ["jira", "confluence", "scale", "code", "swagger", "database", "athena", "kubernetes", "composite"]
            if scope["source_system"] not in valid_systems:
                errors.append(f"scope.source_system: Invalid value '{scope['source_system']}'")
        
        return errors
    
    def _validate_metadata(self, metadata: Dict[str, Any]) -> List[str]:
        """Validate metadata object with strict field enforcement."""
        errors = []
        required = ["title", "status"]
        
        # STRICT: Check for additional metadata fields
        # Mirrors unified-intake-format.schema.json's metadata.properties exactly.
        # `tags` was missing here, which meant JiraExtractor's own output -- which
        # always emits metadata.tags -- failed this validator on every extraction.
        # The schema is the authority; this list had drifted from it.
        allowed_metadata_fields = {"title", "status", "priority", "created_at", "updated_at",
                                   "description", "tags"}
        unexpected = set(metadata.keys()) - allowed_metadata_fields
        if unexpected:
            errors.append(f"metadata: Contains unexpected fields (HARD FORMAT VIOLATION): {sorted(unexpected)}")
        
        for field in required:
            if field not in metadata:
                errors.append(f"metadata: Missing required field '{field}'")
        
        if "priority" in metadata:
            valid_priorities = ["critical", "high", "medium", "low", "optional"]
            if metadata["priority"] not in valid_priorities:
                errors.append(f"metadata.priority: Invalid value '{metadata['priority']}'")
        
        return errors

    def _validate_links(self, links: Any) -> List[str]:
        """Validate `links` array which should reference other UIF resources.

        Links must be a non-empty list. Each link may be a string or a small
        object (dict) describing the referenced UIF resource.
        """
        errors = []
        if not isinstance(links, list) or len(links) == 0:
            errors.append("links: Must be a non-empty list")
            return errors

        for idx, item in enumerate(links):
            if not isinstance(item, (str, dict)):
                errors.append(f"links[{idx}]: Invalid link type '{type(item).__name__}', expected string or object")

        return errors


def validate_and_report(uif: Dict[str, Any], source_name: str = "UIF") -> bool:
    """Validate UIF and print report with hard format enforcement."""
    validator = UIFValidator()
    is_valid, errors = validator.validate(uif)
    
    if is_valid:
        print(f"✓ {source_name} is valid (hard format compliant)")
        return True
    else:
        print(f"✗ {source_name} validation failed:")
        for error in errors:
            if "HARD FORMAT VIOLATION" in error:
                print(f"  [CRITICAL] {error}")
            else:
                print(f"  [ERROR] {error}")
        return False
