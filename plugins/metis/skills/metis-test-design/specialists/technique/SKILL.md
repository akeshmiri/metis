---
name: metis-test-design-technique
description: Choose the test design technique each behaviour warrants and enumerate its coverage items — equivalence partitions, boundaries, decision table rules, pairs — from the guard itself, carrying every refusal through. Use when a request is about which technique applies, how many cases a behaviour needs, or why a technique cannot be used here.
allowed-tools:
  - design_sections
  - design_inputs
  - design_report
  - get_model
  - validate_model
  - get_requirement
  - product_risk
  - ask
  - run_status
  - list_workflows
---

# Métis test-design · technique

## Prerequisites, from the parent

The parent (`metis-test-design`) has already established, and this skill does
not re-derive:

- a design missing a required input is `incomplete`, never lean;
- the shape comes from `design_sections()` and is never restated in prose;
- rows are ordered by risk, and a band ranks — it never forecasts;
- Métis proposes every row and decides none of them.

This skill owns the `technique` and `dimensions` sections.

## What this does

Selects a technique per behaviour and says how many distinct things it asks for.
Everything comes from the guard and the declared constraints: `mbt/techniques.py`
partitions and bounds, `mbt/design.py` builds decision tables and pairs. Nothing
here reads a name.

`../../../shared/references/test-techniques-reference.md` is the technique
material itself — true whether or not Métis exists. Read it when choosing
between techniques, not before.

## The refusals, and why each is a row rather than a silence

| Refusal | Cause | What it means |
|---|---|---|
| `only one transition on this (state, trigger)` | a table of one row | a single test states the same thing |
| `a guard contains OR` | a disjunction | half a table is worse than none (M-17) |
| `not a numeric threshold` | `t.isEmpty()` has no boundary | a two-way partition, and **no boundary claim at all** |
| `only one input varies` | one factor | pairwise here is equivalence partitioning renamed |

**Every one of these appears in the design.** A designer needs to know a
technique was considered and declined. Dropping the row makes the design look
like it considered fewer options than it did.

## The reduction, which is where the count actually comes from

An endpoint varies along several axes — authentication, authorisation, payload,
each field. Treated as independent they **multiply**: `3 x 2 x 10 = 60` cases
for one endpoint. They are not independent. They are a short-circuit chain: a
request that fails authentication never reaches authorisation, so varying
authorisation underneath it produces no observable difference.

    1 + 1 + 9 + 1 = 13 tests, not 60.

The `dimensions` section carries that chain per behaviour — each recovered
condition, its evaluation order, its class, and the bounded count against the
full product. **Read it before quoting a coverage-item total**: a technique
count that ignores the chain is counting cases nobody can reach.

Two refusals travel with it and neither may be softened:

- **GD-9** — where precedence could not be recovered, the chain is neither
  assumed ordered nor assumed independent. The full product is **reported, not
  generated**, and the reason says so.
- **X-10c** — a check that matched no declared class keeps its position and
  participates in the chain anyway. A blank `Class` is a recovered fact, not a
  gap.

An empty `dimensions` section means **no guard check was recovered**, which is a
statement about what extraction reached and not about whether the code branches.

## Steps

`steps/01-select.md`, then `steps/02-enumerate.md`.

## The standard behind this, and what it does not certify

**ISO/IEC/IEEE 29119-4** — `../../../shared/references/iso-29119-4-coverage-measures.md`
for the coverage *measures*; `../../../shared/references/test-techniques-reference.md`
beside it for the techniques themselves. A coverage item is what a technique
asks for; whether anything asserts it is a different question (C-11).

**A coverage map, never a compliance claim.** `metis_mcp/standards.py` is the
registry — which standard governs which skill, what Métis computes against it,
and what it refuses to claim. Whether the result satisfies an obligation is a
judgement about the obligation, not a property Métis can compute.

## What this skill must not do

1. **Never award a technique on a name.** `POST /login` does not imply boundary
   analysis. The guard does, or nothing does (X-6).
2. **Never invent a boundary for a predicate.** `t.isEmpty()` has none, and
   manufacturing one is inventing data (M-9).
3. **Never present a partial decision table as complete.** A missing row reads
   as a covered one, which is why the table is refused whole.
4. **Never count coverage items as coverage.** An item is what a technique asks
   for; whether anything asserts it is a different question (C-11).
