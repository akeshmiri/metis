---
topics: operator
---
# 15 · One requirement, end to end

One ticket, followed the whole way. Everything below is the real demo corpus in
`demo_project/trackers/` — the outputs are what the commands actually print, not
an illustration.

## The tickets

The demo tracker holds three, and the contrast between two of them is the point.

**DEMO-1** — *When a record has been archived, the system shall reject an update
with 409.*

**DEMO-2** — *Archive is broken again.*

One of these is a requirement. The other is somebody's note to themselves.

The third, **DEMO-100** (*Archiving*), is an Epic — a container, not a claim about
behaviour. It has no checkable sentence either, so it takes the same route DEMO-2
does. Watch for it below; it is a fair question whether that is the right answer
for a backlog container, and today it is the honest one.

## Step 1 — bring them in

Métis reads the tracker and writes one document per item. Every field records
where it came from:

```
jira: 3 item(s) from https://tracker.example.com
  DEMO-100       Epic         Archiving
  DEMO-1         Story        When a record has been archived, the system shall reject
  DEMO-2         Bug          Archive is broken again
```

Nothing is inferred here. The title is the title; the description is the
description; the link back to the ticket is built from the URL that was actually
read, never from a template.

## Step 2 — the two outcomes

Before anything is landed, each document is checked for whether its text is
phrased in a checkable way:

```
  DEMO-100.uif.json  conformant
      advisory: the text is not EARS-conformant, so this lands as a Finding
      pointing at knowledge-capture and NOT as a Requirement (S-13)
  DEMO-1.uif.json  conformant
  DEMO-2.uif.json  conformant
      advisory: the text is not EARS-conformant, so this lands as a Finding
      pointing at knowledge-capture and NOT as a Requirement (S-13)
```

Read that carefully, because it is the most important behaviour in the system.

**DEMO-1 becomes a `Requirement`.** Its sentence has a shape that can be checked:
a situation (*has been archived*), an action (*an update*), and an expected
result (*409*).

**DEMO-2 becomes a `Finding`.** Not a requirement, not an error, not silently
dropped. A note saying *this needs formalising, and here is where to do it*.

**DEMO-100, the Epic, becomes a `Finding` too** — for the same mechanical reason,
though it is a different kind of thing. An Epic is a container for work, not a
statement about behaviour, so there is no sentence to check. Métis has no label
for a backlog container today, so it records what it can honestly say: *this is
not a requirement, and here is where somebody would formalise the ones under it*.

Métis could easily have invented a requirement from "Archive is broken again".
It refuses, because a fluent requirement nobody wrote is worse than an obvious
gap — you cannot tell it is wrong by looking at it.

## Step 3 — land them, at Quarantine

```
--- DEMO-1.uif.json
  Episode:           1        the ingestion run — what can be re-run
  JiraItem:          1        the ticket itself, as evidence
  Requirement:       1

--- DEMO-2.uif.json
  Episode:           1
  JiraItem:          1
  Finding:           1
```

Two things worth noticing:

- **The ticket lands as its own record**, separate from the requirement. If the
  requirement is later rejected, the evidence it came from survives — rejecting
  a claim must never destroy the thing it was based on.
- **Everything is at Quarantine.** Nothing here is agreed with. A person has to
  say so.

## Step 4 — what the code actually does

Separately, Métis reads the service's source and recovers what it really does —
which situations exist and how the system moves between them. This is
independent of the tickets, deliberately: if it read the tickets first it would
find what it was told to find.

## Step 5 — the comparison

Now the two sides meet, and there are three possible answers per behaviour:

| | Meaning |
|---|---|
| **Both agree** | The code does what the ticket says. Recorded, and quietly the least interesting result |
| **Only the code has it** | Behaviour nobody wrote down. Either undocumented, or something nobody meant to build |
| **Only the ticket has it** | A stated requirement with no implementation, or one Métis could not find |
| **They disagree** | The valuable one — *the code says 3 attempts, the criterion says 5* |

A disagreement is not resolved automatically, and it never will be. One of *the
code is wrong* and *the requirement is stale* is right, and **no rule can decide
which**. A person chooses, and records why.

## Step 6 — the gate

Everything stops here until a human decides. The screen shows the model, every
validation finding, both directions of the comparison, and every state whose name
was never confirmed.

If any of that cannot be shown, the screen refuses the decision rather than
showing you a partial page.

## Step 7 — test cases

Only from what was approved. A step looks like this:

> **Given** the record has been archived
> **When** a PUT is sent to `{base}/record/{id}`
> **Then** the response is `409`

Note `{base}`. Métis does not know your hostname and will not invent one — it
renders the placeholder with the reason beside it. Same for a request body: you
get *a string, 3 to 40 characters, required* rather than a value that looks real
enough to paste and is wrong.

## What changed for the ticket

DEMO-2 is still sitting there as a finding. Nobody has rewritten it. That is
visible, counted, and does not block anything else — which is the difference
between a system that tracks its gaps and one that hides them.

Next: [the screens you will use](16-the-screens-you-will-use.md).
