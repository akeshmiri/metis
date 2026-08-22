# The v1 MCP tool contracts

`metis-mcp-tool-contracts.json` describes **eighteen tools, none of which
exist.** They were the v1 agent surface — `metis_get_context`,
`metis_get_traceability`, `metis_check_coverage`, `metis_impact_analysis`,
`metis_submit_episode`, `metis_quality_score`, `metis_generate_quality_report`,
`metis_propose_test_skeleton` and ten more — and they went with the v1 engine at
commit `61814dc`.

## What the surface actually offers

Seven tools, in `metis-server/metis_mcp/server.py`:

| Tool | Answers |
|---|---|
| `list_workflows` | every defined workflow, its stages, and where it stops for a human |
| `route_request` | which workflow a request maps to — null when it matches none |
| `get_model` | one model's states and transitions; summary by default |
| `validate_model` | well-formedness findings by severity, `unverifiable` kept separate |
| `coverage` | the coverage ledger — what is *tested*, never what is *working* |
| `run_status` | where a workflow run got to and what it is waiting for |
| `why_read_only` | why no decision can be taken through this surface |

The surface is **read-only by construction** (N-8): no tool imports a write
path, and `test_mcp_server.py` asserts it. The v1 contracts here describe a
`metis_submit_episode` that wrote to the graph from an agent session — precisely
what N-8 now forbids, and the clearest single reason this file is history rather
than a specification.

`metis-adversarial-injection-corpus.json` fed the guardrail corpus runner, whose
CronJob and Dockerfile were removed with the rest of the v1 guardrail stack.

A third file, `metis-mcp-tool-contracts.json.work`, was a 43KB editor scratch
file that `.gitignore` already excluded. It was deleted rather than moved.
