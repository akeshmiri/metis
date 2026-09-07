# 03 — the publication gate (G2)

## Actions

1. Show the batch **in full** — every case, once (T-17).
2. Say which transport is in force and whether anything will actually be sent.
3. Ask **once**, for the whole batch (T-19), stating that the default is No.
4. On a literal `publish`, run the publish stage. On anything else, stop and say
   nothing was sent.

## Forbidden substitutions

- Do not ask per case. Do not accept `y`, `yes`, `true` or a truthy value: the
  gate costs the exact word, in this run (T-18).
- Do not supply the literal yourself under any circumstance, including when the
  user has said "just do it". The word is the human's or it is nothing.
- Do not imply a timeout means yes. There is no timeout-implies-yes.

## Drift check

The batch shown must be the batch published. If anything changed between the
showing and the confirmation, the confirmation does not carry — re-show and ask
again.

## Report

What was shown, what the answer was, which transport ran, and — plainly —
whether anything left Métis.
