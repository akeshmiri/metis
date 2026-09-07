# 4 · The design-acceptance gate

## Actions

1. Show the design — the row counts per section, the partial sections, and the
   unanswered required inputs in full.
2. State plainly that Métis proposed every row and decided none of them.
3. Ask **once**, for the whole design, stating that the default is No.
4. On the literal `accept-design` **and** a named identity, resume the run. On
   anything else, stop and say the design stands as a proposal.

## Forbidden substitutions

- Do not ask per section. Do not accept `y`, `yes`, `ok` or a truthy value: the
  gate costs the exact word, in this run.
- Do not supply the literal yourself under any circumstance, including when the
  user has said "just do it". The word is the human's or it is nothing.
- Do not accept because every section built. A full design still needs a person:
  "Métis derived this" is a statement about Métis.
- Do not imply a timeout means yes. There is no timeout-implies-yes.

## Drift check

The design shown must be the design accepted. If the model moved between the
showing and the acceptance, the acceptance does not carry — regenerate and ask
again.

## Report

What was shown, what the answer was, who accepted, and where the document was
written.
