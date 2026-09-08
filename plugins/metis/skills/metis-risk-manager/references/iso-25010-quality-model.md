# Product quality model — ISO/IEC 25010

**A side reference, not loaded by default.** Consult it when a risk category has
to be justified, or when somebody asks why the register's vocabulary is closed.

It would still be true if Métis were deleted, which is why it is a reference
rather than knowledge.

## What the standard is

25010 is part of the SQuaRE series (ISO/IEC 25000). It defines a **product
quality model** — a taxonomy of quality characteristics, each with sub-
characteristics — and, separately, a quality-in-use model. Métis uses the product
quality model only.

## The nine characteristics, and the 2011 → 2023 change

Métis follows **25010:2023**, which is nine characteristics rather than the eight
of 25010:2011. Two changes matter when reading an older register:

- **Usability** was renamed **Interaction capability**.
- **Safety** was **added**. Software that can hurt somebody is not merely
  unreliable, and 2011 had nowhere to record that.
- **Portability** became **Flexibility**, absorbing scalability.

The nine, with Métis's own gloss on each, are in `metis_mcp/risk/rbs.py` —
`PRODUCT_CATEGORIES` — which is the source of truth. It is not restated here,
for the same reason no `SKILL.md` restates a design section's columns: a second
copy is the one that goes stale.

## Why a closed vocabulary at all

A register whose categories are free text grows `Tech`, `Technical` and
`technical` as three rows in one chart. `risk_register_check` reports that as
incoherence. The taxonomy is closed so that grouping is possible at all.

**The row worth knowing about:** *testability* sits under **Maintainability**.
That placement is the standard's, and it is why an untestable requirement is
recorded as a product risk rather than only as a process complaint.

## The half 25010 does not cover

`rbs.py` carries a second taxonomy — `PROCESS_CATEGORIES` — for risks that are
not properties of the product at all: requirements, test design, test data, test
environment, automation, regression, release, observability, technical debt,
capability. These are **not** from 25010, and they are kept separate rather than
appended, because giving them a position in the product model would say the model
contained something it does not.

## What this reference does not do

It does not reproduce the standard, and Métis does not **measure** a quality
characteristic. It uses the model as a taxonomy. `risk_register_check` reports
what is incoherent in a register, never whether a risk is real.
