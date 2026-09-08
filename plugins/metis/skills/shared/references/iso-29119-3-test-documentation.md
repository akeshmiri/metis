# Test documentation — ISO/IEC/IEEE 29119-3

**A side reference, not loaded by default.** Consult it when a work product has
to be named in the standard's own vocabulary — a compliance requirement cites a
clause, an auditor asks which document Métis produced, or a reviewer questions
whether something Métis marks `out-of-scope` really is.

It would still be true if Métis were deleted, which is why it is a reference
rather than knowledge. What Métis computes against it is in
`metis_mcp/design/standards.py`, served by `design_standards()`.

**Shared, because two skills consume it.** `metis-test-design` answers the
design-time work products; `metis-test-generate` answers the two the design
deliberately does not.

## What the standard is

29119-3 is the documentation part of the ISO/IEC/IEEE 29119 series. It defines
templates and content for the documents produced across a test project, and it
**supersedes IEEE 829-2008** — which Métis still carries separately, because 829
remains the more commonly spoken naming reference in practice.

The series as a whole: **-1** concepts and vocabulary, **-2** test processes,
**-3** documentation, **-4** test techniques, **-5** keyword-driven testing.
Métis works against -2, -3 and -4; it makes no claim against -1 or -5.

## The design-time work products, and who answers each

| Code | Work product | Métis | Where |
|---|---|---|---|
| TP | Test Plan | partial | `basis`, `compliance`, `uncertainty` — the scope and what it rests on. Schedule, staffing and budget are not Métis's to state |
| TDS | Test Design Specification | full | `conditions`, `technique`, `dimensions`, `security`, `performance`, `contract`, `journey` |
| TCS | Test Case Specification | out of scope **for the design** | `metis-test-generate` renders it from an approved model (`rendering/test_case.py`) |
| TPR | Test Procedure Specification | out of scope **for the design** | as above — a `.feature` file as specification, never step definitions |
| TDR | Test Data Requirements | full | `data` — conditions on the accepted space, never values (M-9) |
| TER | Test Environment Requirements | partial | `setup`, `levels`. The environments themselves are an `asked` input |

**TCS and TPR are `out-of-scope` in the design and owned in generation.** That is
one hand-off, not a gap: design derives conditions and coverage items, generation
turns them into cases and procedures. `design/areas.py` records the crossing so a
test can check it.

## The three that are out of scope everywhere

A **Test Log**, a **Test Incident Report** and a **Test Summary Report** are
execution and reporting artefacts. Métis marks all three `out-of-scope` and names
where the answer actually lives.

This is the C-10/C-11 line in the standard's vocabulary. A coverage figure
answers *is this tested*; a log and an incident report answer *what happened when
it ran*. Métis ingests execution results (§8.7, revised) and keeps them attached
to the `TestCase` that ran — it does not write the coverage ledger from them, and
it does not render them as a work product it produced.

## What this reference does not do

It does not reproduce the standard. 29119-3 is a purchased document, and a
paraphrase detailed enough to substitute for one would be both a licence problem
and a worse source than the original. Read this to place Métis's output against a
clause somebody else is reading.

**Answering a work product is not conforming to the standard.** Métis publishes a
coverage map. Whether that map satisfies an obligation is a judgement about the
obligation, and `design/standards.py` forbids a `because` line that reads
otherwise.
