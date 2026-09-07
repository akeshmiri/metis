# 3 · Consolidate, and say what may happen next

## Actions

1. Write the document: `metis intent review <file> -o review.md`. It carries
   every gap with the aspect that found it and what would close it.
2. State the verdict in the narrow sense it has:
   - **`not-ready`** — name the blocking gaps and what has to change in the
     claim. There is no literal that passes this.
   - **`ready`** — say it can be landed at `Quarantine`, that nobody has agreed
     with it, and that the reported gaps travel with it to G1.
3. Add what none of the four readers can see. A gap an analyst writes into the
   document by hand survives regeneration, and it is the reason the file is
   editable.

## The hand-off

| If | Then |
|---|---|
| `not-ready` | send it back with the specific gap. Do not land it, and do not soften the reason |
| `ready`, gaps open | `metis intake land` or `metis intent land`, and say which questions are still open at G1 |
| criteria missing | `metis-knowledge-capture` — it is the skill that produces them |
| nobody has costed it | `metis-risk-manager-requirement-risk`, and its assessment reports `incomplete` until answered |

## Forbidden substitutions

- Do not present a gap count as a quality score. The four aspects are not
  commensurable, and averaging them lets a missing statement hide behind a
  missing environment list.
- Do not report `ready` without the gap list. That is the half that makes it
  safe to read.

## Report

The verdict in its narrow sense, the blocking gaps if any, the open questions
with owners, and where the document was written.
