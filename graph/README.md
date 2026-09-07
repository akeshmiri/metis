# `graph/` — authored facts a person writes, not a derived database

Everything here is **written by a person**. The Neo4j database is built from
authored sources and is disposable: drop the container, run
`metis-server/rebuild_graph.sh`, and you have it back.

That is the whole point of the split. The graph is *derived*, so a pull request
against an authored source is the review — there is no shared database to
reconcile, and no second copy that can disagree.

## What is actually here

| Path | Contents | Read by |
|---|---|---|
| `fixtures.yaml` | Selectors and values the model cannot recover | **Nothing yet** — see below |

That is the complete list, and it is shorter than this directory's design.

**This README used to describe four directories that do not exist** —
`models/`, `intent/`, `criteria/`, `reviews/` — and three CLI verbs that do not
either: `metis payload`, `metis generate`, `metis spec-kit`. None of it was
wrong when it was written as a plan; all of it read as a description of the
tree. Saying so is cheaper than a reader discovering it.

**`fixtures.yaml` has no reader.** The *concept* is real and is documented in
`rendering/contract.py`: a rendered body carries the accepted space
(`<string, length 3..40, required>`) and a literal value appears only where a
fixtures join supplied one, labelled as authored. What does not exist is the
join — there is no `--fixtures` flag on any verb, and nothing opens this file.
The format is here so that the authored half has somewhere to live when the
join is built; today it is a design, not a capability.

## Where the authored sources actually live

`rebuild_graph.sh` builds from the test corpus, not from this directory:

| Path | Contents | Landed by |
|---|---|---|
| `metis-server/demo_project/records-service` | The API surface | `analyse` → two JVM packs |
| `metis-server/demo_project/records-ui` | The React surface | `analyse` → `react-ui` |
| `metis-server/demo_project/records-page` | The plain-DOM surface | `analyse` → `js-ui` |
| `metis-server/demo_project/specs` | Acceptance criteria — the intent side | `demo_data/land_spec_criteria.py` |
| `metis-server/demo_data/models/*.json` | Authored behaviour models | `metis land --source authored` |
| `metis-server/demo_data/models/*.review.json` | Approval decisions | `metis review export` / `apply` |
| `metis-server/demo_data/intent/*.json` | Needs and glossary (§4.1, §4.6a) | `metis intent`, `metis glossary` |
| `docs/academy/*.md` | The academy | `metis lessons` |

**The review convention lives beside those models**, not here. `*.review.json`
is the record of what a human approved and why; it is not local scratch state,
and a model change belongs in the same pull request as the decisions it
invalidates — `review apply` refuses a decision whose model has moved, so the
two halves have to travel together.

## Not here, and deliberately

**Nothing recovered from code.** States and transitions extracted by the Joern
packs have no file: their source is the service's own tree, and re-extraction is
how they are refreshed. A recovered model committed here would be a second copy
that goes stale the moment the code moves.

**No generated automation artefacts.** A generated suite is derived from an
approved model exactly as the database is derived from an authored source —
regenerate it and you have it back. Committing one invites a hand-edit that the
next regeneration silently discards, which is the instruction every emitted file
already carries in its header.

A project's graph MAY be kept as Cypher at `<repo>/.metis/storage/`, written by
`metis storage export`. That is a restore file, not a second source: its
manifest records the commit and the ontology it came from, `metis storage
verify` compares them against the checkout, and a rebuild re-ingests rather than
restoring when they disagree. The rule is **restore when the file matches,
re-ingest when it does not** — RD-9's "re-ingest, never migrate" was about the
v1 → v2 engine cutover (completed at `61814dc`), not about keeping a backup.

## One caveat before relying on shared decision files

`review apply` checks a `fingerprint` and refuses if the model has moved since
the export. That is correct — it stops you approving a model that changed
underneath you — but it means a colleague's exported decisions go stale as soon
as the model is re-extracted. Export, decide and apply within one change.
