# Extraction — all sources follow this pattern

**Used by:** any source in the Supported Sources table (`jira`, `confluence`, `swagger`, `scale`, `code`, `database`) — [intake-processor](../SKILL.md)

**R** Read source data: fetch from API (Jira/Confluence) or parse from file (Swagger/code/schema). Stop and report if source is unreachable or malformed.

**P** Map to UIF: apply the source-specific extractor. Separate FACTS from SPECIFICATIONS. Mark conflicts explicitly — never silently reconcile.

**I** Write UIF JSON to `~/.atlas/tmp/uif/<source>/<scope-id>.json`. Validate schema before write. Report path and key counts on completion.

**Gate** File must exist and pass schema validation before downstream skills may consume it.
