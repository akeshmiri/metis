# Step 2 — Plan (P)

**Scope Lock (carried from Step 1):** the same one `<journey>`-`<surface>`
model. A cross-surface question is a second model and a second run.

## Actions

1. **Run all four checks in one command.** They are one gate, not four, and
   running them together is what makes the output comparable between runs.
   ```
   metis validate --journey <j> --surface <s>
   metis validate <model.json>
   ```

2. **Sort the findings by severity, and keep the three apart.**

   | Severity | Means | What you do with it |
   |---|---|---|
   | `blocking` | this is wrong | generation is blocked (M-18); name the elements |
   | `unverifiable` | this cannot be *shown* to be right | report as its own outcome — never as a pass, never as a failure (M-17) |
   | `advisory` | neither | report, do not gate on it |

   Quote each finding's `detail` verbatim. "3 problems" is not something anybody
   can act on, which is why `require_valid` prints the findings and not a count.

3. **For a determinism finding, quote both guards.** The finding names the
   conflicting pair. Which one should win — or whether they are one transition —
   is a modelling decision, and picking silently produces a machine that
   validates and does not describe the system.

4. **For a guard-completeness finding, name the input that matches nothing.**
   This is the check worth the most: an interaction matching no transition is
   silent everywhere, including in the graph.

5. **Form the recommendation.** *Well-formed* only when there is no `blocking`
   and no `unverifiable` finding. A model with unverifiable findings is
   **not** well-formed — it is unproven, and saying so is the whole point of the
   third outcome.

## Confidence tagging

Every finding is `VERIFIED` — it is the checker's real output, not inference.
The recommendation is `VERIFIED` when it is a direct summary of those findings.
Do not add commentary about what the author probably meant.

## Drift check

Confirm the findings belong to the model you locked in Step 1 — check the model
id in the output header, not just the journey you typed. A stale `.review.json`
overlay is refused rather than applied (E-8), and that refusal is itself a real
finding to report.

## Output of this stage

Every finding, grouped by the three severities and never merged, each quoted
verbatim with its elements; and one recommendation. Nothing inferred.
