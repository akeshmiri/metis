"""Confluence to UIF extractor."""

from typing import Any, Dict, Optional
import re
from .base_extractor import BaseExtractor


class ConfluenceExtractor(BaseExtractor):
    """Extract UIF from Confluence pages."""
    
    def extract(self, page_id: str, confluence_client: Optional[Any] = None, raw_page: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Extract UIF from Confluence page.
        
        Args:
            page_id: Confluence page ID
            confluence_client: Optional Confluence client instance
            raw_page: Optional raw Confluence page dict (for testing without client)
        
        Returns:
            Minimal UIF object with facts and specifications
        """
        if not raw_page and not confluence_client:
            raise ValueError("Either raw_page or confluence_client must be provided")
        
        # Fetch page if not provided
        if not raw_page:
            try:
                raw_page = confluence_client.get_page_by_id(page_id, expand='body.storage')
            except Exception as e:
                raise RuntimeError(f"Failed to fetch Confluence page {page_id}: {e}")
        
        # Extract fields
        title = raw_page.get("title", "")
        page_body = raw_page.get("body", {}).get("storage", {}).get("value", "")
        created = raw_page.get("created", "")
        updated = raw_page.get("updated", "")
        
        # Parse sections from body
        sections = self._parse_sections(page_body)
        
        # Build UIF
        source_ref = self._build_source_reference(
            source_system="confluence",
            source_id=page_id,
            source_url=f"https://confluence.example.com/pages/viewpage.action?pageId={page_id}",
            fields_extracted=["title", "body"]
        )
        
        scope = self._build_uif_scope(
            primary_id=page_id,
            primary_type="feature",
            source_system="confluence"
        )
        
        metadata = {
            "title": title,
            # Full paragraph, not truncated. The Atlas original capped this at
            # 200 characters -- the identical defect the Jira extractor carried,
            # and it matters more here: a Confluence page's opening paragraph is
            # frequently where the requirement is stated, and the cap cut it
            # mid-word. The UIF schema sets no maxLength, and in this pipeline
            # the description IS the evidence that gets mined.
            "description": self._extract_first_paragraph(page_body),
            "status": self._build_normalized_status(),
            "priority": "high",
            "tags": []
        }
        
        # Build specifications from sections
        specifications = self._build_specifications_from_sections(sections)
        
        # Build UIF with empty comments (Confluence comments would need separate extraction)
        uif = self._build_uif(
            scope=scope,
            metadata=metadata,
            specifications=specifications,
            comments=[],
            source_references=[source_ref]
        )
        
        return uif
    
    def _parse_sections(self, html_body: str) -> Dict[str, str]:
        """Parse sections from Confluence HTML body by header patterns."""
        sections = {}
        
        # Simple regex-based header extraction (real implementation would use BeautifulSoup)
        header_pattern = r'<h[2-6]>(.*?)</h[2-6]>'
        headers = re.findall(header_pattern, html_body)
        
        # Known section patterns
        section_patterns = {
            "Requirements": "business_rules",
            "Acceptance Criteria": "acceptance_criteria",
            "Performance": "nfr",
            "Deployment": "deployment_model",
            "Dependencies": "dependencies",
            "Known Issues": "known_issues"
        }
        
        for header in headers:
            clean_header = header.lower().strip()
            for pattern, section_key in section_patterns.items():
                if pattern.lower() in clean_header:
                    # Extract content following this header
                    sections[section_key] = self._extract_section_content(html_body, header)
                    break
        
        return sections
    
    def _extract_section_content(self, html_body: str, header: str) -> str:
        """Extract content following a specific header."""
        # Find header position
        header_pos = html_body.find(header)
        if header_pos == -1:
            return ""
        
        # Extract until next header or end
        next_header_pos = html_body.find("<h", header_pos + 1)
        if next_header_pos == -1:
            content = html_body[header_pos:]
        else:
            content = html_body[header_pos:next_header_pos]
        
        # Remove HTML tags
        content = re.sub(r'<[^>]+>', '', content)
        return content.strip()
    
    def _extract_first_paragraph(self, html_body: str) -> str:
        """Extract first paragraph from HTML body."""
        # Find first <p> tag
        match = re.search(r'<p>(.*?)</p>', html_body, re.DOTALL)
        if match:
            text = re.sub(r'<[^>]+>', '', match.group(1))
            return text.strip()
        return ""
    
    def _build_specifications_from_sections(self, sections: Dict[str, str]) -> Dict[str, Any]:
        """Build specifications object from parsed sections."""
        specs = {}
        
        # Requirements → business_rules
        if "business_rules" in sections:
            specs["business_rules"] = [
                {"statement": line.strip(), "type": "functional"}
                for line in sections["business_rules"].split("\n")
                if line.strip() and not line.strip().startswith("<")
            ]
        
        # Acceptance Criteria → acceptance_criteria[]
        if "acceptance_criteria" in sections:
            criteria = []
            for line in sections["acceptance_criteria"].split("\n"):
                if line.strip() and not line.strip().startswith("<"):
                    criteria.append(self._build_acceptance_criterion(
                        statement=line.strip(),
                        criterion_type="functional"
                    ))
            if criteria:
                specs["acceptance_criteria"] = criteria
        
        # Performance → nfr[]
        if "nfr" in sections:
            specs["non_functional_requirements"] = [
                {
                    "id": f"nfr_{i}",
                    "category": "performance",
                    "requirement": line.strip(),
                    "targets": {},
                    "measurement_method": ""
                }
                for i, line in enumerate(sections["nfr"].split("\n"))
                if line.strip() and not line.strip().startswith("<")
            ]
        
        # Deployment model
        if "deployment_model" in sections:
            specs["deployment_model"] = [
                {"component": line.strip()}
                for line in sections["deployment_model"].split("\n")
                if line.strip() and not line.strip().startswith("<")
            ]
        
        # Dependencies
        if "dependencies" in sections:
            specs["dependencies"] = [
                {"description": line.strip()}
                for line in sections["dependencies"].split("\n")
                if line.strip() and not line.strip().startswith("<")
            ]
        
        return specs

    def convert(self, raw: Dict[str, Any], identifier: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Convert a raw Confluence page payload into a UIF object.
        """
        page_id = identifier or raw.get("id") or raw.get("pageId") or raw.get("page_id")
        if not page_id:
            raise ValueError("Could not infer page id from raw payload; provide `identifier` or include `id` in raw data")
        return self.extract(page_id=page_id, raw_page=raw)
