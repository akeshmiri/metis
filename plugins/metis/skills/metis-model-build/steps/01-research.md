# Step 1 — Research (R)

**Scope Lock:** one service, one surface. A monorepo report covers many; the
scope is the one the user named.

## Actions

1. **Establish what exists before running anything.**
   ```
   python3 -m metis_mcp.mbt.cli sources
   python3 -m metis_mcp.mbt.cli workflow status model-build--<scope>
   ```
   A run may already be halted at G1 — in which case this is a *review* task, and
   `metis-review-assist` is the skill, not this one.

2. **Locate the pack reports**, and confirm which commit they describe. A report
   whose `commit` does not match the code the user is asking about describes a
   different system; stop and ask rather than extracting from it.

3. **Confirm the service scoping.** If the report spans several services, the
   `--service` value must be one of them. The source refuses an unscoped
   multi-service report — that refusal is correct, not an obstacle to route
   around.

## Forbidden substitutions

Do not fall back to `--source authored` because `--source code` failed. They
record different provenance, and swapping them to get a green run is precisely
the substitution that put `hand_authored` on thirteen statically-analysed models.
