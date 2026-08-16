// ==========================================================
// Métis schema — GENERATED from metis_mcp/ontology/labels.py
// Do not hand-edit: regenerate with
//     python3 -m metis_mcp.ontology.schema --write
// Hand-edits are drift, and test_ontology.py will fail on them.
// ==========================================================

// ---- Part 2: relationship indexes ----

CREATE INDEX rel_r_e_p_r_e_s_e_n_t_s_t_valid IF NOT EXISTS FOR ()-[x:REPRESENTS]-() ON (x.t_valid);
CREATE INDEX rel_l_i_n_k_s__t_o_t_valid IF NOT EXISTS FOR ()-[x:LINKS_TO]-() ON (x.t_valid);
CREATE INDEX rel_h_a_s__a_c_t_valid IF NOT EXISTS FOR ()-[x:HAS_AC]-() ON (x.t_valid);
CREATE INDEX rel_v_a_l_i_d_a_t_e_s_t_valid IF NOT EXISTS FOR ()-[x:VALIDATES]-() ON (x.t_valid);
CREATE INDEX rel_w_h_e_n_t_valid IF NOT EXISTS FOR ()-[x:WHEN]-() ON (x.t_valid);
CREATE INDEX rel_t_h_e_n_t_valid IF NOT EXISTS FOR ()-[x:THEN]-() ON (x.t_valid);
CREATE INDEX rel_i_n_v_o_k_e_s_t_valid IF NOT EXISTS FOR ()-[x:INVOKES]-() ON (x.t_valid);
CREATE INDEX rel_c_o_n_t_a_i_n_s_t_valid IF NOT EXISTS FOR ()-[x:CONTAINS]-() ON (x.t_valid);
CREATE INDEX rel_g_e_n_e_r_a_t_e_d__f_r_o_m_t_valid IF NOT EXISTS FOR ()-[x:GENERATED_FROM]-() ON (x.t_valid);
CREATE INDEX rel_c_o_v_e_r_s_t_valid IF NOT EXISTS FOR ()-[x:COVERS]-() ON (x.t_valid);
CREATE INDEX rel_p_r_o_d_u_c_e_s_t_valid IF NOT EXISTS FOR ()-[x:PRODUCES]-() ON (x.t_valid);
CREATE INDEX rel_p_r_o_d_u_c_e_d_t_valid IF NOT EXISTS FOR ()-[x:PRODUCED]-() ON (x.t_valid);
CREATE INDEX rel_a_b_o_u_t_t_valid IF NOT EXISTS FOR ()-[x:ABOUT]-() ON (x.t_valid);
CREATE INDEX rel_h_a_s__r_e_v_i_s_i_o_n_t_valid IF NOT EXISTS FOR ()-[x:HAS_REVISION]-() ON (x.t_valid);

// ---- Catalogue (the closed set enforced by ontology.validation) ----
//   (JiraItem)-[:REPRESENTS]->(Requirement)  — System-of-record source
//   (JiraItem)-[:LINKS_TO]->(JiraItem)  — A real Jira issue link — provenance, not traceability
//   (Requirement)-[:HAS_AC]->(AcceptanceCriterion)  — Its atomic conditions
//   (AcceptanceCriterion)-[:VALIDATES]->(Transition)  — Confirmed match (spec X-18)
//   (State)-[:WHEN]->(Transition)  — Source state — the implicit Given
//   (Transition)-[:THEN]->(State)  — Resulting target state
//   (Transition)-[:INVOKES]->(Transition)  — A UI interaction drives this API behaviour (spec M-5a)
//   (ModelVersion)-[:CONTAINS]->(State)  — Membership of this version
//   (ModelVersion)-[:CONTAINS]->(Transition)  — Membership of this version
//   (TestPath)-[:GENERATED_FROM]->(ModelVersion)  — The exact version this path covers
//   (TestPath)-[:COVERS]->(Transition)  {sequence, is_validated}  — Ordered traversal — makes coverage computable
//   (TestPath)-[:PRODUCES]->(TestCase)  — The rendered artefact
//   (Run)-[:PRODUCED]->(TestPath)  — Which run generated this path
//   (Finding)-[:ABOUT]->(*) [any label]  — What the finding concerns
//   (*)-[:HAS_REVISION]->(Revision) [any label]  — Written only by the revision recorder (spec ONT-010)
CREATE INDEX rel_c_o_v_e_r_s_sequence IF NOT EXISTS FOR ()-[x:COVERS]-() ON (x.sequence);
CREATE INDEX rel_c_o_v_e_r_s_is_validated IF NOT EXISTS FOR ()-[x:COVERS]-() ON (x.is_validated);
