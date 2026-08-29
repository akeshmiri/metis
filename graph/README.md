# `graph/` — the authored half of the knowledge graph

Everything here is **written by a person** and is the reviewable record of what
the graph should contain. The database is built from it and is disposable: drop
the container, run `metis-server/rebuild_graph.sh`, and you have it back.

That is the whole point of the split. The graph is *derived*, so a pull request
against this directory is the review — there is no shared database to reconcile,
and no second copy that can disagree with this one.

## What goes where

| Directory | Contents | Landed by |
|---|---|---|
| `models/` | Authored behaviour models (`*.json`) | `metis land --source authored` |
| `intent/` | Needs and glossary (§4.1, §4.6a) | `metis intent`, `metis glossary` |
| `criteria/` | Acceptance criteria, Spec Kit layout | `metis intake`, `spec-kit` |
| `reviews/` | Approval decisions (`*.review.json`) | `metis review export` / `apply` |
| `fixtures.yaml` | Selectors and values for automation | `metis payload --fixtures` |


**Not here: generated automation artefacts.** `metis generate --out
tmp/testcases/<model>` writes them, and `tmp/` is git-ignored. A generated suite
is derived from an approved model exactly as the database is derived from this
directory — regenerate it and you have it back. Committing one invites a
hand-edit that the next regeneration silently discards, which is the instruction
every emitted file already carries in its header.

**Not here: anything recovered from code.** States and transitions extracted by
the Joern packs have no file — their source is the service's own source tree,
and re-extraction is how they are refreshed (RD-9: re-ingest, never migrate).
Putting a recovered model here would create a second copy that goes stale the
moment the code moves.

**Not here either: `metis-server/demo_project/` and `demo_data/`.** Those are
test fixtures, asserted against line by line by `test_extraction.py` — the demo
corpus is a *condition*, not content, and it stays beside the tests that read it.

### Fixtures are per model in practice

`--fixtures` takes a path, so `graph/fixtures/<model>.yaml` works today with no
format change — and it is usually what you want. One file across every model
means the "matched nothing" report fires constantly: a selector for the records
UI legitimately matches nothing in the login API model, and a warning that is
always noisy trains a reader to ignore it.

## The review convention

**Decisions are committed.** `reviews/*.review.json` is the record of what a
human approved and why; it is not local scratch state. A model change and the
decisions it invalidates belong in the **same pull request**, so a reviewer sees
both halves at once.

One caveat worth knowing before you rely on shared decision files: `review apply`
checks a `fingerprint` and refuses if the model has moved since the export. That
is correct — it stops you approving a model that changed underneath you — but it
means a colleague's exported decisions go stale as soon as the model is
re-extracted. Export, decide and apply within one change.
