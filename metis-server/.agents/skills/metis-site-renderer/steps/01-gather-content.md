# Step 1 — Gather content (R/P, RPI-gated)

Identical real call to `metis-deck-renderer`'s own step 1: `metis_mcp.academy.assemble_content()`
for each Academy page (`kind="academy_page"`) plus one
`kind="quality_summary"` call for the index page's live snapshot. Same
Forbidden Substitutions rule: a `None` metric value is shown as such, never
guessed or rounded to "looks fine."
