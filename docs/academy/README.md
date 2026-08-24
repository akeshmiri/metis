# The Métis academy

**Authored, not generated.** That is the difference between this directory and
`docs/guide/`: the guide is produced from `labels.py`, `intakes.json`,
`stages.py` and the CLI parser, and a diff in CI fails the build. Nothing here
is checkable that way, because it is reasoning rather than reference — so it is
kept separate and labelled, instead of being mixed in where a reader could not
tell which sentences the engine stands behind.

Read them in order. The first is the one that saves the most time.

1. [What Métis does not do](01-what-metis-does-not-do.md)
2. [The shape of the model](02-the-shape-of-the-model.md)
3. [Facts, evidence, and why nothing is approved](03-facts-and-evidence.md)
4. [Joins that cannot be made yet](04-deferred-joins.md)

## Not yet landed in the graph

The intended end state is that these lessons land through the normal intake
path, so `ask`, `journey_walkthrough` and `call_recipe` answer questions about
Métis exactly as they answer questions about a product — and any lesson that
reads badly through `ask` is a finding about the tools rather than about the
lesson.

**That is not built.** The `knowledge` intake reads JSON and lands
`BusinessArea`, `BusinessEntity` and `Intent`; an academy lesson is none of
those, and forcing one into a `BusinessEntity` would put a document about Métis
into the space reserved for nouns of the system under test. Landing them needs a
label that does not exist, which is an ontology change under D-2 — reviewed, not
edited — and D-1 requires a named writer *and* a named reader before a label is
worth adding. Neither has been argued for yet.

So today these are files. Saying so is cheaper than a reader discovering it.
