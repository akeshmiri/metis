// ==========================================================
// Métis Graph Schema -- Part 2: Entity-specific constraints
// Hand-written -- these encode judgment calls from the spec,
// not mechanical boilerplate. Run AFTER 01-entity-baseline.
// ==========================================================

// ---- Requirement / AcceptanceCriterion: EARS + concurrency (§4.3, §4.5) ----

CREATE CONSTRAINT requirement_ears_pattern IF NOT EXISTS
FOR (r:Requirement) REQUIRE r.ears_pattern IS NOT NULL;
// Application code enforces ears_pattern IN ['Ubiquitous','EventDriven','StateDriven',
// 'UnwantedBehavior','Optional'] -- Neo4j property existence constraints can't express
// enum membership directly; the Cognify-stage EARS check (REQ-METIS-ONT-04) is the real
// gate, this constraint just guarantees the field is never silently absent.

CREATE CONSTRAINT requirement_revision_required IF NOT EXISTS
FOR (r:Requirement) REQUIRE r.revision IS NOT NULL;

CREATE CONSTRAINT ac_revision_required IF NOT EXISTS
FOR (a:AcceptanceCriterion) REQUIRE a.revision IS NOT NULL;

CREATE INDEX requirement_ears_pattern_lookup IF NOT EXISTS
FOR (r:Requirement) ON (r.ears_pattern);

// ---- Confidence tiering (§7 Layer 3) -- applies to every entity that can be
// AI-extracted, not just Requirement. Rather than repeat this per label, this
// is enforced at the application layer (the Load stage never writes a node
// without a confidence_tier), but the index below is what makes the guardrail
// dashboard (§7.1) queries fast at scale.

CREATE INDEX confidence_tier_requirement IF NOT EXISTS FOR (n:Requirement) ON (n.confidence_tier);
CREATE INDEX confidence_tier_ac IF NOT EXISTS FOR (n:AcceptanceCriterion) ON (n.confidence_tier);
CREATE INDEX confidence_tier_businessrule IF NOT EXISTS FOR (n:BusinessRule) ON (n.confidence_tier);
CREATE INDEX confidence_tier_transition IF NOT EXISTS FOR (n:Transition) ON (n.confidence_tier);
CREATE INDEX confidence_tier_constraint IF NOT EXISTS FOR (n:Constraint) ON (n.confidence_tier);

// ---- Corroboration count (§7 Layer 4) -- required on the high-risk entity
// types named explicitly in the spec: Requirement, BusinessRule, Transition
// (for guard/security-relevant edges), Constraint.

CREATE CONSTRAINT requirement_corroboration_count IF NOT EXISTS
FOR (r:Requirement) REQUIRE r.corroboration_count IS NOT NULL;
CREATE CONSTRAINT businessrule_corroboration_count IF NOT EXISTS
FOR (b:BusinessRule) REQUIRE b.corroboration_count IS NOT NULL;
// Transition and Constraint only need this when risk_tag = 'High' -- that's a
// conditional rule (Neo4j doesn't support conditional existence constraints),
// so it's enforced at the Load stage (§6.1) rather than here; the index still
// helps the guardrail metrics query in §7.1.
CREATE INDEX transition_corroboration_count IF NOT EXISTS FOR (n:Transition) ON (n.corroboration_count);
CREATE INDEX constraint_corroboration_count IF NOT EXISTS FOR (n:Constraint) ON (n.corroboration_count);

// ---- Disputed / contradiction tracking (§5.3, §7 Layer 5) ----

// Filtered/partial range indexes (WHERE-scoped CREATE INDEX) are not valid
// syntax on Neo4j 5.26 Enterprise -- confirmed by actually running this
// against a real instance, not assumed. Per this note's own fallback
// instruction: dropped, relying on the general requirement_lifecycle_state
// index from Part 1 instead (functionally equivalent, just less selective).

// ---- Transition: state-machine shape (§4, Behavior layer) ----
// Relationship existence isn't a Neo4j-native constraint (no "this node must
// have exactly one FROM edge" primitive pre-2026.06) -- enforced at Load stage
// via the SHACL-equivalent structural validation (§7 Layer 2). This index
// supports that check's lookup pattern:

CREATE INDEX transition_lookup_by_state_machine IF NOT EXISTS
FOR (n:Transition) ON (n.state_machine_id);

// ---- Episode node (the ingestion primitive itself -- not part of the typed
// ontology loop above, since every entity references it, not vice versa) ----

CREATE CONSTRAINT episode_id_unique IF NOT EXISTS
FOR (e:Episode) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT episode_t_recorded_required IF NOT EXISTS
FOR (e:Episode) REQUIRE e.t_recorded IS NOT NULL;
CREATE CONSTRAINT episode_source_connector_required IF NOT EXISTS
FOR (e:Episode) REQUIRE e.source_connector IS NOT NULL;
CREATE INDEX episode_t_recorded IF NOT EXISTS FOR (e:Episode) ON (e.t_recorded);
CREATE INDEX episode_unit_id IF NOT EXISTS FOR (e:Episode) ON (e.unit_id);
// unit_id (§10) is content-derived, not globally unique by itself across
// episode types -- uniqueness is enforced per source_connector + unit_id pair
// at the application layer, not as a single-property Neo4j constraint.

// ---- Control-plane nodes (metis_mcp/temporal.py, sleep_time_consolidation.py,
// memify.py -- same category as Episode above: system-internal machinery
// state, not an "extracted fact about the world," so deliberately NOT part
// of KNOWN_LABELS/the closed 49-label ontology structural_validation.py
// gates -- but still real, persistent nodes that deserve the same
// database-level integrity guarantee every other label gets. Real gap
// found auditing this project after it shipped: these three were added
// via direct session.execute_write (bypassing Layer 2 by design, same as
// Episode), but never got the uniqueness/existence constraints Episode
// itself has -- MERGE-based idempotency in application code is not a
// substitute for a real database constraint. ----

CREATE CONSTRAINT revision_id_unique IF NOT EXISTS FOR (r:Revision) REQUIRE r.id IS UNIQUE;
CREATE CONSTRAINT revision_t_valid_required IF NOT EXISTS FOR (r:Revision) REQUIRE r.t_valid IS NOT NULL;
CREATE INDEX revision_t_valid IF NOT EXISTS FOR (r:Revision) ON (r.t_valid);
CREATE INDEX revision_t_invalid IF NOT EXISTS FOR (r:Revision) ON (r.t_invalid);

CREATE CONSTRAINT mergeproposal_id_unique IF NOT EXISTS FOR (mp:MergeProposal) REQUIRE mp.id IS UNIQUE;
CREATE CONSTRAINT mergeproposal_status_required IF NOT EXISTS FOR (mp:MergeProposal) REQUIRE mp.status IS NOT NULL;
CREATE INDEX mergeproposal_status IF NOT EXISTS FOR (mp:MergeProposal) ON (mp.status);

CREATE CONSTRAINT confidenceadjustment_id_unique IF NOT EXISTS
FOR (ca:ConfidenceAdjustment) REQUIRE ca.id IS UNIQUE;

// ---- Constitution (§4.2, §7.2) -- highest-precedence rule set ----

CREATE CONSTRAINT constitution_precedence_required IF NOT EXISTS
FOR (c:Constitution) REQUIRE c.precedence_rank IS NOT NULL;
// precedence_rank is always the numeric minimum among rule types -- enforced
// at the application layer (§7.2: Constitution checks run before general
// Validation Rule Engine checks), this constraint just guarantees the field
// is always set so the ordering can never silently fall back to "unranked."

// ---- ExternalAPISpec (§4.2) -- external-dependency corroboration ----

CREATE CONSTRAINT externalapispec_registry_source_required IF NOT EXISTS
FOR (x:ExternalAPISpec) REQUIRE x.registry_source IS NOT NULL;

// ---- Relationship property indexes (bi-temporal edges, §5.1) ----
// Neo4j 2026.x supports relationship property indexes; these are the ones
// every temporal query (§5.4's as_of/history/diff) actually filters on.
// Applied to the relationship types that carry bi-temporal validity --
// structural edges (HAS_AC, PRODUCES, IMPLEMENTS, VERIFIES, TRACES_TO,
// COVERS) are the ones expected to change validity over the entity's
// lifetime.
//
// Session 10 additions -- the real Intent/TestDesign structural edges:
//   Transition/Requirement/AcceptanceCriterion/TestDesign -[:TRACES_TO]->
//     Intent (reuses the existing generic edge, same as
//     Capability->Goal/Epic->Capability/etc. -- not a new relationship
//     type per hop).
//   TestDesign -[:COVERS]-> AcceptanceCriterion (genuinely new -- no
//     existing edge captured "this design covers that criterion").
//   TestDesign -[:PRODUCES]-> TestCase (reuses the existing PRODUCES
//     edge, already used for PullRequest->Commit/TestRun->Defect).
//   TestCase -[:VERIFIES]-> AcceptanceCriterion is unchanged from
//     Session 9 -- unrelated to this addition.
//
// Session 11 additions -- real TestRun modeling (item 2) and Table/Database
// linkage (item 3), both previously undeclared/dangling:
//   TestRun -[:EXECUTES]-> TestCase (the spec always named this edge; no
//     connector or generator ever created it before Session 11).
//   TestRun -[:PART_OF]-> TestSuite (genuinely new -- mirrors the existing
//     TestCase -[:PART_OF]-> TestSuite edge, made real the same session).
//   TestRun -[:TRACES_TO]-> Release (reuses the existing generic TRACES_TO
//     edge, only for run_type='regression' TestRuns).
//   Database -[:HAS]-> Table (the spec always named this edge; the whole
//     Architecture layer had zero internal relationships before this).
//
// Session 12: TestRun renamed to TestCycle (a batch/container); per-case
// results moved to the new TestExecution node --
//   TestExecution -[:PART_OF]-> TestCycle (reuses PART_OF, same as
//     TestCase -[:PART_OF]-> TestSuite).
//   TestExecution -[:EXECUTES]-> TestCase (moved down from TestCycle --
//     an execution executes a case, not a whole cycle in aggregate).
//   TestExecution -[:PRODUCES]-> Defect (moved down from TestCycle --
//     reuses the existing PRODUCES edge, a Defect comes from a specific
//     failing execution, not the cycle abstractly).
//   TestExecution -[:RAN_AGAINST]-> ApplicationConfiguration (genuinely
//     new -- which component-version snapshot this execution ran against).
//   ApplicationConfiguration -[:INCLUDES_VERSION {version}]-> Service
//     (genuinely new -- reuses the real Service label from Session 11
//     instead of inventing a new "component" label; version lives on the
//     edge, not a node property, so each version stays independently
//     queryable/traceable).
//
// Session 13: Transition-[:TRACES_TO]->Intent (Session 10) is REMOVED --
// superseded by AcceptanceCriterion-[:VALIDATES]->Transition (genuinely
// new), the only bridge from the Intent/Requirement/TestDesign backbone
// to real State/Transition behavior now. Trigger/Guard removed as
// separate node types entirely (both were attributes of exactly one
// Transition, not their own entities) -- ON_TRIGGER/WHEN_GUARD no longer
// exist; see docs/metis-ontology-specification.md, the new authoritative
// per-label/per-relationship reference every future ontology change must
// be checked against (schema-01/02 + structural_validation.py's
// KNOWN_LABELS/ALLOWED_RELATIONSHIPS + this doc, kept in sync together).
// FROM_STATE/TO_STATE (both Transition->State) renamed to LAUNCHES/
// LANDS_IN, then to WHEN (State->Transition, direction reversed) / THEN
// (Transition->State, unchanged) -- reads as one continuous forward path,
// State-[:WHEN]->Transition-[:THEN]->State, mirroring the Given/When/Then
// shape a Transition already structurally is (the State it's reached
// from is the implicit Given). Neither FROM_STATE nor TO_STATE ever had
// a real relationship-property index (an oversight); WHEN/THEN get one,
// closing that gap at the same time.

CREATE INDEX rel_t_valid IF NOT EXISTS FOR ()-[r:HAS_AC]-() ON (r.t_valid);
CREATE INDEX rel_t_invalid IF NOT EXISTS FOR ()-[r:HAS_AC]-() ON (r.t_invalid);
CREATE INDEX rel_implements_t_valid IF NOT EXISTS FOR ()-[r:IMPLEMENTS]-() ON (r.t_valid);
CREATE INDEX rel_implements_t_invalid IF NOT EXISTS FOR ()-[r:IMPLEMENTS]-() ON (r.t_invalid);
CREATE INDEX rel_verifies_t_valid IF NOT EXISTS FOR ()-[r:VERIFIES]-() ON (r.t_valid);
CREATE INDEX rel_produces_t_valid IF NOT EXISTS FOR ()-[r:PRODUCES]-() ON (r.t_valid);
CREATE INDEX rel_traces_to_t_valid IF NOT EXISTS FOR ()-[r:TRACES_TO]-() ON (r.t_valid);
CREATE INDEX rel_covers_t_valid IF NOT EXISTS FOR ()-[r:COVERS]-() ON (r.t_valid);
CREATE INDEX rel_executes_t_valid IF NOT EXISTS FOR ()-[r:EXECUTES]-() ON (r.t_valid);
CREATE INDEX rel_part_of_t_valid IF NOT EXISTS FOR ()-[r:PART_OF]-() ON (r.t_valid);
CREATE INDEX rel_has_t_valid IF NOT EXISTS FOR ()-[r:HAS]-() ON (r.t_valid);
CREATE INDEX rel_ran_against_t_valid IF NOT EXISTS FOR ()-[r:RAN_AGAINST]-() ON (r.t_valid);
CREATE INDEX rel_includes_version_t_valid IF NOT EXISTS FOR ()-[r:INCLUDES_VERSION]-() ON (r.t_valid);
CREATE INDEX rel_validates_t_valid IF NOT EXISTS FOR ()-[r:VALIDATES]-() ON (r.t_valid);
CREATE INDEX rel_when_t_valid IF NOT EXISTS FOR ()-[r:WHEN]-() ON (r.t_valid);
CREATE INDEX rel_then_t_valid IF NOT EXISTS FOR ()-[r:THEN]-() ON (r.t_valid);

// Every relationship of these types also carries: created_by (human|ai_decision
// node ref), created_at, confidence (§7.1's edge-level confidence, distinct
// from node-level confidence_tier). These are NOT separately constrained here
// because Neo4j relationship property existence constraints apply uniformly
// to every instance of the type, and a small number of legacy-migration edges
// (§16, Atlas/Athena backfill imports) are explicitly allowed to lack
// created_by during a bounded migration window -- enforced at the application
// layer with a migration-window flag, not a blanket schema constraint.
