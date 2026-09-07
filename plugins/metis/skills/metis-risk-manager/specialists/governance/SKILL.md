---
name: metis-risk-manager-governance
description: Decide who owns a risk, who may accept one, what escalates and at what threshold, and what the audit trail has to record. Use when a request is about risk roles, escalation, sign-off, accountability or a risk policy.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - describe_policy
  - risk_report
  - risk_register_check
---

# Métis risk-manager · governance  (area 12)

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- risks are ranked and banded against thresholds agreed at planning time;
- every risk has one named owner.

## What this does

The part that makes an accepted risk a **decision** rather than a drift. Roles
and who may accept what (`steps/01-roles.md`), and escalation with its audit
trail (`steps/02-escalation.md`).

Read `../../references/risk-governance.md` for standard practice on roles and
escalation.

## The distinction everything here rests on

**Accepting a risk and failing to respond to one look identical in a register
six months later** — unless the acceptance was recorded with who accepted it,
when, and on what basis. That record is the whole of governance; the rest is
arrangements for producing it.

This is the same principle as Métis's own gates: G1 and G2 halt for a human and
record who decided, because a decision nobody is named for is one nobody made.
`describe_policy` shows how that is enforced for model approval and publication.

## What this skill must not do

- **Never let the risk owner be the acceptor** for anything above the agreed
  threshold. The person managing a risk has an interest in it being acceptable —
  the same reason N-10 stops an author approving their own requirement.
- **Never leave an escalated risk in the project register** as though it were
  still being managed. Escalated means somebody else owns it; if it sits in both
  places it is owned in neither.
- **Never record an acceptance without a name and a date.** Anonymous acceptance
  is indistinguishable from neglect.
- **Never set a threshold you will not enforce.** A threshold that is routinely
  crossed without escalation teaches everybody that the bands are decorative.
- **Never treat a model-derived risk as accepted because nobody rated it.** An
  unrated candidate has not been through any decision at all.
