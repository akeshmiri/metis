# IEEE 829-2008 Test Documentation Reference

**Status of this file:** side reference, not loaded by default. Consult only when a design must be defended against, or reconciled with, a strict IEEE 829 documentation obligation (e.g. a formal audit, a contractual deliverable, or an explicit user request to confirm 829 coverage). Day-to-day `test-designer` runs use `resources/templates/test-design-template.md` directly and do not need this file.

## What IEEE 829-2008 Is

IEEE 829-2008 is the legacy Software Test Documentation standard (formally superseded by ISO/IEC/IEEE 29119-3, but still the common naming reference for classic test work products). It defines eight named documents that together make up a complete test documentation set.

## The Eight IEEE 829 Work Products

| # | Work Product | Purpose | Section In `test-design-template.md` |
|---|---|---|---|
| 1 | Test Plan | Scope, approach, resources, schedule for a set of test activities | Specification Metadata And Document Control, Scope Summary, Stakeholders, Readiness Criteria |
| 2 | Test Design Specification | Refines the test approach for a feature; identifies test conditions and pass/fail criteria | Proposed Test Design Specifications (`TDS-*`) |
| 3 | Test Case Specification | Concrete inputs, preconditions, and expected results for a condition | Proposed Test Case Catalog (`TCS-*`) |
| 4 | Test Procedure Specification | Ordered steps to execute one or more test cases | Proposed Test Procedure Catalog (`TPR-*`) |
| 5 | Test Item Transmittal Report | Identifies the exact items being delivered for test | Specification Metadata And Document Control (Feature Name/ID, Status) |
| 6 | Test Log | Chronological record of what was executed and observed | Out of scope for `test-designer` — owned by test execution/reporting tooling, not design |
| 7 | Test Incident Report | Records an anomaly encountered during test execution | Out of scope for `test-designer` — see `report-generator`'s defect route |
| 8 | Test Summary Report | Summarizes testing activity and results against exit criteria | Out of scope for `test-designer` — see `report-generator`'s quality route |

Work products 6-8 are execution/reporting artifacts, not design artifacts — `test-designer` only produces the design-time work products (1-5). Route execution and reporting concerns to `report-generator`.

## Elements Checklist (Design-Time Scope)

`test-design-template.md`'s "IEEE 829 Test Plan Elements Checklist" section already tracks every classic Test Plan element (Test Plan Identifier, Test Items, Features To Be/Not To Be Tested, Approach, Item Pass/Fail Criteria, Suspension/Resumption, Test Deliverables, Testing Tasks, Environmental Needs, Responsibilities, Staffing And Training, Schedule, Risks And Contingencies, Approvals) against the section that covers it. Use this file only to look up **why** an element exists or **what it originally meant** in the standard when a reviewer questions a deviation — the checklist itself lives in the template, not here.

## When To Consult This File

- A reviewer or auditor asks "does this artifact satisfy IEEE 829?" and you need the original element definitions to answer precisely.
- The team's current design deviates from the template's default checklist mapping and needs to be justified against the standard's actual intent.
- Onboarding a new analyst who needs the historical context for why the template's sections are named the way they are.

Do not duplicate this file's content back into the template — it stays a side reference.
