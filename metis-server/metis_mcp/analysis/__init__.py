"""Pre-import analysis: reading a stated intent before it becomes a node.

`gaps` is the taxonomy, `readiness` composes the four readings, `document`
renders the result as something a person edits, and `areas` records which skill
owns which reading. Everything here is pure — the graph-reading halves are
passed in by the caller, which is what keeps the whole family testable with no
Neo4j.
"""
