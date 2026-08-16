// ==========================================================
// Métis schema — GENERATED from metis_mcp/ontology/labels.py
// Do not hand-edit: regenerate with
//     python3 -m metis_mcp.ontology.schema --write
// Hand-edits are drift, and test_ontology.py will fail on them.
// ==========================================================


// ---- EDITION: enterprise ----
// Property-existence constraints are an ENTERPRISE-only feature. Under
// Community (spec C1/DD-2) they cannot be created, so required-property
// enforcement lives in metis_mcp/ontology/validation.py instead.
//
// This is the same split spec ONT-012 already makes for enum membership: the
// database enforces what it can, the application gate enforces the rest, and
// both are required. Verified against a real Neo4j 5 Community instance --
// attempting them there fails with "requires Neo4j Enterprise Edition".

// ---- Part 1: node constraints and indexes ----

// AcceptanceCriterion — One atomic, testable condition
CREATE CONSTRAINT acceptance_criterion_id_unique IF NOT EXISTS FOR (n:AcceptanceCriterion) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT acceptance_criterion_source_episode_id_required IF NOT EXISTS FOR (n:AcceptanceCriterion) REQUIRE n.source_episode_id IS NOT NULL;
CREATE CONSTRAINT acceptance_criterion_name_required IF NOT EXISTS FOR (n:AcceptanceCriterion) REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT acceptance_criterion_revision_required IF NOT EXISTS FOR (n:AcceptanceCriterion) REQUIRE n.revision IS NOT NULL;
CREATE INDEX acceptance_criterion_lifecycle_state_lookup IF NOT EXISTS FOR (n:AcceptanceCriterion) ON (n.lifecycle_state);
CREATE INDEX acceptance_criterion_provenance_lookup IF NOT EXISTS FOR (n:AcceptanceCriterion) ON (n.provenance);
//   AcceptanceCriterion.provenance ∈ {code_derived, human_confirmed, independently_authored} — enforced by ontology.validation, not by Neo4j
//   AcceptanceCriterion.lifecycle_state ∈ {Quarantine, Approved, Disputed, Rejected, Deprecated} — enforced by ontology.validation, not by Neo4j

// Episode — Immutable record of one ingested unit; everything derived points here
CREATE CONSTRAINT episode_id_unique IF NOT EXISTS FOR (n:Episode) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT episode_t_recorded_required IF NOT EXISTS FOR (n:Episode) REQUIRE n.t_recorded IS NOT NULL;
CREATE CONSTRAINT episode_source_connector_required IF NOT EXISTS FOR (n:Episode) REQUIRE n.source_connector IS NOT NULL;
CREATE CONSTRAINT episode_job_id_required IF NOT EXISTS FOR (n:Episode) REQUIRE n.job_id IS NOT NULL;
CREATE INDEX episode_source_connector_lookup IF NOT EXISTS FOR (n:Episode) ON (n.source_connector);
CREATE INDEX episode_job_id_lookup IF NOT EXISTS FOR (n:Episode) ON (n.job_id);
CREATE INDEX episode_checkpoint_status_lookup IF NOT EXISTS FOR (n:Episode) ON (n.checkpoint_status);

// Finding — A divergence, gap, unverifiable guard, or drift item
CREATE CONSTRAINT finding_id_unique IF NOT EXISTS FOR (n:Finding) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT finding_source_episode_id_required IF NOT EXISTS FOR (n:Finding) REQUIRE n.source_episode_id IS NOT NULL;
CREATE CONSTRAINT finding_name_required IF NOT EXISTS FOR (n:Finding) REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT finding_finding_type_required IF NOT EXISTS FOR (n:Finding) REQUIRE n.finding_type IS NOT NULL;
CREATE INDEX finding_finding_type_lookup IF NOT EXISTS FOR (n:Finding) ON (n.finding_type);
CREATE INDEX finding_severity_lookup IF NOT EXISTS FOR (n:Finding) ON (n.severity);
CREATE INDEX finding_resolution_lookup IF NOT EXISTS FOR (n:Finding) ON (n.resolution);
CREATE INDEX finding_lifecycle_state_lookup IF NOT EXISTS FOR (n:Finding) ON (n.lifecycle_state);

// JiraItem — Evidence anchor for one Jira issue; survives its Requirement being rejected
CREATE CONSTRAINT jira_item_id_unique IF NOT EXISTS FOR (n:JiraItem) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT jira_item_source_episode_id_required IF NOT EXISTS FOR (n:JiraItem) REQUIRE n.source_episode_id IS NOT NULL;
CREATE CONSTRAINT jira_item_name_required IF NOT EXISTS FOR (n:JiraItem) REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT jira_item_jira_key_required IF NOT EXISTS FOR (n:JiraItem) REQUIRE n.jira_key IS NOT NULL;
CREATE CONSTRAINT jira_item_issue_type_required IF NOT EXISTS FOR (n:JiraItem) REQUIRE n.issue_type IS NOT NULL;
CREATE INDEX jira_item_jira_key_lookup IF NOT EXISTS FOR (n:JiraItem) ON (n.jira_key);
CREATE INDEX jira_item_lifecycle_state_lookup IF NOT EXISTS FOR (n:JiraItem) ON (n.lifecycle_state);

// ModelVersion — One versioned snapshot of a <journey>-<surface> model
CREATE CONSTRAINT model_version_id_unique IF NOT EXISTS FOR (n:ModelVersion) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT model_version_source_episode_id_required IF NOT EXISTS FOR (n:ModelVersion) REQUIRE n.source_episode_id IS NOT NULL;
CREATE CONSTRAINT model_version_name_required IF NOT EXISTS FOR (n:ModelVersion) REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT model_version_journey_required IF NOT EXISTS FOR (n:ModelVersion) REQUIRE n.journey IS NOT NULL;
CREATE CONSTRAINT model_version_surface_required IF NOT EXISTS FOR (n:ModelVersion) REQUIRE n.surface IS NOT NULL;
CREATE CONSTRAINT model_version_version_required IF NOT EXISTS FOR (n:ModelVersion) REQUIRE n.version IS NOT NULL;
CREATE INDEX model_version_journey_lookup IF NOT EXISTS FOR (n:ModelVersion) ON (n.journey);
CREATE INDEX model_version_surface_lookup IF NOT EXISTS FOR (n:ModelVersion) ON (n.surface);
CREATE INDEX model_version_version_lookup IF NOT EXISTS FOR (n:ModelVersion) ON (n.version);
CREATE INDEX model_version_commit_sha_lookup IF NOT EXISTS FOR (n:ModelVersion) ON (n.commit_sha);
CREATE INDEX model_version_lifecycle_state_lookup IF NOT EXISTS FOR (n:ModelVersion) ON (n.lifecycle_state);
//   ModelVersion.surface ∈ {ui, api} — enforced by ontology.validation, not by Neo4j

// Requirement — One requirement statement
CREATE CONSTRAINT requirement_id_unique IF NOT EXISTS FOR (n:Requirement) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT requirement_source_episode_id_required IF NOT EXISTS FOR (n:Requirement) REQUIRE n.source_episode_id IS NOT NULL;
CREATE CONSTRAINT requirement_name_required IF NOT EXISTS FOR (n:Requirement) REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT requirement_ears_pattern_required IF NOT EXISTS FOR (n:Requirement) REQUIRE n.ears_pattern IS NOT NULL;
CREATE CONSTRAINT requirement_revision_required IF NOT EXISTS FOR (n:Requirement) REQUIRE n.revision IS NOT NULL;
CREATE INDEX requirement_ears_pattern_lookup IF NOT EXISTS FOR (n:Requirement) ON (n.ears_pattern);
CREATE INDEX requirement_lifecycle_state_lookup IF NOT EXISTS FOR (n:Requirement) ON (n.lifecycle_state);

// Revision — Property-level history for non-model entities
CREATE CONSTRAINT revision_id_unique IF NOT EXISTS FOR (n:Revision) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT revision_source_episode_id_required IF NOT EXISTS FOR (n:Revision) REQUIRE n.source_episode_id IS NOT NULL;
CREATE CONSTRAINT revision_name_required IF NOT EXISTS FOR (n:Revision) REQUIRE n.name IS NOT NULL;
CREATE INDEX revision_recorded_at_lookup IF NOT EXISTS FOR (n:Revision) ON (n.recorded_at);
CREATE INDEX revision_lifecycle_state_lookup IF NOT EXISTS FOR (n:Revision) ON (n.lifecycle_state);

// Run — One pipeline execution: scope, criterion and versions (spec F-3)
CREATE CONSTRAINT run_id_unique IF NOT EXISTS FOR (n:Run) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT run_source_episode_id_required IF NOT EXISTS FOR (n:Run) REQUIRE n.source_episode_id IS NOT NULL;
CREATE CONSTRAINT run_name_required IF NOT EXISTS FOR (n:Run) REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT run_criterion_required IF NOT EXISTS FOR (n:Run) REQUIRE n.criterion IS NOT NULL;
CREATE INDEX run_criterion_lookup IF NOT EXISTS FOR (n:Run) ON (n.criterion);
CREATE INDEX run_started_at_lookup IF NOT EXISTS FOR (n:Run) ON (n.started_at);
CREATE INDEX run_lifecycle_state_lookup IF NOT EXISTS FOR (n:Run) ON (n.lifecycle_state);

// State — One observable situation on one surface (spec M-3)
CREATE CONSTRAINT state_id_unique IF NOT EXISTS FOR (n:State) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT state_source_episode_id_required IF NOT EXISTS FOR (n:State) REQUIRE n.source_episode_id IS NOT NULL;
CREATE CONSTRAINT state_name_required IF NOT EXISTS FOR (n:State) REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT state_surface_required IF NOT EXISTS FOR (n:State) REQUIRE n.surface IS NOT NULL;
CREATE INDEX state_surface_lookup IF NOT EXISTS FOR (n:State) ON (n.surface);
CREATE INDEX state_lifecycle_state_lookup IF NOT EXISTS FOR (n:State) ON (n.lifecycle_state);
CREATE INDEX state_functional_areas_lookup IF NOT EXISTS FOR (n:State) ON (n.functional_areas);
//   State.surface ∈ {ui, api} — enforced by ontology.validation, not by Neo4j
//   State.lifecycle_state ∈ {Quarantine, Approved, Disputed, Rejected, Deprecated} — enforced by ontology.validation, not by Neo4j

// TestCase — One rendered, human-executable artefact
CREATE CONSTRAINT test_case_id_unique IF NOT EXISTS FOR (n:TestCase) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT test_case_source_episode_id_required IF NOT EXISTS FOR (n:TestCase) REQUIRE n.source_episode_id IS NOT NULL;
CREATE CONSTRAINT test_case_name_required IF NOT EXISTS FOR (n:TestCase) REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT test_case_content_hash_required IF NOT EXISTS FOR (n:TestCase) REQUIRE n.content_hash IS NOT NULL;
CREATE INDEX test_case_content_hash_lookup IF NOT EXISTS FOR (n:TestCase) ON (n.content_hash);
CREATE INDEX test_case_published_id_lookup IF NOT EXISTS FOR (n:TestCase) ON (n.published_id);
CREATE INDEX test_case_published_status_lookup IF NOT EXISTS FOR (n:TestCase) ON (n.published_status);
CREATE INDEX test_case_level_lookup IF NOT EXISTS FOR (n:TestCase) ON (n.level);
CREATE INDEX test_case_lifecycle_state_lookup IF NOT EXISTS FOR (n:TestCase) ON (n.lifecycle_state);
//   TestCase.level ∈ {unit, integration, api_functional, web_functional, e2e, performance} — enforced by ontology.validation, not by Neo4j

// TestPath — One covering walk: setup plus a single validated transition
CREATE CONSTRAINT test_path_id_unique IF NOT EXISTS FOR (n:TestPath) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT test_path_source_episode_id_required IF NOT EXISTS FOR (n:TestPath) REQUIRE n.source_episode_id IS NOT NULL;
CREATE CONSTRAINT test_path_name_required IF NOT EXISTS FOR (n:TestPath) REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT test_path_criterion_required IF NOT EXISTS FOR (n:TestPath) REQUIRE n.criterion IS NOT NULL;
CREATE CONSTRAINT test_path_generator_version_required IF NOT EXISTS FOR (n:TestPath) REQUIRE n.generator_version IS NOT NULL;
CREATE INDEX test_path_criterion_lookup IF NOT EXISTS FOR (n:TestPath) ON (n.criterion);
CREATE INDEX test_path_lifecycle_state_lookup IF NOT EXISTS FOR (n:TestPath) ON (n.lifecycle_state);

// Transition — One interaction: trigger, guard, source and target state
CREATE CONSTRAINT transition_id_unique IF NOT EXISTS FOR (n:Transition) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT transition_source_episode_id_required IF NOT EXISTS FOR (n:Transition) REQUIRE n.source_episode_id IS NOT NULL;
CREATE CONSTRAINT transition_name_required IF NOT EXISTS FOR (n:Transition) REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT transition_trigger_required IF NOT EXISTS FOR (n:Transition) REQUIRE n.trigger IS NOT NULL;
CREATE CONSTRAINT transition_guard_expression_required IF NOT EXISTS FOR (n:Transition) REQUIRE n.guard_expression IS NOT NULL;
CREATE CONSTRAINT transition_implementation_status_required IF NOT EXISTS FOR (n:Transition) REQUIRE n.implementation_status IS NOT NULL;
CREATE CONSTRAINT transition_surface_required IF NOT EXISTS FOR (n:Transition) REQUIRE n.surface IS NOT NULL;
CREATE INDEX transition_surface_lookup IF NOT EXISTS FOR (n:Transition) ON (n.surface);
CREATE INDEX transition_lifecycle_state_lookup IF NOT EXISTS FOR (n:Transition) ON (n.lifecycle_state);
CREATE INDEX transition_implementation_status_lookup IF NOT EXISTS FOR (n:Transition) ON (n.implementation_status);
CREATE INDEX transition_extraction_method_lookup IF NOT EXISTS FOR (n:Transition) ON (n.extraction_method);
CREATE INDEX transition_functional_areas_lookup IF NOT EXISTS FOR (n:Transition) ON (n.functional_areas);
//   Transition.surface ∈ {ui, api} — enforced by ontology.validation, not by Neo4j
//   Transition.implementation_status ∈ {implemented, planned} — enforced by ontology.validation, not by Neo4j
//   Transition.extraction_method ∈ {hand_authored, static_analysis, ac_mined} — enforced by ontology.validation, not by Neo4j
//   Transition.lifecycle_state ∈ {Quarantine, Approved, Disputed, Rejected, Deprecated} — enforced by ontology.validation, not by Neo4j
