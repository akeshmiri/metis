"""Static code analysis sidecar (application spec §13).

The CPG stays outside the Métis graph; only ontology-shaped results cross the
boundary (X-2). `contract.py` declares what a query pack must emit, `mapper.py`
projects it onto the ontology.
"""
from code_analysis.contract import (
    CONTRACT_VERSION,
    Anchor,
    CallFact,
    CheckFact,
    EndpointFact,
    ExtractionReport,
    MemberFact,
    MethodFact,
    OutcomeFact,
    validate_report,
)
from code_analysis.synthesis import INITIAL_STATE, SynthesisResult, state_name, synthesise
from code_analysis.mapper import (
    LayerNotImplemented,
    MappedReport,
    TypeRegistryEntry,
    map_report,
    plan_transitions,
    verify_fields,
)

__all__ = [
    "CONTRACT_VERSION", "Anchor", "MethodFact", "CallFact", "EndpointFact",
    "MemberFact", "CheckFact", "OutcomeFact", "ExtractionReport", "validate_report",
    "map_report", "MappedReport", "TypeRegistryEntry", "verify_fields",
    "plan_transitions", "LayerNotImplemented",
    "synthesise", "SynthesisResult", "state_name", "INITIAL_STATE",
]
