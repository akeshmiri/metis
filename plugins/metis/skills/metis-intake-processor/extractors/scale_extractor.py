"""Zephyr Scale to UIF Extractor."""

from typing import Any, Dict, List, Optional
from .base_extractor import BaseExtractor


class ScaleExtractor(BaseExtractor):
    """Extract Zephyr Scale test cases into UIF format."""
    
    def extract(self, case_key: str = None, raw_case: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        """Extract UIF from Zephyr Scale test case.
        
        Args:
            case_key: Scale test case key (e.g., "PROJ-T-123")
            raw_case: Pre-loaded test case dict
        
        Returns:
            UIF object with business_flows and acceptance_criteria
        """
        if raw_case:
            test_case = raw_case
        elif case_key:
            # TODO: Implement API client for fetching from Zephyr
            raise NotImplementedError("API client not yet implemented. Use raw_case dict.")
        else:
            raise ValueError("One of case_key or raw_case required")
        
        # Extract test case metadata
        case_id = test_case.get("key", case_key or "unknown")
        summary = test_case.get("name", test_case.get("summary", ""))
        description = test_case.get("description", "")
        priority = test_case.get("priority", "medium").lower()
        status = test_case.get("status", "draft").lower()
        
        # Extract test steps → business_flows
        business_flows = self._extract_business_flows(test_case)
        
        # Extract expected results → acceptance_criteria
        acceptance_criteria = self._extract_acceptance_criteria(test_case)
        
        # Build UIF scope
        scope = self._build_uif_scope(
            primary_id=case_id,
            primary_type="test_case",
            source_system="scale"
        )
        
        # Build normalized status
        metadata_status = self._build_normalized_status(
            summary_status=self._normalize_status(status),
            validation_status="manual_definition"
        )
        
        source_ref = self._build_source_reference(
            source_system="scale",
            source_id=case_id
        )
        
        uif = self._build_uif(
            scope=scope,
            metadata={
                "title": f"{case_id}: {summary}",
                "description": description,
                "status": metadata_status,
                "priority": priority,
                "tags": ["test_case", "scale", status]
            },
            specifications={
                "business_flows": business_flows,
                "acceptance_criteria": acceptance_criteria
            },
            comments=[],
            source_references=[source_ref]
        )
        
        return uif
    
    def _extract_business_flows(self, test_case: Dict) -> List[Dict]:
        """Extract test steps into business_flows."""
        flows = []
        
        steps = test_case.get("steps", [])
        if not steps:
            steps = test_case.get("testcase_steps", [])
        
        for idx, step in enumerate(steps, 1):
            if isinstance(step, str):
                step_text = step
                step_expected = ""
            elif isinstance(step, dict):
                step_text = step.get("step", step.get("description", ""))
                step_expected = step.get("expected", step.get("expected_result", ""))
            else:
                continue
            
            flow = {
                "id": self._generate_id(f"{test_case.get('key', 'case')}_flow_{idx}"),
                "sequence": idx,
                "step_number": idx,
                "action": step_text,
                "expected_outcome": step_expected,
                "preconditions": [],
                "source_reference": self._build_source_reference(
                    source_system="scale",
                    source_id=f"{test_case.get('key', 'case')}_step_{idx}"
                )
            }
            flows.append(flow)
        
        return flows
    
    def _extract_acceptance_criteria(self, test_case: Dict) -> List[Dict]:
        """Extract test results into acceptance_criteria."""
        criteria = []
        
        # From explicit expected_result
        expected_result = test_case.get("expected_result", "")
        if expected_result:
            crit = {
                "id": self._generate_id(f"{test_case.get('key', 'case')}_criterion_1"),
                "description": expected_result,
                "verification_method": "manual_verification",
                "acceptance_criteria_type": "functionality",
                "success_condition": expected_result,
                "source_reference": self._build_source_reference(
                    source_system="scale",
                    source_id=f"{test_case.get('key', 'case')}_expected_result"
                )
            }
            criteria.append(crit)
        
        # From step-level expected results
        steps = test_case.get("steps", [])
        if not steps:
            steps = test_case.get("testcase_steps", [])
        
        for idx, step in enumerate(steps, 1):
            if isinstance(step, dict):
                step_expected = step.get("expected", step.get("expected_result", ""))
                if step_expected:
                    crit = {
                        "id": self._generate_id(f"{test_case.get('key', 'case')}_criterion_step_{idx}"),
                        "description": f"Step {idx}: {step_expected}",
                        "verification_method": "manual_verification",
                        "acceptance_criteria_type": "step_verification",
                        "success_condition": step_expected,
                        "source_reference": self._build_source_reference(
                            source_system="scale",
                            source_id=f"{test_case.get('key', 'case')}_step_{idx}_expected"
                        )
                    }
                    criteria.append(crit)
        
        return criteria
    
    def _normalize_status(self, status: str) -> str:
        """Normalize test case status to UIF status enum."""
        status_map = {
            "draft": "draft",
            "ready": "active",
            "approved": "active",
            "executing": "active",
            "pass": "completed",
            "fail": "completed",
            "blocked": "blocked",
            "deprecated": "archived"
        }
        return status_map.get(status.lower(), "draft")
    
    def _generate_id(self, name: str) -> str:
        """Generate deterministic ID from name."""
        import uuid
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))

    def convert(self, raw: Dict[str, Any], identifier: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Convert a raw Zephyr Scale test case payload into a UIF object.
        """
        case_key = identifier or raw.get("key") or raw.get("id")
        return self.extract(case_key=case_key, raw_case=raw)
