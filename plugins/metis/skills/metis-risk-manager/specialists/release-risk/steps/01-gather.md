# 1 · Gather the readiness evidence

## Run the tool

`release_risk(journey, surface)` reads `coverage_report` with `detail=True` —
which matters, because the default payload carries a *count* of blocking findings
and a risk saying "3 blocking findings" without naming them cannot be acted on.

## What each gathered fact decides

| Fact | If it is bad |
|---|---|
| blocking validation findings | stage 3 blocks on any failure (M-18), and everything downstream assumes it passed — the highest impact here |
| no execution evidence | coverage alone supports no verdict. This is why "we are 95% covered" is not an answer to "is it safe to ship" |
| `unmeasured` entries | a figure could not be produced. A risk about the report, not the behaviour |
| `confidence_capped_by` | names the weakest input the figures rest on; the report is worth no more than it |
| change exposure | what this diff leaves unasserted, graded by `change_review` |

## The execution tier changes what absence means

At `METIS_EXECUTE=off` nothing was observed, and the empty list is the honest
value — Métis was never permitted to look. Above `off`, an absent value means
*not gathered*, which is a different statement. `describe_execution` says which
tier is in force; report it, because "nothing ran" and "we were not allowed to
check" are not the same risk.

## Read what was not gathered

As always, the boundary of the assessment is part of the assessment.

## Residual risk, which is what the exit decision is actually made against

ISO/IEC/IEEE 29119-2 expresses a test exit criterion as **residual risk**, not as
a coverage percentage. `residual_risk(journey, surface)` returns it as two
populations, and they are deliberately not summed:

| Population | What it is | What it needs |
|---|---|---|
| `unnoticed` | high-band behaviour nothing would notice breaking | a test |
| `failing` | behaviour a test that ran reported broken | a fix |

**One total would hide the thing you most need to see.** A rising failure count
cancelled by rising coverage nets out to "unchanged", and the release is worse
than it was.

`risk_coverage(journey, surface)` answers the other half — whether the uncovered
part is the part that matters. It is a pivot, never a weighted percentage: *of
the N behaviours in this band, k are uncovered*. An ordinal band cannot be
averaged, and "80% covered" is a different fact depending on which 20% is
missing.

**This is still not readiness, and it is still not a verdict.** Pass the
thresholds the release agreed at planning time (`max_unnoticed`, `max_failing`,
`max_unmeasured`) and `exit_criteria` reports which are breached. With no
thresholds it reports the counts and says plainly that nothing here can judge
them — the same shape as a missing appetite, and for the same reason.
