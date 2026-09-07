# 01 — gather the contract facts

## Actions

1. `payload_shape` for each type the paths touch. Record bounds and
   required-ness; these are what a boundary case is chosen from.
2. `auth_facts` for the journey. **Carry its caveat into the report** — what
   extraction could not see is part of the answer.
3. `call_recipe` for the routes under test, to see the accepted space as a caller
   would meet it.

## Forbidden substitutions

- Do not read a value out of an example in a spec document and use it.
- Do not treat "no security declared" as "open".

## Drift check

Every fact gathered should belong to a transition in the generated paths. A shape
for a type nothing touches is scope creep.

## Report

Types with their bounds, what auth was declared, and what could not be seen.
