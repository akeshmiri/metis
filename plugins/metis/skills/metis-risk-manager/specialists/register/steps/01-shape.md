# 1 · Shape the register

## The fields, and what each is for

| Field | Why it exists |
|---|---|
| `id` | the join key for every reference. Must be unique — `RISK-DUPLICATE-ID` is an error because an id naming two rows makes every reference ambiguous |
| `description` | cause → event → effect. A one-word row cannot be rated, responded to, or monitored |
| `category` | from `risk_categories()`, validated. Free text destroys every aggregate |
| `polarity` | threat or opportunity. Decides which strategy set is valid |
| `probability`, `impact` | 1–5 each, against the scale written down at planning time |
| `score` | probability × impact — and **recomputed**, never trusted |
| `owner` | one named person who can act. Not "the team" |
| `response` | from the set matching the polarity |
| `status` | Open or Closed, with a reason on closure |
| `derived_from` | `authored` or `model`. The field that keeps two kinds of claim apart |
| `derived_by` | for model-derived rows: which tool observed it, so it can be re-checked |

## Where it lives

In the repository, beside the code it is about. It is authored content, and
authored content here lives in files: reviewable in a pull request, diffable, and
readable with no database.

## Start it from something

An empty register invites an empty identification pass. Seed it with
`risk_candidates` and `requirement_risk` output — those are real, already
severity-graded, and they make the first review a review rather than a blank
page. They cover one category of ten, so run a human technique as well.

## Wire the check in

`metis risk check <file>` in CI. It exits 1 on an error, 2 on a file problem, so
a register that contradicts itself fails the build rather than being discovered
six months later.
