# Life-cycle process alignment — ISO/IEC/IEEE 12207 and 15288

**A side reference, not loaded by default.** Consult it when a design has to be
placed against a life-cycle process because a compliance requirement names one,
or when a reviewer questions whether a process is genuinely out of scope for a
software-only change.

It would still be true if Métis were deleted, which is why it is a reference
rather than knowledge.

## Which standard applies

**ISO/IEC/IEEE 12207** defines the life-cycle processes for *software*.
**ISO/IEC/IEEE 15288** defines them for *systems* — hardware included. They are
deliberate counterparts and most scopes are software-only, so 12207 is the more
commonly applicable of the two.

Prefer 15288 where the scope spans hardware, firmware, or a system boundary
crossing more than one deployable component. Where it does, most of what Métis
recovers stops being the whole picture, and the design should say so.

## The processes a test design touches

| Process | 12207 | What it covers | Where Métis answers it |
|---|---|---|---|
| Stakeholder requirements definition | §6.4.1 | what stakeholders need, before solutioning | the basis section, and `metis-business-analyst` upstream of it |
| Requirements analysis | §6.4.2 | turning needs into verifiable requirements | EARS conformance and criterion quality, in the basis section |
| Architecture / design definition | §6.4.4 | structure, components, interfaces | **asked.** `runtime_architecture` and `design_specification` are questions; Métis recovers what the code does, not what it was meant to do |
| Integration | §6.4.6 | combining units into an integrated whole | the contract and journey sections |
| Verification | §6.4.7 | built *right* — conforms to the specified requirement | the **`verification`** section, which carries the box transparency each guard's evidence supports, plus technique, dimensions and data |
| Validation | §6.4.8 | does the *right thing* — meets the actual need | the **`validation`** section. Mostly `no` or `clarify`, and that is the finding rather than a failure of the section |
| Qualification testing | §6.4.9 | independent evaluation before release | `metis-release-readiness`, not the design |

## The row worth arguing about

**Architecture and design definition is `asked`, and that is a decision rather
than a gap.** Métis could describe an architecture by summarising what it
recovered from the code. That description would be the implementation restated as
its own intent — the same defect S-19 names when a criterion is written from the
code and then used to check it. A design built on such a summary would be testing
the system against itself, and would look thorough while doing it.

So the process is named, the answer is a question, and a design without it says
which sections it therefore could not state.

## The two directions this can go wrong

- **Claiming a process the design does not touch.** Qualification testing needs
  execution evidence; a design has none. Claiming it is the C-11 conflation in
  life-cycle clothing.
- **Marking a process `not applicable` because nobody thought about it.** For a
  software-only scope most 15288 system-level processes genuinely do not apply —
  but "does not apply" and "nobody looked" are different, and only the first is
  an answer.

## When to consult this file

- A compliance requirement cites 12207 or 15288 by name.
- A reviewer questions a `not applicable` row and you need the clause definition
  to confirm it.
- The scope grows a hardware or system boundary, and 15288 becomes the right
  reference.

## What this reference does not do

It does not reproduce either standard, and **nothing computes this alignment** —
it is a reading a person recorded here, checked by no test. That is the one entry
in `metis_mcp/standards.py` with an empty `computes`, declared rather than filled
with a module name that would not be doing the work.

It is also not a conformance claim. Placing a design section against a life-cycle
process says which process the section touches; whether the process is
adequately performed is a judgement about the project.


## Why these two are separate sections and not one

12207 keeps §6.4.7 and §6.4.8 apart, and Métis follows it for a reason of its
own: **"built right" is answerable from the implementation and "the right thing"
is not answerable from it at all.**

Métis computes a great deal about verification — every guard, its atomic
conditions, how much of the inside was visible when it was recovered. It
computes almost nothing about validation, because the only evidence for a *need*
is a criterion somebody wrote **without reading the code**. Where the criterion
was written from the code, its agreeing with the code is coverage and never
correctness (S-19, §4.1), so validation there is not weak — it is impossible.

A single "V&V" section would put a full table beside an empty one under one
heading, and the fullness would be read as covering both. Keeping them adjacent
and separate is what makes the emptiness of the second legible.
