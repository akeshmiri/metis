# 1 · What Métis does not do

The fastest way to be wrong about this system is to assume it does one of the
following. Each is a deliberate design decision with the rule that fixes it in
place.

## It never executes anything against the system under test

**X-7a.** Métis reads intake sources and writes its own graph. It does not call
the API it models, drive the UI it models, or run a query against the database
it models.

The distinction that does the work: *a database Métis reads to learn structure
is an intake source; the same database reached to check a test's outcome is the
system under test.* Same server, different act, and only the first is available.

This is structural rather than remembered. Every `access` mode in
`connectors/intakes.json` is read-only, `executes_against_sut` is a schema
`const` of `false`, and the loader refuses a declaration that says otherwise.
There is deliberately **no mode meaning "runs something"**. Adding one is the
change that would have to be argued for.

## It reports coverage, never correctness

**C-11.** A coverage figure answers *is this behaviour tested?* and never *is it
working?* No execution result is ingested, so none can be reported.

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

## It does not publish

`DryRunTransport` is the only registered transport. `test-generate`'s `publish`
stage builds and validates a real payload and sends nothing. If you pass a G2
confirmation expecting a write to a test management tool, you will get a
successful dry run and no write.

## It does not guess

This is the one that shapes the most code.

- A base URL renders as `{base}` with its reason, never as a plausible host.
- A payload field renders as `<string, length 3..40, required>` — the accepted
  space, never a value that looks real enough to paste.
- A UI element whose selector the page code never names in a literal lookup
  becomes a stub that raises, not a guessed CSS path.
- A repository query whose table no catalogue confirms lands as `JpaQuery` with
  its reason, not as `:Postgres` with an invented `SELECT`.
- A guard it cannot decompose is returned whole. One condition treated as atomic
  is a weaker claim than a wrong decomposition.

A fabricated answer is worse than an absent one, because an absent one is
visibly absent.

## What it is for, then

Recovering a behaviour model from code, comparing it against what somebody said
the system should do, and generating human-executable test cases from the part
that survives human review. Everything above is in service of the last clause.
