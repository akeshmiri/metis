-- Minimal mock of the Athena schema shape this connector reads (§the
-- athena_internal_read protocol -- see
-- ../../connectors/metis-connector-application-code.json). No real Athena
-- instance is available in this environment (no athena_schema_catalog.py
-- exists here either), so per PLAN.md Phase 2's explicit instruction, this
-- is a minimal mock table matching Athena's declared shape
-- (athena.mv_commits "and related git-derived objects"), not a different
-- shape invented from scratch.
--
-- Scope note: the manifest's entity_type_mapping also covers PullRequest
-- and Commit. This environment has no real git history to draw them from
-- (this directory isn't a git repository) -- rather than fabricate commit
-- authors/dates/messages, this mock covers Repository and source-file rows
-- only, seeded with genuinely real content (this actual codebase's own
-- .py files). Commit/PullRequest ingestion is deferred to when a real (or
-- realistically-seeded-from-real-git-log) source exists, not faked here.

CREATE SCHEMA IF NOT EXISTS athena;

CREATE TABLE IF NOT EXISTS athena.mv_repositories (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS athena.mv_source_files (
    id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL REFERENCES athena.mv_repositories(name),
    path TEXT NOT NULL,
    content TEXT NOT NULL,
    language TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repository_name, path)
);
