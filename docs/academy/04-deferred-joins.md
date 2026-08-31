---
topics: concepts
---
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

## Where you meet it

X-19 was once mechanised as four `JoinKind`s — entity-to-table, query-to-table,
route-to-page, element-to-selector. All four joined labels the 2026-08-31
re-baseline staged out, so the machinery went with them: Métis is a requirement
tool over a state machine, and none of those joins was between two things a
requirement is about. The **principle** is not a casualty of that, because it
was never really about joins. It is about refusing to collapse three answers
into two, and it survives in the two places that matter most.

### `unverifiable` — validation's third outcome

**M-17.** A guard checker returns pass, fail, or *cannot be decided from the
text alone*. On a real service:

```
validate: 0 blocking, 4 unverifiable, 28 advisory
```

Those four are guard-completeness questions over conditions like
`an exception is thrown AND NOT (ex.getCause() instanceof ConstraintViolationException)`
— either no real input matches them, or they cannot hold together, and which
one it is a checker cannot say. Reporting them as *pass* would claim coverage
nobody has; as *fail* would block generation over a guard that may be perfectly
fine. They are reported, and generation stops until a person accepts the risk
with `--allow-unverifiable`, which is **recorded, not silent**.

### `unmodelled` — recovery's third outcome

An endpoint recovered from code that no transition explains is neither dropped
(the graph would claim the service has fewer entry points than it does) nor
invented (a transition nobody recovered). It becomes a `Finding` — a work item
that closes when somebody models it, or stays visible while they do not.

That is the same three-way shape: `covered`, `contradicted`, and *not yet
reached*. The middle one is the answer a retry loop destroys by treating "no" as
"not yet", and the one a reviewer needs most.

## Why a selector is a property and not a node

A selector is not a thing in the system; it is how to reach one. Landing
`#archive` as an entity would put a CSS string in the label space and hand a
reviewer something to approve that is not a fact about the system. So
`edges_for` skips property-valued joins and `properties_for` picks them up.
