---
name: metis-coverage-report
description: Report what a model covers, what it does not, and — the part that makes the rest safe to read — what could not be measured at all. Use when someone asks how covered a scope is, wants a quality or readiness report, or asks whether something is ready to release.
workflow: coverage-report
allowed-tools:
  - list_workflows
  - route_request
  - run_status
  - ask
  - get_model
  - validate_model
  - coverage
  - coverage_report
  - test_design
  - trace
knowledge-from:
  - mbt.coverage
  - reconciliation.gaps
---

# Métis coverage-report

One stage, no gates. The work is not computing the number; it is refusing to let
the number be read as something it is not.

## Three answers that are not the same

| The question | The answer this gives |
|---|---|
| is this behaviour **tested**? | yes — that is coverage (C-11) |
| is this behaviour **working**? | **not from a coverage figure.** Execution results are ingested (§8.7, revised) but attach to the `TestCase` that ran and never write the coverage ledger (C-10) — *tested* and *passing* stay two figures |
| is this **ready to release**? | **it cannot say**, and will not compute a verdict from a coverage figure |

The third is the one people ask for. Answer it by giving them the first, saying
plainly that the second is not available, and letting a person decide — a Go
computed from coverage reads a coverage figure as a claim about quality, which
is exactly the trigger §6.8a names for reinstating the execution labels.

## Absence has a vocabulary, and using it is the point

A figure that was not measured and a figure that is zero are different facts, and
almost every reporting layer flattens them. `server._prune` drops null, empty
and false on the way out, so `unmeasured: []` and "never computed" leave the same
trace — none.

So every figure is one of:

- **measured** — with the version and commit it refers to (P-16)
- **unmeasured**, with a cause and a **kind**
- **not available in this build** — say which, rather than omitting the row

**The kind matters as much as the cause**, and collapsing the two is a specific
harm rather than untidiness:

| Kind | Meaning | Reported as |
|---|---|---|
| `structural` | the data genuinely does not exist | `transition_skipped`, `not_recorded`, `unverifiable`, `no_confirmed_matches`, `not_a_covering_mechanism` |
| `operational` | something that should have answered did not | an unreachable graph, a query that failed, a source never consulted |

An outage reported as "unmeasurable" reads as a permanent gap in the data model
and hides a problem somebody could fix in a minute. A genuine gap reported as an
outage sends them to restart a service that was never involved.

**One operational absence this skill must state, because no tool reports it.**
`MANUALLY_EDITED` and `OBSOLETE` publication drift read zero whenever nothing has
been recorded as sent — which means *cannot tell*, not *no drift*. `metis drift`
says so; `coverage_report` cannot, because `PublicationLedger` lives in a write
path and reaching for it would put that path on the read surface. Carry it by
hand when drift is part of what was asked.

**Confidence is capped by the weakest input used.** A coverage number computed
over a model with blocking validation findings is not worth more than those
findings, and the report says so in one sentence rather than leaving a reader to
notice.

## Commands

```
metis coverage-gap --journey <j> --surface api
metis validate --journey <j> --surface api
metis reconcile --journey <j>
metis workflow run coverage-report --scope <scope>
```

Exit codes: `0` complete · `5` **blocked on a human decision, not a failure** ·
anything else failed.

Through MCP, `coverage_report` returns all of the above joined, including
`unmeasured` and `confidence_capped_by`; `trace` answers "what justifies this
case" and reports the hop where the chain breaks.

## Steps

`steps/01-gather.md`, `steps/02-report.md`. Read
`../shared/knowledge/anti-hallucination-protocol.md` once; its gates apply here.


The reasoning behind the engine this skill drives is in
`knowledge/index.md` — generated from the module docstrings that are its
source of truth, so it cannot drift from the code it explains. Read a
fragment when you need the why, not before.
## Covered is not the same as adequately covered

`coverage` is binary per transition: a case walking the happy path makes it
covered. **A positive case is not coverage for a prohibited, boundary or
partition condition** — that needs a test with the condition's own oracle.

`test_design`'s `depth` answers the second question by comparison —
`all-transitions` yields one target per transition, `guard-coverage` one per
branch — and reports `full`, `partial`, or `positive-only`. It does not change
what `coverage` means (C-11, C-1); two figures that redefined each other would
disagree in front of a reader.

## Routing to a specialist

- **"is it ready to release?"** → `metis-release-readiness`. It assembles the
  same evidence and is explicit about handing the judgement back, because that
  question is the one most likely to be answered with a number that gets read as
  a verdict.

Everything on this page applies there too. The specialist adds the discipline for
the one question, not a different set of rules.

## The standard behind this, and what it does not certify

**ISO/IEC/IEEE 29119-4** — `../shared/references/iso-29119-4-coverage-measures.md`.
It names the seven criteria Métis computes and the three things every figure is
bounded by: what extraction reached, approval state, and C-11 — a transition may
be fully covered and currently failing.

**A coverage map, never a compliance claim.** `metis_mcp/standards.py` is the
registry — which standard governs which skill, what Métis computes against it,
and what it refuses to claim. Whether the result satisfies an obligation is a
judgement about the obligation, not a property Métis can compute.

## What this skill must not do

1. **Never emit a Go / No-Go, a readiness score, or a pass rate** (C-11, C-10).
   Not even hedged. The moment a number reads as a verdict, it will be used as
   one.
2. **Never present coverage as correctness.** A model whose criteria are all
   `code_derived` is documentation agreeing with itself: real coverage, and no
   evidence the behaviour is right (S-19, §4.1).
3. **Never omit a figure it could not compute.** Silence reads as zero. Name it
   and say why (F-10).
4. **Never count an `initiated` transition as covered** (C-1). It is reported
   and never counted, and the two are different rows.

## Verification

```
uv run python -m pytest -q test_mcp_server.py -k coverage_report
```
