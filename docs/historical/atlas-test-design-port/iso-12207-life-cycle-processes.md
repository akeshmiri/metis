# ISO/IEC/IEEE 12207 Life Cycle Processes Reference

**Status of this file:** side reference, not loaded by default. Consult only when a design must be justified against a specific software life cycle process due to a compliance deviation, or when clarifying the software-specific process definitions behind the template's default rows. Day-to-day `test-designer` runs use `resources/templates/test-design-template.md`'s "Life Cycle Process Alignment" section directly and do not need this file.

## What ISO/IEC/IEEE 12207 Is

ISO/IEC/IEEE 12207 defines the life cycle processes for **software** specifically — the software-only counterpart to ISO/IEC/IEEE 15288 (systems, hardware-inclusive). Most Atlas scopes are software-only, so 12207 is the more commonly applicable of the two life cycle standards, but it is still an opt-in reference here, not an always-loaded one.

## Life Cycle Processes Relevant To Test Design

| Process | Clause | What It Covers | Section In `test-design-template.md` |
|---|---|---|---|
| Stakeholder Requirements Definition | §6.4.1 | Capturing what stakeholders need from the software, before solutioning | Life Cycle Process Alignment (row: Stakeholder Needs & Requirements Definition) |
| Software Requirements Analysis | §6.4.2 | Translating stakeholder needs into verifiable software requirements | Life Cycle Process Alignment (row: System/Software Requirements Analysis) |
| Software Architecture/Design | §6.4.4 | Defining the software's structure, components, and interfaces | Life Cycle Process Alignment (row: Architecture/Design Definition) |
| Software Integration | §6.4.6 | Combining software units/components into an integrated whole | Life Cycle Process Alignment (row: Integration Process) |
| Software Verification | §6.4.7 | Confirming the software was **built right** — conforms to specified requirements | Life Cycle Process Alignment (row: Verification Process) → backed by `TCN`/`TCS` rows |
| Software Validation | §6.4.8 | Confirming the software **does the right thing** — meets the stakeholder's actual need | Life Cycle Process Alignment (row: Validation Process) → backed by Acceptance Criteria and the scenario matrix |
| Software Qualification Testing | §6.4.9 | Independent evaluation that the software satisfies its specified requirements before release/transition | Life Cycle Process Alignment (row: Transition / Qualification Testing) → backed by Readiness Criteria and deployment sequence |

## When To Consult This File

- A compliance or audit requirement explicitly cites ISO/IEC/IEEE 12207 by name.
- The template's "Life Cycle Process Alignment" section has rows marked `not applicable` and a reviewer questions whether that's correct for a software-only scope — use the clause definitions here to confirm.
- Onboarding a new analyst who needs the process-level vocabulary behind the template's default rows.

For scopes that include hardware, firmware, or a system boundary spanning more than one deployable software component, prefer `iso-15288-life-cycle-processes.md` instead.

Do not duplicate this file's content back into the template — it stays a side reference.
