# 2 · Did anybody say how it behaves?

## The question to ask, and who answers it

> You have said what you want. What would somebody *see* the system do that
> would tell them it is working? Describe the behaviour, not the feature.

Ask whoever raised the need. If they cannot answer it, that is the finding —
and it is more useful than a specification you wrote for them.

## What a specification has to carry

| Field | Why it is not optional |
|---|---|
| `statement` | it is the sentence the code is compared against |
| `intent` | a specification pointing at no need is a dangling reference (D-1) |
| `provenance` | `code_derived` can only report that the code agrees with itself (S-19) |
| `entities` | the business nouns, matched against the glossary — a term nobody has defined is its own gap (I-2) |

## Forbidden substitutions

- Do not write the statement and attribute it to the requester.
- Do not fill `entities` from words in the sentence. An entity is a defined
  business noun, and `list_entities` says which exist.
- Do not mark a specification `independently_authored` because a person typed
  it into a ticket after reading the code. That is `code_derived` wearing a
  different hat, and the grade is what keeps §4.1's comparison alive.

## Report

Which needs have a checkable specification, which do not, and — for each that
does not — the exact question that was asked and who owes the answer.
