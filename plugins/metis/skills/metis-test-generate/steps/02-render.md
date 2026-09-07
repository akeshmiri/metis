# 02 — render the cases

## Actions

1. `metis paths --journey <j> --criterion <c>` then `metis render --journey <j>`.
2. Report `uncoverable` and `failures` in full. A target the criterion could not
   reach is a coverage gap; a path that would not render is a defect in the
   model. Neither is a rounding error.
3. For a `.feature` file, render Gherkin. It is **specification, not code**, and
   the file says so in its own header — it lands in somebody's test repository
   where our documentation is not.

## Forbidden substitutions

- Do not invent a selector, a base URL, or an example value to make a case look
  complete. `<string, length 3..40, required>` is the answer (X-6e).
- Do not merge two assertions into one case to reduce the count (T-1a).

## Drift check

Re-read the criterion. If cases were produced that no criterion asked for, they
are not coverage — they are additions nobody reviewed.

## Report

Cases rendered, targets uncoverable with reasons, paths that failed to render.
