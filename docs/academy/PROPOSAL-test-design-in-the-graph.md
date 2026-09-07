---
topics: concepts
---
# Proposal: the `TestDesign` label, under D-2

**Status: REFUSED for now, 2026-09-07.** The recommendation reached at the end
is that a test design stays a Markdown document, and that a specific, checkable
condition would change that. This is written down rather than left implicit so
the question does not get re-litigated from scratch each time somebody notices
that the design is not in the graph.

**This one is different from the risk proposal in one way that matters.**
`TestDesign` is not a label nobody thought of: it is already in
`ontology.labels.STAGED_OUT`, and the trigger recorded beside it is *"a concrete
need appears"*. That need has now appeared — somebody asked for test design as a
discipline and it was built. So this document is the answer to a question the
ontology explicitly deferred, and the answer is *not yet, and here is what would
change it*.

## What exists today

`metis_mcp/design/` holds the gather-or-ask ledger (`inputs`), the deterministic
section registry (`sections`), the row builders (`builders`), the merge-preserving
renderer (`document`) and the areas map (`areas`). Three MCP tools expose them,
`metis design` writes the document, and the `test-design` workflow runs the
lifecycle with its own acceptance gate.

**None of it touches the graph except `design_report`, which only reads.** The
design itself is a file — Markdown, verified by `metis design --verify`, living
wherever the team keeps it.

## The case for a `TestDesign` node

It is real, and it is more than one question.

**Traceability would become a traversal.** Today a design row points at a
transition by id, in a text cell. As a node it would be an edge, and "which
design decisions cover this behaviour" would be a query rather than a grep.

**A decision would be reviewable through the same gate as everything else.**
Every other claim in Métis lands at `Quarantine` and a person approves it at G1.
A design decision is approved by a literal on the CLI and recorded in a Markdown
cell, which is a second review mechanism for the same kind of act.

**Supersession would work.** When a transition's guard changes, the design rows
about it are stale and nothing says so. `identity.carry_human_facts` already
solves exactly this for approvals; a design in the graph would inherit it.

**"What did we decide to test, in March?" would be answerable.** The document is
in git, so the answer exists — but it is a diff, not a query, and it cannot be
joined against what the model said at the time.

## The case against, which is the one that wins today

**The design's most valuable column is the one nobody has filled in.** Seven of
its inputs are `asked`: the architecture, the design specification, the
environments, the data constraints, the NFR targets, the security obligations,
the entry and exit criteria. A design is `incomplete` until a person answers
them, and on a real service most stay unanswered for weeks. **A node whose
defining fields are empty is not a fact; it is a form.** Landing one puts a
`Quarantine` node in the graph that no reviewer can act on, which is what D-1
exists to prevent and what `analysis/gaps.py` refuses at the intake door for
precisely the same reason.

**A design is edited, and the graph is not the place for a document under
active revision.** The whole `document_table` machinery exists because a design
is worked on: a decision changes, an owner changes, an analyst adds a row Métis
cannot see. That is a text file's shape. Reproducing it in the graph means
either landing a new revision per keystroke or having a write path that mutates
approved nodes — and `identity` is explicit that a claim which changes is a new
node while an element which changes is the same one modified. A design row is
neither cleanly.

**The rows are derived, and re-derivable.** Every computed cell comes from the
model, the guards, the contract and the risk profile. Persisting them duplicates
facts the graph already holds, and a duplicate is a second place to be wrong —
this codebase's most common defect, named as such in `ontology/labels.py`'s own
comments. What is *not* re-derivable is the human half, and the human half is
five columns.

**Nothing would read it yet.** `risk/candidates.py` earns `risk_candidates`
because something consumes it. No tool, workflow or report would query a
`TestDesign` node today; generation reads an approved *model* (D-10), not a
design, and it must keep doing so — a design that could feed generation would
let a document a person edited become the source of what gets tested, which is
§4.1's circularity by a longer route.

## The condition that would reverse this

Land `TestDesign` when **any one** of these is true, and not before:

1. **A design's human columns become the input to something other than a human.**
   The moment a tool needs to read `decision = accept` — to filter a batch, to
   drive a report, to gate a release — the join is real and a text cell is the
   wrong home for it.
2. **Two designs need comparing in the graph.** "What changed in the design
   between these two releases, and which behaviour moved" is a query the file
   cannot answer, and it is the same argument that would bring back `Run`.
3. **A design decision has to be revoked automatically when its behaviour
   changes.** That is `carry_human_facts` (I-17/I-18) and it needs the decision
   to be on a node with a validity window. Today the design is regenerated and a
   stale decision survives the merge, which is a real limitation and is recorded
   here rather than hidden.
4. **The asked half is routinely answered.** If teams do answer the seven, the
   "a node whose defining fields are empty" objection goes away, and most of the
   case against goes with it.

Of the four, **the third is the strongest and the most likely to arrive first.**
It is also the one with a partial fix available now: `metis design --verify`
reports a document that has drifted from the shape the merge expects, but it
cannot report a decision that has drifted from the behaviour it was about. That
gap is real and it is the honest reason to expect this proposal to be revisited.

## What this proposal is not

It is not an argument that the design does not matter. It is an argument that a
document a person edits, in git, beside the code, is where a design under active
revision belongs — and that the moment a machine needs to read one of its human
columns, that stops being true.
