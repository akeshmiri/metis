# Step 1 — Research (R)

**Scope Lock:** exactly one statement, and exactly one `<journey>`-`<surface>`
model. A statement that spans two surfaces is two runs, because a model is one
machine per surface (M-1).

## Actions

1. **Write the statement down verbatim, before anything else.**
   Copy the person's own words into a scratch note. Every criterion you draft
   will claim to be a formalisation of this sentence, and a claim nobody can
   check against its source is not evidence. This becomes `statement` in the
   file and `source_statement` on every entry.

2. **Establish which model it is about.**
   ```
   python3 -m metis_mcp.mbt.cli workflow list
   python3 -m metis_mcp.mbt.cli validate --journey <j> --surface <s>
   ```
   If the statement does not name a scope, **ask**. Do not infer one from a
   word it happens to share with a journey name — `route()` refuses to break a
   tie for the same reason, and a run started against the wrong model produces a
   confident artefact about the wrong thing.

3. **Read what the model already says about this behaviour.**
   ```
   python3 -m metis_mcp.mbt.cli reconcile --journey <j> --surface <s>
   ```
   Record the existing transitions whose trigger or target the statement touches,
   with their guards **verbatim**. These are the elements a contradiction will be
   found against, and you need their exact wording to recognise one.

4. **Check whether a criterion for this already exists.**
   An existing criterion that says the same thing means the answer is *already
   there*, and drafting a near-duplicate with a new id would create a second
   node saying one thing.

## Forbidden substitutions

- Do not paraphrase the statement "for clarity". The words are the grounding.
- Do not decide the scope from a filename, a recent command, or the last model
  you looked at. If it is not stated, **stop and ask**.
- If `validate` or `reconcile` returns nothing for the named journey, that is a
  real answer — there is no model here yet. Say so; do not proceed as though the
  model were empty by choice.

## Output of this stage

A `VERIFIED` note holding: the statement verbatim, the `<journey>`/`<surface>`,
the existing transitions the statement touches with their guards quoted, and any
existing criteria on them. Nothing inferred.
