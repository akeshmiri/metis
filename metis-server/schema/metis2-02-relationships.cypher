// ==========================================================
// Métis schema — GENERATED from metis_mcp/ontology/labels.py
// Do not hand-edit: regenerate with
//     python3 -m metis_mcp.ontology.schema --write
// Hand-edits are drift, and test_ontology.py will fail on them.
// ==========================================================

// ---- Part 2: relationship indexes ----

CREATE INDEX rel_r_e_p_r_e_s_e_n_t_s_t_valid IF NOT EXISTS FOR ()-[x:REPRESENTS]-() ON (x.t_valid);
CREATE INDEX rel_d_e_s_c_r_i_b_e_s_t_valid IF NOT EXISTS FOR ()-[x:DESCRIBES]-() ON (x.t_valid);
CREATE INDEX rel_c_i_t_e_s_t_valid IF NOT EXISTS FOR ()-[x:CITES]-() ON (x.t_valid);
CREATE INDEX rel_l_i_n_k_s__t_o_t_valid IF NOT EXISTS FOR ()-[x:LINKS_TO]-() ON (x.t_valid);
CREATE INDEX rel_s_p_e_c_i_f_i_e_d__b_y_t_valid IF NOT EXISTS FOR ()-[x:SPECIFIED_BY]-() ON (x.t_valid);
CREATE INDEX rel_h_a_s__a_c_t_valid IF NOT EXISTS FOR ()-[x:HAS_AC]-() ON (x.t_valid);
CREATE INDEX rel_s_p_e_c_i_f_i_e_s_t_valid IF NOT EXISTS FOR ()-[x:SPECIFIES]-() ON (x.t_valid);
CREATE INDEX rel_r_e_a_l_i_s_e_d__b_y_t_valid IF NOT EXISTS FOR ()-[x:REALISED_BY]-() ON (x.t_valid);
CREATE INDEX rel_h_a_s__s_c_e_n_a_r_i_o_t_valid IF NOT EXISTS FOR ()-[x:HAS_SCENARIO]-() ON (x.t_valid);
CREATE INDEX rel_e_x_p_o_s_e_s_t_valid IF NOT EXISTS FOR ()-[x:EXPOSES]-() ON (x.t_valid);
CREATE INDEX rel_c_o_n_t_a_i_n_s_t_valid IF NOT EXISTS FOR ()-[x:CONTAINS]-() ON (x.t_valid);
CREATE INDEX rel_h_a_s__p_a_g_e_t_valid IF NOT EXISTS FOR ()-[x:HAS_PAGE]-() ON (x.t_valid);
CREATE INDEX rel_i_m_p_l_e_m_e_n_t_s_t_valid IF NOT EXISTS FOR ()-[x:IMPLEMENTS]-() ON (x.t_valid);
CREATE INDEX rel_v_a_l_i_d_a_t_e_s_t_valid IF NOT EXISTS FOR ()-[x:VALIDATES]-() ON (x.t_valid);
CREATE INDEX rel_w_h_e_n_t_valid IF NOT EXISTS FOR ()-[x:WHEN]-() ON (x.t_valid);
CREATE INDEX rel_t_h_e_n_t_valid IF NOT EXISTS FOR ()-[x:THEN]-() ON (x.t_valid);
CREATE INDEX rel_t_r_i_g_g_e_r_s_t_valid IF NOT EXISTS FOR ()-[x:TRIGGERS]-() ON (x.t_valid);
CREATE INDEX rel_i_n_v_o_k_e_s_t_valid IF NOT EXISTS FOR ()-[x:INVOKES]-() ON (x.t_valid);
CREATE INDEX rel_s_h_o_w_s_t_valid IF NOT EXISTS FOR ()-[x:SHOWS]-() ON (x.t_valid);
CREATE INDEX rel_h_a_s__e_l_e_m_e_n_t_t_valid IF NOT EXISTS FOR ()-[x:HAS_ELEMENT]-() ON (x.t_valid);
CREATE INDEX rel_c_o_n_n_e_c_t_s__t_o_t_valid IF NOT EXISTS FOR ()-[x:CONNECTS_TO]-() ON (x.t_valid);
CREATE INDEX rel_h_a_s__s_c_h_e_m_a_t_valid IF NOT EXISTS FOR ()-[x:HAS_SCHEMA]-() ON (x.t_valid);
CREATE INDEX rel_h_a_s__o_b_j_e_c_t_t_valid IF NOT EXISTS FOR ()-[x:HAS_OBJECT]-() ON (x.t_valid);
CREATE INDEX rel_h_a_s__c_o_l_u_m_n_t_valid IF NOT EXISTS FOR ()-[x:HAS_COLUMN]-() ON (x.t_valid);
CREATE INDEX rel_s_t_o_r_e_d__i_n_t_valid IF NOT EXISTS FOR ()-[x:STORED_IN]-() ON (x.t_valid);
CREATE INDEX rel_o_n__e_v_e_n_t_t_valid IF NOT EXISTS FOR ()-[x:ON_EVENT]-() ON (x.t_valid);
CREATE INDEX rel_n_a_v_i_g_a_t_e_s__t_o_t_valid IF NOT EXISTS FOR ()-[x:NAVIGATES_TO]-() ON (x.t_valid);
CREATE INDEX rel_d_e_r_i_v_e_d__f_r_o_m_t_valid IF NOT EXISTS FOR ()-[x:DERIVED_FROM]-() ON (x.t_valid);
CREATE INDEX rel_g_e_n_e_r_a_t_e_d__f_r_o_m_t_valid IF NOT EXISTS FOR ()-[x:GENERATED_FROM]-() ON (x.t_valid);
CREATE INDEX rel_c_o_v_e_r_s_t_valid IF NOT EXISTS FOR ()-[x:COVERS]-() ON (x.t_valid);
CREATE INDEX rel_p_r_o_d_u_c_e_s_t_valid IF NOT EXISTS FOR ()-[x:PRODUCES]-() ON (x.t_valid);
CREATE INDEX rel_b_e_l_o_n_g_s__t_o_t_valid IF NOT EXISTS FOR ()-[x:BELONGS_TO]-() ON (x.t_valid);
CREATE INDEX rel_r_e_f_e_r_e_n_c_e_s_t_valid IF NOT EXISTS FOR ()-[x:REFERENCES]-() ON (x.t_valid);
CREATE INDEX rel_a_b_o_u_t_t_valid IF NOT EXISTS FOR ()-[x:ABOUT]-() ON (x.t_valid);
CREATE INDEX rel_a_c_c_e_p_t_s_t_valid IF NOT EXISTS FOR ()-[x:ACCEPTS]-() ON (x.t_valid);
CREATE INDEX rel_o_f__t_y_p_e_t_valid IF NOT EXISTS FOR ()-[x:OF_TYPE]-() ON (x.t_valid);
CREATE INDEX rel_r_e_t_u_r_n_s_t_valid IF NOT EXISTS FOR ()-[x:RETURNS]-() ON (x.t_valid);
CREATE INDEX rel_d_e_c_l_a_r_e_s__m_e_t_h_o_d_t_valid IF NOT EXISTS FOR ()-[x:DECLARES_METHOD]-() ON (x.t_valid);
CREATE INDEX rel_h_a_n_d_l_e_d__b_y_t_valid IF NOT EXISTS FOR ()-[x:HANDLED_BY]-() ON (x.t_valid);
CREATE INDEX rel_c_a_l_l_s_t_valid IF NOT EXISTS FOR ()-[x:CALLS]-() ON (x.t_valid);
CREATE INDEX rel_i_s_s_u_e_s_t_valid IF NOT EXISTS FOR ()-[x:ISSUES]-() ON (x.t_valid);
CREATE INDEX rel_q_u_e_r_i_e_s_t_valid IF NOT EXISTS FOR ()-[x:QUERIES]-() ON (x.t_valid);
CREATE INDEX rel_u_s_e_s_t_valid IF NOT EXISTS FOR ()-[x:USES]-() ON (x.t_valid);
CREATE INDEX rel_d_e_c_l_a_r_e_s_t_valid IF NOT EXISTS FOR ()-[x:DECLARES]-() ON (x.t_valid);
CREATE INDEX rel_g_u_a_r_d_e_d__b_y_t_valid IF NOT EXISTS FOR ()-[x:GUARDED_BY]-() ON (x.t_valid);
CREATE INDEX rel_r_e_n_d_e_r_s_t_valid IF NOT EXISTS FOR ()-[x:RENDERS]-() ON (x.t_valid);
CREATE INDEX rel_e_x_e_r_c_i_s_e_s_t_valid IF NOT EXISTS FOR ()-[x:EXERCISES]-() ON (x.t_valid);
CREATE INDEX rel_r_e_q_u_i_r_e_s_t_valid IF NOT EXISTS FOR ()-[x:REQUIRES]-() ON (x.t_valid);
CREATE INDEX rel_e_x_p_e_c_t_s_t_valid IF NOT EXISTS FOR ()-[x:EXPECTS]-() ON (x.t_valid);
CREATE INDEX rel_c_o_n_s_t_r_a_i_n_e_d__b_y_t_valid IF NOT EXISTS FOR ()-[x:CONSTRAINED_BY]-() ON (x.t_valid);

// ---- Catalogue (the closed set enforced by ontology.validation) ----
//   (JiraItem)-[:REPRESENTS]->(Requirement)  — System-of-record source
//   (ConfluenceItem)-[:REPRESENTS]->(Requirement)  — System-of-record source
//   (OpenApiItem)-[:REPRESENTS]->(Requirement)  — System-of-record source
//   (ZephyrItem)-[:REPRESENTS]->(Requirement)  — System-of-record source
//   (DatasourceItem)-[:REPRESENTS]->(Requirement)  — System-of-record source
//   (CodeItem)-[:REPRESENTS]->(Requirement)  — System-of-record source
//   (SpecDocument)-[:DESCRIBES]->(Component)  — The component version this specification renders
//   (EntityDocument)-[:DESCRIBES]->(BusinessEntity)  — The business noun this specification defines
//   (SpecDocument)-[:CITES]->(AcceptanceCriterion)  — A rule rendered in this document
//   (EntityDocument)-[:CITES]->(AcceptanceCriterion)  — A criterion that touches this entity
//   (JiraItem)-[:LINKS_TO]->(JiraItem)  — A real Jira issue link — provenance, not traceability
//   (Intent)-[:SPECIFIED_BY]->(Specification)  — A need, once somebody has said how it behaves
//   (Specification)-[:HAS_AC]->(AcceptanceCriterion)  — The atomic conditions this specified behaviour breaks into
//   (Specification)-[:SPECIFIES]->(Requirement)  — The requirement this behaviour belongs to — kept so §7.8's chain still reaches a Requirement (A-24)
//   (Specification)-[:REALISED_BY]->(Feature)  — The capability this behaviour is part of. `feature.derive` groups SPECIFICATIONS -- on the business noun they name, or the component that implements them -- so this is the edge the grouping actually establishes. Without it the derivation planned AcceptanceCriterion edges using specification ids, and every one matched nothing
//   (AcceptanceCriterion)-[:REALISED_BY]->(Feature)  — The capability this condition is part of
//   (Requirement)-[:REALISED_BY]->(Feature)  — The capability this requirement is part of
//   (Feature)-[:HAS_SCENARIO]->(Scenario)  — The walks that demonstrate this capability
//   (RestServer)-[:EXPOSES]->(Endpoint)  — The entry points it serves
//   (RestServer)-[:CONTAINS]->(Transition)  — Its behaviour at one commit
//   (WebServer)-[:HAS_PAGE]->(Page)  — The screens it serves
//   (WebServer)-[:CONTAINS]->(Transition)  — Its behaviour at one commit
//   (Endpoint)-[:IMPLEMENTS]->(Specification)  — This entry point is one implementation of that behaviour
//   (Action)-[:IMPLEMENTS]->(Specification)  — This affordance is one implementation of that behaviour
//   (Requirement)-[:HAS_AC]->(AcceptanceCriterion)  — Its atomic conditions
//   (AcceptanceCriterion)-[:VALIDATES]->(Transition)  — Confirmed match (spec X-18)
//   (State)-[:WHEN]->(Transition)  — Source state — the implicit Given
//   (Transition)-[:THEN]->(State)  — Resulting target state
//   (UiAction)-[:TRIGGERS]->(ApiCall)  — This interaction starts that API flow; the UI continues (M-5a)
//   (UiAction)-[:INVOKES]->(ApiCall)  — This UI outcome rendered that API outcome (M-5a, M-5b)
//   (Component)-[:HAS_PAGE]->(Page)  — A screen this web component presents
//   (Page)-[:SHOWS]->(State)  — A condition this page can be observed in (M-2, M-3)
//   (Page)-[:HAS_ELEMENT]->(UiElement)  — A control this surface presents
//   (Page)-[:HAS_ELEMENT]->(Menu)  — A control this surface presents
//   (Page)-[:HAS_ELEMENT]->(UiTable)  — A control this surface presents
//   (Page)-[:HAS_ELEMENT]->(Form)  — A control this surface presents
//   (Page)-[:HAS_ELEMENT]->(Dialog)  — A control this surface presents
//   (Page)-[:HAS_ELEMENT]->(Action)  — A control this surface presents
//   (Page)-[:HAS_ELEMENT]->(Event)  — A control this surface presents
//   (Page)-[:HAS_ELEMENT]->(Navigation)  — A control this surface presents
//   (Menu)-[:HAS_ELEMENT]->(Action)  — A control this surface presents
//   (Menu)-[:HAS_ELEMENT]->(Event)  — A control this surface presents
//   (Menu)-[:HAS_ELEMENT]->(Navigation)  — A control this surface presents
//   (Menu)-[:HAS_ELEMENT]->(Dialog)  — A control this surface presents
//   (UiTable)-[:HAS_ELEMENT]->(Action)  — A control this surface presents
//   (UiTable)-[:HAS_ELEMENT]->(Event)  — A control this surface presents
//   (UiTable)-[:HAS_ELEMENT]->(Navigation)  — A control this surface presents
//   (UiTable)-[:HAS_ELEMENT]->(Dialog)  — A control this surface presents
//   (UiTable)-[:HAS_ELEMENT]->(Row)  — A control this surface presents
//   (UiTable)-[:HAS_ELEMENT]->(Pagination)  — A control this surface presents
//   (UiTable)-[:HAS_ELEMENT]->(Sort)  — A control this surface presents
//   (Form)-[:HAS_ELEMENT]->(Action)  — A control this surface presents
//   (Form)-[:HAS_ELEMENT]->(Event)  — A control this surface presents
//   (Form)-[:HAS_ELEMENT]->(Navigation)  — A control this surface presents
//   (Form)-[:HAS_ELEMENT]->(Dialog)  — A control this surface presents
//   (Dialog)-[:HAS_ELEMENT]->(Action)  — A control this surface presents
//   (Dialog)-[:HAS_ELEMENT]->(Event)  — A control this surface presents
//   (Dialog)-[:HAS_ELEMENT]->(Navigation)  — A control this surface presents
//   (Row)-[:HAS_ELEMENT]->(Action)  — A control this surface presents
//   (Row)-[:HAS_ELEMENT]->(Event)  — A control this surface presents
//   (Row)-[:HAS_ELEMENT]->(Navigation)  — A control this surface presents
//   (Row)-[:HAS_ELEMENT]->(Dialog)  — A control this surface presents
//   (Pagination)-[:HAS_ELEMENT]->(Action)  — A control this surface presents
//   (Pagination)-[:HAS_ELEMENT]->(Event)  — A control this surface presents
//   (Sort)-[:HAS_ELEMENT]->(Action)  — A control this surface presents
//   (Sort)-[:HAS_ELEMENT]->(Event)  — A control this surface presents
//   (Datasource)-[:CONNECTS_TO]->(Database)  — Which database this connection addresses
//   (Database)-[:HAS_SCHEMA]->(Schema)  — A grouping it contains
//   (Schema)-[:HAS_OBJECT]->(Table)  — An object it contains
//   (Schema)-[:HAS_OBJECT]->(View)  — An object it contains
//   (Schema)-[:HAS_OBJECT]->(Function)  — An object it contains
//   (Schema)-[:HAS_OBJECT]->(DbObject)  — An object it contains
//   (Database)-[:HAS_OBJECT]->(Table)  — An object it contains
//   (Database)-[:HAS_OBJECT]->(View)  — An object it contains
//   (Database)-[:HAS_OBJECT]->(Function)  — An object it contains
//   (Database)-[:HAS_OBJECT]->(DbObject)  — An object it contains
//   (Table)-[:HAS_COLUMN]->(Column)  — A column it declares
//   (View)-[:HAS_COLUMN]->(Column)  — A column it declares
//   (BusinessEntity)-[:STORED_IN]->(Table)  — Where this business noun is persisted
//   (Action)-[:ON_EVENT]->(Event)  — The interaction that invokes this action
//   (Navigation)-[:NAVIGATES_TO]->(Page)  — Where this control goes
//   (Transition)-[:DERIVED_FROM]->(Action)  — The control this interaction was recovered from
//   (Lesson)-[:CONTAINS]->(Passage)  — Its sections, each carrying its own vector
//   (Component)-[:CONTAINS]->(State)  — Membership of this component version
//   (Component)-[:CONTAINS]->(Transition)  — Membership of this component version
//   (Scenario)-[:GENERATED_FROM]->(Component)  — The exact version this path covers
//   (Scenario)-[:COVERS]->(Transition)  {sequence, is_validated}  — Ordered traversal — makes coverage computable
//   (Scenario)-[:PRODUCES]->(TestCase)  — The rendered artefact
//   (BusinessEntity)-[:BELONGS_TO]->(BusinessArea)  — Which domain this noun lives in
//   (Requirement)-[:BELONGS_TO]->(BusinessArea)  — Which domain this requirement governs
//   (AcceptanceCriterion)-[:REFERENCES]->(BusinessEntity)  — A business noun this criterion acts on or constrains
//   (Finding)-[:ABOUT]->(*) [any label]  — What the finding concerns
//   (Component)-[:EXPOSES]->(Endpoint)  — The entry points this deployable presents
//   (Endpoint)-[:ACCEPTS]->(Parameter)  — What a caller must send
//   (Parameter)-[:OF_TYPE]->(Class)  — The payload schema — the same node as the declared type
//   (Endpoint)-[:RETURNS]->(Class)  — The declared response body type
//   (Class)-[:OF_TYPE]->(Class)  — A field of this type is itself a declared type — the nested payload. Which field is on `f_<name>_type`
//   (Class)-[:DECLARES_METHOD]->(Method)  — Its methods
//   (Endpoint)-[:HANDLED_BY]->(Method)  — The handler behind the route
//   (Method)-[:CALLS]->(Method)  — A resolved call edge (Layer 1)
//   (Method)-[:ISSUES]->(Query)  — A query this method sends to a database
//   (Query)-[:QUERIES]->(Table)  — A table this query reads or writes
//   (Query)-[:QUERIES]->(View)  — A view this query reads
//   (Query)-[:USES]->(Column)  — A column this query names — a test-design input, because it is what a fixture has to populate
//   (Endpoint)-[:DECLARES]->(DeclaredOutcome)  — A result this entry point can produce
//   (DeclaredOutcome)-[:GUARDED_BY]->(Check)  — The condition selecting this outcome
//   (ExceptionMapping)-[:HANDLED_BY]->(Method)  — The @ExceptionHandler that maps it
//   (Route)-[:RENDERS]->(Page)  — The page this frontend route shows
//   (Page)-[:CALLS]->(Endpoint)  — An API call this page makes
//   (Transition)-[:DERIVED_FROM]->(Endpoint)  — The entry point this behaviour was recovered from
//   (Transition)-[:DERIVED_FROM]->(DeclaredOutcome)  — The recovered outcome this transition represents
//   (Transition)-[:DERIVED_FROM]->(ExceptionMapping)  — The exception→status mapping behind a derived rejection
//   (Transition)-[:EXERCISES]->(Parameter)  — An input this transition sends (replaces inputs_json)
//   (Transition)-[:REQUIRES]->(Class)  — A payload type whose field constraints a case must satisfy or violate (GD-3)
//   (Transition)-[:EXPECTS]->(Class)  — The response body a case should assert
//   (Endpoint)-[:CONSTRAINED_BY]->(Check)  — A condition recovered in this endpoint's handler that no outcome references
//   (Transition)-[:CONSTRAINED_BY]->(Check)  — The recovered condition behind this transition's guard
CREATE INDEX rel_c_o_v_e_r_s_sequence IF NOT EXISTS FOR ()-[x:COVERS]-() ON (x.sequence);
CREATE INDEX rel_c_o_v_e_r_s_is_validated IF NOT EXISTS FOR ()-[x:COVERS]-() ON (x.is_validated);
