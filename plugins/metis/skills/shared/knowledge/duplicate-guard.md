# Duplicate guard — check before you create, and never assume absence

Before creating anything durable — a test case in a tracker, a document in a
team's repository, a node in the graph — establish whether it already exists. If
it does, **a person decides** whether to update it or add another. Nothing here
decides that, and nothing overwrites.

## Four verdicts, and only one of them proceeds

| Verdict | Meaning | Effect |
|---|---|---|
| `no_match` | searched, found nothing | create |
| `exact_match` | the same item exists | **stop**, ask |
| `similar_match` | something materially close exists | **stop**, ask |
| `unknown` | **the check could not run** | **stop** — never read as `no_match` |

**The fourth row is the whole point.** An unreachable tracker, a timed-out
query, a ledger that has never recorded anything: none of these is evidence of
absence. Treating a failed lookup as "nothing found" is how a second copy of
everything gets created, and it is indistinguishable from a correct run until
somebody looks at the tracker.

## Where Métis had exactly this bug

Worth keeping, because it is the concrete form the mistake takes here.

Nothing ever wrote `PublicationLedger.published` — only deserialisation and the
tests did. `compare` read the resulting empty map and reported *"no published
case for this path"*, which is a claim of knowledge. Under `DryRunTransport`
that is invisible, because nothing is sent either way. The moment a live
transport ran against such a ledger, every case would read as new and be created
a second time.

Two things fixed it, and both were needed: `drift.record_publication` gives the
ledger something to see, and `ledger.live_publications == 0` makes "cannot tell"
say so instead of saying "no".

## What this is not

**Not a coverage check.** "Is this behaviour already covered?" is a question
about adequacy, and `coverage`/`coverage_report` answer it. This asks a narrower
mechanical one: *am I about to create a second copy of this thing?* Both apply;
neither substitutes for the other.

**Not the G2 gate.** G2 asks a human whether to publish a batch at all.
This asks whether one item in it already exists. A confirmation to publish is
not a decision to overwrite — approving a batch is not approving a replacement
of something somebody edited by hand (T-15).

## Asking

When something exists, put the choice as a question with real options and wait:

> A `<kind>` named `<identity>` already exists: `<match>`.
> Update the existing one, or create a new one alongside it?

Silence is not consent, and neither is a bare "yes" to a different question.
Approval of an earlier step never carries: a person who approved a test design
has not approved overwriting last week's published cases.

**Never supply the answer on the user's behalf**, including when they have said
to go ahead in general terms — the same rule the gate literals carry (T-18).

---

**Ported from Atlas** (`.agents/skills/shared/knowledge/duplicate-guard.md`).
What changed: Atlas's version routes through its own `duplicate_guard.py` and a
CLI with exit codes, and covers artifacts Métis does not produce — merge
requests, defects, generated code. What crossed is the verdict vocabulary and
the rule that `unknown` blocks, because Métis had the same defect in its
publication ledger and could not see it. Atlas's autopilot mode did not cross:
Métis has no unattended-run concept, and `METIS_ALLOW_EXTERNAL_WRITES` plus a
literal in the run already carry that weight.
