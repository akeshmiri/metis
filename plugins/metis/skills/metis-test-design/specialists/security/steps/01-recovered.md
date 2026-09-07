# 1 · What was recovered

## Actions

1. `design_report(journey, surface, section="security")`.
2. `auth_facts` for the declarative detail, and read its caveat: declarative
   security is all extraction can see.
3. Report the count of calls carrying a recovered check **and** the count
   carrying none. The second number is the one that needs confirming.

## Forbidden substitutions

- Do not describe a call with no recovered check as "public". Describe it as
  "no declarative check recovered", which is what is true.
- Do not infer a role from an endpoint path or a method name.

## Report

Recovered scheme and authority per call, and the calls where nothing was found.
