---
name: metis-intake-processor
description: Capture a stated requirement from a tracker or wiki — a Jira issue, a Zephyr Scale test case, or a Confluence page — as a Unified Intake Format document and land it in the graph. Every field traces to the response it came from; nothing is inferred. Use when somebody wants what a source SAYS the system should do brought into Métis. For code, OpenAPI or a database, see "Sources that do not go through UIF" below.
---

# Métis intake-processor

Bring one real source into the graph as evidence of what somebody *stated*. Two
commands, both `metis`:

```bash
metis intake fetch --system jira --key ABC-123 --base-url https://x.atlassian.net \
                   --token-env METIS_TRACKER_TOKEN --out ./uif
metis intake land ./uif/ABC-123.uif.json
```

`fetch` prints a conformance verdict per document before you land anything, so a
document that will be refused says so at the door rather than after a run.

## Sources this skill covers

| `--system` | Source | Anchor landed |
|---|---|---|
| `jira` | a named Jira issue — summary, description, type, status, labels | `JiraItem` |
| `scale` | a named Zephyr Scale test case — name, objective, status, labels | `ZephyrItem` |
| `confluence` | a named Confluence page — title, body, status, labels | `ConfluenceItem` |

`scale` is Zephyr Scale. The value is `scale` and not `zephyr` because that is
what `intake_landing.ANCHORS` keys `ZephyrItem` on; renaming it would detach
every item from its anchor.

**Named items only.** These read the keys they are given. They do not crawl a
project, run JQL, walk a Confluence space, or follow links — a crawl is a
different capability and would need arguing for.

**Read-only by construction.** `tracker.ENDPOINTS` is a closed allowlist of GET
paths and `assert_read_only` checks every URL before it is issued, so a reader
that grew a write fails in the test suite rather than in front of somebody's
tracker (X-7a).

**The token is named, never passed.** `--token-env` takes the NAME of an
environment variable. A secret on a command line is in the shell history, the
process list, and every CI log that echoes its commands (PLT-005).

## Sources that do not go through UIF

Code, OpenAPI and databases are read directly into the extraction contract by
their own readers, which recover far more than a UIF can carry. Do not reach for
this skill for them:

| Source | Command | Reader |
|---|---|---|
| source code | `metis analyse` | the Joern query packs |
| OpenAPI / Swagger | `metis spec` | `code_analysis.openapi` |
| a database catalogue | `metis data` | `code_analysis.db_catalogue` |

`metis guide` renders the current capability map, and `connectors/intakes.json`
is the declaration it is generated from — including what each intake **cannot**
do.

## Non-negotiable rules

1. **A document's claimed acceptance criteria are never trusted.** A UIF may
   arrive with `specifications.acceptance_criteria` already labelled as such,
   and no `AcceptanceCriterion` is created from it. A criterion asserted by the
   document that raised the requirement is not independent evidence of it
   (S-13). The text goes through mining and review like any other intake, and
   `intake land` reports how many claims it declined.
2. **Everything lands at `Quarantine`.** No intake writes `Approved` (S-4).
3. **Only EARS-conformant text becomes a `Requirement`.** Free prose — most Jira
   titles — lands as a `Finding` pointing at `knowledge-capture` instead. That
   is correct behaviour and it is also the most surprising thing this intake
   does, which is why `fetch` says it before you land.
4. **Never state a value the source did not.** No invented priority, no guessed
   URL, no reconstructed formatting.

## Verification

```bash
cd metis-server
uv run python -m pytest test_tracker.py test_intake_landing.py test_intakes.py -q
```

No Neo4j, no network, no model calls: the reader's fixture path is what the
suite exercises, and the live read goes through a transport the caller opens.

## Where this came from

Below the operational content deliberately: it is provenance, and it was costing
a full screen ahead of the instructions on every invocation.

This skill was ported from Atlas (`.agents/skills/intake-processor`) and carried
six extractor modules with it. **They have been retired.** Five were superseded
by server-side readers that do strictly more — `code_analysis.tracker`,
`code_analysis.openapi`, `code_analysis.db_catalogue` and the Joern packs — and
three of those six could not run at all, raising `NotImplementedError` for the
live path. The sixth, Confluence, was ported into `code_analysis.tracker`, where
it dropped three defects rather than carrying them across:

| Defect in the ported extractor | What it did |
|---|---|
| parsed an "Acceptance Criteria" heading into `specifications` | manufactured exactly the self-asserted criterion S-13 refuses |
| hardcoded `"priority": "high"` | stated a value no source said |
| hardcoded an example.com page URL | gave every page provenance pointing at a domain nobody owns |

It also took only the first `<p>` as the description, losing every requirement
stated below the opening paragraph. The body is now carried whole.

What remains of Atlas here is attribution, which is required, and no live wire,
which is forbidden — the distinction `test_independence.py` draws.
