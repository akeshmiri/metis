# Step 1 — Research (R)

**Scope Lock:** exactly one model, named by `<journey>`/`<surface>`. Related
models that appear in reconciliation output are noted, not reviewed.

## Actions

1. **Find where the run stopped.**
   ```
   metis workflow status model-build--<scope>
   ```
   The record names the blocked stage, the outstanding elements, and the exact
   command that records the decision. If there is no run, the user may be
   reviewing outside a workflow — that is fine; continue from step 2.

2. **Get the well-formedness findings.**
   ```
   metis validate --journey <j> --surface <s>
   ```
   Record each finding's severity verbatim. The three are not synonyms:
   `blocking` means this is wrong; `unverifiable` means it *cannot be shown* to
   be right (M-17); `advisory` means neither. Report them as they are — do not
   summarise an unverifiable finding as a pass.

3. **Get both reconciliation directions.**
   ```
   metis reconcile --journey <j> --surface <s>
   ```
   Record `UNSPECIFIED BEHAVIOUR` and `UNIMPLEMENTED` **separately** (F-5) — a
   specification gap and an implementation gap have different causes and
   different owners. Also record how many matches are intent-backed versus
   documentation-only: a match against a code-derived criterion is documentation
   agreeing with itself (§4.1).

4. **Export the review file.**
   ```
   metis review export --journey <j> --surface <s> -o review.json
   ```
   Each item carries `evidence` (what the reviewer is shown), `proposed_by`, and
   where one exists `criterion_id` / `criterion_text`.

## Forbidden substitutions

If a command returns nothing, or the journey does not exist, **stop and ask**.
Do not substitute a similar-looking journey name, and do not proceed on the
assumption that "no findings" and "the command found no model" are the same
thing — they are opposite conclusions from identical-looking silence.

## Output of this stage

A `VERIFIED` list of: outstanding elements, findings by severity, both gap
directions, and which items carry a criterion. Nothing inferred.
