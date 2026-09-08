---
name: metis-test-design
description: Design what to test and how — the techniques each behaviour warrants, the data conditions they need, the level each is asserted at, and the questions nobody has answered — as one document a person owns and regeneration never overwrites. Use when someone asks what testing a scope involves, wants a test design or test approach, or asks which technique applies. Not for rendering cases from an approved model; that is metis-test-generate.
workflow: test-design
allowed-tools:
  - list_workflows
  - route_request
  - run_status
  - ask
  - design_sections
  - design_standards
  - design_inputs
  - design_report
  - get_model
  - validate_model
  - get_requirement
  - get_spec
  - coverage_report
  - test_design
  - product_risk
  - risk_priority
knowledge-from:
  - standards
  - design.inputs
  - design.sections
---

# Métis test-design

Design is the question before generation. `metis-test-generate` renders cases
from an approved model; this decides what those cases should be about, at which
level, and what remains unknown.

**One rule is specific to this system and load-bearing:**

**A design missing a required input is `incomplete`, never lean.** Métis holds
the model, the guards, the risk profile and the coverage ledger. It does not
hold the architecture, the design specification, the environments, the data
constraints or the NFR targets — and those decide most of what a test design
says. `design_inputs` splits the two halves and carries the exact question for
each; `design_report` reports `incomplete` until they are answered, with that
word above the first section rather than below the last.

## The shape is served, never restated

`design_sections()` returns every group, section, column and closed vocabulary.
**Do not describe the format in prose here or anywhere else** — a template a
model imitates is imitated differently every run, and a prose copy of a served
fact is the copy nothing checks. Call the tool; render what it gives you.

## Routing — which specialist

**Route on the section, which is a lookup rather than a judgement.** A
specialist owning more than one section owns them together, because they answer
one question in two tables — splitting them would make a reader consult two
skills to learn what one technique costs.

**No count is stated here, and that is deliberate.** This table said "nine
sections, seven specialists, and the parent keeps two" while `design_sections()`
served sixteen and the table below listed four — a hand-written number that
drifted three ways at once, in the one file whose whole point is that the shape
is served rather than restated. `design_sections()` is the inventory; this is
the routing, and `test_design_areas.py` asserts every served section appears in
one of the two tables.

| Route to | For | Section |
|---|---|---|
| **`metis-test-design-technique`** | which technique a behaviour warrants, and its coverage items | `technique`, `dimensions` |
| **`metis-test-design-data`** | what the data must satisfy | `data` |
| **`metis-test-design-levels`** | which level, what already covers it, what can be automated | `levels`, `profile`, `setup`, `verification` |
| **`metis-test-design-security`** | authorisation and authentication conditions | `security` |
| **`metis-test-design-performance`** | load candidacy, and where nobody has sized it | `performance` |
| **`metis-test-design-contract`** | what an endpoint declares against what it does | `contract` |
| **`metis-test-design-journey`** | which UI action invokes which call (M-5c) | `journey` |

## What standards this answers, and what it does not

`design_standards()` maps every section onto ISO/IEC/IEEE 29119-3's six
design-time work products and IEEE 829's eight documents, and the `compliance`
section renders it. **Three are `out-of-scope` and that is an answer, not a gap**
— a Test Log, a Test Incident Report and a Test Summary Report are execution and
reporting artefacts, and a design that claimed them would be claiming an
observation it never made.

**It is a coverage map, never a compliance claim.** It says which section answers
which product and what is missing where the answer is partial. Whether that meets
an obligation is a judgement about the obligation, and saying otherwise would be
Métis certifying something it cannot compute.

Two side references carry the *why*, and neither is loaded by default:
`references/ieee-829-work-products.md` for the original element definitions when
a deviation needs defending, and `references/life-cycle-alignment.md` for 12207
and 15288 when a compliance requirement names one.

### Keep these yourself

| Stay here | Section | Why |
|---|---|---|
| the basis, and whether there is one | `basis` | every specialist's rows are about it |
| condition completeness | `conditions` | it is the denominator every other section is measured against |
| negative obligations | `obligations` | it crosses authorisation, contract and data, and belongs to none of them |
| whether it was the right thing | `validation` | it rests on criterion provenance, not on the model — and a criterion written from the code cannot validate it (S-19) |
| missing-criterion candidates | `mirror` | it is the completeness question `conditions` opens, answered as specific proposals rather than classes — and no specialist owns a question about all of them |
| the uncertainty ledger | `uncertainty` | consolidating what each section could not state *is* running the design |
| the machine in scope | `machine` | the one thing Métis draws, and it is the whole scope rather than any specialist's slice of it |
| the standards map | `compliance` | it is a statement about the document, not the system, so it is about every specialist at once |

**The `conditions` section is the one that decides whether the rest can be
trusted.** A positive case says what the system does. It does not say what the
system must reject, prevent, limit or leave alone — and counted as coverage for
those, it excuses exactly the gaps testing is for. Every behaviour gets a row
for all eight classes, including the ones that do not apply: a `boundary` row
marked `not-applicable` **with a reason** is the mechanism, and a class that
silently disappears is the failure it prevents.

Métis reaches six of the eight. `dependency-failure` and `non-goal` are
**undrawn** — what happens when something outside this code stops answering, and
what was deliberately excluded, are not in the source it read. Both come back
`clarify`, which is neither "we will test it" nor "it does not apply".

**`obligations` is the same question shaped by the endpoint rather than the
requirement.** A path parameter obliges a not-found; a declared security
requirement obliges a refusal; a body obliges a rejection; an enumerated input
obliges a case per constant. Each is raised by a **recovered fact** and names
it — a route that merely looks like it should have one obliges nothing (X-6).

**`unmet` is a question and never a defect.** It says no such outcome was
*recovered*. Whether the behaviour is unhandled or extraction did not see it is
something only a person can settle, and saying otherwise would be asserting a
conclusion from an absence. Report the recovered outcomes beside it, always:
"`GET /x/{id}` produces 200, 204 and 400, and no 404" is a question somebody can
answer; "missing 404" is one they cannot.

`design/areas.py` records which skill owns which section and `test_design_areas.py`
asserts it in both directions, so a specialist that stopped covering its area
fails a test rather than quietly leaving a gap.

## Risk decides the order, and never the probability

Rows come back ordered by `risk.prioritisation.order` — detectability, then
defect-proneness, then id — which is exactly what `metis-test-generate`'s
`prioritise` stage applies to generated paths. The design and the batch cannot
disagree about what matters first.

**Two rules cross from the risk family intact:**

- A **band** says how much there is to get wrong. It is `derived_from: model`
  and it is not a forecast. No design table has a probability column, and none
  may grow one.
- Where a band warrants deeper testing than the model can support, that gap is
  an **open question with an owner**, not a figure. It will never show up in a
  coverage number: the behaviour may be fully covered at the depth it can reach.

For the rating itself, route to `metis-risk-manager-product-risk`. This skill
consumes bands; it does not produce them.

## Commands

```
metis design --journey <j> --surface api -o design.md
metis design --journey <j> --section data
metis design --verify -o design.md
metis workflow run test-design --scope <scope> --journey <j>
```

Exit codes: `0` complete · `5` **blocked on a human decision, not a failure** ·
anything else failed.

## Steps

`steps/01-gather.md`, `steps/02-sections.md`, `steps/03-questions.md`,
`steps/04-accept.md`, in that order. Read
`../shared/knowledge/anti-hallucination-protocol.md` once; its gates apply here.
When a guard's complement has no case, `../shared/knowledge/requirement-condition-coverage.md`
says which class it belongs to.

The reasoning behind the ledger and the registry is in `knowledge/index.md` —
generated from the module docstrings that are its source of truth, so it cannot
drift from the code it explains. Read a fragment when a step cites it, not
before.

## The document is edited, and that is the point

`metis design -o <file>` writes Markdown whose `Decision`, `Owner` and `Notes`
columns are yours, along with every row you add. Regeneration preserves both.
The ID column is derived from what a row is about, so a decision stays attached
to its condition when the model changes — **never renumber it**.

`metis design --verify` checks an edited document is still the shape the merge
can read. Python computes, a person writes, Python verifies.

## The design-acceptance gate

The workflow halts until a named person accepts. Métis proposed every row and
decided none of them, so an unaccepted design is a set of proposals — and a
design whose sections are all full still needs accepting, because "Métis derived
this" is a statement about Métis rather than a decision about testing.

The literal is `accept-design`, it is the human's, and it is not `accept-risk`.

## The standard behind this, and what it does not certify

**ISO/IEC/IEEE 29119-3** — `../shared/references/iso-29119-3-test-documentation.md`.
The design answers four of the six design-time work products; the Test Case and
Test Procedure specifications are `metis-test-generate`'s, which is a hand-off
rather than a gap. IEEE 829 and the 12207/15288 alignment are the two side
references already named above.

**A coverage map, never a compliance claim.** `metis_mcp/standards.py` is the
registry — which standard governs which skill, what Métis computes against it,
and what it refuses to claim. Whether the result satisfies an obligation is a
judgement about the obligation, not a property Métis can compute.

## What this skill must not do

1. **Never present the gathered half as the design.** It is the half that was
   reachable, and it does not contain the architecture.
2. **Never invent an architecture, an environment or an SLA** to fill a section.
   `no-basis` and `waiting on:` are the honest values, and both are printed.
3. **Never emit a value where the model states a space** (X-6e, M-9). A design
   states `attempts = 4` as a condition; producing the fixture is somebody
   else's job.
4. **Never read a short section as a small job.** Check `status`. If it is
   `incomplete`, the section is short because nobody answered.
5. **Never let a risk band become a probability.** It ranks; it does not
   forecast.
6. **Never generate from this document.** Generation reads an approved model
   (D-10), not a design.
