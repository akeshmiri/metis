---
topics: concepts
---
# Proposal: `Epic`, `Goal` and `Capability` labels, under D-2

**Status: REFUSED, 2026-09-04.** The recommendation below was accepted. The
trigger in `labels.py` and §8.7 has been replaced with the narrower one this
argues for, so the old condition — which has fired — cannot fire again on the
same evidence. The ontology stays at forty-three.

*The argument as it was made:* D-2 makes adding a label
a reviewed change rather than an edit. This is the argument, written down so the
refusal can be checked rather than assumed — and so the next person who reads the
staged-out trigger and concludes it has fired does not have to redo the work.

## Why this is being asked at all

`labels.py` stages out three labels with one shared trigger:

| Label | Trigger recorded in `STAGED_OUT` |
|---|---|
| `Epic` | *a backlog hierarchy is actually queried* |
| `Goal` | *a backlog hierarchy is actually queried* |
| `Capability` | *a backlog hierarchy is actually queried* |

**That trigger has fired.** Query-based intake means a team now selects work with
`--query "project = DEMO AND type = Story"` rather than naming keys, and the
first question anybody asks of a selected backlog is *what belongs to what*. The
demo corpus already contains the shape: `DEMO-100` is an Epic, `DEMO-1` is its
child, and the fixture carries the link.

So the trigger is met. The question this proposal exists to answer is whether
meeting it implies these labels, and it does not.

## The hierarchy is already a traversal

An epic and its stories are two `JiraItem` anchors joined by `LINKS_TO`, each
`REPRESENTS`-ing a `Requirement`. That is not a design sketch; it is what the
graph holds today. Landed from the demo fixture:

```
from            kind      to
jira:DEMO-1     parent    jira:DEMO-100
jira:DEMO-2     causes    jira:DEMO-1
```

and read back through `read.requirement_hierarchy`:

```
jira:DEMO-100:  linked_from=[('DEMO-1', 'parent')]
jira:DEMO-1:    links_to=[('DEMO-100', 'parent')]  linked_from=[('DEMO-2', 'causes')]
```

Decomposition, both directions, with the relationship kind distinguished. No
label in that answer is new.

## What actually had to be fixed, and it was not a label

The mechanism existed and was **one field short of useful**. `PlannedEdge`
carried `from_label`, `from_id`, `rel_type`, `to_label`, `to_id` and nothing
else, so no edge anywhere in the system could hold a property. The intake read
each link's `relation` — `parent`, `blocks`, `causes` — planned the edge, and had
nowhere to put the kind.

Every link therefore landed indistinguishable from every other, and
`requirement_hierarchy` honestly reported `"type": "unknown"` for all of them.
*What are this epic's children* was not answerable, and neither was *what blocks
this*, because the two were the same query returning the same undifferentiated
list.

`PlannedEdge` now has a `properties` field, the intake records the kind the
tracker asserted, and the reader returns it. **That is the whole change.** It is
smaller than one label, it benefits every relationship whose kind varies rather
than only these three, and it leaves the ontology at forty-three.

## The argument for adding the labels, stated fairly

**A first-class `Epic` node would be queryable without going through an anchor.**
`MATCH (e:Epic)` is a plainer question than *every `JiraItem` whose
`issue_type` is `epic` and which something links to with `relation: parent`*.
For a report that groups coverage by epic, the second is a mouthful.

**The anchor route is Jira-shaped.** `LINKS_TO` is declared between anchors of
the same kind, so a Confluence page that is the parent of a Jira story is
inexpressible — the intake skips it and says so. A team whose hierarchy spans two
systems gets nothing. That is a real limitation and these labels would not have it.

**`Goal` and `Capability` are not tracker artefacts at all.** They are product
management's own vocabulary, and forcing them through an anchor means Métis can
only hold a hierarchy somebody already built in a tracker. A team that keeps its
capability map in a spreadsheet cannot land it.

## The argument against, which is the recommendation

**D-1 asks for a named writer and a named reader, and only the writer exists.**
Intake could write `Epic`. Nothing would read it: no report groups by epic, no
coverage figure is scoped to one, and `requirement_hierarchy` already answers the
question through the anchors. This is precisely the shape D-13 records going
wrong once with `Method` and `CALLS` — landed, then unread, defensible only
because the choice was explicit. Repeating it here has less excuse, because the
traversal already works.

**Three labels for one trigger is the ontology growing by category, not by
need.** The trigger says *a backlog hierarchy is queried*. It is now queried, and
it was answered without any of them. `Goal` and `Capability` are not implied by
that trigger at all — they were staged out beside `Epic` because they resembled
it, and admitting all three on evidence for one is how a closed ontology stops
being closed.

**The cross-system limitation is real and is not fixed by these labels either.**
A `Capability` node that no intake writes is not better than a `LINKS_TO` a
Confluence page cannot use. If cross-system hierarchy is the need, the change to
argue for is an anchor-agnostic link, not three nouns.

## Recommendation

**Refuse, and record why here rather than in the trigger.** The trigger is met;
the answer is a five-line field on `PlannedEdge` plus the reader that already
existed. The ontology stays at forty-three.

**The condition that should reopen this** is narrower than the current trigger
and worth writing down in its place:

> A named consumer groups or reports on requirements by a hierarchy node —
> coverage per epic, readiness per capability — **and** that consumer cannot be
> served by `requirement_hierarchy` over anchors.

Until something wants to *report* by epic, an epic is a link.

## What was done instead

1. `PlannedEdge.properties`, written with `SET r += row.properties` so a source
   that knows less about an edge cannot erase what another recorded.
2. `intake_landing` records each link's `relation` as the tracker asserted it —
   provenance, not inference. A link with no stated relation is `unknown`, not
   absent: *the tracker did not say* and *nobody recorded it* are different.
3. `read.requirement_hierarchy` returns the kind, so parent and blocks are
   different answers.
4. Tests in `test_intake_landing.py` that fail when the relation stops being
   recorded, and that assert an ordinary edge still carries no properties.
