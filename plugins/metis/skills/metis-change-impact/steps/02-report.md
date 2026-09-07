# 02 — report the behaviour at risk

## Actions

1. List the transitions touched, with the evidence each was reached through.
2. List the criteria that validate them — and say where there are none.
3. List the files that matched nothing, by name.
4. Where a case's justification matters, trace it and report the break rather
   than an empty chain.

## Forbidden substitutions

- Do not rank findings by severity you invented. This reports what is touched,
  not how bad it is.
- Do not describe an unmatched file as unaffected.

## Drift check

Every transition reported should trace to a file in the change. One that does
not came from a path-suffix collision — say so.

## Report

Transitions touched, criteria validating them, files that matched nothing, and
how current the graph is.
