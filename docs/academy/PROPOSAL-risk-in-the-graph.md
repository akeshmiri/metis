---
topics: concepts
---
# Proposal: a `Risk` label, under D-2

**Status: REFUSED for now, 2026-09-04.** The recommendation reached at the end
is that the risk register stays a file, and that a specific, checkable condition
would change that. This is written down rather than left implicit so the
question does not get re-litigated from scratch each time somebody notices the
register is not in the graph.

D-2 makes adding a label a reviewed change rather than an edit. This is the
argument, including the case against and the condition under which it should
still be refused.

## What exists today

`metis_mcp/risk/` holds the arithmetic (`exposure`), the taxonomy (`rbs`), the
register's shape and coherence rules (`register`), and the one piece wired to
the model (`candidates`). Six MCP tools expose them. The `risk-manager` skill
family drives the lifecycle. **None of it touches the graph except
`risk_candidates`, which only reads.**

The register itself is a file — JSON, validated by `risk_register_check`, living
wherever the team keeps it.

## The case for a `Risk` node

It is real, and it is one question:

> *Which recovered behaviour does this risk touch?*

With `Risk` as a node and a `Risk-[:THREATENS]->Transition` edge, that is a
traversal. Without it, it is a manual cross-reference somebody maintains by hand
and stops maintaining within a month.

Three things follow from that one question:

- **Impact analysis would include risk.** `impact` already reports which
  transitions a diff touches; it could report which risks those transitions
  carry. Today a risk register and a change review are two documents nobody
  joins.
- **Closure could be checked.** A model-derived risk is *behaviour nothing
  validates*. It closes when something validates it. In the graph that is a
  query; on a file it is a person re-running `risk_candidates` and diffing by
  eye.
- **Coverage-weighted-by-risk becomes possible.** "We are 80% covered" and "the
  20% uncovered carries every High risk" are very different sentences, and only
  the second is actionable.

## The case against, which is D-1's bar

**A label needs a named writer and a named reader.** Today `Risk` has neither.

- **No writer.** Nothing lands a risk. `risk_candidates` *derives* candidates and
  returns them; it does not write them anywhere, and it should not — landing
  requires `METIS_MCP_WRITE`, an identity and an evidence fingerprint, and a
  candidate nobody has rated is not a fact about the system. The authored half of
  a register is typed by a person into a file, and no intake path exists for it.
- **No reader.** No query, no report and no tool would traverse it on the day it
  landed. Every use above is a *future* use.

Two further objections that are specific to this system:

**The provenance rule would be harder to keep, not easier.** The whole point of
`derived_from` is that a model-derived risk and an authored one are different
claims. In a file they sit in one column and `risk_register_check` reports the
split on every summary. In the graph they would be two provenances on one label,
and every query that forgot to filter would merge them silently — which is the
exact failure mode `label_expression` exists to prevent for `Transition`, and it
took three separate incidents to learn there.

**A risk's identity rule is genuinely unclear.** `identity` splits the graph into
claims (a new wording is a new node) and elements (an edit modifies the node).
A risk is neither cleanly. Is a re-rated risk the same risk? Probably yes — the
rating is an attribute. Is a re-worded risk the same risk? Probably yes too,
which makes it an *element* — but its probability is a judgement with a validity
window, which is what makes the four `VALIDITY_LABELS` claims. Landing a label
before that is settled would bake in whichever answer the first writer happened
to implement.

## What a file costs, honestly

Not nothing. The join is manual, closure is not checkable, and nothing stops two
teams keeping two registers. Those are real, and they are the price.

But a file is reviewable in a pull request, diffable, and needs no database to
read — which is the same reasoning that keeps the engine database-free and the
authored half of the knowledge graph in `demo_data/`. The register is authored
content. Authored content here lives in files.

## Recommendation

**Refuse for now.** Keep the register in a file. Ship the arithmetic, the
coherence rules and the skills, which are the parts that are useful immediately
and useful without a graph at all.

## The condition that would bring it back

Both halves, not either:

> *A risk register is being maintained against a real project for long enough
> that its rows outlive a single release* **and** *somebody has asked, twice, for
> the join between a risk and the behaviour it threatens.*

The first half establishes there is something worth landing. The second
establishes a reader — which is the half D-1 actually requires, and the half
this proposal cannot currently satisfy.

If that condition fires, the design work still to do is: the identity rule
above, an intake path for the authored half, and a decision about whether
`derived_from` should be a distinct label rather than a property. None of those are
hard; all of them are premature.

**If the condition has not fired within two releases, refuse this permanently
and delete the file.** A proposal that stays pending indefinitely is a decision
nobody made.
