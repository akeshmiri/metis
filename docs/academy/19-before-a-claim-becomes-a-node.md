---
topics: operator
---
# 19 · Before a claim becomes a node

You have a ticket. Somebody wrote a sentence in it. Before Métis will put that
sentence in the graph, four different readers look at it — and each one sees a
problem the other three cannot.

## Why this happens before landing, not after

Intake used to run: fetch the ticket, check its shape, **land it**, then assess
its risk. That order has an obvious problem once you say it out loud — the first
moment anybody saw what was wrong with a claim was after it was already a node
other things could point at.

So the reading moved in front of the landing. Nothing is imported until it has
been looked at.

## The four readings

| Reading | The question | What only this reader catches |
|---|---|---|
| **intent** | Is there a need here, and did anybody say how it behaves? | "Records should be tidy" — a goal with no stated behaviour |
| **requirement** | Can two people satisfy this the same way? | wording two readers would act on differently |
| **design** | Could anything ever test it? | a claim that is well written, agreed, and impossible to verify |
| **risk** | What does being wrong cost? | nobody has said what is at stake |

**The third one is the expensive mistake.** A requirement can be perfectly
worded, agreed by everyone, and have no observable outcome — and you find that
out after it is built. Asking before the work starts costs one question.

Three of the four are performed by skills that already own those procedures. The
business analyst consults them rather than doing their job again, because a
second copy of a procedure drifts from the one that actually runs.

## Ready means one narrow thing

The verdict is `ready` or `not-ready`, and both are narrower than they sound.

**`not-ready`** means the claim cannot be *represented*. A need nobody has
specified would become a node nothing can ever be checked against — it would sit
in the review queue forever, because there is nothing a reviewer could approve it
*against*. There is no literal that passes this, no override, no "just import it
anyway". **The claim itself has to change.**

**`ready`** means representable, and nothing more. It lands at `Quarantine`
carrying every gap that was found, and a person decides at G1. **Nobody has
agreed with it.**

That distinction does real work. A requirement nobody has costed, whose
environments are unlisted and which has no acceptance criteria yet, is `ready` —
and it lands with all three of those recorded beside it. Refusing it would mean
Métis only ever accepted requirements that were already finished, which is not
what intake is for.

## What you will see

Every gap names two things: which reading found it, and what would close it. A
gap with no closer is a complaint, so there are none.

```
[intent      BLOCKS] INT-2: no specification says how this behaves
[requirement report] ABC-1: not EARS-conformant — it will land as a Finding
[design      report] scope: nobody has said which environments exist
[risk        report] scope: business criticality is unrated
```

One of those stops the import. The other three travel with it.

## The document is editable, and that is the point

`metis intent review <file> -o review.md` writes the gap ledger. `Closed`,
`Owner` and `Notes` are yours and survive regeneration — and **so does any gap
you add by hand**, which is the case the file exists for. Four readers is not
five, and the fifth is you.

## What this does not do

It does not decide whether the requirement is a good idea. It does not write the
specification for you — turning "records should be tidy" into a behaviour is
inventing the requirement, and the invention would carry provenance it has not
earned. And it never lands anything: it reports, and the gated command writes.

If a claim comes back `not-ready`, read
[when Métis refuses](17-when-metis-refuses.md) — the refusal is the same shape as
every other one here, and it means the same thing.
