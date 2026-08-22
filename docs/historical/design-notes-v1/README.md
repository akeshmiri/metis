# The v1 design notes

Fifteen documents from the design conversation that preceded the current engine.
**None of them is authoritative.**
[`docs/metis-application-spec.md`](../../metis-application-spec.md) is, and it
is the only design document in the live tree.

They are here rather than deleted because the reasoning is the valuable part and
most of it survived into the spec — but reading them as current will mislead you
on specifics, because their vocabulary is the v1 engine's.

## What they are

A series of **Constitution Amendments**, plus the memos around them:

| Document | What it decided |
|---|---|
| `metis-data-quality-framework.md` | Amendment 1 — the metrics catalogue and quality gate |
| `metis-foolproof-security-framework.md` | Amendment 2 — trust boundaries, non-expert hardening |
| `metis-behavior-model-test-pipeline.md` | Amendment 3 — requirement → state machine → tests |
| `metis-standards-integration.md` | Amendment 4 — ISO/IEEE alignment |
| `metis-gap-remediation.md` | Amendment 5 — nine of ten flagged gaps |
| `metis-constitution-adopted.md` · `-template.md` | the constitution itself |
| `metis-const-053-confirmation-record.md` | a procurement checklist, pending an answer that never landed here |
| `metis-deep-review-gaps.md` | a review pass over all 23 documents |
| `metis-connector-architecture.md` | the connector design — see `connectors/README.md` for its status |
| `metis-multi-client-integration.md` | Claude + Copilot against one MCP server |
| `metis-cost-review-15k-tests.md` | token-cost modelling at scale |
| `metis-code-graph-archaeology-extension.md` | CPG-based recovery, which became §5 |
| `athena-repositioning-reconciliation.md` | the ETL reconciliation; note its own naming caveat |
| `metis-review-queue-ui.html` | a static mockup of the reviewer's queue |

## What is stale in them

- **Tool names.** `metis_get_context`, `metis_get_traceability`,
  `metis_check_coverage`, `metis_submit_episode` and the rest. The surface is
  seven read-only tools in `metis-server/metis_mcp/server.py`; the v1 contracts
  are in [`../mcp-contracts-v1/`](../mcp-contracts-v1/).
- **Module names.** `structural_validation.py`, `confidence_tiering.py`,
  `guardrails/`, `layer8_heuristics.py`, `dq_metrics.py`, `uif_intake.py`,
  `cognify/`, `classification_gate.py`. None exists.
- **Identifier schemes.** `CONST-0NN` and `REQ-METIS-XXX-NN` were replaced by
  the spec's rule ids (`M-18`, `S-13`, `P-16`, `D-1`, `N-8`, …), which the code
  cites inline.
- **`metis-review-queue-ui.html`** is a mockup. The review UI is real and lives
  at `metis-server/metis_mcp/review_ui/`.
- **Product naming.** `athena-repositioning-reconciliation.md` carries its own
  note that the platform it proposes as "Athena" was later named Ariadne, and
  that "Athena" elsewhere means the real ETL system.
