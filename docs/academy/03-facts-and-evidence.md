# 3 · Facts, evidence, and why nothing is approved

## Everything lands at Quarantine

**S-4.** No source writes `Approved`. Not the code intake, not OpenAPI, not an
authored file, not a UIF from Jira. Intake is not agreement.

Generation reads only `Approved` (**D-10**), so the gap between those two rules
is exactly one person deciding. That is the point of the system, not an
inconvenience in it.

## A fact serves the model or it is not landed

**X-6d.** Facts are classified surface, supporting or internal, and what does
not serve the model does not get carried. Two consequences worth knowing:

- **A field is a property of its type, not a node.** `Field` is staged out. A
  scalar is `f_<name>_*` on its `Class`; a complex one is a
  `Class-[:OF_TYPE]->Class` edge. `ontology.facts` holds the encoder and decoder
  together so the flat form and the nested document cannot drift apart.
- **Noise is dropped on provable inertness, never on visibility or
  reachability** (**X-5a**). Both obvious axes were tried and measured wrong.
  `private` was 59 of 389 methods on a real service and two were reachable from
  a handler — one guarding an endpoint and raising the cause of a 400 — so
  filtering on it deletes a rejection path. Call-reachability drops a service
  implementation's 31 business methods, because the frontend does not resolve
  interface dispatch. Fields are never filtered at all: they are private by
  convention and carry `@Schema`, required-ness and validation bounds.

  What may go is *jointly* inert — matching field, short body, no control
  structure, no call but operators — so a getter that branches survives. The
  count dropped is always reported.

## Evidence is anchored

A recovered fact carries `file:line@commit` (**T-9a**). A guard a reviewer
cannot trace back to a line is a claim they have to take on trust, and the whole
review gate assumes they do not have to.

This is why a `Check` node is preferred over splitting a guard string. Both
describe the same branch, but a `Check` carries the line it came from **and its
position in the evaluation sequence** — and the order is itself a data
requirement, because checks short-circuit. A fixture aimed at the third
condition never reaches it unless the first two already hold, and splitting
`a AND b AND c` on `AND` cannot recover that.

## Two claims that look alike and are not

- `Transition -[:CONSTRAINED_BY]-> Check` — a condition was **found** near this
  transition.
- `DeclaredOutcome -[:GUARDED_BY]-> Check` — this condition **selected** this
  outcome over its siblings.

Landing refuses to conflate them and so does every reader. A reviewer approves
the two differently.

## Derived, never authored

**T-9b.** Anything Métis generates says where it came from. **T-9c**: it states
conditions, never values. **T-9d**: what could not be recovered is *marked*, not
guessed — which is why a Page Object method with no recovered selector raises
`NotImplementedError` naming the reason instead of clicking a plausible CSS
path.
