# 01 — establish what the UI side cannot see alone

## Actions

1. Determine whether `INVOKES` links were supplied for this journey.
2. If they were, resolve inherited guards (M-5c) before judging completeness.
3. Record which links are **confirmed** and which are proposals. Only confirmed
   ones count (M-5g, F-7).

## Forbidden substitutions

- Do not treat an unconfirmed proposal as a fact.
- Do not report ambiguity without stating whether the API side was consulted.

## Drift check

Every inherited guard should trace to a confirmed link. One that does not is a
machine's guess wearing a fact's clothes.

## Report

Links supplied or not, confirmed versus proposed, and guards resolved.
