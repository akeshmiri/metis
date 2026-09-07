# IEEE 829-2008 test documentation — the eight work products

**A side reference, not loaded by default.** Consult it when a design has to be
defended against, or reconciled with, a documentation obligation — a formal
audit, a contractual deliverable, or somebody asking "does this satisfy 829?".
Day-to-day work uses `design_standards()`, which serves the mapping; this file
says what the products originally *meant*, which is the part a tool cannot serve.

It would still be true if Métis were deleted, which is why it is a reference
rather than knowledge.

## What the standard is

IEEE 829-2008 is the legacy Software Test Documentation standard. It is formally
superseded by ISO/IEC/IEEE 29119-3, and it remains the common naming reference —
most people who ask for "a test plan and test design specs" are naming 829's
products whether or not they know it. Both are carried for that reason.

## The eight products

| # | Product | What the standard asks it to contain |
|---|---|---|
| 1 | Test Plan | scope, approach, resources and schedule for a set of test activities |
| 2 | Test Design Specification | the approach for a feature: its test conditions and pass/fail criteria |
| 3 | Test Case Specification | concrete inputs, preconditions and expected results |
| 4 | Test Procedure Specification | the ordered steps that execute one or more cases |
| 5 | Test Item Transmittal Report | which exact items are being delivered for test |
| 6 | Test Log | a chronological record of what was executed and observed |
| 7 | Test Incident Report | an anomaly encountered during execution |
| 8 | Test Summary Report | activity and results against the exit criteria |

**Products 6–8 are execution artefacts.** A design has not run anything, so it
cannot produce them, and a design claiming to would be claiming an observation it
never made. `design_standards()` marks all three `out-of-scope` and names where
each actually lives.

## The classic Test Plan elements

The element list is the part auditors ask about, and it is worth knowing which of
them Métis can answer at all:

| Element | Métis |
|---|---|
| Test plan identifier | the design's own subject and generation stamp |
| Test items | the basis section: the claims and the recovered behaviour in scope |
| Features to be tested | every section's rows |
| Features **not** to be tested | `out_of_scope`, an asked input — absent, every gap reads as an omission |
| Approach | the technique, dimensions and levels sections |
| Item pass/fail criteria | the acceptance criteria a case asserts against |
| Suspension and resumption | **not answerable.** Métis observes no test run |
| Test deliverables | the design, and the cases generation renders from an approved model |
| Testing tasks | **not answerable.** No schedule exists (TD-2) |
| Environmental needs | the setup section, and `environments` as an asked input |
| Responsibilities | the `Owner` column, and it is a person's to fill |
| Staffing and training | **not answerable** |
| Schedule | **not answerable** (TD-2) |
| Risks and contingencies | the profile section and the risk family |
| Approvals | the design-acceptance halt, which records who accepted |

**Six of the fifteen are not answerable, and saying so is the useful part.** A
design that filled them would be inventing a plan; a design that omitted them
silently would let a reader assume they were covered.

## When to consult this file

- An auditor asks whether an artefact satisfies 829 and you need the original
  element definitions to answer precisely.
- A design deviates from the default mapping and the deviation needs justifying
  against what the standard actually intended.
- Somebody new needs the historical context for why the products are named as
  they are.

Do not copy this content into a skill. The mapping is served by
`design_standards()`; this is the *why* behind it, and duplicating it would
create the second copy that drifts.
