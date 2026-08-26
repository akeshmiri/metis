# 5 · The two gates, and why there are only two

Métis stops for a human twice. Everything else runs unattended, and the two
places it stops are chosen so that the **safe failure is always "no tests
generated"**, never "tests generated from something nobody checked".

| Gate | Sits before | Decides | Evidence a reviewer is shown |
|---|---|---|---|
| **G1 — model approval** | anything is generated | is this behaviour real | validation findings, reconciliation gaps, the criteria each rule carries |
| **G2 — publication** | any external write | do we send this | the whole batch, in full |

## Nothing auto-approves, and nothing expires into approval

An unreviewed model stays unapproved indefinitely. There is no timeout that
promotes it, no "approved unless objected to", and no threshold of confidence
that stands in for a decision. Generation reads only `Approved` (**D-10**), so an
unreviewed model produces nothing rather than producing something unmarked.

This is worth stating because the alternative is so tempting. A queue of 200
elements invites a bulk accept, and a bulk accept is indistinguishable from
nobody looking. **N-5** permits a batch decision and prohibits batch blindness:
the decision may cover many elements, and it must name what it covered.

## A decision that cannot show its evidence is blocked

**N-4.** If the screen cannot present validation findings and reconciliation
gaps, it does not present a thinner screen — it refuses the decision. Over HTTP
that is a `409`. The reasoning is that an approval means *"I looked at the
evidence"*, and an approval taken without it is a record of something that did
not happen.

## The proposer may not approve

**N-10.** Whoever put an element forward cannot be the one who accepts it. The
analyser is the proposer for code-derived models, which is why the audit record
carries `proposed_by` — before it did, `check_self_approval` received `None` for
every landed element and the separation had never once fired.

An override exists and is **recorded as an override**, never silent (**N-11**).

## G2 is a literal word, in that run

Publication takes an affirmative confirmation — the literal word, not a default,
not a `-y` flag (**T-18**). It covers a batch shown in full (**T-17**), and it
records who gave it (**N-13**).

On a terminal, *"in that run"* enforces itself: the run is the process the
operator is looking at. Over HTTP it does not — a request body is a string a
proxy can retry and a client can resend. So a confirmation over the API is a
single-use ticket bound to the batch shown and the identity shown it, consumed on
first use (**N-19**).

Today publication is dry-run only. The gate is real; the transport behind it
sends nothing.

## What this costs, honestly

Two gates mean two places a person must be present, and a system that cannot run
end to end without one. That is the trade: Métis is not trying to be autonomous.
It is trying to make the moment of judgement **visible and recorded**, and
everything above follows from taking that seriously.
