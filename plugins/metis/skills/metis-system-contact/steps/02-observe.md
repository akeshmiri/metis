# 2 · Read the live system

Available at `observe` and above: SQL against a live database, and cluster
evidence — logs, health, events.

**Every fact you collect here is `observed_from_running_system`.** Carry that
label into whatever you report. It is what stops the fact being read later as
something Métis recovered from code.

## SQL

`sql_review` before `sql_confirm` — the review half says what a query will do,
and the confirm half is the one that acts. Do not start that flow without
finishing it: a reviewed query nobody confirmed is a plan, not evidence.

## Cluster

Collect what the question needs and no more. A dump of everything is not
evidence; it is a haystack somebody else has to search, and the reader cannot
tell which part you actually relied on.

## Reporting it

State, together:

- **what you observed**, with the time;
- **what it was observed from** — which environment, which instance;
- **what it does not tell you.** A healthy cluster at one moment is not a claim
  about the release, and a query returning rows is not a claim that the
  behaviour producing them is correct.

**Where an observation contradicts the model**, say both, and say which
questions that raises. Do not resolve it. Either the model is stale or the
system is wrong, and choosing between those needs someone who knows what was
deployed.
