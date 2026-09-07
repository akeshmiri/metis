# 1 · Read what is actually there

## Lock the subject before you read

A half-formed intent invites filling in. Before anything else, establish **which
claim this is about** and record everything else as related rather than merging
it in — the scope lock in
`../../shared/knowledge/anti-hallucination-protocol.md`, applied to analysis.

A key appearing in a commit message is evidence the commit touched it, not
evidence it is in scope.

## Actions

1. `analysis_report(document_json, journey=...)`. Pass `journey` — it is what
   lets the **design** aspect be gathered from the real model. Without one the
   design half is answered from the ledger alone, and `journey_consulted: false`
   is reported so a reader knows which it was.
2. `check_intent(document_json)` for an intent file specifically. It is the
   reader that answers *is every need specified*, and it was reachable only from
   the CLI before this.
3. Read `subjects` in full. A document with no claim in it is a finding about
   the document.

## What each blocking gap means

| Gap | Why it blocks |
|---|---|
| a need with no statement | an intent with no words is a label, and nothing can be checked against a label |
| a need with no specification | landing it creates a node nothing can ever be checked against (D-1) |
| a specification pointing at no need | the same dangling reference, from the other end |
| two claims sharing an id | one silently replaces the other |

Everything else is **reported and imported**. Say so when you report it: a long
gap list on a `ready` claim is normal and is not a reason to send it back.

## Report

The claims found, the blocking gaps with the exact reason, and the reported gaps
by aspect. Then `02-consult.md`.
