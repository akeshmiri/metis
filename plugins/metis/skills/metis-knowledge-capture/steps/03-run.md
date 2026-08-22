# Step 3 — Run (I)

**Scope Lock (carried from Step 2):** the checked knowledge file. This step
proposes; it never decides.

## Actions

1. **Compare before landing.**
   ```
   python3 -m metis_mcp.mbt.cli knowledge compare <knowledge.json> --journey <j> --surface <s>
   ```
   Read the three counts and report them **separately** (F-5):
   *already in the model* · *contradicting* · *new*. Never a percentage, never a
   single "reconciled" figure.

2. **If anything contradicts, stop and present it.**
   Quote both guards — the model's and the statement's — with the transition
   they disagree about. Then say plainly that neither wins automatically (S-10):
   the model may be recording a defect, or the statement may be out of date, and
   only a person can tell which. Do not pick.

3. **Run the workflow.**
   ```
   python3 -m metis_mcp.mbt.cli workflow run knowledge-capture --scope <scope> \
       --knowledge <knowledge.json> --journey <j> --surface api
   ```
   Exit `5` is the expected outcome: the run halted at G1 with the criteria
   waiting for a reviewer. It is **not** a failure, and reporting it as one
   trains people to ignore the gate.

4. **Hand over the decision, do not make it.**
   ```
   python3 -m metis_mcp.mbt.cli review export --journey <j> --surface <s> -o review.json
   ```
   Say which entries are inferred complements, and that approving one unchanged
   leaves it `code_derived` — it documents the system without validating it
   (S-19). The value is in the edits.

## Drift check

Re-running the same unchanged file must report **nothing new**. If `compare`
says `ADDED` for behaviour already in the model, something is wrong with the
natural key, not with the model — report it rather than landing duplicates.

## Output of this stage

A run id, the three counts stated separately, every contradiction quoted with
both sides, and the exact `review export` command. No decision recorded here.
