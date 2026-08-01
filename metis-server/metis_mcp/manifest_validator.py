"""
Connector manifest validation -- connectors/metis-connector-manifest-schema.json's
own stated purpose (REQ-METIS-CONN-01/02): "a new intake source is added by
writing a manifest conforming to this schema, not by modifying pipeline
code." Nothing in this codebase previously actually validated the 7 real
manifest files against it -- test_manifest_validator.py is the first real
check that they do.
"""
import json
from pathlib import Path

import jsonschema

CONNECTORS_DIR = Path(__file__).resolve().parent.parent.parent / "connectors"
SCHEMA_PATH = CONNECTORS_DIR / "metis-connector-manifest-schema.json"


def load_schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def real_manifest_paths() -> list[Path]:
    """Every *.json in connectors/ except the schema file itself."""
    return sorted(p for p in CONNECTORS_DIR.glob("*.json") if p.name != SCHEMA_PATH.name)


def validate_manifest(schema: dict, manifest: dict) -> list[str]:
    """Returns a list of real jsonschema error messages -- empty if valid.
    Never raises: a manifest failing validation is exactly the case this
    function exists to report, not to crash on."""
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in validator.iter_errors(manifest)]


def validate_all_real_manifests() -> dict:
    schema = load_schema()
    results = {}
    for path in real_manifest_paths():
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f)
        results[path.name] = validate_manifest(schema, manifest)
    return results
