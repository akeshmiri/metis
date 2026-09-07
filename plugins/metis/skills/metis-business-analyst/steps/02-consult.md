# 2 · Consult the other three readings

## Do not reimplement them

Three of the four readings belong to skills that already run the procedure.
`analysis_aspects()` names them. Consult; do not restate.

| Reading | Route to | Ask it for |
|---|---|---|
| requirement | `metis-knowledge-capture` | EARS conformance, and atomic criteria where there are none |
| design | `metis-test-design` | is this testable at all, and what would it take |
| risk | `metis-risk-manager-requirement-risk` | what does being wrong cost, and how settled is it |

**The design reading is the one an intake process normally has no reader for**,
and it catches the expensive mistake: a claim that is well worded, agreed, and
impossible to verify. Asking before the work starts costs one question; asking
after costs the build.

## Put the questions as written

`design_inputs()` and `risk_inputs("requirement")` carry the exact wording. A
topic gets a shrug; a question gets an answer.

The two that matter most here, because nothing downstream works without them:

> If this requirement is wrong, or never built, what does the business actually
> lose? Name the consequence, not a severity word.

> What does this run as, and what does it talk to? Name the processes, the
> datastores and the systems you do not own.

## Forbidden substitutions

- Do not answer a question on the requester's behalf, however obvious it looks.
- Do not convert "nobody has said" into a default. `incomplete` and `no-basis`
  are the values, and both are printed.
- Do not treat a criterion the document claims about itself as a criterion
  (S-13). Count it; do not trust it.

## Report

What each consulted reading found, and which questions are still open with the
name of who owes each answer.
