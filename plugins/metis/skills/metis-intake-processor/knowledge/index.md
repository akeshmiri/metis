# Knowledge Index — intake-processor

No fragments extracted yet. The three UIF sources (`jira`, `scale`,
`confluence`) share one generic procedure — see `steps/01-extract.md` — because
they share one reader, `code_analysis.tracker`, and differ only by an entry in
its endpoint and field tables.

This is a single-step skill dispatched by `--system`, not a multi-route skill
with distinct per-source procedures. The non-negotiable rules stay in
`../SKILL.md` since they are enforced regardless of source.

Code, OpenAPI and database sources are deliberately **not** here: they do not go
through UIF at all, and `../SKILL.md` names the command for each.
