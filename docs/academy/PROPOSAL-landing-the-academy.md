# Proposal: a `Lesson` label, under D-2

**Status: argued, not decided.** D-2 makes adding a label a reviewed change
rather than an edit, so this is the argument, written down so it can be refused
on its merits. Nothing has been added.

## What is being asked for

One label, `Lesson`, so that `docs/academy/` lands through the normal intake path
and `ask` answers questions about Métis exactly as it answers questions about a
product under test.

## Why the existing labels do not fit

The `knowledge` intake lands `BusinessArea`, `BusinessEntity` and `Intent`. Each
of those is a noun **of the system under test**. A lesson is a document *about
Métis*, and forcing one into `BusinessEntity` would put "how the two gates work"
into the space reserved for "what a Customer is" — two different kinds of thing
under one label, which is the ambiguity the closed ontology exists to prevent.

`SpecDocument` and `EntityDocument` are closer in shape and wrong in meaning:
both describe the system being modelled. There is no label for a document about
the modelling tool.

## D-1's bar: a named writer and a named reader

D-1 admits a label only when something writes it and something reads it. Both
sides can be named concretely, which is the test this proposal has to pass.

| | Named |
|---|---|
| **Writer** | a `lessons` intake reading `docs/academy/*.md` — front matter for the title and order, body as text |
| **Reader** | `ask`, `search_knowledge`, and the searchable labels it would join |

The reader is the substantive half, and it is not hypothetical. Search already spans
`Intent`, `Specification`, `Requirement`, `AcceptanceCriterion` and
`BusinessEntity`. A `Lesson` carrying a `text` property joins that index with no
new machinery: the schema generator emits the index from `SEARCH_TARGETS`, and
one entry adds it.

## The argument for

**A lesson that reads badly through `ask` is a finding about the tools.** That is
the real reason to do this, and it is not a documentation argument. Today the
academy is prose nobody can interrogate. Landed, every lesson becomes a test of
the retrieval surface against content whose correct answer is known — if asking
*"when does Métis stop for a human"* does not surface the gates lesson, the defect
is in retrieval, not in the writing.

Métis's own claim is that a graph plus disciplined retrieval answers questions
better than documents do. Refusing to hold its own documentation to that claim is
the kind of exemption this codebase does not otherwise grant itself.

## The argument against, stated fairly

**The ontology is for the system under test, and this is not that.** Every label
in the catalogue describes something recovered from or stated about a product.
`Lesson` would be the first label describing Métis itself, and that is a category
the ontology has so far deliberately not had. The label count is already described in the spec as "a warning to heed rather than explain away".

There is also a cheaper answer: publish the academy as a static site and let
ordinary search find it. That costs no label and loses the property above — the
lessons stop being a test of the tools.

## What would have to be true

If accepted, four things follow, and none should be skipped:

1. `Lesson` in `labels.py` with a named writer and reader, and the Cypher schema
   regenerated from it.
2. A `lessons` entry in `connectors/intakes.json` declaring what it reads, what
   it lands, and its limits — `test_intakes.py` will refuse a declaration that
   does not match the registered source.
3. `SEARCH_TARGETS` gains `Lesson`, so the full-text index covers it.
4. Lessons land at `Quarantine` like everything else (**S-4**). They are authored
   text, not approved fact, and the academy is not exempt from the rule it teaches.

## Recommendation

**Accept, but only with the reader built in the same change.** A label added
ahead of its reader is what D-13 already records happening once with `Method` and
`CALLS` — landed, then unread, and only defensible because the choice was
explicit. Adding `Lesson` and leaving `ask` unable to use it would repeat that
with less excuse, since the reader here is one entry in an existing index rather
than new machinery.

If the reader is not built in the same change, refuse this and publish a static
site instead.
