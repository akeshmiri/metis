# 3 · Ask what Métis cannot derive

## Put the questions as written

`design_inputs()` carries the exact wording. Use it. A topic gets a shrug; a
question gets an answer:

> ❌ "What's the architecture?"
> ✅ "What does this run as, and what does it talk to? Name the processes, the
> datastores and the systems you do not own."

## Ask the right person

| Question | Usually |
|---|---|
| `runtime_architecture` | whoever owns the service, or its architect |
| `design_specification` | the author of the change, if there is one at all |
| `environments` | the delivery or platform lead |
| `test_data_constraints` | data protection, or whoever provisions the environment |
| `nfr_targets` | the person who asked for the feature — and the answer is often "nobody has said" |
| `security_obligations` | legal, compliance, or the contract owner |
| `entry_exit_criteria` | whoever decides the release |

## Record the answers where the next run will find them

Put them in the document. Regeneration preserves the human columns, so an answer
given once is not asked for again — and a question asked twice is how a process
teaches people to stop answering it.

## If the answers do not come

Say so. An unanswered required input keeps the design `incomplete`, and that
word is the finding: *nobody has said what this runs on*. That is a real,
reportable state and it is more useful than a section somebody invented to fill
the page.

**"Nobody has stated an SLA" is an answer.** It makes every performance row
`no-basis`, which is correct and is not the same as "none of these need load
testing".
