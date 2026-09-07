# 1 · Gather what Métis holds

## Run the tool, do not assemble it by hand

`requirement_risk(requirement_id, journey=...)` does the gathering and names the
tool behind every fact. Passing `journey` is what lets coverage be gathered — a
requirement id alone does not name a scope, and without one coverage reports as
*not gathered* rather than as zero.

That distinction matters: **not measured and measured-as-zero are different
facts**, and only one of them is a finding about the requirement.

## What each gathered fact decides

| Fact | If it is bad |
|---|---|
| `criteria_count == 0` | nothing can ever validate this requirement — the highest impact here |
| all criteria `code_derived` | the requirement is validated by a restatement of the implementation (S-19) |
| not EARS-conformant | two readers can satisfy it differently (S-13) |
| `lifecycle_state != Approved` | nothing may be generated from it (D-10) |
| superseded | it is a closed claim; work against it is work against the past |
| coverage 0 | the behaviour is untested — **not** that it is broken |
| no anchor | nothing outside Métis records who asked for it |

## Read what was NOT gathered

The output lists every gathered input that has no value, with what its absence
means. That list is not an error report — it is the boundary of what this
assessment covers, and reporting the findings without it overstates them.

## Then ask

Never stop here. `02-ask.md`.
