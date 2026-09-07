# 01 — extract, and count what could not be verified

## Actions

1. Run extraction against the checkout. Record the engine and pack versions.
2. Report the number of facts dropped, with the ground for each — provable
   inertness, never visibility.
3. Count `unverified`: facts with no anchor, no source line, no episode. **State
   the number.** "Some facts were skipped" and "eleven facts were skipped" are
   different statements, and only the second can be checked.

## Forbidden substitutions

- Do not infer a transition from a name.
- Do not fill a missing anchor to make a fact landable.
- Do not filter fields.

## Drift check

Every element should trace to a file in the analysed tree. One that does not came
from a path collision.

## Report

Elements recovered, facts dropped with grounds, and `unverified` as a number.
