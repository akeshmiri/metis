# 1 · What this is, and what it is not

## Actions

1. `list_entities` and `get_entity` for the business nouns in the statement.
   Report every noun that resolves to nothing — that is the glossary gap, and it
   is cheap to close now and expensive later.
2. `search_knowledge` for what the graph already holds about this area. A need
   that restates an existing claim is a duplicate, and
   `../../../../shared/knowledge/duplicate-guard.md` has the four verdicts —
   `unknown` blocks.
3. Ask the three questions nobody volunteers:

> Who is this for? Name the role, not "users".

> What does this depend on that we do not own — a team, a supplier, a system?

> What is deliberately **not** in scope here, and who decided that?

## Forbidden substitutions

- Do not answer the third question with "nothing was mentioned". Nothing
  mentioned means nobody has decided, and that is what to report.
- Do not resolve a noun to the closest-matching entity. A near match is a
  different thing with a similar name, and joining on it is worse than not
  joining.

## Report

Entities that resolved and nouns that did not, the actors named, the
dependencies outside this repository, and what is recorded as out of scope —
or that nothing is.
