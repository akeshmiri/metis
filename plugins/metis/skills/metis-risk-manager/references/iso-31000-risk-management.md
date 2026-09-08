# Risk management — ISO 31000

**A side reference, not loaded by default.** Consult it when the lifecycle this
family runs has to be placed against the published one, or when somebody asks
whether Métis "implements ISO 31000".

It would still be true if Métis were deleted, which is why it is a reference
rather than knowledge.

## What the standard is, and what it is not

ISO 31000 is **guidance**, not a certifiable requirements standard. It has no
conformity assessment and no shall-clauses to audit against; ISO says so
explicitly. Any claim that a tool "complies with ISO 31000" is therefore a
category error, and Métis makes none.

It is organised in three parts: **principles** (what good risk management is
for), **framework** (how an organisation supports it) and **process** (what is
actually done, repeatedly).

## The process, and where Métis sits

| 31000 process step | Métis | Owner |
|---|---|---|
| Scope, context, criteria | the scale, thresholds and appetite are settled before anything is rated | `metis-risk-manager-framing` |
| Risk identification | techniques, and candidates derived from the model | `-identification`, `risk_candidates` |
| Risk analysis | exposure on the 5x5, EMV, PERT | `-qualitative`, `-quantitative` |
| Risk evaluation | ranking against the agreed threshold | `-qualitative`, `risk_priority` |
| Risk treatment | the four threat and four opportunity strategies | `-threat-response`, `-opportunity-response`, `-response-planning` |
| Monitoring and review | cadence, triggers, closure | `-monitoring` |
| Recording and reporting | one consolidated report | `-register`, `-governance`, `risk_report` |
| Communication and consultation | **not automated** | it is a conversation with people, and a tool that claimed it would be claiming the conversation happened |

## The two rules Métis adds, which 31000 does not contain

Both are Métis's, not the standard's, and both are load-bearing.

- **`derived_from: authored | model`, never merged.** A risk Métis derived from a
  model says *this behaviour is untested*. It does not say *this is likely to
  fail*, and it carries `probability: null` until a person sets one. The two
  kinds are never combined in a total, an average or a chart. This is C-11 one
  domain over.
- **An ordinal rank is not a number.** A 5x5 exposure orders risks; it does not
  measure them. Averaging ordinals produces a figure with no meaning, and the
  register's coherence rules refuse it.

## Why `Risk` is not a graph label

The register is a document, not a node type. The argument, and the condition that
would reverse it, are in `docs/academy/PROPOSAL-risk-in-the-graph.md`.

## What this reference does not do

It does not reproduce the standard, and it does not claim conformance — 31000
offers none to claim. Read it to place the family's stages against the published
process when somebody asks which step they are in.
