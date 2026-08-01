// ==========================================================
// Métis Graph Schema -- Part 3: Single-Database Consolidation
// Replaces metis-graph-03-postgres-schema-SUPERSEDED.sql entirely.
// Episode log, review queue, cost tracking, and RBAC all move
// into Neo4j (Enterprise Edition -- see the licensing note in
// the risk register; this schema assumes Enterprise for native
// RBAC and backup/clustering, per the single-database decision).
// ==========================================================

// ---- Episode log (was Postgres metis_graph.episodes) ----
// Already had baseline constraints in 02-entity-specific-constraints.cypher;
// this extends it to be the SOLE episode log, no Postgres counterpart.

CREATE CONSTRAINT episode_unit_id_per_connector IF NOT EXISTS
FOR (e:Episode) REQUIRE (e.source_connector, e.unit_id) IS UNIQUE;
// This is the idempotency guarantee (§10.1) previously enforced by Postgres's
// UNIQUE(source_connector, unit_id) constraint -- Neo4j 2026.x supports
// composite node-key constraints natively, so nothing is lost moving this
// off a relational table.

CREATE INDEX episode_checkpoint_status IF NOT EXISTS
FOR (e:Episode) ON (e.checkpoint_status);
// Supports the §10.2 resume algorithm's "find all PENDING units" query --
// same purpose as the Postgres partial index, expressed as a Neo4j index.

CREATE CONSTRAINT episode_job_id_required IF NOT EXISTS
FOR (e:Episode) REQUIRE e.job_id IS NOT NULL;

// Cost tracking (was Postgres metis_graph.model_call_log) -- attached
// directly to the Episode it was spent producing, not a separate log table.
// This is a deliberate simplification enabled by moving to one database:
// "how much did this episode cost to extract" is now a property lookup,
// not a join.
//   e.extraction_model         -- which model produced this episode's content
//   e.extraction_input_tokens
//   e.extraction_output_tokens
//   e.extraction_cost_usd
//   e.extraction_confirmed_by  -- user id, null if under auto-proceed threshold (§9.2)
// No new constraint needed beyond what Part 2 already requires (source_episode_id
// existence, etc.) -- these are plain properties, aggregated via Cypher
// (SUM/AVG over Episode nodes matching a job_id or date range) rather than
// a dedicated summary table.

// ---- Review queue: eliminated as a separate structure ----
// Was Postgres metis_graph.review_queue. A "review queue" is now just a
// query, not a table that has to stay in sync with the graph:
//
//   MATCH (n) WHERE n.lifecycle_state = 'Quarantine'
//   RETURN n, n.risk_tag, n.triage_reason
//   ORDER BY n.risk_tag DESC, n.t_ingested ASC
//
// triage_reason ('needs_second_source' | 'judge_disagreement' | ...) and
// assigned_reviewer_id become properties on the entity node itself:

// Filtered/partial range indexes (WHERE-scoped CREATE INDEX) are not valid
// syntax on Neo4j 5.26 Enterprise -- confirmed by actually running this
// against a real instance. Dropped the WHERE clauses; these composite
// (lifecycle_state, risk_tag) indexes still serve the triage query above
// equality-then-sort, just without pre-filtering storage to Quarantine rows.
CREATE INDEX review_triage_lookup IF NOT EXISTS
FOR (n:Requirement) ON (n.lifecycle_state, n.risk_tag);
// Repeat this pattern for other entity types that enter Quarantine --
// BusinessRule, Transition, Constraint -- same index shape, per label.
CREATE INDEX review_triage_lookup_ac IF NOT EXISTS
FOR (n:AcceptanceCriterion) ON (n.lifecycle_state, n.risk_tag);
CREATE INDEX review_triage_lookup_br IF NOT EXISTS
FOR (n:BusinessRule) ON (n.lifecycle_state, n.risk_tag);
CREATE INDEX review_triage_lookup_transition IF NOT EXISTS
FOR (n:Transition) ON (n.lifecycle_state, n.risk_tag);

// ---- Identity / access: Neo4j Enterprise native RBAC ----
// Was Postgres metis_graph.users / team_membership. Replaced by Neo4j's own
// role-based access control (Enterprise Edition feature -- this is one of
// the capabilities the Enterprise licensing cost, §15 risk register, is
// actually paying for, so using it natively avoids maintaining a second,
// hand-rolled permission system on top).

CREATE ROLE metis_reviewer IF NOT EXISTS;
CREATE ROLE metis_contributor IF NOT EXISTS;
CREATE ROLE metis_admin IF NOT EXISTS;

// Team-scoping (was Postgres team_membership table) is expressed as
// per-team roles, one pair per owner_team value discovered in the graph --
// generated dynamically as teams are onboarded, not hand-written per team
// here. Pattern for one example team ("billing"), replicated per team by
// the onboarding process (§B.4/BS-004's credential-scoping principle,
// now implemented as a real Neo4j privilege grant instead of an
// application-layer filter):

// CREATE ROLE metis_reviewer_billing IF NOT EXISTS;
// GRANT MATCH {*} ON GRAPH metis NODE Requirement, AcceptanceCriterion, BusinessRule, Constraint, Incident
//   WHERE n.owner_team = 'billing' TO metis_reviewer_billing;
// (Illustrative -- Neo4j's property-based access control syntax should be
// verified against the specific 2026.x Enterprise version deployed; the
// WHERE-scoped GRANT pattern shown is the current mechanism as of this
// schema's writing, subject to the deployed version's exact syntax.)

CREATE INDEX node_owner_team_lookup IF NOT EXISTS
FOR (n:Service) ON (n.owner_team);
// Supports BS-005's re-check-team-scope-at-every-hop requirement --
// every traversal that needs to verify scope mid-walk uses this index.

// ---- Metrics rollup (was Postgres metis_graph.test_run_results) ----
// Handles the 1M+/month test execution volume WITHOUT storing raw
// executions in the graph (see the sizing computation: raw storage is
// 12M nodes/year; a naive daily rollup only cuts that 2x, not enough to
// matter at this scale -- weekly rollup cuts it 15x, which is why this
// schema defaults to a TIERED cadence, not a flat one).

CREATE CONSTRAINT metrics_snapshot_id_unique IF NOT EXISTS
FOR (m:MetricsSnapshot) REQUIRE m.id IS UNIQUE;
CREATE INDEX metrics_snapshot_period IF NOT EXISTS
FOR (m:MetricsSnapshot) ON (m.test_case_id, m.period_start);
CREATE INDEX metrics_snapshot_rollup_tier IF NOT EXISTS
FOR (m:MetricsSnapshot) ON (m.rollup_cadence);

// Tiered cadence rule (application-layer logic, indexed here for the query
// pattern it drives): a TestCase gets DAILY MetricsSnapshot rollups only if
// EITHER (a) it's tagged Performance:SLA-critical (§4.4 taxonomy), OR
// (b) its implementing code changed within the last 14 days (via the
// code-graph CALLS/IMPLEMENTS edges -- a recently-touched test is exactly
// where you want tighter-grained trend visibility). Every other TestCase
// (the large majority at 15,000 scale) gets WEEKLY rollups. This tiered
// approach keeps the "recently risky" subset closely observed while
// avoiding the 12M-node/year cost of treating everything as high-frequency.

CREATE INDEX testcase_needs_daily_rollup IF NOT EXISTS
FOR (t:TestCase) ON (t.performance_sla_critical, t.code_last_changed);

// A MetricsSnapshot node itself does NOT duplicate Athena's raw execution
// rows -- it stores the aggregate (pass_rate, p95_duration_ms, run_count)
// for its period, with a reference field pointing back to Athena's own
// execution-data query (e.g. an athena_query_ref storing enough context to
// re-run the aggregation against Athena's live tables if deeper drill-down
// is ever needed) rather than a copy of every row that produced the number.
