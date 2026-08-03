"""
CONST-062 (docs/metis-gap-remediation.md §7): real contract tests for
metis_mcp/server.py's 12 MCP tool handlers against
mcp-contracts/metis-mcp-tool-contracts.json's real input/output JSON
schemas -- spawned as a real subprocess over the real MCP protocol (same
approach as test_e2e.py), not a mock of the handler functions.

Real finding from building this (disclosed, not hidden): the contract
describes the full PRODUCTION tool shape (§8.1 pinned-context retrieval,
§8.2 hybrid retrieval, full Episode/decision provenance tracking, an
object-shaped quality_score scope, etc.) -- server.py is explicitly the
Phase 0 dogfooding stand-in (see its own module docstring, and
QUICKSTART.md's "Isn't: the production server"), and several of its
adaptations were already disclosed there (metis_impact_analysis,
metis_propose_test_skeleton/metis_submit_episode). Running this test for
real against the actual local-backend server shows EVERY one of the 12
tools currently deviates from the full production contract shape in some
way -- most of that deviation was NOT previously disclosed anywhere. This
test file is the accurate, current record of exactly which tool deviates
and why, per CONST-062's own purpose ("testing against them is nearly
free given they already exist") -- it is not a claim that Phase 0
dogfooding mode is contract-complete; it's the opposite, made precise and
regression-checkable instead of assumed.

Each entry below encodes an explicit, deliberate expectation
(conforms=True/False + reason). A tool flipping from expected False to an
unexpected pass, or from expected True to a failure, fails this test --
either is a real signal (a gap got silently closed, or a working contract
regressed) that needs a human to update this file's own expectations
deliberately, not have the test silently drift with the code.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import jsonschema

from metis_mcp.contract_validator import load_contracts, validate_against_contract

SERVER_DIR = Path(__file__).resolve().parent

# tool_name -> (input_payload, expected_conforms, reason)
CASES = {
    "metis_explain_decision": (
        {"node_id": "CONST-047"}, False,
        "Real output uses {found,id,explanation,provenance,corroboration} -- no 'decisions' "
        "array at all (the contract's core shape for this tool).",
    ),
    "metis_get_context": (
        {"anchor": "CONST-047"}, False,
        "Contract's anchor is an object (oneOf file_path/method_signature/task_description); "
        "dogfooding mode takes a plain string id instead, and returns a flat node view, not "
        "the graded-fact/pinned-context production shape (needs §8.1/§8.2, not yet built).",
    ),
    "metis_get_traceability": (
        {"node_id": "CONST-047"}, False,
        "Real output has 'upstream'/'downstream' arrays, not a flattened 'chain' array; the "
        "contract's direction enum (up/down/both) also differs from the real one "
        "(upstream/downstream/both).",
    ),
    "metis_check_coverage": (
        {"target_id": "CONST-047"}, False,
        "Real output has no 'stale' field (§7.2 stale-coverage detection isn't wired into this "
        "tool) and uses 'covering_items' instead of the contract's 'test_cases'.",
    ),
    "metis_impact_analysis": (
        {"node_id": "CONST-047"}, False,
        "Already disclosed in server.py's own module docstring: dogfooding mode takes node_id "
        "directly since there's no code graph in the text-only corpus, vs. the contract's "
        "changed_files/diff.",
    ),
    "metis_propose_test_skeleton": (
        {"transition_id": "some-transition"}, False,
        "graph.backend=local (this server's configured default) has no Transition ontology -- "
        "the honest 'not applicable' response omits the contract's required 'skeleton'/"
        "'requires_human_review' fields entirely. graph.backend=neo4j's real implementation "
        "(metis_mcp/test_skeleton_generator.py) DOES match the contract shape when a Transition "
        "has a determinable gap -- see test_test_skeleton_generation.py, not re-tested here "
        "since this file exercises the currently-configured server as a real subprocess.",
    ),
    "metis_submit_episode": (
        {"episode_type": "test", "payload": {}, "source_ref": "test"}, False,
        "Already disclosed: REQ-METIS-CPT-01 disables the write path by default, always "
        "returning {accepted, reason} -- never the contract's {episode_id, confidence_tier, status}.",
    ),
    "metis_explain_answer": (
        {"prior_response_id": "CONST-047"}, False,
        "Fixed (previously forwarded to metis_explain_decision's unrelated shape): now returns "
        "real 'explanation'/'sources'/'confidence_summary'/'academy_links' fields. Still not fully "
        "conformant on graph.backend=local specifically -- these dogfooding text documents have no "
        "formal Episode record, so 'sources' falls back to source_file/source_heading (disclosed via "
        "adapted:true), missing the contract's required source_episode_id/source_connector/"
        "t_recorded. graph.backend=neo4j's real output DOES fully conform (verified directly against "
        "the contract schema, not re-tested here since this file exercises the local-backend server).",
    ),
    "metis_quality_score": (
        {"scope": "all"}, False,
        "Contract's scope is an object (oneOf release_id/service_id/requirement_id/"
        "project_wide); dogfooding mode takes a plain string. Output uses the orphan-rate "
        "proxy shape (or, for graph.backend=neo4j, metis_mcp/dq_metrics.py's real "
        "quality_score/components shape) -- neither matches the contract's "
        "composite_score/dimension_breakdown/gate_status shape.",
    ),
    "metis_generate_quality_report": (
        {"scope": {"project_wide": True}}, False,
        "graph.backend=local (this server's configured default) has no real Requirement/"
        "Service/Release ontology -- the honest {adapted, note} response omits the "
        "contract's required scope_description/composite_score/gate_status/"
        "executive_summary/detail fields entirely. graph.backend=neo4j's real "
        "implementation (metis_mcp/quality_report.py) DOES match the contract shape.",
    ),
    "metis_generate_release_report": (
        {"release_id": "some-release"}, False,
        "Same real gap as metis_generate_quality_report: graph.backend=local returns the "
        "honest {adapted, note} response, omitting the contract's required fields.",
    ),
    "metis_generate_test_design_report": (
        {"scope": {"project_wide": True}}, False,
        "Same real gap as metis_generate_quality_report: graph.backend=local returns the "
        "honest {adapted, note} response, omitting the contract's required fields "
        "(scope_description/requirements/total_acceptance_criteria/etc.).",
    ),
}


async def _run() -> dict:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "metis_mcp.server"], cwd=str(SERVER_DIR),
        env=os.environ.copy(),
    )
    results = {}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for tool_name, (payload, expected_conforms, reason) in CASES.items():
                r = await session.call_tool(tool_name, payload)
                output = json.loads(r.content[0].text)
                results[tool_name] = output
    return results


def test_all_twelve_tools_match_their_documented_conformance_state():
    contracts = load_contracts()
    outputs = asyncio.run(_run())
    assert set(outputs.keys()) == set(CASES.keys()), "server tool set no longer matches CASES"

    failures = []
    for tool_name, (_, expected_conforms, reason) in CASES.items():
        output = outputs[tool_name]
        actual_conforms = True
        error_detail = None
        try:
            validate_against_contract(contracts, tool_name, "output", output)
        except jsonschema.ValidationError as e:
            actual_conforms = False
            error_detail = e.message

        if actual_conforms != expected_conforms:
            failures.append(
                f"{tool_name}: expected conforms={expected_conforms} ({reason}), got "
                f"conforms={actual_conforms}" + (f" (schema error: {error_detail})" if error_detail else "")
            )

    assert not failures, "Contract conformance state changed -- update CASES deliberately:\n" + "\n".join(failures)


if __name__ == "__main__":
    tests = [test_all_twelve_tools_match_their_documented_conformance_state]
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
