---
topics: concepts
---
# Proposal: a `Release` label, under D-2

**Status: DEFERRED, 2026-09-04.** The recommendation below was accepted: the
shape is right and the timing is not. The trigger in `labels.py` and §8.7 has
been replaced with the narrower one this argues for, and the cheaper alternative
named at the end — an `as_of` argument on the readiness report — has been built.
**If that turns out to be enough, this should be refused permanently rather than
left pending**, and the paragraph below saying so is the test of that.

*The argument as it was made:*
D-2 makes adding a label a reviewed change rather than an edit. This is the
argument, including the case against and the condition under which it should
still be refused.

## The trigger, and how much of it has fired

`labels.py` stages out `Release` with a two-part trigger:

> *execution results are ingested **and** release reporting is required*

**The first half has fired.** §8.7 was revised: `execution_intake` lands
`TestExecution`, `TestCycle`, `Defect`, `Metrics`, `Logs` and `Alert`, at
`Quarantine`, carrying `provenance: observed_from_running_system`, attached to
the `TestCase` that ran and never to the transition it covers. C-10 still holds —
nothing there writes the coverage ledger — so *is this tested* and *did it pass*
are two figures and neither is the other.

**The second half has not, and that is the whole of this proposal.** Nothing
currently requires a *named* release. `metis-release-readiness` exists and asks
for `coverage`, `coverage_report`, `trace` and `impact`; every one of those is
scoped by journey and surface, and none of them asks "as of release 2.4".

## What the graph can already answer

Bi-temporal validity is not a plan; it is on every claim. `valid_from` is when a
claim started being true and `valid_to` is empty while it still is, so an as-of
question is a `WHERE` clause:

```cypher
WITH '2030-01-01T00:00:00+00:00' AS asof
MATCH (r:Requirement)
WHERE r.valid_from <= asof AND (r.valid_to = '' OR r.valid_to > asof)
RETURN count(r)      // 1
```

and against an instant before anything landed, the same query returns `0`. *What
did we believe in March* already works, with no new label and no stored copy.

**So a `Release` must not hold a claim set.** A node listing the requirements
that were current at a moment would duplicate what the windows already encode,
and the duplicate would be the half that goes stale — a requirement superseded
after the release was recorded would still be listed in it, and the list would be
the more convincing of the two answers because it is explicit.

## What is genuinely missing

**A name for an instant.** `2026-08-14T11:02:19+00:00` is not a thing anybody
says. "Did 2.4 ship with the 409 behaviour or the 423 behaviour" is the real
question, and answering it today requires somebody to know which timestamp 2.4
was — which lives in a release note, a tag, or nobody's head.

That is a small, honest gap and it is the only one. The label being proposed is
therefore very thin: a `Release` is a **name, an as-of instant, and nothing
else**. Everything about what the release contained is a traversal from the
instant.

## The argument for

**It closes the loop the execution labels opened.** Ingesting a `TestExecution`
without a release to attribute it to means "did 2.4 pass" cannot be asked, only
"did this cycle pass". The first half of the trigger fired precisely because
somebody wanted outcomes in the graph; outcomes are reported per release
everywhere outside this system.

**It is the cheapest possible label.** Two properties, one writer, and no
duplication of anything the graph already holds. Contrast `Epic`, where the
mechanism turned out to exist already — here the mechanism genuinely does not:
there is no way to name a moment.

**It makes an as-of query usable by a non-technical reader.** A QA lead can ask
for a release by name. They cannot be expected to supply an ISO timestamp, and a
report that demands one is a report they will not run.

## The argument against, stated fairly

**D-1 asks for a named writer and a named reader, and neither exists yet.** No
verb records a release. No report takes one. `metis-release-readiness` would be
the reader and does not currently ask for it — so accepting this now would land a
label ahead of both halves, which is exactly what D-13 records going wrong with
`Method` and `CALLS`, and what the hierarchy proposal was refused for.

**A release is arguably not Métis's fact.** Every other label describes something
recovered from a system or stated about it. A release is an event in somebody's
delivery process, and Métis has consistently declined to model those: §12
excludes defect and operational work, and `Incident` is staged out for the same
reason. A tag in a repository already names the instant, and the honest answer
may be "read it from there".

**Half a trigger is not a trigger.** The condition was written as a conjunction
deliberately. Firing on the first clause because the second seems likely is how a
staged-out list stops meaning anything.

## Recommendation

**Accept the shape; refuse the timing.** The design is right and the label is
thin, but D-1's bar is not met today and the trigger's second clause has not
fired. Adding it now would be a label with a writer nobody calls and a reader
that does not ask for it.

**The condition that should bring it back**, replacing the current wording:

> A report or workflow takes a release NAME as an input — readiness for 2.4,
> outcomes for 2.4 — **and** the name cannot be resolved to an instant outside
> Métis. Then `Release` is a name plus an as-of instant, and the claim set stays
> a traversal.

## What should be done in the meantime, and is not a label

1. **Say that an as-of query exists.** It is on every claim, it works, and no
   document tells a reader how to ask it. That is a delivery gap of exactly the
   kind the academy was rendered to fix.
2. **Let the readiness report take an as-of instant.** `coverage_report` scoped
   by journey and surface could take one more optional argument and answer
   "readiness as it stood then" with no ontology change at all. If that turns out
   to be enough, this proposal should be refused permanently rather than deferred.
