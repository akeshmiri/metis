---
name: metis-intake-processor
description: Capture a stated requirement from a tracker or wiki — a Jira issue, a Zephyr Scale test case, or a Confluence page — as a Unified Intake Format document and land it in the graph. Every field traces to the response it came from; nothing is inferred. Use when somebody wants what a source SAYS the system should do brought into Métis. For code, OpenAPI or a database, see "Sources that do not go through UIF" below.
workflow: intake
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - describe_policy
  - get_requirement
  - get_spec
  - search_knowledge
  - model_sources
  - list_entities
  - get_entity
  - check_ears
  - validate_intake
knowledge-from:
  - model_sources.intake_landing
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

**Where the keys come from, since nothing else says.** "Named items only" is a
constraint, not an answer: somebody still has to produce the names. Derive
candidates from the repository already in front of you —

```
git log --pretty=%s%n%b <range> | grep -oE '[A-Z]{2,6}-[0-9]+' | sort -u
```

— and from branch names. This reads the local checkout and never the tracker, so
it stays inside X-7a, and it produces exactly the shape `--key` takes.

Three rules on the result.

**An empty result is two different answers.** A command that found no keys and a
command that failed both print nothing, and a shell pipeline erases the
difference. Check the exit status: no keys is a finding, a failed `git` is
`unknown` and blocks — the rule in
`../shared/knowledge/duplicate-guard.md`, which exists because reading a failed
lookup as "nothing there" is how the wrong thing gets created.

**Confirm the list before fetching it**, showing the count; a range wider than
intended turns a targeted intake into the crawl the paragraph above rules out,
and the default answer is No.

**Lock the primary subject before you extract**: the ticket the work is actually
about, with everything else recorded as related rather than merged into it. A key
appearing in a commit message is evidence the commit touched it, not evidence it
is in scope — that is the scope lock in
`../shared/knowledge/anti-hallucination-protocol.md`, applied to intake.

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
| a database catalogue | *not reachable* | `code_analysis.db_catalogue` |

**The third row is not a command, and saying so is the point.**
`code_analysis.db_catalogue` is built and tested, and nothing invokes it: it has
no CLI verb, no workflow stage, and no entry in `connectors/intakes.json`. This
row used to name a `data` verb, which the CLI has never registered — long enough
that a reader could have tried it. A reader that nothing calls is a capability
nobody has, and naming a plausible command for it is worse than admitting the gap.

`metis guide` renders the current capability map, and `connectors/intakes.json`
is the declaration it is generated from — including what each intake **cannot**
do.

The reasoning behind the engine this skill drives is in
`knowledge/index.md` — generated from the module docstrings that are its
source of truth, so it cannot drift from the code it explains. Read a
fragment when you need the why, not before.

## The document's shape

A UIF is validated against `../shared/schemas/unified-intake-format.schema.json`
— 830 lines, and the machine-readable half of everything below. The prose here
says what must not be trusted; the schema says what a document must contain for
the question to arise at all.

## The standard behind this, and what it does not certify

**ISO/IEC/IEEE 29148** — `../shared/references/iso-29148-requirements.md`. It is
why free prose lands as a `Finding` rather than a `Requirement`: `ears_pattern`
has no empty form, and a sentence with no trigger and no response cannot become
one without inventing the missing half (S-13).

**A coverage map, never a compliance claim.** `metis_mcp/standards.py` is the
registry — which standard governs which skill, what Métis computes against it,
and what it refuses to claim. Whether the result satisfies an obligation is a
judgement about the obligation, not a property Métis can compute.

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
