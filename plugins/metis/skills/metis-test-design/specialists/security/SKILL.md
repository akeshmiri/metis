---
name: metis-test-design-security
description: Design the authorisation and authentication conditions each call carries, including the negative condition an API suite usually lacks, and refuse to read an unrecovered check as an absent one. Use when a request is about auth, roles, permissions, or testing that the wrong caller is refused.
allowed-tools:
  - design_sections
  - design_inputs
  - design_report
  - auth_facts
  - get_model
  - get_requirement
  - search_knowledge
  - product_risk
  - ask
  - run_status
  - list_workflows
---

# Métis test-design · security

## Prerequisites, from the parent

The parent (`metis-test-design`) has already established, and this skill does
not re-derive:

- a design missing a required input is `incomplete`, never lean;
- the shape comes from `design_sections()` and is never restated in prose;
- rows are ordered by risk, and a band ranks — it never forecasts;
- Métis proposes every row and decides none of them.

This skill owns the `security` section.

## What this does

States what each call requires of a caller, from what extraction recovered, and
puts the **negative condition** beside it: the identity that must be refused.

## The negative condition is the column that matters

A recovered authorisation check with no case for the caller who must be refused
is asserted by nothing, and that is the ordinary state of an API test suite.
Métis can state the complement as a condition. It cannot say whether the check
is the right one — which is why `security_obligations` is asked.

## The most dangerous empty section in the document

An empty security section looks identical whether **nothing is exposed** or
**nothing was read**. Declarative security is all extraction can see: an
annotation is recoverable, a check written inside a method body often is not.

So an empty result here is a finding to confirm, never evidence that a surface is
open by design — and saying so is this specialist's main job.

## Steps

`steps/01-recovered.md`, then `steps/02-negative.md`.

## What this skill must not do

1. **Never read an absent finding as an absent control.** Nobody looked is not
   nothing there.
2. **Never rate a control.** Whether a role is the correct one, and whether being
   wrong is a compliance event, are answers a person gives.
3. **Never state a credential, a token or a role value.** The condition is
   "a caller without the required authority", and that is the whole of it (M-9,
   X-6e).
4. **Never design an attack.** This states the conditions a functional test must
   satisfy. Penetration testing is a different discipline with a different
   authorisation.
