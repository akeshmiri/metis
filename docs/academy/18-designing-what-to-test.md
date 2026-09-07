---
topics: practice
---
# 18 · Designing what to test

Coverage tells you whether a behaviour is tested. It does not tell you what
testing that behaviour should *consist of* — which conditions matter, at which
level, with what data, and what nobody has decided yet. That is test design, and
it is a different question asked of the same model.

## The question before generation

`metis-test-generate` renders cases from an approved model. It is very good at
turning a walk through a machine into a test case, and it has no opinion about
whether that walk was the right one to take.

Design is the prior question, and it runs **before approval on purpose**. That is
when it changes a decision: a design that says *nothing here can be asserted*
arrives most usefully while somebody can still change the code.

## Fourteen sections, and the two that matter most

The document has six groups. Most of them are what you would expect — techniques,
data conditions, levels, load, contracts. Two are worth knowing by name.

**Condition completeness** is the denominator. A positive case says what the
system does; it says nothing about what the system must reject, prevent, limit or
leave alone. Counted as coverage for those, it excuses exactly the gaps testing
is for. So every behaviour gets a row for all eight classes — `allowed`,
`prohibited`, `partition`, `boundary`, `state-transition`, `authorization`,
`dependency-failure`, `non-goal` — **including the ones that do not apply**.

That last part is the mechanism. A `boundary` row marked `not-applicable`
*because the guard is a predicate and predicates have no edges* is a decision
somebody can disagree with. A `boundary` row that silently disappeared is not.

**Open questions and assumptions** is the last section and the reason the rest
can be trusted. It lists every input nobody supplied, what its absence means, and
which section it silenced.

## What Métis cannot see, and says so

Seven of the design's inputs are questions rather than facts:

| Asked | Because |
|---|---|
| the runtime architecture | Métis reads code, not deployments |
| the design specification | it recovers what the code does, not what it was meant to do |
| the environments | it does not know what you can actually run |
| test data constraints | it cannot see who provisions data, or what may not appear in it |
| NFR targets | nobody has told it what "too slow" is |
| security obligations | whether being wrong is a compliance event is a business fact |
| entry and exit criteria | the threshold is yours |

**The architecture one is the interesting refusal.** Métis could write an
architecture section by summarising what it recovered from the code. That summary
would be the implementation described back to you as though it were the plan —
and a test design built on it would be testing the code against itself.

So a design says `incomplete` until those are answered, with the word **above the
first section**. An unfinished design read as a finished one is the failure that
ordering prevents.

## Three ways a section can be short

They look similar on the page and mean different things:

- **rows, nothing missing** — this is the section.
- **rows *and* missing inputs** — marked `Partial`. This is the dangerous one: it
  looks complete and is not.
- **no rows** — either `nobody could state it` with the inputs it is waiting on,
  or `it was stated and there is nothing in it`.

An empty section announces itself. A partial one has to be told to.

## The document is yours to edit

`Decision`, `Owner` and `Notes` are your columns. Regeneration rewrites
everything else and preserves those — and preserves any row you add, because a
condition Métis cannot see is exactly what an editable document is for.

Two rules make that work:

- **Never renumber the ID column.** It is derived from what the row is *about*,
  so your decision stays attached to its condition when the model changes. An id
  that counted rows off would move every decision one row down the moment a
  behaviour was added.
- **Run `metis design --verify` after editing.** Python computes the document,
  you write into it, Python checks it is still the shape the merge can read. It
  checks structure and vocabularies, never judgement — a checker with an opinion
  about whether your decision is *right* is one people route around.

## Nothing here decides anything

Métis proposes every row and decides none of them. The workflow halts until a
named person accepts, and a design whose sections are all full still needs
accepting — *Métis derived this* is a statement about Métis, not a decision about
testing.

Read [what Métis does not do](01-what-metis-does-not-do.md) next if that
distinction is not yet second nature, and
[where a thing belongs](10-where-a-thing-belongs.md) if you are about to add a
section.
