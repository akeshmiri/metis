# Requirement condition coverage

Use this when a stated requirement or a recovered guard is turned into
acceptance criteria. It is a decomposition aid, **not permission to invent a
requirement** — every row it produces lands at `Quarantine` like everything else
(S-4), and a human settles it.

## The problem it solves

A positive criterion says what the system does. It does not say what the system
must reject, prevent, limit or leave alone. Métis draws exactly one complement
today — the negative branch of a guard — and stops. The other seven classes below
are undrawn, which means they are neither present nor *visibly* absent.

The required decision is the whole mechanism. A requirement with no documented
numeric limit still needs a `boundary` row marked `not-applicable` **with a
reason**; what it must not do is silently disappear.

## The eight condition classes

Record one row per applicable class, and an explicit `not-applicable` with a
reason when a class does not apply.

| Class | The question | Where Métis already has machinery |
|---|---|---|
| `allowed` | What is permitted and produces the intended outcome? | the transition itself |
| `prohibited` | What must be rejected, prevented, or never changed? | `inferred_complement` |
| `partition` | Which valid and invalid input classes exist? | `mbt/dimensions.py` |
| `boundary` | Which limits, thresholds, lengths, counts, dates matter? | `mbt/criteria.py` |
| `state-transition` | Which states permit or block the action? | the machine; `validate` |
| `authorization` | Which actors, roles, scopes may and may not act? | `auth_facts` |
| `dependency-failure` | What happens when a required dependency fails? | — undrawn |
| `non-goal` | What is explicitly outside this change? | — undrawn |

## Evidence, in Métis's own vocabulary

The source protocol carried five evidence states. Three of them are S-19
provenance grades Métis already stores, and using those instead of a parallel
vocabulary is the point of porting this rather than copying it:

| The condition is… | Métis records it as |
|---|---|
| stated by an independent source | `independently_authored` — intent |
| confirmed by a contract or the implementation | `code_derived` — **coverage, never correctness** (§4.1) |
| confirmed by a person | `human_confirmed` |
| a risk-based candidate nobody has confirmed | `code_derived`, left at `Quarantine` |
| not established by the source | a `Finding`, not a criterion — and the run says so |
| not applicable | an explicit decision, with its reason |

`code_derived` may become a criterion even when the stated requirement is silent,
and it stays labelled as what it is. A criterion written *from* the code and used
to check that code can only ever report agreement — which is why the grade is
load-bearing and not decoration.

## Guardrails

1. **Do not add generic authentication, rate-limiting, concurrency, audit or
   injection conditions because they are common.** Add them only where the source
   or the recovered contract supports them; otherwise record `not-applicable`.
2. **A successful request with invalid input is not a positive variant.** A
   prohibited condition needs its own rejection, no-op or rollback oracle.
3. **A non-goal is not evidence that the system must reject an input.** It limits
   scope; a prohibited condition defines behaviour inside the boundary.
4. **Do not collapse distinct partitions into one "invalid input"** when their
   expected outcomes differ.
5. **Never choose a boundary value by guesswork.** Take it from the schema, the
   code, the configuration or an approved rule — otherwise record it unknown.
   This is the same refusal `ac_mining` makes when text is not EARS-conformant
   (S-13): there is no empty form, and guessing one is the failure mode.
6. **An unknown condition blocks.** It becomes a question for the owner, and
   nothing downstream may treat it as settled.

## Before approving a set, ask

- What is allowed, and what must never happen — and what is the oracle when it
  is attempted?
- Which partitions are valid and invalid, and do their outcomes differ?
- Where are the lower, upper, empty, duplicate, missing and just-outside edges?
- Which actors and lifecycle states change the result?
- What happens when a dependency fails or half-completes?
- What is explicitly out of scope, and what supports that exclusion?
- Which of these answers are facts, which are code-derived, and which are still
  pending confirmation?

---

**Ported from Atlas** (`.agents/skills/shared/knowledge/requirement-condition-coverage.md`).
What changed, and why: the source keyed its evidence states to its own
`canonical-spec.json` handoff and a `condition_id` carried between JSON
artefacts. Métis has no such artefact and does not need one — the graph is the
handoff — so the five evidence states were mapped onto the S-19 provenance
grades the ontology already stores, and the two classes with no machinery behind
them are marked undrawn rather than described as if they worked.
