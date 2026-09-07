# 1 · The links, and what they carry

## Actions

1. `design_report(journey, surface="ui", section="journey")`.
2. `journey_walkthrough` for the composed view a reader can follow.
3. Report confirmed links and proposed links **separately**. A proposed link is
   a question for whoever owns the UI.

## What each column decides

| Column | If it is absent |
|---|---|
| `invokes` | the UI action reaches no known call — either no link was recovered, or there is none |
| `inherited_guard` | the action has no condition from the API; check it has one of its own |
| `selector` | the case cannot be executed as written, and no guess will fix that |

## Forbidden substitutions

- Do not fill `selector` from an id you saw in a DOM extract unless it was
  authored as the selector.
- Do not merge a UI transition and its API transition into one row. They are two
  behaviours with two outcomes.

## Report

Confirmed links, proposed links, actions with no selector, and which surface the
missing half belongs to.
