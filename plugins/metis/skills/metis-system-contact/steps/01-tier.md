# 1 · Establish the tier, and say it out loud

**Run** `describe_execution()`.

**Report**, before anything else and in your own first sentence:

- the tier in force (`off`, `observe`, `run`);
- which optional clients are installed, and which are not;
- what that means for the request you were given.

**Do not substitute** your own list of available tools for this answer. At `off`
the observer and runner modules are never imported, so their tools are *absent*
rather than refused — and an absent tool looks identical to a tool you simply
were not granted. Only `describe_execution()` distinguishes the two.

## If the tier does not permit what was asked

Stop and say so plainly, naming what would have to change:

- `off` → `METIS_EXECUTE=observe` is a deployment decision somebody makes on the
  machine. It is not something a caller can supply in a request.
- a missing client → the extra by name (`metis[execute]`, `metis[load]`), from
  `execution.REQUIREMENTS`, so the reader installs the right one.

**A refusal here is a complete answer.** Do not offer to approximate the
observation from what was recovered from source — that is precisely the merge
this skill exists to prevent, and it would be the worst possible substitution:
confident, plausible, and about a different system state.
