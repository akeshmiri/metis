---
system: metis
---
# The Métis academy

**Authored, not generated.** That is the difference between this directory and
`docs/guide/`: the guide is produced from `labels.py`, `intakes.json`,
`stages.py` and the CLI parser, and a diff in CI fails the build. Nothing here
is checkable that way, because it is reasoning rather than reference — so it is
kept separate and labelled, instead of being mixed in where a reader could not
tell which sentences the engine stands behind.

## Two tracks

The lessons split by **who you are**, not by difficulty. Read the track that
matches what you do; the other one is there when you want it.

The file numbers are stable identifiers, not a single reading order — a lesson's
number is its natural key, and renumbering would detach every lesson already
landed in the graph from its own history. Each track below is in its own order.

---

### Operator track — using Métis

*For a business analyst, product owner, QA lead or reviewer. Assumes no
programming.* Start at the top.

1. [What Métis is for](12-what-metis-is-for.md) — the problem, and the finding
   that justifies the whole thing
2. [The words we use](13-the-words-we-use.md) — a plain-language glossary, because
   several ordinary words mean something narrower here
3. [Your first week](14-your-first-week.md) — four roles, four different first
   hours
4. [One requirement, end to end](15-one-requirement-end-to-end.md) — a real ticket
   followed the whole way, with the real output
5. [The screens you will use](16-the-screens-you-will-use.md) — the two that
   have a page, the four that do not, and the evidence each one requires
6. [When Métis refuses](17-when-metis-refuses.md) — what each refusal means and
   what to do next
7. [Before a claim becomes a node](19-before-a-claim-becomes-a-node.md) — the four
   readings a ticket gets before anything is imported, and why `ready` is narrower
   than it sounds

---

### Concepts track — how it thinks, and why

*For somebody extending Métis or deciding whether to trust it. Assumes you read
code.* The first is the one that saves the most time.

1. [What Métis does not do](01-what-metis-does-not-do.md)
2. [The shape of the model](02-the-shape-of-the-model.md)
3. [Facts, evidence, and why nothing is approved](03-facts-and-evidence.md)
4. [Joins that cannot be made yet](04-deferred-joins.md)
5. [The two gates, and why there are only two](05-the-two-gates.md)
6. [From a repository to test cases](06-from-a-repository-to-test-cases.md)
7. [Time: what was true, and when](07-time-what-was-true-and-when.md)
8. [Finding things, and which surface to ask](08-finding-things.md)

### Contributor track — adding to Métis

*For somebody writing a tool, a skill or an agent here.*

9. [Generating code from a flow](09-generating-code-from-a-flow.md)
10. [Where a thing belongs](10-where-a-thing-belongs.md)
11. [Which skill, and why that one](11-which-skill-and-why.md)
12. [Designing what to test](18-designing-what-to-test.md) — the question before
    generation, the eight condition classes, and the seven things Métis has to ask

## They land in the graph, beside the product facts

These lessons are not only files. `Lesson` is a real label with a writer
(`model_sources/lessons.py`) and a CLI verb (`metis lessons`), and stage 4b of
`rebuild_graph.sh` lands them at `Quarantine` like every other source. A fresh
database gets the academy and nothing else, deliberately: filling a new graph
with the demo corpus means a first `ask` is answered out of Records and
Contracts fixtures nobody asked about.

**The same graph as the product facts, on purpose.** The intent is that `ask`
answers a question about Métis the way it answers one about a product, and Neo4j
cannot join across databases in one session — so a separate academy database
would put these lessons somewhere `search_knowledge` could never see them beside
a criterion. Separation is by label and by episode, not by database. A question
naming this system rather than a product is answered from the academy, with the
topics it belongs to and what to read next.

**Lessons are linked, not isolated.** `Topic` is a shared node many documents
point at (`Lesson-[:BELONGS_TO]->Topic`), so *what else covers this* is a
traversal rather than a second search. A topic is read from the document's own
frontmatter and **never inferred** — a title is not a topic.

`retrieval-bench --land` turns a ranking miss into an advisory `Finding` about
the node that should have won, so a lesson that reads badly through `ask`
becomes a finding about the tools rather than a matter of opinion.

The argument that was made for the label before it was added — including the
case against, and the condition under which it should have been refused — is in
[PROPOSAL-landing-the-academy.md](PROPOSAL-landing-the-academy.md), kept as the
record of a D-2 decision rather than as a live proposal.

## The D-2 proposals, and what each one decided

A label is a reviewed change (D-2), so each argument is written down with its
case against and the condition that would reverse it. **The refusals are the
useful half**: they say what was considered and why it did not land, which is the
part that otherwise gets re-litigated from scratch every few months.

| Proposal | Decision |
|---|---|
| [PROPOSAL-landing-the-academy.md](PROPOSAL-landing-the-academy.md) | **Accepted** — `Lesson` is a real label with a writer and a reader |
| [PROPOSAL-release-baseline.md](PROPOSAL-release-baseline.md) | **Deferred** — the shape is right, the timing is not; a cheaper `as_of` argument was built instead |
| [PROPOSAL-requirement-hierarchy.md](PROPOSAL-requirement-hierarchy.md) | **Refused** — hierarchy labels with no reader |
| [PROPOSAL-risk-in-the-graph.md](PROPOSAL-risk-in-the-graph.md) | **Refused for now** — the risk register stays a file; `Risk` has neither a writer nor a reader yet |
| [PROPOSAL-test-design-in-the-graph.md](PROPOSAL-test-design-in-the-graph.md) | **Refused for now** — `TestDesign`'s staged-out trigger ("a concrete need appears") was met and answered a different way: a design is a document under active revision, and seven of its defining fields are unanswered |
