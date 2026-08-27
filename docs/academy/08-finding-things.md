---
topics: practice
---
# 8 · Finding things, and which surface to ask

## Three surfaces, one engine

| Surface | Use it when | Can it decide? |
|---|---|---|
| **CLI** | doing the work — extraction, landing, generation | yes, with an identity |
| **MCP** | an agent is asking questions | read-only by default |
| **HTTP** | a dashboard, CI, or another service | yes, behind a token |

The CLI is the fullest surface. The MCP surface is read-only **by
construction** — with writes off, the write modules are never imported, so the
tools that could decide do not exist rather than existing and declining
(**N-8**). The HTTP surface authenticates rather than trusting what it is told
(**N-18**).

They do not disagree. A read endpoint returns the same content as the MCP tool
that answers the same question, because it calls it.

## Search

Search used to be substring matching, which cannot rank and cannot tell a title
match from a body match. It is now Lucene, with a stemming analyzer:

| Query | Substring | Full text |
|---|---|---|
| `locking` | matches, unranked, includes superseded | ranked, current only |
| `lock` | **nothing** | matches "the account is locked" |

Search covers `Intent`, `Specification`, `Requirement`,
`AcceptanceCriterion`, `BusinessEntity` and `Lesson` — so a search for a business
phrase finds the stated need and not only the criterion derived from it, and the
academy is searchable beside the product it teaches.

Two things the corpus taught the tools, both found by asking it questions whose
answers were known. Accents are folded into a second indexed copy, because
`Metis` returned nothing for a corpus about Métis. And a snake_case identifier
contributes its parts, because `valid_to` is one token to Lucene and was
invisible to anyone asking about validity in ordinary words.

`metis retrieval-bench` measures this against a question set whose answers were
written first. The academy's own set scores 11 of 15 first-place, and the four
misses are semantic rather than lexical — which is the measured case for the
embedding provider, not an argument for one.

## Semantic search, if you want it

A vector index exists and is **inert until somebody supplies an embedding
provider**. No model is bundled: the database performs the similarity search, so
the only thing an implementation must provide is the query vector.

When both are present, results are merged by **rank, not score**. A Lucene score
of 0.5 and a cosine similarity of 0.5 mean nothing to each other, and averaging
them is a category error dressed as arithmetic. A document both retrievers found
outranks one either found alone, and each hit records which found it.

**An embedding is meaningless outside its model.** A query whose model disagrees
with the corpus is refused rather than answered — the results would be
confidently wrong with no error, which is the pinned-engine lesson (**X-3**) in a
different costume.

## What `ask` will not do

`ask` composes the read tools and **may say nothing they did not** (**X-6e**). It
is not a model reasoning over the graph; it is a reader of it. A fluent wrong
answer about how authentication works is the worst thing this system can produce,
and the constraint exists to make that impossible rather than unlikely.

Better retrieval does not loosen it. Finding more candidates is a different thing
from asserting more.
