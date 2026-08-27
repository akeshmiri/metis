---
topics: concepts
---
# 2 · The shape of the model

One model is one `<journey>-<surface>` state machine (**M-1**). `mfa-api` is a
model; `mfa` is the journey and `api` the surface. Passing the model id where a
journey is wanted used to return an empty model reported as a success — it now
refuses and tells you which is which.

## States and transitions

A `State` is a situation the system can be in. A `Transition` is one
interaction: trigger, guard, source, target.

`trigger` and `guard` are **properties, never separate entities** (**M-11**).
A guard is preserved verbatim as recovered and is a *test data requirement*, not
a solved value (**M-8**, **M-9**): the model states what must be true, and
deciding what to actually send is a person's job or a factory's.

An outcome status is held on the transition rather than read out of the target
state's name, because the two are different things. `201` is what the caller
receives; *the resource now exists* is the situation the system is left in.
Conflating them forces every outcome to be its own state and turns the machine
into a star.

## The trap: a specialisation replaces its parent

A classified transition is written `:ApiCall` or `:UiAction` **instead of**
`:Transition`. Not in addition to it.

So `MATCH (t:Transition)` matches **nothing** on a classified estate. Use
`label_expression("Transition")` in queries and
`landing.transition_label_for(surface)` when planning an edge into one.

This is not hypothetical. A `VALIDATES` edge planned against `:Transition`
passed the ontology check — `is_allowed` walks the specialisation chain — and
then merged nothing, because the node carries `:ApiCall`. `land` reported it as
`unmatched`; it did not fail. Both stages said "landed", the counts looked
plausible, and the chain was broken.

The same applies to `Query` (`Postgres`, `Oracle`, `MySql`, `JpaQuery`),
`DbObject` (`Table`, `View`, `Function`), `Component` and `UiElement`.

## Ids are namespaced

`{model_id}::{element_id}` — `landing.namespaced_id`. **The bare id matches no
node.** This is the single most common way a query here returns nothing and
reports success.

## The ontology is closed

64 labels, and `metis_mcp/ontology/labels.py` is the single source: `LABELS`,
`ALLOWED_RELATIONSHIPS`, and `STAGED_OUT` — the deliberately-excluded labels,
each recorded with the trigger that would bring it back. An absence with a
reason is a decision; an absence without one is an oversight.

The Cypher schema is **generated** from `labels.py`, so those two cannot drift.
Adding a label or a relationship is a reviewed change under **D-2**, and **D-1**
sets the bar: a label needs a named writer *and* a named reader. A label nothing
writes is a promise; a label nothing reads is a cost.

Hand-written Cypher is the place D-2 cannot generate, so a test scans every
Cypher string in the tree and fails on a label the ontology does not have.
That check exists because staging out `Field` left
`(t)-[:REQUIRES]->(f:Field)` in a query: still valid Cypher, matching nothing,
returning an empty list, failing nothing.
