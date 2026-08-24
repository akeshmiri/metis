# 4 · Joins that cannot be made yet

Two facts that belong together often arrive at different times, and the
tempting responses are both wrong: drop the join, or invent the edge.

**X-19** is the third answer. One side proposes, the other confirms, and a
proposal carries the basis it was made on so a reviewer can weigh it.

## Three outcomes, and the difference matters

| | |
|---|---|
| `confirmed` | the confirming intake ran and contains the target — this becomes an edge, or a property |
| `refuted` | it ran and does **not** contain the target — the belief was wrong |
| `proposed` | it has **not run** — the join may yet resolve |

Collapsing `refuted` and `proposed` is the failure this distinction exists to
prevent. A retry loop treats "no" as "not yet" and never stops asking, and a
reviewer never learns their proposal was wrong. A plain `dict.get` returns the
same empty string for both.

## The four kinds

| kind | edge | proposed by | confirmed by |
|---|---|---|---|
| `entity_storage` | `BusinessEntity -[:STORED_IN]-> Table` | knowledge, structure | database |
| `query_target` | `Query -[:QUERIES]-> Table` | code | database |
| `route_page` | `Route -[:RENDERS]-> Page` | web | structure |
| `element_selector` | *(a property, not an edge)* | structure | web |

An intake declares which joins it can offer and which it can settle, so a new
intake adds a row rather than code.

## A worked refutation

The demo store's `TagEntity` states no `@Table`. Spring's naming strategy
proposes `tag_entity`, the catalogue declares `record_tag`, and the join is
**refuted** — reported with both halves, so a person can see the proposal, the
basis, and what the database actually has.

The same shape one layer up: the demo router's `RecordDetailPage` meets the
authored `record-detail` page and confirms. `RecordListPage` does **not** meet
`records-list`, and that refutation is the right answer. Stripping an `s` to
make them match is an open-ended guess of exactly the kind the closed UI-suffix
list exists to avoid — it would marry a `Records` page to a `Record` route on
some estate where those are different screens.

## Why a selector is a property and not a node

A selector is not a thing in the system; it is how to reach one. Landing
`#archive` as an entity would put a CSS string in the label space and hand a
reviewer something to approve that is not a fact about the system. So
`edges_for` skips property-valued joins and `properties_for` picks them up.
