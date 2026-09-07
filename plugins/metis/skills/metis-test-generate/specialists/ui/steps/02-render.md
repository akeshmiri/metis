# 02 — render the cases

## Actions

1. Render the paths. One case, one assertion (T-1a).
2. Where an element has an authored selector, use it verbatim.
3. Where it has none, **raise and name the element**. Do not continue past it
   silently.

## Forbidden substitutions

- Do not derive a locator from a component name.
- Do not describe an action in terms the model does not carry.

## Drift check

Every step should trace to a transition. A step describing an interaction the
model has no transition for was invented.

## Report

Cases rendered, elements lacking a selector, and what was not generated because
of them.
