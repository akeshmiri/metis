# 1 · Gather what Métis holds

## Run the tool, do not assemble it by hand

`design_report(journey, surface, requirement_id=...)` does the gathering and
names the tool behind every fact. Passing `requirement_id` is what lets the
**basis** be gathered — a journey alone names a scope, not a claim, and without
one the design describes what the code does with nothing stating what it should.

That distinction matters: **a design with no basis can only report that the
implementation agrees with itself** (S-19). It is not a weaker design; it is a
different artefact.

## What each gathered fact decides

| Fact | If it is bad |
|---|---|
| no `requirement` | nothing states what correct is — every assertion would be one Métis chose |
| criteria all `code_derived` | the design validates a restatement of the implementation (S-19) |
| not EARS-conformant | two readers design differently from the same sentence (S-13) |
| `lifecycle_state != Approved` | nothing may be generated from it later (D-10) — the design is still worth making |
| no `guards` | there is nothing to partition; a technique chosen anyway is chosen on a name (X-6) |
| blocking validation findings | the model cannot support a design claim (M-18) |
| coverage not measured | **not** zero coverage, and only one of them is a design gap |

## Read what was NOT gathered

`design_report` returns `missing_inputs`, each with `absent_means`. That list is
not an error report — it is the boundary of what this design covers, and
reporting the sections without it overstates them.

## Report

The model id, which inputs were gathered and by which tool, and the count of
required inputs that were not. Then `02-sections.md`.
