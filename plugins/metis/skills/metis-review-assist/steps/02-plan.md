# Step 2 — Plan (P)

Form a recommendation per element. Do not apply anything in this stage.

## Actions

1. **Group the outstanding elements by what the evidence says**, not by kind:

   | Group | Evidence | Usual recommendation |
   |---|---|---|
   | Clean | no findings, matched by an intent-backed criterion | approve |
   | Unspecified | real behaviour, no criterion describes it | approve the *behaviour* if it is real, and record the specification gap |
   | Unverifiable guard | M-17 finding | do not approve silently — the reviewer accepts the risk explicitly or the guard gets checked |
   | Blocking finding | determinism, reachability, observability | reject or fix; approving leaves a model that generates confidently wrong tests |

2. **For each item carrying a criterion**, decide which of three applies, and say
   which — they are different acts with different consequences (S-19):

   - the criterion is right → approve, leaving it `code_derived`;
   - the criterion is *nearly* right → **edit `criterion_text`**, which promotes
     it to `human_confirmed`;
   - the criterion is right and the reviewer has genuinely checked it against
     what the business intends → set `affirmed_as_intent: true`.

   Never recommend the third across a batch. Affirming without editing is
   legitimate for one criterion somebody thought about; it is not legitimate for
   two hundred.

3. **Confidence-tag every recommendation** `VERIFIED` / `INFERRED` /
   `UNVERIFIED`, and never carry an `UNVERIFIED` item into step 3 without saying
   so to the user.

## Gate

Show the user the grouped recommendation and **wait**. This is the point of the
whole skill: the reviewer decides, and they need the evidence in front of them
when they do.
