"""Swagger/OpenAPI to UIF Extractor."""

import json
import yaml
from typing import Any, Dict, List, Optional
from pathlib import Path
from .base_extractor import BaseExtractor


class SwaggerExtractor(BaseExtractor):
    """Extract Swagger/OpenAPI specifications into UIF format."""
    
    def extract(self, spec_path: str = None, spec_url: str = None, 
                raw_spec: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        """Extract UIF from Swagger/OpenAPI specification."""
        # Load spec
        if raw_spec:
            spec = raw_spec
        elif spec_path:
            spec = self._load_spec_file(spec_path)
        elif spec_url:
            raise NotImplementedError("URL loading not yet implemented")
        else:
            raise ValueError("One of spec_path, spec_url, or raw_spec required")
        
        # Extract title, version, servers
        title = spec.get("info", {}).get("title", "API Specification")
        version = spec.get("info", {}).get("version", "1.0.0")
        base_path = self._extract_base_path(spec)
        
        # Extract endpoints and schemas
        api_endpoints = self._extract_api_endpoints(spec, base_path)
        data_model = self._extract_data_model(spec)
        
        # Build UIF
        scope = self._build_uif_scope(
            primary_id=f"{title.lower().replace(' ', '-')}-{version}",
            primary_type="api_specification",
            source_system="swagger"
        )
        
        source_ref = self._build_source_reference(
            source_system="swagger",
            source_id=spec_path or "raw_spec"
        )
        
        uif = self._build_uif(
            scope=scope,
            metadata={
                "title": f"{title} (v{version})",
                "description": spec.get("info", {}).get("description", ""),
                "status": {"summary_status": "active"},
                "tags": ["api", "swagger"]
            },
            specifications={
                "api_endpoints": api_endpoints,
                "data_model": data_model
            },
            comments=[],
            source_references=[source_ref]
        )
        
        return uif
    
    def _load_spec_file(self, spec_path: str) -> Dict[str, Any]:
        """Load Swagger spec from JSON or YAML file."""
        path = Path(spec_path)
        if not path.exists():
            raise FileNotFoundError(f"Spec file not found: {spec_path}")
        
        with open(path, 'r') as f:
            if path.suffix.lower() in ['.yaml', '.yml']:
                return yaml.safe_load(f)
            elif path.suffix.lower() == '.json':
                return json.load(f)
            else:
                raise ValueError(f"Unsupported file format: {path.suffix}")
    
    def _extract_base_path(self, spec: Dict) -> str:
        """Extract base path from spec (OpenAPI 2.0 or 3.0)."""
        if "servers" in spec and spec["servers"]:
            return spec["servers"][0].get("url", "")
        return spec.get("basePath", "")
    
    def _extract_api_endpoints(self, spec: Dict, base_path: str = "") -> List[Dict]:
        """Extract API paths and operations into api_endpoints."""
        endpoints = []
        
        paths = spec.get("paths", {})
        for path_str, path_obj in paths.items():
            full_path = f"{base_path}{path_str}".rstrip("/") or "/"
            
            for method, operation in path_obj.items():
                if method.lower() not in ["get", "post", "put", "delete", "patch", "head", "options"]:
                    continue
                
                endpoint = {
                    "id": self._generate_id(f"{method.upper()}_{path_str}"),
                    "path": full_path,
                    "method": method.upper(),
                    "summary": operation.get("summary", ""),
                    "description": operation.get("description", ""),
                    "operationId": operation.get("operationId", ""),
                    "tags": operation.get("tags", []),
                    "parameters": self._extract_parameters(operation),
                    "requestBody": self._extract_request_body(operation),
                    "responses": self._extract_responses(operation),
                    "source_reference": self._build_source_reference(
                        source_system="swagger",
                        source_id=f"{method.upper()} {full_path}"
                    )
                }
                endpoints.append(endpoint)
        
        return endpoints
    
    def _extract_parameters(self, operation: Dict) -> List[Dict]:
        """Extract parameters from operation."""
        parameters = []
        
        for param in operation.get("parameters", []):
            param_obj = {
                "name": param.get("name", ""),
                "in": param.get("in", "query"),
                "required": param.get("required", False),
                "type": param.get("type", param.get("schema", {}).get("type", "string")),
                "description": param.get("description", "")
            }
            parameters.append(param_obj)
        
        return parameters
    
    def _extract_request_body(self, operation: Dict) -> Optional[Dict]:
        """Extract request body from operation."""
        req_body = operation.get("requestBody", {})
        if not req_body:
            return None
        
        content = req_body.get("content", {})
        if not content:
            return None
        
        first_type = next(iter(content.keys()))
        schema = content[first_type].get("schema", {})
        
        return {
            "required": req_body.get("required", False),
            "contentType": first_type,
            "schema": schema.get("$ref") or schema.get("type", "object")
        }
    
    def _extract_responses(self, operation: Dict) -> List[Dict]:
        """Extract responses from operation."""
        responses = []
        
        for status_code, response in operation.get("responses", {}).items():
            resp_obj = {
                "statusCode": status_code,
                "description": response.get("description", ""),
                "contentTypes": list(response.get("content", {}).keys()) if response.get("content") else []
            }
            responses.append(resp_obj)
        
        return responses
    
    def _extract_data_model(self, spec: Dict) -> List[Dict]:
        """Extract data model from schemas."""
        data_entities = []
        
        schemas = spec.get("components", {}).get("schemas", {})
        if not schemas:
            schemas = spec.get("definitions", {})
        
        for schema_name, schema_def in schemas.items():
            entity = {
                "id": self._generate_id(schema_name),
                "name": schema_name,
                "type": schema_def.get("type", "object"),
                "description": schema_def.get("description", ""),
                "properties": self._extract_properties(schema_def),
                "required": schema_def.get("required", []),
                "source_reference": self._build_source_reference(
                    source_system="swagger",
                    source_id=schema_name
                )
            }
            data_entities.append(entity)
        
        return data_entities
    
    def _extract_properties(self, schema: Dict) -> List[Dict]:
        """Extract properties from schema."""
        properties = []
        
        for prop_name, prop_def in schema.get("properties", {}).items():
            prop_obj = {
                "name": prop_name,
                "type": prop_def.get("type", "string"),
                "description": prop_def.get("description", ""),
                "format": prop_def.get("format", ""),
                "required": prop_name in schema.get("required", [])
            }
            properties.append(prop_obj)
        
        return properties
    
    def _generate_id(self, name: str) -> str:
        """Generate deterministic ID from name."""
        import uuid
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))

    def convert(self, raw: Dict[str, Any], identifier: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Convert an in-memory OpenAPI/Swagger spec dict into a UIF object.
        """
        return self.extract(raw_spec=raw)
