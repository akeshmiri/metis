"""Database schema to UIF Extractor."""

import json
from typing import Any, Dict, List, Optional
from .base_extractor import BaseExtractor


class DatabaseExtractor(BaseExtractor):
    """Extract database schema into UIF format."""
    
    def extract(self, config_path: str = None, raw_schema: Dict[str, Any] = None, db_type: str = None, **kwargs) -> Dict[str, Any]:
        """Extract UIF from database schema.
        
        Args:
            config_path: Path to database connection config
            raw_schema: Pre-loaded schema introspection dict
            db_type: Database type (postgresql, oracle, mysql, sqlserver)
        
        Returns:
            UIF object with data_model containing tables, columns, keys, indexes
        """
        if raw_schema:
            schema_data = raw_schema
            source_id = schema_data.get("database", "unknown_db")
        elif config_path:
            # TODO: Implement database connection and introspection
            raise NotImplementedError("Database introspection not yet implemented. Use raw_schema dict.")
        else:
            raise ValueError("One of config_path or raw_schema required")
        
        # Extract tables and their columns
        data_model = self._extract_tables(schema_data)
        
        # Build UIF scope
        scope = self._build_uif_scope(
            primary_id=source_id,
            primary_type="database_schema",
            source_system="database"
        )
        
        # Build normalized status
        metadata_status = self._build_normalized_status(
            validation_status="schema_defined"
        )
        
        source_ref = self._build_source_reference(
            source_system="database",
            source_id=source_id
        )
        
        uif = self._build_uif(
            scope=scope,
            metadata={
                "title": f"Database Schema: {source_id}",
                "database_type": db_type or schema_data.get("db_type", "unknown"),
                "status": metadata_status,
                "tags": ["database_schema", "data_model", db_type or "unknown"],
                "table_count": len(data_model),
                "total_columns": sum(len(t.get("attributes", [])) for t in data_model)
            },
            specifications={
                "data_model": data_model
            },
            comments=[],
            source_references=[source_ref]
        )
        
        return uif
    
    def _extract_tables(self, schema_data: Dict) -> List[Dict]:
        """Extract table definitions from schema introspection."""
        tables = []
        
        tables_list = schema_data.get("tables", [])
        for idx, table in enumerate(tables_list, 1):
            table_name = table.get("table_name", f"table_{idx}")
            
            # Extract columns
            columns = self._extract_columns(table.get("columns", []))
            
            # Extract constraints
            constraints = table.get("constraints", [])
            
            # Extract indexes
            indexes = table.get("indexes", [])
            
            table_obj = {
                "id": self._generate_id(table_name),
                "entity_name": table_name,
                "entity_type": "table",
                "schema": table.get("schema", "public"),
                "description": table.get("description", f"Table: {table_name}"),
                "attributes": columns,
                "constraints": self._normalize_constraints(constraints),
                "indexes": self._normalize_indexes(indexes),
                "row_count": table.get("row_count", 0),
                "source_reference": self._build_source_reference(
                    source_system="database",
                    source_id=f"table_{table_name}"
                )
            }
            tables.append(table_obj)
        
        return tables
    
    def _extract_columns(self, columns_list: List) -> List[Dict]:
        """Extract column definitions."""
        columns = []
        
        for col in columns_list:
            col_name = col.get("column_name", "unknown_column")
            col_type = col.get("data_type", "UNKNOWN")
            
            # Extract constraints
            constraints = []
            if col.get("is_nullable") == False:
                constraints.append("NOT_NULL")
            if col.get("is_primary_key"):
                constraints.append("PRIMARY_KEY")
            if col.get("is_unique"):
                constraints.append("UNIQUE")
            if col.get("is_foreign_key"):
                constraints.append("FOREIGN_KEY")
            if col.get("has_default"):
                constraints.append("HAS_DEFAULT")
            
            column = {
                "attribute_name": col_name,
                "data_type": col_type,
                "character_maximum_length": col.get("character_max_length"),
                "numeric_precision": col.get("numeric_precision"),
                "numeric_scale": col.get("numeric_scale"),
                "column_default": col.get("column_default"),
                "constraints": constraints,
                "nullable": col.get("is_nullable", True),
                "description": col.get("description", "")
            }
            columns.append(column)
        
        return columns
    
    def _normalize_constraints(self, constraints_list: List) -> List[Dict]:
        """Normalize constraint definitions."""
        constraints = []
        
        for constraint in constraints_list:
            constraint_obj = {
                "constraint_name": constraint.get("constraint_name", "unknown"),
                "constraint_type": constraint.get("constraint_type", "UNKNOWN"),
                "columns": constraint.get("columns", []),
                "definition": constraint.get("definition", "")
            }
            constraints.append(constraint_obj)
        
        return constraints
    
    def _normalize_indexes(self, indexes_list: List) -> List[Dict]:
        """Normalize index definitions."""
        indexes = []
        
        for index in indexes_list:
            index_obj = {
                "index_name": index.get("index_name", "unknown"),
                "index_type": index.get("index_type", "BTREE"),
                "columns": index.get("columns", []),
                "is_unique": index.get("is_unique", False),
                "is_primary": index.get("is_primary", False),
                "definition": index.get("definition", "")
            }
            indexes.append(index_obj)
        
        return indexes
    
    def _generate_id(self, name: str) -> str:
        """Generate deterministic ID from name."""
        import uuid
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))

    def convert(self, raw: Dict[str, Any], identifier: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Convert raw schema introspection dict into a UIF object.
        """
        source_id = identifier or raw.get("database") or raw.get("source") or raw.get("db_name")
        return self.extract(raw_schema=raw, db_type=raw.get("db_type"))
