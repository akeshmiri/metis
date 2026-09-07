---
topics: concepts
---
# 1 · What Métis does not do

The fastest way to be wrong about this system is to assume it does one of the
following. Each is a deliberate design decision with the rule that fixes it in
place.

## It does not touch the system under test unless you configured it to

**X-7a, revised.** This used to read "never", and the argument that would have
to be made was made: contact with the system under test is now a tier, and `off`
is the default.

The distinction that does the work is unchanged: *a database Métis reads to
learn structure is an intake source; the same database reached to check a test's
outcome is the system under test.* Same server, different act — and the second
now has a switch rather than a prohibition.

- `off` — no contact. The default, because a system that starts able to touch
  production is one nobody chose to make able to.
- `observe` — read a live system: a query, a log, a cluster's state.
- `run` — also make something happen, and it costs the literal word `execute`
  in the call.

**Still structural at `off`.** `metis_mcp/execution.py` is the single place
contact is permitted, and at the default tier the `observers/` and `runners/`
modules are never imported at all — `test_execution.py` proves it in a
subprocess, the same way the read-only write surface is proved. The clients are
optional extras, so a default install cannot reach a database or a cluster even
if something tried.

**What the tiers protect is the part that did not change.** A fact read from a
running system is labelled `observed_from_running_system` and is never merged
with one recovered from source. Reading a log tells you what happened once; it
is not what the code says it does. §8.7 stages out the execution labels for
exactly this reason, and merging the two is how a coverage figure becomes a
correctness claim — which the next section is about.

## It reports coverage, never correctness

**C-11.** A coverage figure answers *is this behaviour tested?* and never *is it
working?* That has not changed, and what changed around it is worth being exact
about, because this lesson used to say *no execution result is ingested* and
that is no longer true.

Execution results **are** ingested — `TestExecution`, `TestCycle`, `Defect`,
`Metrics`, `Logs` and `Alert` were staged out with the condition that would
bring them back, and it arrived. They land through `execution_intake` at
`Quarantine`, carrying `provenance: observed_from_running_system`, attached to
the **`TestCase`** that ran and never to the transition it covers.

That routing is the whole design. Edging an execution to a transition would make
*this behaviour passed* expressible in one hop, and coverage would quietly
become correctness. Instead there are two figures: one answering *is this
tested*, one answering *did it pass*. A transition can be fully covered and
currently failing, and Métis now sees both without reporting either as the
other. Nothing in the execution path writes the coverage ledger, and
`test_execution_intake.py` asserts that structurally rather than trusting it.

The sharper version: a criterion written from the code it checks lands as
`code_derived`, the weakest provenance. Its agreeing with the code is evidence
of coverage and evidence of nothing else. If the code is wrong, a `code_derived`
criterion is wrong in exactly the same way and the two agree perfectly.

## It does not approve its own work

Everything recovered lands at `Quarantine` (**S-4**). No source writes
`Approved`. Generation reads only `Approved` (**D-10**). The gap between those
two sentences is a person, and it is not optional — the two human gates exist
because an agent session cannot provide the evidence presentation that N-3
requires for a decision.

## It does not publish by accident, and it will not publish on one key

`DryRunTransport` is the default and `test-generate`'s `publish` stage uses it:
it builds and validates a real payload and sends nothing. That is what you get
unless somebody has deliberately arranged otherwise.

**A live transport does exist**, and this lesson said it did not for as long as
it took somebody to check — which is the worse direction for a safety claim to
be wrong in. `metis publish --transport zephyr-scale` writes test cases into a
real Zephyr Scale project. It is gated on **two** keys, and the second is the
point:

- a G2 confirmation, the literal word `publish`, supplied **in that run** — and
  whatever drives the run can supply it, including an agent;
- `METIS_ALLOW_EXTERNAL_WRITES=yes` on the **installation**, which an agent
  cannot set for itself.

So a real write needs a word from the run *and* a deployment somebody
configured to permit one. Everything else Métis writes lands at `Quarantine` in
a graph the project owns and can throw away; this leaves and stays left, which
is why it is the one thing with two locks rather than one.

## It does not guess

This is the one that shapes the most code.

- A base URL renders as `{base}` with its reason, never as a plausible host.
- A payload field renders as `<string, length 3..40, required>` — the accepted
  space, never a value that looks real enough to paste.
- A UI element whose selector the page code never names in a literal lookup
  becomes a stub that raises, not a guessed CSS path.
- A repository method whose statement cannot be recovered is reported with its
  reason, never as an invented `SELECT`. (The database layer is staged out
  entirely under X-6d — a requirement is stated about behaviour, not about a
  table — so there is no dialect label to guess wrongly into either.)
- A guard it cannot decompose is returned whole. One condition treated as atomic
  is a weaker claim than a wrong decomposition.

A fabricated answer is worse than an absent one, because an absent one is
visibly absent.

## What it is for, then

Recovering a behaviour model from code, comparing it against what somebody said
the system should do, and generating human-executable test cases from the part
that survives human review. Everything above is in service of the last clause.
