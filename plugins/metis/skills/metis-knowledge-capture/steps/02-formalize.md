# Step 2 — Formalize (P)

**Scope Lock (carried from Step 1):** the one statement, the one model. This
step writes a file and runs one free check. It touches no graph.

## Actions

1. **Split the statement into behaviours, one at a time.**
   *"an admin can archive, restore and export"* is three behaviours. Each becomes
   its own criterion: one condition, one action, one validation. Never one
   criterion listing three actions, and never a criterion naming a permission
   ("an admin has full access") — a permission is not a behaviour and nothing
   can be tested from it.

2. **Write each criterion in a shape `ac_mining` parses.** Two, and only two:
   ```
   Given <situation>, when <one action>[, and <one condition>], then <one outcome>.
   While <situation>, when <one action>, the <system> shall <one outcome>.
   ```
   The condition clause is introduced by `, and` — with the comma. Without it,
   `and` reads as a second action and the check rejects it. That is deliberate:
   English does not distinguish the two readings and the punctuation does.

3. **Draft the complement of every positive criterion**, and label it.
   `polarity: "negative"`, `derived: "inferred_complement"`, `complement_of` set
   to the id it complements. Nobody stated it; the file says so. It is still a
   real requirement and still needs its own test.

4. **Fill `source_statement` on every entry**, including inferred ones. Every
   word you used should be traceable to it. A criterion containing a noun the
   person never said is a widening, not a formalisation — ask instead.

5. **Run the check. It is free — no graph, no model call.**
   ```
   python3 -m metis_mcp.mbt.cli knowledge check <knowledge.json>
   ```
   It reports every defect at once. Fix them all and re-run until it is clean.

## Confidence tagging

Tag each criterion in your working notes:

- `VERIFIED` — every word traceable to the statement.
- `INFERRED` — the complement, or a situation you supplied. Must be
  `derived: "inferred_complement"`, or asked about before it goes in the file.
- `ASSUMED` — **not allowed in the file.** If you needed to assume it, ask.

## Output of this stage

A knowledge file that `knowledge check` reports clean, and a note naming which
entries are inferred and why. Show the person the inferred ones explicitly before
running anything against the graph — they are being asked to own a requirement
they did not write.
