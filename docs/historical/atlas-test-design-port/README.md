# The Atlas test-design port

Six files, ported from Atlas's `test-designer` skill and never rewired.

They were reachable from nothing. No `SKILL.md` referenced them, no Python read
them, and their own cross-references pointed at things that do not exist in this
tree: a `test-designer` skill, a "Stage 08 Gate", and a `resources/templates/`
path. The four ISO/IEEE files are maps *into* `test-design-template.md` — a
table per standard saying which section of the template covers which clause — so
they have no meaning once the template is not the artefact anybody produces.

Métis does not produce a test-design document from a template. It renders test
cases through `metis_mcp/rendering/test_case.py` and the stakeholder
specification through `metis_mcp/specgen/`, both from an approved model.

**Kept for the standards mapping**, which is real work and would be tedious to
redo: if Métis ever needs to defend its output against ISO/IEC/IEEE 29119 or
IEEE 829, the clause-by-clause tables here are the starting point.

Two files from the same port stayed in the skill tree because they stand on
their own and are still referenced:

- `plugins/metis/skills/shared/knowledge/anti-hallucination-protocol.md` — four
  skills cite its gates.
- `plugins/metis/skills/shared/knowledge/test-techniques-reference.md` — makes
  no reference to the template.
