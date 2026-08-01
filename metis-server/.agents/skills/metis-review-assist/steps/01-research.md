# Step 1 — Research (R)

**Scope Lock:** this stage covers exactly one node id — the quarantined
item the user named. Do not follow references to other quarantined items
and start reviewing them too; note them as related, don't drift onto them.

## Actions

1. Call `metis_get_context(anchor=<the node id>)`.
   - If `found: false`: stop here. Tell the user this id doesn't exist in
     the graph. Do not guess a similar-looking id and substitute it
     (Forbidden Substitutions) — ask the user to confirm the correct id.
   - If `found: true`: record `text`, `source_file`, `source_heading`,
     `references`, `referenced_by` verbatim. These are `VERIFIED` facts —
     they came directly from a real tool call, not inference.

2. Call `metis_get_traceability(node_id=<the node id>, direction="both")`.
   Record the real `upstream`/`downstream` hop lists. These are also
   `VERIFIED` — real BFS results, not guessed relationships.

3. Call `metis_explain_decision(node_id=<the node id>)` for the
   corroboration count and provenance.

## Confidence tagging

Tag every fact you're about to carry into Step 2:
- `VERIFIED`: came directly from one of the three calls above.
- `INFERRED`: a reasonable reading of the VERIFIED facts (e.g., "this item
  looks isolated" from an empty `references`/`referenced_by` list) — label
  it as inference, don't present it as fact.
- `UNVERIFIED`: anything you don't actually have tool output for. Don't
  carry these into a recommendation without flagging them.

## Drift check

Re-read the Scope Lock above. Did this stage stay on the one locked node
id, or did it wander into summarizing unrelated items? If it drifted,
redo this stage focused back on the locked id.

## Stage Confirmation

Present real findings (not a summary that hides the actual tool output) and:

```
[C]ontinue to Plan
[R]eview this stage in detail
[B]ack — re-run Research
[X]it
```
Do not proceed to Step 2 without an explicit choice.
