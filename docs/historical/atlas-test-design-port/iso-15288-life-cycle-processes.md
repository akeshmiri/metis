# ISO/IEC/IEEE 15288 Life Cycle Processes Reference

**Status of this file:** side reference, not loaded by default. Consult only when a scope spans system or hardware boundaries (not software-only), or when a design must be justified against a specific systems-engineering life cycle process due to a compliance deviation. Day-to-day `test-designer` runs use `resources/templates/test-design-template.md`'s "Life Cycle Process Alignment" section directly and do not need this file.

## What ISO/IEC/IEEE 15288 Is

ISO/IEC/IEEE 15288 defines the life cycle processes for **systems** (hardware, software, and their integration) across the full life span: concept, development, production, utilization, support, and retirement. It is the systems-engineering counterpart to ISO/IEC/IEEE 12207 (software-only).

## Technical Processes Relevant To Test Design

| Process | Clause | What It Covers | Section In `test-design-template.md` |
|---|---|---|---|
| Stakeholder Needs and Requirements Definition | §6.4.2 | Capturing what stakeholders actually need, before solutioning | Life Cycle Process Alignment (row: Stakeholder Needs & Requirements Definition) |
| System Requirements Definition | §6.4.3 | Translating stakeholder needs into verifiable system requirements | Life Cycle Process Alignment (row: System/Software Requirements Analysis) |
| Architecture Definition | §6.4.4 | Defining the system's structure across hardware/software/interfaces | Life Cycle Process Alignment (row: Architecture/Design Definition) |
| Integration | §6.4.7 | Combining system elements into an aggregate that satisfies requirements | Life Cycle Process Alignment (row: Integration Process) |
| Verification | §6.4.8 | Confirming the system was **built right** — conforms to specified requirements | Life Cycle Process Alignment (row: Verification Process) → backed by `TCN`/`TCS` rows |
| Validation | §6.4.9 | Confirming the system **does the right thing** — meets the stakeholder's actual need in its intended operational environment | Life Cycle Process Alignment (row: Validation Process) → backed by Acceptance Criteria and the scenario matrix |
| Transition | §6.4.10 | Moving the system into the operational environment (installation, cutover, qualification) | Life Cycle Process Alignment (row: Transition / Qualification Testing) → backed by Readiness Criteria and deployment sequence |

## When To Consult This File

- The scope includes hardware, firmware, or a system boundary that spans more than one deployable software component.
- A compliance or audit requirement explicitly cites ISO/IEC/IEEE 15288 by name.
- The template's "Life Cycle Process Alignment" section has rows marked `not applicable` and a reviewer questions whether that's correct — use the clause definitions here to confirm.

For software-only scopes (the Atlas default), prefer `iso-12207-life-cycle-processes.md` instead — the process names are the same but the clause numbering and software-specific framing differ slightly.

Do not duplicate this file's content back into the template — it stays a side reference.
