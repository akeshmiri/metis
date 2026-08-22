# v1 Cypher schema — superseded

These three files were the hand-maintained Neo4j schema for the v1 ontology's 45
labels. Nothing reads them.

**The current schema is generated, not written.**
`metis-server/metis_mcp/ontology/labels.py` is the single source, and
`ontology/schema.py` emits `metis-server/schema/metis2-01-constraints.cypher`,
`metis2-01-constraints-enterprise.cypher` and `metis2-02-relationships.cypher`
from it. Two places that cannot drift is strictly better than two places kept in
step by discipline — which is exactly what these files failed at.

Regenerate with:

```bash
cd metis-server
uv run python -c "from metis_mcp.ontology import schema; schema.write('schema')"
```

The Community/Enterprise split is real: existence constraints are an
Enterprise-only feature, so they are emitted commented-out in the Community file
and live in the `-enterprise` one.

`superseded/metis-graph-03-postgres-schema-SUPERSEDED.sql`, if present, predates
even that — it is the pre-single-database design, kept only as a record of the
decision to consolidate on Neo4j.
