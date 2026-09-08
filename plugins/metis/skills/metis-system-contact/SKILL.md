---
name: metis-system-contact
description: Touch the system Métis models — read a live database or cluster, or drive load against it — after stating which tier is in force and what a fact observed there may and may not be used for. Use when someone asks Métis to look at a running system, collect cluster or query evidence, or run a load scenario. Not for anything recovered from source; that is metis-model-build.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - describe_execution
  - describe_policy
  - why_read_only
  - get_model
  - coverage_report
  - test_design
  - classify_failure
---

# Métis system-contact

Every other skill here reads what was recovered from source. This one reaches a
running system, and that difference is the whole reason it has its own rules.

**X-7a used to say Métis never touches the system it models.** That prohibition
was lifted by an explicit product decision. What it protected was not.

## The tier, and why it is the first thing you do

`METIS_EXECUTE` is `off` | `observe` | `run`, enforced in one place
(`metis_mcp/execution.py`) the way `policy.py` enforces writes.

**At `off` — the default — `observers/` and `runners/` are never imported.** The
tools below do not exist on the surface; they are not refused, they are absent.
So the old guarantee still holds by construction for any deployment that did not
ask for this, and `test_execution.py` proves it in a subprocess.

**Call `describe_execution()` first, every time, and say what it returns before
you act.** It reports the tier in force, which optional clients are installed
(`metis[execute]`, `metis[load]`), and what a run costs. A default install has
none of those clients, so a refusal must name the missing extra rather than
surface an `ImportError` three frames down.

Do not infer the tier from a tool being present or absent in your own list. Ask
the deployment.

## The rule the tiers exist to keep

**A fact observed from a running system is labelled
`observed_from_running_system` and is never merged with one recovered from
source.** They are different claims.

This is not bookkeeping. §8.7 staged the execution labels out precisely because
merging the two turns coverage into correctness (C-11), and C-10 still holds:
nothing observed here writes the coverage ledger. A transition can be fully
covered and currently failing, and Métis reports both halves without letting
either stand in for the other.

So when you report what you saw:

- say it was observed, and when;
- never fold it into a coverage figure, a readiness percentage, or a total that
  also contains something recovered from code;
- an observation that contradicts the model is a **finding about one of them**,
  and which one is a person's call.

## What each tier buys

| Tier | May | Costs |
|---|---|---|
| `off` | nothing — the modules are not imported | the default |
| `observe` | read a live system: SQL, cluster logs and health | the `metis[execute]` extra |
| `run` | also make something happen: drive load | the `metis[load]` extra, **and** the literal `execute` in the call |

**The literal is not a formality.** `run` changes the state of somebody's
system. A caller that cannot supply the word has not been authorised to do this,
and neither have you on their behalf.

## Steps

`steps/01-tier.md` — establish and state the tier. Then `steps/02-observe.md`
for reading, and `steps/03-run.md` only if the tier is `run` and the request
actually asked for load.

## What this skill must not do

1. **Never act before stating the tier.** A reader who does not know whether
   Métis touched their system cannot judge anything else you tell them.
2. **Never merge an observation with a recovered fact.** Not in a count, not in
   an average, not in a sentence that implies one corroborates the other. This
   is C-11 in the place it does the most damage.
3. **Never write the coverage ledger from anything observed here** (C-10).
   *Is this tested* and *did it pass* stay two figures.
4. **Never run load to "see what happens".** A load scenario needs a sized
   target; without one the performance verdict is `no-basis`, and a number with
   no threshold is one nobody can call a pass or a failure.
5. **Never treat an absent tool as a refusal you can work around.** At `off` the
   modules are not imported by design. Report the tier and stop.
