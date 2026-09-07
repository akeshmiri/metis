# 2 · Ask the five Métis cannot derive

## Put the questions as written

`risk_inputs("requirement")` carries the exact wording. Use it. A topic gets a
shrug; a question gets an answer:

> ❌ "What's the business impact?"
> ✅ "If this requirement is wrong, or never built, what does the business
> actually lose? Name the consequence, not a severity word."

The second one is answerable by somebody who does not think in severity scales,
which is most of the people who know the answer.

## Ask the right person

| Question | Usually |
|---|---|
| business criticality | the person who asked for the requirement |
| volatility | the same person, or whoever owns the roadmap |
| regulatory exposure | legal, compliance, or the contract owner |
| stakeholder agreement | the requester — and the answer is often "no, that is my write-up" |
| external dependency | the delivery lead |

## Turn the answers into ratings

Business criticality becomes the **impact**; volatility becomes the
**probability**. Then `risk_exposure(probability, impact)` — never multiply in
prose, and never convert a qualitative answer into a number without saying who
made the conversion.

Once a person supplies these, the rating is **theirs**. What stays true is that
the risk was *identified* by the model, which `derived_from` continues to record.

## Record the answers where the next run will find them

Put them in the document. `metis risk assess` preserves the human columns across
regeneration, so an answer given once is not asked for again — and a question
asked twice is how a process teaches people to stop answering it.

## If the answers do not come

Say so. An unanswered required input keeps the assessment `incomplete`, and that
word is the finding: *nobody has said what is at stake*. That is a real,
reportable state and it is more useful than a rating somebody invented to close
the row.
