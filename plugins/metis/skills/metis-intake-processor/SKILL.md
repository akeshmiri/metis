---
name: metis-intake-processor
description: Extract evidence from Jira, Confluence, Swagger/OpenAPI, Zephyr Scale, source code or a database, normalize it to one Unified Intake Format (UIF) document, and land it in the Métis graph as an Episode so its Requirements and AcceptanceCriteria can be mined. Use when a user wants to get a real source into Métis — not for mining an Episode that already exists (call metis_mine_requirements directly for that).
---

# Métis intake-processor

**Ported from Atlas** (`.agents/skills/intake-processor`), then rewired: the
extractors are unchanged real code, but the output no longer stops at a UIF file
on disk — it lands in the Métis graph.

The extractors were the cleanly-portable part of Atlas's tree: they import only
the standard library and each other, with no dependency on Atlas's shared
runtime (`_shared_loader`, `config_provider`, `artifact_provider`). That is why
this skill was ported first.

## What changed from the Atlas original

| | Atlas | Métis |
|---|---|---|
| Output | UIF JSON written to `~/.atlas/tmp/uif/<source>/<scope-id>.json` | UIF landed as an `Episode` carrying `raw_content` |
| Consumer | Downstream Atlas skills read the file | `metis_mine_requirements` mines the Episode |
| Schema | `.agents/skills/shared/schemas/` | `plugins/metis/skills/shared/schemas/` |

Writing a UIF file is still supported and useful for inspection, but it is no
longer the end of the pipeline.

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
source → extractor → UIF → Episode(raw_content) → metis_mine_requirements
                                                    ├─ Stage 1 deterministic triage (free)
                                                    ├─ Stage 2 model mining (only the ambiguous remainder)
                                                    └─ Stage 4 Requirement + AC + TestDesign, at Quarantine
```

`metis_mcp/uif_intake.py` performs the UIF→Episode step. It renders the UIF's
*prose* — acceptance criteria, business rules, flows, facts, error scenarios — as
markdown, and drops ids, timestamps and extractor metadata. That is deliberate:
Stage 1 triages prose for behavioural cues, and handing it raw JSON would get
every block discarded.

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
cd metis-server
.venv/bin/python3.13 test_uif_intake.py      # 10 tests, no Neo4j, no model calls
```

The load-bearing test is `test_rendered_content_is_minable_by_stage_1`: it runs
the real Stage 1 segmenter over the real rendered output, so "the extractor feeds
the miner" is verified rather than assumed.
