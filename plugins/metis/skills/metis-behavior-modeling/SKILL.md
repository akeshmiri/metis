---
name: metis-behavior-modeling
description: Check a state machine for determinism, guard completeness, reachability and observability before anything is generated from it, and report unverifiable guards as the third outcome they are rather than as a pass. Use when a user is defining or reviewing states and transitions and wants them checked for well-formedness.
---

# Métis behavior-modeling

Wraps stage 3 of the pipeline (`docs/metis-application-spec.md` §3.2), the one
stage that **blocks on any failure** (M-18). Everything downstream — path
generation, rendering, publication — assumes this ran and passed.

## The four properties, from §2.6

| Check | Question | Failure means |
|---|---|---|
| **determinism** | does one interaction match two transitions? | the machine is ambiguous; a test cannot say which behaviour it exercised |
| **guard completeness** | does some interaction match *no* transition? | a real input silently matches nothing — invisible anywhere in the graph |
| **reachability** | is there a dead state, or a missing transition? | behaviour nobody can reach, or a gap in the walk |
| **observability** | is each state distinguishable through the surface? | two "states" that no test can tell apart (M-3) |

## The third outcome, which is the point

A guard this checker cannot parse is reported **`unverifiable`** — never assumed
correct, and never merged into either of the other two. "This is wrong" and "this
cannot be shown to be right" are different facts, and collapsing them is how an
unparseable guard reads as a pass (M-17).

`unverifiable` **blocks by default.** An operator who accepts the risk does so
through `--allow-unverifiable`, which is recorded, not silent.

## Command

```
python3 -m metis_mcp.mbt.cli validate <model.json>
python3 -m metis_mcp.mbt.cli validate --journey <j> --surface <s>
```

Add `--allow-unverifiable` only when the user has explicitly accepted the risk,
and say in the report that they did.

## Steps

`steps/01-research.md`, `steps/02-plan.md`, `steps/03-implementation.md`. Read
`../shared/knowledge/anti-hallucination-protocol.md` once; its gates apply here.

## Naming a technique when you report a gap

Guard completeness and boundary coverage are the same question asked twice, and
the second phrasing is the one a tester acts on. `mbt/criteria.py` implements
ISO/IEC/IEEE 29119-4's boundary value analysis and equivalence partitioning by
name, and `mbt/dimensions.py` builds the equivalence classes — so when a guard
turns on a range, a length or a count, say which technique the gap belongs to.
`../shared/knowledge/test-techniques-reference.md` is the table to name it from.
It is a vocabulary, not a checklist: do not run through it looking for
techniques to apply.

## What this skill must not do

**Do not resolve an ambiguity for the user.** Two transitions on one trigger with
overlapping guards is a real modelling decision — which one should win, or
whether they should be one transition. Picking silently produces a machine that
validates and does not describe the system. Report the conflicting pair with both
guards verbatim and let a person choose.

**Do not report a cross-surface model as ambiguous without saying what was not
checked.** A UI transition can inherit its guard from the API transition it
invokes (M-5c), so a UI model read alone looks ambiguous exactly where the API
side determines it. If no `INVOKES` guards were supplied, the finding says so —
carry that caveat into what you tell the user.
