---
name: metis-intake-processor
description: Extract a real source — Jira, Confluence, Swagger/OpenAPI, Zephyr Scale, source code or a database — into one Unified Intake Format (UIF) document, every field traced to the response it came from, nothing inferred. Use when a user wants a source captured in a normalized, reviewable shape. The landing half has no implementation in this build and says so rather than pretending.
---

# Métis intake-processor

Extract one real source into one Unified Intake Format document. Every field
traces to the response it came from; nothing is inferred.

Writing a UIF file is supported and useful for inspection. It is not the end of
the pipeline — see **What this build cannot do** below before promising a user
that anything reaches the graph.

## Supported sources

| Source | Extractor | Config |
|---|---|---|
| `jira` | `extractors/jira_extractor.py` | `configs/extractors/jira-extractor.yaml` |
| `confluence` | `extractors/confluence_extractor.py` | `configs/extractors/confluence-extractor.yaml` |
| `swagger` | `extractors/swagger_extractor.py` | `configs/swagger-extractor.yaml` |
| `scale` | `extractors/scale_extractor.py` | `configs/scale-extractor.yaml` |
| `code` | `extractors/code_extractor.py` | `configs/code-extractor.yaml` |
| `database` | `extractors/database_extractor.py` | `configs/database-extractor.yaml` |

**Step**: [steps/01-extract.md](steps/01-extract.md) — one generic procedure for
every source above.

## The pipeline this feeds

```
source → extractor → UIF   (the file is the deliverable)
                                                    ├─ Stage 1 deterministic triage (free)
                                                    ├─ Stage 2 model mining (only the ambiguous remainder)
                                                    └─ Stage 4 Requirement + AC + TestDesign, at Quarantine
```

## What this build cannot do

**The UIF→Episode step no longer exists.** It ran through
`metis_mcp/uif_intake.py`, which was removed with the v1 engine; `--land` now
refuses with that reason rather than writing nothing and reporting success.
Extraction is unaffected and real.

Say this to the user before they run an extraction expecting the graph to
change. A refusal they were warned about is a limitation; the same refusal
after they have staged a source is a waste of their time.

When the step returns, it will render the UIF to markdown and drop ids,
timestamps and extractor metadata. That is deliberate: Stage 1 triages prose for
behavioural cues, and handing it raw JSON would get every block discarded.

## Non-negotiable rules

1. **A UIF's claimed structure is not trusted.** UIF arrives with
   `specifications.acceptance_criteria` already labelled as acceptance criteria.
   This skill still does **not** create `AcceptanceCriterion` nodes from that
   claim — the text goes through the same mining and guardrail path as any other
   intake, landing at `Quarantine` for human review. Trusting an upstream
   extractor's labelling is the shortcut `atlas_bridge.py` explicitly refuses,
   and this skill refuses it too.
2. **Never land an empty Episode.** A UIF that renders to no prose is refused
   with a reason, not written — an empty Episode looks like successful ingestion
   of nothing.
3. **Never construct UIF paths inline.** Output paths come from `configs/`.
4. **Output is JSON only.** No code samples in extractor output.

## Verification

```bash
cd plugins/metis/skills/metis-intake-processor
python3 -m pytest tests/ -q      # extractor tests: no Neo4j, no model calls
```

Three files: `tests/test_jira_extractor.py`, `tests/test_validators.py`,
`tests/test_hard_format_constraints.py`.

**13 of the 14 pass. `test_empty_source_references` fails, and it is a real gap,
not a flaky test.** `validators.py` checks `uif_version`, `scope`, `metadata` and
`links` and **never looks at `traceability` at all** — so a UIF with no
provenance whatsoever validates clean. The schema requires
`traceability.source_references`, all six extractors emit it, and this skill's
whole claim is that every field is traced to the response it came from. The two
tests also disagree with each other: `test_valid_uif`'s fixture carries no
`traceability` either and expects to pass. Deciding which is right is a semantic
call about this component, not a cleanup, so it is stated here rather than
guessed at.

**This used to name `metis-server/test_intake_processor.py`, which does not
exist** — it tested the UIF→Episode landing that went with the v1 engine, and it
was removed with it. A verification section naming a file nobody can run is worse
than none: it reads as evidence.

## Where this came from

Below the operational content deliberately: it is provenance, and it was costing
a full screen ahead of the instructions on every invocation.

**Ported from Atlas** (`.agents/skills/intake-processor`), then rewired. The
extractors are unchanged real code; what changed is where the output goes. They
were the cleanly-portable part of Atlas's tree — standard library and each
other, no dependency on Atlas's shared runtime (`_shared_loader`,
`config_provider`, `artifact_provider`) — which is why this skill was ported
first.

The first port took Jira alone and said so. The remaining five — Confluence,
Swagger/OpenAPI, Zephyr Scale, code, database — followed because they are the
sources Requirements have to be built from, and reaching into another project's
tree for them was the one real coupling Métis had left.

| | Atlas | Métis |
|---|---|---|
| Output | UIF JSON at `~/.atlas/tmp/uif/<source>/<scope-id>.json` | UIF intended to land as an `Episode` carrying `raw_content` |
| Consumer | The UIF file itself, for review or later ingestion | The graph — **not implemented in this build** |
| Schema | `.agents/skills/shared/schemas/` | `plugins/metis/skills/shared/schemas/` |
| Sources | six extractors | six extractors |
