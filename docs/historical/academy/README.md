# The v1 academy

Four explainers and the static site built from them. Both describe the engine
that commit `61814dc` replaced, and they name modules that no longer exist:
`structural_validation.py` and its "49 closed-ontology labels",
`confidence_tiering.py`, `guardrails/calibration.py`, `layer8_heuristics.py`,
`metis_mcp/dq_metrics.py`, and the `metis_get_traceability` MCP tool.

Kept because the *teaching* is still good — how to read a traceability chain,
what a confidence tier is for, why a graph model needs a closed ontology. What
is stale is every identifier. Anyone rebuilding an academy should start from
these and re-point them at the current engine: 45 labels in
`metis_mcp/ontology/labels.py`, lifecycle in `mbt/model.py`, and the seven
read-only tools in `metis_mcp/server.py`.

`site/` is the rendered form of the same content and is stale in exactly the
same way.
