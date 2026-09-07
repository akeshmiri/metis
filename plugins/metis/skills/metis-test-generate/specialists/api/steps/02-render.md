# 02 — render the cases

## Actions

1. Render the paths. One case, one assertion (T-1a).
2. For each case, state the route, the accepted input space, and the declared
   outcome.
3. Report `uncoverable` and `failures` in full.

## Forbidden substitutions

- Do not substitute a concrete base URL for `{base}`.
- Do not merge two assertions to reduce the count.

## Drift check

A case that names a route not in the model came from somewhere else.

## Report

Cases rendered, targets uncoverable with reasons, paths that failed to render.
