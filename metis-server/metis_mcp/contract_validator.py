"""
CONST-062 (docs/metis-gap-remediation.md §7): "MCP tool handlers get
contract tests validated directly against metis-mcp-tool-contracts.json's
existing input/output schemas." This module is the small, reusable piece
that loads the real contract file and validates a real tool call's
input/output against it -- test_mcp_contracts.py is what actually drives
it against a real running server.
"""
import json
from pathlib import Path

import jsonschema

CONTRACTS_PATH = Path(__file__).resolve().parent.parent.parent / "mcp-contracts" / "metis-mcp-tool-contracts.json"


def load_contracts() -> dict:
    with open(CONTRACTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _schema_with_defs(contracts: dict, sub_schema: dict) -> dict:
    """$ref: '#/$defs/provenance' resolves against whatever document root
    is handed to the Validator -- embedding the real top-level $defs
    alongside the tool's own input/output schema is what makes that
    resolution work without a separate resolver/registry setup."""
    return {"$defs": contracts["$defs"], **sub_schema}


def validate_against_contract(contracts: dict, tool_name: str, direction: str, payload: dict) -> None:
    """direction: 'input' or 'output'. Raises jsonschema.ValidationError on
    a real mismatch -- never swallowed, since a silently-ignored schema
    violation would defeat the entire point of a contract test."""
    tool_schema = contracts["tools"][tool_name][direction]
    schema = _schema_with_defs(contracts, tool_schema)
    jsonschema.Draft202012Validator(schema).validate(payload)
