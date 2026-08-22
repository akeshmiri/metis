"""Source code to UIF Extractor."""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from .base_extractor import BaseExtractor


class CodeExtractor(BaseExtractor):
    """Extract acceptance criteria and data models from source code."""
    
    def extract(self, source_path: str = None, raw_content: str = None, language: str = None, **kwargs) -> Dict[str, Any]:
        """Extract UIF from source code (BDD, DDL, comments).
        
        Args:
            source_path: Path to source file
            raw_content: Pre-loaded source content
            language: Programming language (java, python, sql, etc.)
        
        Returns:
            UIF object with acceptance_criteria and data_model
        """
        if raw_content:
            content = raw_content
            source_id = "raw_code"
        elif source_path:
            if not os.path.exists(source_path):
                raise FileNotFoundError(f"Source file not found: {source_path}")
            with open(source_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            source_id = os.path.basename(source_path)
        else:
            raise ValueError("One of source_path or raw_content required")
        
        # Detect language if not specified
        if not language and source_path:
            ext = Path(source_path).suffix.lower()
            language = self._detect_language(ext)
        
        # Extract BDD scenarios → acceptance_criteria
        acceptance_criteria = self._extract_bdd_scenarios(content)
        
        # Extract DDL statements → data_model
        data_model = self._extract_ddl_statements(content)
        
        # Build UIF scope
        scope = self._build_uif_scope(
            primary_id=source_id,
            primary_type="source_code",
            source_system="code_repository"
        )
        
        # Build normalized status
        metadata_status = self._build_normalized_status(
            validation_status="code_defined"
        )
        
        source_ref = self._build_source_reference(
            source_system="code_repository",
            source_id=source_id
        )
        
        uif = self._build_uif(
            scope=scope,
            metadata={
                "title": f"Code Artifacts: {source_id}",
                "language": language,
                "status": metadata_status,
                "tags": ["source_code", "bdd", "ddl"] if (acceptance_criteria or data_model) else ["source_code"],
                "content_length": len(content),
                "scenario_count": len(acceptance_criteria),
                "table_count": len(data_model)
            },
            specifications={
                "acceptance_criteria": acceptance_criteria,
                "data_model": data_model
            },
            comments=[],
            source_references=[source_ref]
        )
        
        return uif
    
    def _detect_language(self, file_ext: str) -> str:
        """Detect programming language from file extension."""
        lang_map = {
            '.java': 'java',
            '.py': 'python',
            '.sql': 'sql',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.cs': 'csharp',
            '.go': 'go',
            '.rb': 'ruby',
            '.php': 'php',
            '.scala': 'scala',
            '.kt': 'kotlin'
        }
        return lang_map.get(file_ext, 'unknown')
    
    def _extract_bdd_scenarios(self, content: str) -> List[Dict]:
        """Extract BDD Given/When/Then scenarios into acceptance_criteria."""
        criteria = []
        
        # Find all Scenarios - match scenario name and steps block
        pattern = r'Scenario:\s*(.+?)\n((?:\s*(?:Given|When|Then|And|But)\s.+\n)*)'
        scenarios = re.findall(pattern, content, re.MULTILINE)
        
        for idx, (scenario_name, steps_block) in enumerate(scenarios, 1):
            # Parse Given/When/Then structure
            given_steps = re.findall(r'Given\s+(.+?)(?:\n|$)', steps_block, re.MULTILINE)
            when_steps = re.findall(r'When\s+(.+?)(?:\n|$)', steps_block, re.MULTILINE)
            then_steps = re.findall(r'Then\s+(.+?)(?:\n|$)', steps_block, re.MULTILINE)
            
            if given_steps or when_steps or then_steps:
                crit = {
                    "id": self._generate_id(f"bdd_scenario_{idx}"),
                    "description": scenario_name.strip(),
                    "verification_method": "automated_bdd",
                    "acceptance_criteria_type": "behavior_driven",
                    "preconditions": given_steps,
                    "actions": when_steps,
                    "success_condition": " AND ".join(then_steps) if then_steps else "",
                    "source_reference": self._build_source_reference(
                        source_system="code_repository",
                        source_id=f"scenario_{idx}"
                    )
                }
                criteria.append(crit)
        
        return criteria
    
    def _extract_ddl_statements(self, content: str) -> List[Dict]:
        """Extract DDL (CREATE TABLE, ALTER TABLE) statements into data_model."""
        tables = []
        
        # Pattern: CREATE TABLE statement
        pattern = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]+)\)'
        matches = re.finditer(pattern, content, re.IGNORECASE | re.DOTALL)
        
        for idx, match in enumerate(matches, 1):
            table_name = match.group(1).strip()
            columns_block = match.group(2)
            
            # Parse columns
            columns = self._parse_columns(columns_block)
            
            table = {
                "id": self._generate_id(table_name),
                "entity_name": table_name,
                "entity_type": "table",
                "description": f"Table: {table_name}",
                "attributes": columns,
                "source_reference": self._build_source_reference(
                    source_system="code_repository",
                    source_id=f"table_{table_name}"
                )
            }
            tables.append(table)
        
        return tables
    
    def _parse_columns(self, columns_block: str) -> List[Dict]:
        """Parse DDL column definitions."""
        columns = []
        
        # Split by comma, handling parentheses (e.g., ENUM('a', 'b'))
        column_defs = self._split_columns(columns_block)
        
        for col_def in column_defs:
            col_def = col_def.strip()
            if not col_def or col_def.startswith('PRIMARY') or col_def.startswith('FOREIGN') or col_def.startswith('UNIQUE') or col_def.startswith('KEY') or col_def.startswith('INDEX') or col_def.startswith('CONSTRAINT'):
                continue
            
            # Parse: COLUMN_NAME TYPE [constraints]
            # Handle types like VARCHAR(255), DECIMAL(10,2), etc.
            col_def_upper = col_def.upper()
            
            # Extract column name (first word)
            parts = col_def.split()
            if len(parts) < 1:
                continue
            
            col_name = parts[0]
            
            # Extract data type (including parentheses)
            type_match = re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\([^)]*\))?', col_def[len(col_name):].strip())
            col_type = type_match.group(0).strip() if type_match else (parts[1] if len(parts) > 1 else 'UNKNOWN')
            
            # Extract constraints
            constraints = []
            if 'NOT' in col_def_upper and 'NULL' in col_def_upper:
                constraints.append('NOT_NULL')
            if 'PRIMARY' in col_def_upper and 'KEY' in col_def_upper:
                constraints.append('PRIMARY_KEY')
            if 'UNIQUE' in col_def_upper:
                constraints.append('UNIQUE')
            if 'DEFAULT' in col_def_upper:
                constraints.append('HAS_DEFAULT')
            
            col = {
                "attribute_name": col_name,
                "data_type": col_type,
                "constraints": constraints,
                "nullable": 'NOT NULL' not in col_def_upper
            }
            columns.append(col)
        
        return columns
    def _split_columns(self, columns_block: str) -> List[str]:
        """Split column definitions by comma, respecting parentheses."""
        columns = []
        current = ""
        paren_depth = 0
        
        for char in columns_block:
            if char == '(':
                paren_depth += 1
                current += char
            elif char == ')':
                paren_depth -= 1
                current += char
            elif char == ',' and paren_depth == 0:
                columns.append(current)
                current = ""
            else:
                current += char
        
        if current:
            columns.append(current)
        
        return columns
    
    def _generate_id(self, name: str) -> str:
        """Generate deterministic ID from name."""
        import uuid
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))

    def convert(self, raw: Any, identifier: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Convert raw code payload into a UIF object. Accepts either a dict with
        `content`/`language` keys or a plain string containing source content.
        """
        if isinstance(raw, dict):
            content = raw.get("content") or raw.get("body") or ""
            language = raw.get("language") or kwargs.get("language")
            source_path = raw.get("path") or raw.get("filename")
        elif isinstance(raw, str):
            content = raw
            language = kwargs.get("language")
            source_path = identifier
        else:
            raise ValueError("Unsupported raw payload for code conversion")

        return self.extract(source_path=source_path, raw_content=content, language=language)
