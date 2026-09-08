# 3 · Make something happen

**Only at `run`, and only when the request actually asked for load.** If you
reached this step from a request that asked to *look* at something, go back:
observing was the whole task.

## Before the call

Two things must be true, and both are the caller's to supply:

1. **A sized target exists.** Without one the performance verdict is `no-basis`
   — `design/builders.py:build_performance` says so — and a load run with no
   threshold produces a number nobody can call a pass or a failure.
2. **The literal `execute` is in the call.** `execution.RUN_LITERAL` is not a
   formality: this changes the state of somebody's system, and a caller who
   cannot supply the word has not been authorised. Neither have you on their
   behalf.

**The load profile is a person's.** Métis says which calls are worth driving
under load; how many concurrent users, for how long, against which environment,
are facts about the business and the deployment. Do not pick them.

## After the run

Report the result as an **observation**, never as a verdict:

- it is `observed_from_running_system`, at a time, against an environment;
- it does not write the coverage ledger (C-10);
- a passing run is not a `Go`. `release_verdict` decides whether the evidence
  supports the words somebody wants to use, and this is one input to that.

**If something failed**, `classify_failure(evidence, …)` says whether it points
at the system, the test, or the environment — which under load is the question
that matters most, because a saturated test harness and a saturated service
produce the same-looking numbers and want opposite responses.
