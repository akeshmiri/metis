---
name: metis-model-build
description: Recover a behaviour model from a codebase and take it to the approval gate — extract states and transitions from a code property graph, draft acceptance criteria for the branches nothing covers, land everything at Quarantine, validate, reconcile, and stop for a human. Use when someone asks to build or rebuild a model for a service, or to re-extract after code changed.
---

# Métis model-build

The `model-build` workflow, end to end. One command runs the ordered stages and
**halts at G1**; a person decides; `resume` continues.

```
extract → ac-draft → land → validate → reconcile → G1 (halt)
```

## Commands

```
python3 -m metis_mcp.mbt.cli workflow list
python3 -m metis_mcp.mbt.cli workflow run model-build --scope <scope> \
    <behaviour-report.json> --endpoints <structural-report.json> --service <svc> \
    --journey <j> --surface api --source code
python3 -m metis_mcp.mbt.cli workflow status model-build--<scope>
python3 -m metis_mcp.mbt.cli workflow resume model-build --scope <scope> \
    --journey <j> --surface <s>
```

Exit codes: `0` complete · `5` **blocked on a human decision, not a failure** ·
anything else failed.

## Where the reports come from

The `code` source reads a query pack's already-emitted report; it does not run
the CPG engine itself. Producing one is two steps — build, then query:

```
# 1. Build the CPG. One artefact per (repo, commit); kept outside the graph.
~/tools/joern-cli/bin/joern-parse <src> --output <cpg.bin> --language javasrc2cpg

# 2. Run a pack against it.
~/tools/joern-cli/bin/repl-bridge --script code_analysis/packs/jvm-structural/query.sc \
    --param cpgPath=<cpg.bin> --param commit=<sha> --param repo=<name> --param out=<file.json>
```

Frontends: `javasrc2cpg` for the JVM, `jssrc2cpg` for JS/TS. Note the `joern`
wrapper needs `greadlink` (GNU coreutils) on macOS; `bin/repl-bridge` is the same
entry point without that dependency.

**`--service` is required on a multi-module report.** The pilot estate's single
report carries outcomes for seven services; synthesising them together produces
one large model wearing one service's name, which is worse than failing because
it looks like a result.

## Steps

`steps/01-research.md`, `steps/02-plan.md`, `steps/03-run.md`. The
anti-hallucination gates in `../shared/knowledge/anti-hallucination-protocol.md`
apply throughout.

## Three things to report honestly, every time

**Provenance.** A model from this path is `static_analysis`. If it is landed
through the `authored` source instead, the graph records that a person wrote what
a machine inferred — say which one actually happened.

**What was skipped.** Extraction reports skipped facts and synthesis findings.
Name them; F-10 forbids presenting a partial result as a complete one.

**Coverage versus correctness.** A model can be fully approved with zero
intent-backed criteria. That run yields **coverage, not correctness** (S-3), and
saying so is the difference between a useful number and a misleading one.

## Why it is a workflow and not six commands

Below the commands deliberately — this is the reasoning, not the procedure.

Every stage exists as its own verb and always did. What did not exist was
anything that knew the order, so the ordering lived in a shell script, two
throwaway helpers under `/tmp`, and the operator's memory. The engine adds three
things a person running verbs by hand cannot get:

- **a stage cannot run before its prerequisites passed** — and not merely
  "passed", but passed against the *same input*. A run that halts on Tuesday and
  resumes on Thursday refuses if the model changed on Wednesday (N-14);
- **a gate halts durably** with a distinct exit code, so CI can tell "waiting on
  a human" from "broken";
- **checks execute.** A stage's `checks` are registered Python predicates; a
  workflow naming a check nothing implements fails the lint before it can run.
