# 2 · Build the sections

## Actions

1. `design_sections()` for the shape. **Render what it returns**; do not
   describe the format from memory, and do not add a column.
2. `design_report(...)` for the rows, or `metis design -o <file>` to write the
   document.
3. Route each section to its specialist when the request is about one section.
   The parent's routing table is the lookup; the section key is the argument.

## Three states a section can be in, and they are not the same

| State | Renders as | Means |
|---|---|---|
| rows, no missing inputs | the table | this is the section |
| rows **and** missing inputs | the table, plus `> **Partial.**` | it looks complete and is not — **this is the dangerous one** |
| no rows, missing inputs | `absent_means` and `waiting on:` | nobody could state it |
| no rows, nothing missing | `empty_means` | it was stated, and there is nothing in it |

Carry the distinction into what you tell the user. "The security section is
empty" is not an answer; "no authentication was recovered on any call, and
`auth_facts` was not consulted" is.

## Forbidden substitutions

- Do not merge two sections because one is short.
- Do not drop a refusal row. A technique that could not be applied is a fact a
  designer needs; omitting it makes the design look like it considered fewer
  options than it did.
- Do not reorder rows. The order is the risk order, and it is the order the
  generated batch will be in.

## Report

Rows per section, which sections are partial and why, which could not be stated.
