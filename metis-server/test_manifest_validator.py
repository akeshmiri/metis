"""
Validates all 7 real connector manifests (connectors/metis-connector-*.json)
against connectors/metis-connector-manifest-schema.json -- REQ-METIS-CONN-01/02.
No mock manifests -- these are the actual files every real connector in
this codebase (application_code_connector.py, atlassian_connector.py,
bmad_method_connector.py, flatfiles_connector.py, grafana_connector.py,
locust_performance_connector.py, test_suite_connector.py) was built against.
"""
import sys

from metis_mcp.manifest_validator import load_schema, real_manifest_paths, validate_manifest, validate_all_real_manifests

EXPECTED_MANIFESTS = {
    "metis-connector-application-code.json",
    "metis-connector-atlassian-prod.json",
    "metis-connector-bmad-method.json",
    "metis-connector-flatfiles.json",
    "metis-connector-grafana.json",
    "metis-connector-locust-performance.json",
    "metis-connector-test-suite.json",
}


def test_discovers_exactly_the_7_real_manifests():
    names = {p.name for p in real_manifest_paths()}
    assert names == EXPECTED_MANIFESTS


def test_all_7_real_manifests_validate_clean():
    results = validate_all_real_manifests()
    failures = {name: errors for name, errors in results.items() if errors}
    assert not failures, f"Real manifest(s) fail schema validation: {failures}"


def test_a_manifest_missing_a_required_field_is_actually_caught():
    """Proves the validator has real teeth -- not just returning [] for
    everything regardless of input."""
    schema = load_schema()
    broken = {"connector_id": "test", "display_name": "Test", "version": "1.0.0"}
    errors = validate_manifest(schema, broken)
    assert errors, "a manifest missing protocol/entity_type_mapping/etc. must be rejected"


def test_trust_tier_on_first_use_cannot_be_overridden():
    """The schema's own stated invariant: 'Hardcoded -- no manifest may set
    anything else.' -- CONST-036's onboarding gate can't be opted out of
    via manifest content."""
    schema = load_schema()
    manifest = {
        "connector_id": "test-connector", "display_name": "Test", "version": "1.0.0",
        "protocol": "file_scan", "file_scan_config": {},
        "entity_type_mapping": [{"source_shape": "x", "target_entity_type": "y"}],
        "temporal_strategy": {"t_recorded_source": "x", "event_time_confidence_default": "verified"},
        "precedence_tier": {"role": "supplementary"},
        "environment_scope": "all_environments",
        "trust_tier_on_first_use": "auto_write",  # attempting to bypass calibration
    }
    errors = validate_manifest(schema, manifest)
    assert errors, "trust_tier_on_first_use must reject any value other than 'calibration_required'"


def test_protocol_conditional_config_is_enforced():
    """allOf's if/then: protocol=mcp_client without mcp_config must fail."""
    schema = load_schema()
    manifest = {
        "connector_id": "test-connector", "display_name": "Test", "version": "1.0.0",
        "protocol": "mcp_client",  # no mcp_config -- should fail
        "entity_type_mapping": [{"source_shape": "x", "target_entity_type": "y"}],
        "temporal_strategy": {"t_recorded_source": "x", "event_time_confidence_default": "verified"},
        "precedence_tier": {"role": "supplementary"},
        "environment_scope": "all_environments",
        "trust_tier_on_first_use": "calibration_required",
    }
    errors = validate_manifest(schema, manifest)
    assert errors, "protocol=mcp_client without mcp_config must be rejected"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
