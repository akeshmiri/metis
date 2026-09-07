---
name: metis-change-impact
description: Show which recovered behaviour a change touches and what validates it, then take the change to the approval gate — re-recovering, revoking only the approvals whose behaviour moved, and stopping for a human on those. Use when someone asks what a diff, branch or commit range affects, or wants to approve a change to a model.
workflow: change-approval
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - impact
  - change_review
  - trace
  - get_model
  - validate_model
  - coverage
  - describe_execution
knowledge-from:
  - impact
  - execution
---

# Métis change-impact

Two things, and the smaller one is usable on its own.

**The question.** Given a set of changed files, or two commits: which transitions
were recovered from those files, what evidence reached them, and which criteria
validate them. Read-only, no gate, answerable in one call.

**The workflow.** `change-approval` is what acts on that answer — re-recover,
grade the diff, land carrying human decisions forward, revalidate, and stop at
G1 with **only what changed** in front of the reviewer. Six stages, one gate.

The second is why this skill drives a workflow where
`metis-behavior-modeling` does not: validation is a stage that runs inside other
workflows, but *approving a change* is an end-to-end act with a decision at the
end of it.

## The distinction that makes it useful

| It answers | It does not answer |
|---|---|
| what behaviour does this change **touch** | whether the change is **correct** |
| which criteria validate that behaviour | whether those criteria pass |
| which files matched nothing | that those files are safe |

**A file that matched nothing is named, never counted as "no impact".** Those
are different answers, and the second one is the dangerous one: a file matches
nothing when the model does not cover it, which is precisely when a reviewer
should look harder.

## Current only as of the last extraction

It queries the graph, never the repository's code. If the model has not been
re-extracted since the change, the answer describes the previous state of the
world — and the commits it matched against come back with the answer so that is
checkable rather than assumed.

## Commands

```
# The question alone — read-only, no gate:
metis analyse --repo <path>          # re-extract first, if the model is stale
metis validate --journey <j>

# The whole change through to the gate:
metis workflow run change-approval --scope <s> --journey <j> \
    --repo <path> --since <commit> [--until HEAD]
metis workflow status change-approval--<scope>
```

**`--since` is required and is not defaulted.** `changed_files` answers a range
git cannot resolve with an empty list, so a default would turn *I could not tell*
into *nothing changed* — the one substitution this whole system exists to refuse.

Exit codes: `0` complete · `5` **blocked on a human decision, not a failure** ·
anything else failed.

Through MCP, `impact` takes either `changed_files` (what `git diff --name-only`
prints) or `repo` + `since` + `until`, and resolves the range itself. A range git
cannot resolve is reported as `range_unresolved` — never as zero impact. `trace`
then answers what justifies a given case, and reports the hop where the chain
breaks.

## Grading what it finds

`change_review` turns the impact answer into severity-graded findings, and the
grades map to what the model can establish rather than to a feeling:

| Grade | Means |
|---|---|
| `critical` | touched behaviour that **nothing validates** (D-4) |
| `major` | covered on the positive path only — the complement has no oracle |
| `minor` | validated only by `code_derived` criteria: coverage, never correctness (S-19) |
| `question` | a changed file matched nothing — **never** reported as "no impact" |

`critical` and `major` block; they are the list `open_merge_request` refuses
over, which had no producer before this.

**It is not a code review.** Style, maintainability, naming and security lint
belong to the tools the repository already runs — Métis has no language server
and no lint configuration, and a second opinion would be worse. Say so when you
report: a clean result is not a statement that the change is good.

## Steps

`steps/01-scope.md`, `steps/02-report.md`. Read
`../shared/knowledge/anti-hallucination-protocol.md` once; its gates apply here.


The reasoning behind the engine this skill drives is in
`knowledge/index.md` — generated from the module docstrings that are its
source of truth, so it cannot drift from the code it explains. Read a
fragment when you need the why, not before.
## What this skill must not do

1. **Never call the system it models** (X-7a). It reads a graph and a git log.
   It does not hit the API, drive the UI, or query the database.
2. **Never write to a tracker or a merge request.** Reviewing is not filing. The
   review gate this came from blocked on Critical findings; that judgement
   belongs to a person with the finding in front of them.
3. **Never present "no impact" without saying what was compared.** An empty
   result and an unresolvable range look identical to a reader and are not.
4. **Never let a stale extraction pass as current.** Report the commit the graph
   was built from beside the commit being reviewed.

## Verification

```
uv run python -m pytest -q test_impact.py
```
