# Step 2 — Classify the repository (CONST-051/052)

**Scope Lock:** the one project/repository being onboarded.

## Actions

1. Determine the real classification: `public_internal`, `confidential`,
   or `restricted` — ask the user, don't infer from the repo name.
2. Add a real entry to `.metis/config.yaml`'s `repositories:` list (see
   `metis.config.example.yaml` for the exact shape) — this is the actual,
   real config `classification_gate.py`'s `ClassificationGate.from_config()`
   reads. Do not classify anywhere else; this file is the single source of
   truth (`config_manager.py`'s whole purpose).
3. If the user doesn't set an explicit classification: per `CONST-052`,
   the repository defaults to `confidential` (fail-closed) — confirm this
   default is what actually happens by running
   `ClassificationGate.from_config(ConfigManager()).check("<the new repo
   name>")` for real and showing the result, not just asserting it should
   work that way.
4. If classified `confidential`: check `zdr.confirmed` in the same config
   file. If `false` (this project's real, current, deliberate value), the
   repository is blocked at the gate until that changes — tell the user
   this plainly, it's a real, current block, not a hypothetical one.

## Stage Confirmation
`[C]ontinue to Step 3` / `[R]eview` / `[B]ack` / `[X]it`
