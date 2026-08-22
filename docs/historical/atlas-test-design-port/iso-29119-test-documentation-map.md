# ISO/IEC/IEEE 29119 Test Documentation Map

**Standard covered:** ISO/IEC/IEEE 29119 (Parts 1-3). This is the **default, always-relevant** knowledge fragment for `test-designer` — read it before Stage 07 and Stage 08 whenever the scope needs formal documentation or the source is a normative specification.

Use this reference when deciding how much documentation detail to include in a `test-designer` artifact.

Three related standards each have their own **side-reference** knowledge file, consulted only when a deviation from the default template must be justified against that specific standard — they are not loaded by default:

- `ieee-829-test-documentation.md` — the legacy named-work-product standard (Test Plan, Test Design/Case/Procedure Specification, Test Item Transmittal Report, Test Log, Test Incident Report, Test Summary Report).
- `iso-15288-life-cycle-processes.md` — systems life cycle processes, for scopes spanning hardware/system boundaries.
- `iso-12207-life-cycle-processes.md` — software life cycle processes, the software-only counterpart to 15288.

## What ISO/IEC/IEEE 29119 Is

ISO/IEC/IEEE 29119 (Parts 1-3) defines software testing vocabulary, test processes, and test documentation content (test plan, test design specification, test case specification, test procedure specification). It is the primary basis for `resources/templates/test-design-template.md`.

## Why One Document Instead Of Many

Atlas does not require every ISO/IEC 29119 work product to become a separate file. Fragmenting a design across many mostly-empty annex files produces less deterministic output, not more. Instead, `resources/templates/test-design-template.md` folds every annex concern into sections of **one** primary markdown artifact per scope:

- Transient artifact: `.atlas/tmp/test-design/<scope-id>/08-design/test-design-index.md`
- Durable artifacts: `.atlas/test-design/<scope-id>.overview.md` (high-level, Stage 06) and `.atlas/test-design/<scope-id>.md` (detailed, Stage 08)

Right-sizing still applies: collapse sections that add no value for a small scope, but do not delete the row/section silently — mark it `n/a` so the checklist stays auditable.

## Atlas Section Mapping

| Standard | Work Product Or Process | Section(s) In `test-design-template.md` | When To Expand |
|---|---|---|---|
| 29119-3 | Test Plan | Specification Metadata And Document Control, Scope Summary, Stakeholders, Readiness Criteria | Formal documentation requested or multi-team review needed |
| 29119-3 | Test Design Specification | Proposed Test Design Specifications (`TDS-*`) | A proposed slice needs objectives, coverage, and pass criteria spelled out |
| 29119-3 | Test Case Specification | Proposed Test Case Catalog (`TCS-*`) | Cases need handoff-ready detail instead of short titles |
| 29119-3 | Test Procedure Specification | Proposed Test Procedure Catalog (`TPR-*`) | Execution order, checkpoints, evidence capture, or cleanup matter |
| 29119-2 | Risk-based test process / technique selection | Testing Approach Summary, Requirement, Risk, And Test Condition Traceability | Any scope — this is core, not optional |
| 29119-1 | Test data / environment requirements | Test Data Requirements (`TDR-*`), Test Environment Requirements (`TER-*`) | Data readiness, masking, generation, setup, or access are significant constraints |
| Normative spec source (any standard) | Clause-by-clause rule derivation | Specification Clause Traceability | The primary source is a requirements spec, API contract, workflow rule set, or acceptance-criteria catalog — derive rules clause by clause instead of implementation-first brainstorming |
| Visual comprehension requirement | Use Case Diagram, Flow Chart | Use Case Diagram And Flow Chart Requirement, Mermaid Diagram Strategy, Mermaid Diagram Drafts | Always (mandatory default; see template) |

For IEEE 829 elements, and for ISO/IEC/IEEE 15288 / 12207 life cycle process alignment, see the side-reference files listed above — the template's "IEEE 829 Test Plan Elements Checklist" and "Life Cycle Process Alignment" sections already cover the default mapping; the side references explain the *why* behind them when a deviation needs justifying.

## Right-Sizing Guidance

- Use only the sections that improve clarity or handoff quality.
- Do not invent data, environment, or ownership detail to fill a template.
- Keep unresolved areas visible as placeholders or `n/a` rather than pretending they are complete or deleting the row.
- Treat deep annex detail as most valuable when the scope is high-risk, complex, regulated, or intended for downstream implementation.
- When a credible specification exists, prefer clause-by-clause derivation of test conditions over implementation-first brainstorming.

## Minimum Good Structure

For most requests, a strong artifact should still include:

- test basis,
- specification or rule inventory when the source is normative,
- scope and assumptions,
- use case diagram and flow chart (visual confirmation of actors and process),
- requirement or risk traceability,
- technique selection rationale,
- coverage and gap analysis,
- proposed test-design slices,
- data or environment gaps,
- life cycle process alignment when the scope is regulated or compliance-relevant,
- and prioritized next actions.

## When To Go Deeper

Expand the annex-style sections within the single template when:

- the user explicitly asks for formal documentation,
- the handoff target needs implementation-ready detail,
- the feature has significant business or compliance risk,
- setup or execution is fragile,
- multiple teams need a common review surface,
- or the source material is already specification-driven and should stay that way throughout design.