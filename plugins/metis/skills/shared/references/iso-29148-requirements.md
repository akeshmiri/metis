# Requirements engineering — ISO/IEC/IEEE 29148

**A side reference, not loaded by default.** Consult it when a requirement has to
be judged against a published definition rather than against taste — somebody
disputes an EARS refusal, or asks what makes a criterion acceptable.

It would still be true if Métis were deleted, which is why it is a reference
rather than knowledge.

**Shared, because four skills consume it**: `metis-business-analyst` reads a
stated intent, `metis-knowledge-capture` formalises it into criteria,
`metis-intake-processor` lands what a tracker says, and `metis-spec-writeback`
regenerates the specification a team reads.

## What the standard is

29148 covers the requirements engineering processes across the life cycle and
defines the **characteristics of a well-formed requirement** and of a
well-formed requirement *set*. It is the published answer to "what makes this
sentence a requirement rather than a wish".

## The characteristics of a single requirement

The standard's list, and what Métis can and cannot check:

| Characteristic | Checkable? | Where |
|---|---|---|
| Necessary | no | why a requirement exists is a stakeholder's judgement |
| Appropriate | no | the right level of abstraction is a judgement too |
| Unambiguous | **partly** | `ac_quality` flags unmeasurable qualifiers — "fast", "user-friendly" |
| Complete | **partly** | `check_ears` refuses text with no trigger or no response |
| Singular | **yes** | `ac_quality` flags non-atomicity; T-1a forbids two assertions in one case |
| Feasible | no | requires knowing the implementation cost |
| Verifiable | **partly** | the design's `conditions` section asks whether anything could ever test it |
| Correct | no | whether it states the real need is exactly what a person must decide |
| Conforming | **yes** | EARS pattern conformance, `ears_checker.py` |

**Six of nine are not computable, and saying so is the point.** A tool that
reported a requirement "conformant" would be answering the three it can and
implying the six it cannot.

## Why EARS, and why free prose is refused

Métis represents a requirement only where the text is EARS-conformant.
`ears_pattern` has no empty form: a sentence with no trigger and no response
cannot be turned into one without inventing the missing half, and inventing it is
what `ac_mining` refuses to do (S-13).

So free prose — most Jira titles — lands as a `Finding` pointing at
`knowledge-capture`, not as a `Requirement`. That is a **narrow** refusal: it
means the claim cannot be *represented* (D-1), never that it is a bad idea. A
claim nobody has costed, whose environments are unlisted and which has no
criteria yet, is `ready` and lands carrying all of those gaps.

## The requirement set

29148 also defines characteristics of a *set*: complete, consistent, affordable,
bounded. Métis checks **consistency** against what the model already holds —
`metis-knowledge-capture` reports what contradicts it and what is new — and
checks none of the other three, each of which needs information about the project
rather than about the text.

## What this reference does not do

It does not reproduce the standard, and Métis makes no conformance claim against
it. Conformance to a sentence pattern is not correctness of a claim: `check_ears`
decides whether text can be represented, and whether it is the *right*
requirement stays a person's decision. `ac_quality` is advisory and blocks
nothing (S-4).
