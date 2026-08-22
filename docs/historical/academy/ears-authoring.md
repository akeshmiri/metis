# EARS Authoring

`REQ-METIS-ACD-02`. EARS (Easy Approach to Requirements Syntax) is the
first real gate a `Requirement` passes through — `metis_mcp/ears_checker.py`,
`REQ-METIS-ONT-04`, `CONST-002`.

## The five real patterns

Checked in this exact order (comma-clause patterns before the bare
Ubiquitous fallback — Ubiquitous's shape is a strict subset of the
others' tail clause, so checking it first would misclassify every
Event/State/Unwanted/Optional sentence):

| Pattern | Shape | Example |
|---|---|---|
| Event-driven | `When <trigger>, the <system> shall <response>.` | "When a subscription renews, the payment service shall charge the customer." |
| State-driven | `While <state>, the <system> shall <response>.` | "While an order is in Placed state, the system shall accept cancellation requests." |
| Unwanted-behavior | `If <condition>, then the <system> shall <response>.` | "If the currency field is missing, then the system shall return HTTP 400." |
| Optional | `Where <feature is included>, the <system> shall <response>.` | "Where multi-currency support is enabled, the system shall convert at the daily rate." |
| Ubiquitous | `The <system> shall <response>.` | "The system shall log every rejected extraction." |

A sentence that doesn't match any of the five is **structurally
non-conformant** — `check_ears_conformance()` returns `conformant: False`
with a specific reason, and Layer 2 structural validation rejects the
candidate outright for missing `ears_pattern`. This is a hard, mechanical
gate, not a style suggestion.

## Structural conformance is necessary, not sufficient

**`CONST-047` is the important distinction to internalize:** a sentence
can pass EARS structural conformance and still be a bad requirement.
"The system shall provide a user-friendly experience." matches the
Ubiquitous pattern perfectly — and fails CONST-047's substantive checklist
immediately, because "user-friendly" isn't measurable.

`metis_mcp/requirement_quality.py` implements the 8 ISO/IEC/IEEE 29148
characteristics CONST-047 requires, split by how they're checked:

- **Deterministic** (checked automatically, `metis_mcp/constitution_gate.py`
  hard-blocks a `Requirement` candidate that fails any of these):
  - *unambiguous* — no known vague/unfalsifiable term (`metis_mcp/vagueness.py`'s
    shared list: "user-friendly", "fast", "several", "TBD", etc.)
  - *complete* — EARS-conformant, no placeholder markers, every captured
    clause non-empty
  - *singular* — exactly one `shall` obligation, no bundled second one
  - *consistent* — no numeric-threshold conflict with another real
    `Requirement` sharing the same pattern and response shape
- **Judgment** (needs a real, deliberate, costed LLM call — never run
  automatically in the hot submission path):
  - *verifiable*, *feasible*, *correct*, *necessary*

## Where to look next

- What happens to a `Requirement` once it passes both gates: [confidence-tiers.md](confidence-tiers.md)
- The entities EARS-checked text feeds into: [graph-model-basics.md](graph-model-basics.md)
