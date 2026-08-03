"""
Session 10: the concrete proof of the Intent/TestDesign backbone -- a
real, hand-authored login-page state machine (not random generation),
demonstrating the full chain end to end:

  Requirement -> Intent <- AcceptanceCriterion -[:VALIDATES]-> Transition
  Intent -> TestDesign -[:COVERS]-> AcceptanceCriterion
  TestDesign -[:PRODUCES]-> TestCase (real 6-level taxonomy)
  TestCase -[:VERIFIES]-> AcceptanceCriterion (Session 9, unchanged)

A later session removed the direct Transition-[:TRACES_TO]->Intent edge:
AcceptanceCriterion-[:VALIDATES]->Transition is now the only bridge
between the Intent/Requirement/TestDesign backbone and real State/
Transition behavior -- which means a `planned` Transition (no AC yet, by
design, see below) has NO live graph path to its own Intent/Requirement
until it's actually built and validated. This is deliberate, not an
oversight: nothing validates unbuilt behavior yet, so no edge should
claim otherwise. See docs/metis-ontology-specification.md for the full,
authoritative relationship catalog this file is written against.

This is deliberately ONE real example, not a retrofit of the ~5,000
synthetic Requirements onto a fabricated state machine -- see CLAUDE.md's
Session 10 addendum for why that's out of scope here.

Every node gets real provenance beyond a static timestamp: after each
node is written, `metis_mcp/temporal.record_revision()` is called for
real, so `history()`/`as_of()`/`diff()` are genuinely queryable for this
example from day one (unlike the rest of the demo data, a known,
disclosed gap this doesn't attempt to backfill everywhere).

16 Transitions are `implementation_status: 'implemented'` (real Intent,
Requirement, AcceptanceCriterion, TestDesign, TestCase -- the full
chain). 1 (2FA enrollment) is deliberately `implementation_status:
'planned'` -- it gets a real Intent and Requirement (the spec exists) but
genuinely no TestDesign/TestCase, proving the distinction the graph now
makes between "not built yet" and "built with a real test-coverage gap"
so a testing-strategy/coverage-map consumer never confuses the two.

Real completeness fix (a later session, found by user inspection, not by
running the checker first): the original login-lockout sub-flow modeled
the 5-attempt counter as a guard on a LoggedOut self-loop
(`attempt_count < 5` / `>= 5`) -- which hid 4 genuinely distinct states
(1/2/3/4 prior failures) behind one guard variable, and hiding them is
exactly what let a real requirements gap go unnoticed: nothing in that
model ever asked "what happens on a VALID login after 1, 2, 3, or 4 prior
failures?" Re-modeled with explicit `Failed1`-`Failed4` states, each with
its own real, distinct EARS-conformant Requirement/AcceptanceCriterion --
both for the failure-count increment AND for the "valid credentials still
succeed from here" recovery path per state. This is the concrete case
`metis_mcp/behavior_model.py`'s `check_completeness()` (CONST-048/049)
exists to catch; it couldn't catch it before because the single-state
model never gave it the chance to.

Display names (later session, user request): "make nodes easier to
understand when visualizing the graph" turned out to need real,
hand-authored labels, not a mechanically truncated `text` property --
truncated AC/Requirement prose reads as an arbitrary cut-off sentence in
Neo4j Browser, not a real title. Every Transition below now carries a
short, deliberately-composed `short_name` (its 15th tuple field) that a
human would actually use to refer to it; State gets a similar hand-
authored STATE_NAMES lookup (10 entries, one per real State in this
example). Intent/Requirement/AcceptanceCriterion/TestDesign all derive
their own `name` property from that SAME short_name (never truncated
text) so every node in this example gets a real caption Neo4j Browser
can show by default (it auto-captions on a `name` property when present).
TestCase keeps its existing real test-function-name `name` -- already
meaningful in a testing context, not something this pass needed to touch.
"""
import random

from metis_mcp.behavior_model import load_transition
from metis_mcp.confidence_tiering import ConfidenceTiering
from metis_mcp.ears_checker import check_ears_conformance
from metis_mcp.temporal import record_revision

REPO = "demo-login-webapp"

# Hand-authored, human-meaningful labels for every real State in this
# example -- used as State.name so Neo4j Browser's default caption (which
# prefers a `name` property) shows something readable instead of the raw
# `demo:login:state:...` id.
STATE_NAMES = {
    "LoggedOut": "Logged Out",
    "LoggedIn": "Logged In",
    "Failed1": "1 Failed Attempt",
    "Failed2": "2 Failed Attempts",
    "Failed3": "3 Failed Attempts",
    "Failed4": "4 Failed Attempts",
    "AccountLocked": "Account Locked",
    "PasswordResetRequested": "Password Reset Requested",
    "PasswordResetSent": "Password Reset Email Sent",
    "SessionExpired": "Session Expired",
}

# Each entry: (transition_id, short_name, from_state, to_state, trigger,
#              guard, intent_text, requirement_text, ac_texts, techniques,
#              test_levels, implementation_status, risk_tag, perf_critical,
#              functional_areas)
#
# short_name: a real, hand-authored short label for this Transition (see
# module docstring's "Display names" section) -- Intent/Requirement/
# AcceptanceCriterion/TestDesign all derive their own `name` from this
# same string, never from truncated `text`.
#
# functional_areas: a real, requested extension -- lets a one-line query
# find everything (Intent/Requirement/AcceptanceCriterion/TestDesign/
# TestCase/State/Transition) belonging to a named functional area, e.g.
# `MATCH (t:Transition) WHERE 'login' IN t.functional_areas RETURN t`.
# Array-valued since a node can genuinely belong to more than one area at
# once (e.g. t3-lockout is both "login" and "login-failed"). "login" is
# the coarse area every entry in this file shares; the second tag narrows
# to the specific sub-flow. See docs/metis-ontology-specification.md.
_TRANSITIONS = [
    (
        "t1-valid-login", "Valid login succeeds", "LoggedOut", "LoggedIn",
        "submit_valid_credentials",
        "credentials_valid AND NOT account_locked",
        "When a user submits valid credentials for an unlocked account, they should be logged in and taken to their dashboard.",
        "When the user submits valid credentials for an unlocked account, the login service shall authenticate the user and transition to the LoggedIn state.",
        [
            "Given valid credentials and an unlocked account, when the user submits the login form, then the system shall redirect to the dashboard within 2 seconds.",
            "Given valid credentials, when authentication succeeds, then a new session token shall be issued.",
        ],
        ["State Transition Testing", "Equivalence Partitioning"],
        ["unit", "api_functional", "web_functional", "e2e", "performance"],
        "implemented", "Medium", True, ["login", "login-successful"],
    ),
    # ---- Invalid-login increment chain: LoggedOut -> Failed1 -> Failed2 ->
    # Failed3 -> Failed4 -> AccountLocked. Each failure count is its own
    # real State (not a guard on a self-loop) -- see module docstring.
    (
        "t2a-invalid-login-attempt-1", "1st invalid login attempt", "LoggedOut", "Failed1",
        "submit_invalid_credentials",
        "NOT credentials_valid",
        "When a user submits invalid credentials for the first time, they should see an error and be allowed to retry.",
        "If the submitted credentials are invalid and this is the 1st failed attempt, then the login service shall reject the login and transition to the Failed1 state.",
        [
            "Given 0 prior failed attempts and invalid credentials, when the user submits the login form, then the system shall display an invalid-credentials error and set the failure count to 1.",
        ],
        ["Equivalence Partitioning"],
        ["unit", "api_functional"],
        "implemented", "Low", False, ["login", "login-failed"],
    ),
    (
        "t2b-invalid-login-attempt-2", "2nd invalid login attempt", "Failed1", "Failed2",
        "submit_invalid_credentials",
        "NOT credentials_valid",
        "When a user submits invalid credentials for the second time, they should see an error and be allowed to retry.",
        "If the submitted credentials are invalid and this is the 2nd failed attempt, then the login service shall reject the login and transition to the Failed2 state.",
        [
            "Given 1 prior failed attempt and invalid credentials, when the user submits the login form, then the system shall display an invalid-credentials error and set the failure count to 2.",
        ],
        ["Equivalence Partitioning"],
        ["unit", "api_functional"],
        "implemented", "Low", False, ["login", "login-failed"],
    ),
    (
        "t2c-invalid-login-attempt-3", "3rd invalid login attempt", "Failed2", "Failed3",
        "submit_invalid_credentials",
        "NOT credentials_valid",
        "When a user submits invalid credentials for the third time, they should see an error and be allowed to retry.",
        "If the submitted credentials are invalid and this is the 3rd failed attempt, then the login service shall reject the login and transition to the Failed3 state.",
        [
            "Given 2 prior failed attempts and invalid credentials, when the user submits the login form, then the system shall display an invalid-credentials error and set the failure count to 3.",
        ],
        ["Equivalence Partitioning"],
        ["unit", "api_functional"],
        "implemented", "Low", False, ["login", "login-failed"],
    ),
    (
        "t2d-invalid-login-attempt-4", "4th invalid login attempt (last chance)", "Failed3", "Failed4",
        "submit_invalid_credentials",
        "NOT credentials_valid",
        "When a user submits invalid credentials for the fourth time, one retry away from lockout, they should see an error and be allowed one final retry.",
        "If the submitted credentials are invalid and this is the 4th failed attempt, then the login service shall reject the login and transition to the Failed4 state.",
        [
            "Given 3 prior failed attempts and invalid credentials, when the user submits the login form, then the system shall display an invalid-credentials error and set the failure count to 4.",
        ],
        ["Boundary Value Analysis", "Equivalence Partitioning"],
        ["unit", "api_functional"],
        "implemented", "Medium", False, ["login", "login-failed"],
    ),
    (
        "t3-lockout", "Account locked after 5th failure", "Failed4", "AccountLocked",
        "submit_invalid_credentials",
        "NOT credentials_valid",
        "When a user exceeds the maximum number of failed login attempts (5 total), their account should be locked to prevent brute-force attacks.",
        "If the submitted credentials are invalid and this is the 5th failed attempt, then the login service shall lock the account and transition to the AccountLocked state.",
        [
            "Given exactly 4 prior failed attempts, when the 5th invalid submission occurs, then the system shall lock the account and notify the user by email.",
        ],
        ["Boundary Value Analysis", "State Transition Testing"],
        ["unit", "api_functional", "web_functional", "e2e"],
        "implemented", "High", False, ["login", "login-failed"],
    ),
    # ---- Valid-login recovery: credentials succeed from ANY pre-lockout
    # failure state, not just LoggedOut (t1) -- the exact gap explicit
    # states surfaced: the single-state model never asked "what happens on
    # a valid login after N prior failures?" for N in 1..4.
    (
        "t1b-valid-login-after-1-failure", "Valid login recovers after 1 failure", "Failed1", "LoggedIn",
        "submit_valid_credentials",
        "credentials_valid",
        "When a user submits valid credentials after 1 prior failed attempt, they should be logged in and their failure count cleared.",
        "When the user submits valid credentials after 1 prior failed attempt, the login service shall authenticate the user, reset the failure count, and transition to the LoggedIn state.",
        [
            "Given exactly 1 prior failed attempt and valid credentials, when the user submits the login form, then the system shall log the user in and reset the failure count to zero.",
        ],
        ["Equivalence Partitioning", "State Transition Testing"],
        ["unit", "api_functional"],
        "implemented", "Medium", False, ["login", "login-successful"],
    ),
    (
        "t1c-valid-login-after-2-failures", "Valid login recovers after 2 failures", "Failed2", "LoggedIn",
        "submit_valid_credentials",
        "credentials_valid",
        "When a user submits valid credentials after 2 prior failed attempts, they should be logged in and their failure count cleared.",
        "When the user submits valid credentials after 2 prior failed attempts, the login service shall authenticate the user, reset the failure count, and transition to the LoggedIn state.",
        [
            "Given exactly 2 prior failed attempts and valid credentials, when the user submits the login form, then the system shall log the user in and reset the failure count to zero.",
        ],
        ["Equivalence Partitioning", "State Transition Testing"],
        ["unit", "api_functional"],
        "implemented", "Medium", False, ["login", "login-successful"],
    ),
    (
        "t1d-valid-login-after-3-failures", "Valid login recovers after 3 failures", "Failed3", "LoggedIn",
        "submit_valid_credentials",
        "credentials_valid",
        "When a user submits valid credentials after 3 prior failed attempts, they should be logged in and their failure count cleared.",
        "When the user submits valid credentials after 3 prior failed attempts, the login service shall authenticate the user, reset the failure count, and transition to the LoggedIn state.",
        [
            "Given exactly 3 prior failed attempts and valid credentials, when the user submits the login form, then the system shall log the user in and reset the failure count to zero.",
        ],
        ["Equivalence Partitioning", "State Transition Testing"],
        ["unit", "api_functional"],
        "implemented", "Medium", False, ["login", "login-successful"],
    ),
    (
        "t1e-valid-login-after-4-failures", "Valid login recovers after 4 failures", "Failed4", "LoggedIn",
        "submit_valid_credentials",
        "credentials_valid",
        "When a user submits valid credentials after 4 prior failed attempts, they should still be able to log in on their last chance before lockout.",
        "When the user submits valid credentials after 4 prior failed attempts, the login service shall authenticate the user, reset the failure count, and transition to the LoggedIn state.",
        [
            "Given exactly 4 prior failed attempts and valid credentials, when the user submits the login form, then the system shall log the user in and reset the failure count to zero, without locking the account.",
        ],
        ["Boundary Value Analysis", "State Transition Testing"],
        ["unit", "api_functional"],
        "implemented", "Medium", False, ["login", "login-successful"],
    ),
    (
        "t4-forgot-password", "User requests password reset", "LoggedOut", "PasswordResetRequested",
        "click_forgot_password", "true",
        "When a user can't remember their password, they should be able to request a reset.",
        "When the user clicks 'forgot password', the login service shall transition to the PasswordResetRequested state.",
        [
            "Given the login page, when the user clicks 'forgot password', then the system shall display the password-reset request form.",
        ],
        ["State Transition Testing"],
        ["unit", "api_functional"],
        "implemented", "Low", False, ["login", "password-reset"],
    ),
    (
        "t5-reset-email-sent", "Password reset email sent", "PasswordResetRequested", "PasswordResetSent",
        "submit_reset_email",
        "email_registered",
        "When a user submits a registered email for password reset, they should receive a reset link.",
        "When the user submits a registered email address, the login service shall send a password reset link and transition to the PasswordResetSent state.",
        [
            "Given a registered email address, when the user submits the reset-request form, then the system shall send a reset link within 1 minute.",
        ],
        ["Equivalence Partitioning"],
        ["unit", "api_functional"],
        "implemented", "Medium", False, ["login", "password-reset"],
    ),
    (
        "t6-session-timeout", "Session expires from inactivity", "LoggedIn", "SessionExpired",
        "session_idle_timeout",
        "idle_time >= 30_minutes",
        "When a logged-in user is idle too long, their session should expire for security.",
        "While the user is idle for 30 minutes or more, the login service shall expire the session and transition to the SessionExpired state.",
        [
            "Given an active session idle for 30 minutes, when the timeout threshold is reached, then the system shall invalidate the session token.",
        ],
        ["Boundary Value Analysis"],
        ["unit", "api_functional"],
        "implemented", "Medium", False, ["login", "session-management"],
    ),
    (
        "t7-expired-redirect", "Expired session redirects to login", "SessionExpired", "LoggedOut",
        "any_action_after_expiry", "true",
        "When an expired-session user tries to do anything, they should be redirected to log back in.",
        "When a user with an expired session attempts any action, the login service shall redirect them to the LoggedOut state.",
        [
            "Given an expired session, when the user attempts any protected action, then the system shall redirect to the login page.",
        ],
        ["State Transition Testing"],
        ["unit", "api_functional"],
        "implemented", "Low", False, ["login", "session-management"],
    ),
    (
        "t8-account-unlock", "Account unlocked", "AccountLocked", "LoggedOut",
        "admin_unlock_or_lockout_elapsed",
        "lockout_period_elapsed OR admin_unlocked",
        "When the lockout period ends or an admin unlocks the account, the user should be able to try logging in again.",
        "If the lockout period has elapsed or an admin has unlocked the account, then the login service shall unlock the account and transition to the LoggedOut state.",
        [
            "Given a locked account whose lockout period has elapsed, when the next login attempt occurs, then the system shall allow the attempt.",
            "Given a locked account, when an admin issues an unlock action, then the account shall be immediately unlocked regardless of elapsed time.",
        ],
        ["Decision Table Testing"],
        ["unit", "api_functional"],
        "implemented", "Medium", False, ["login", "account-recovery"],
    ),
    (
        "t9-logout", "User logs out", "LoggedIn", "LoggedOut",
        "click_logout", "true",
        "When a logged-in user clicks logout, their session should end.",
        "When the user clicks 'logout', the login service shall terminate the session and transition to the LoggedOut state.",
        [
            "Given an active session, when the user clicks logout, then the system shall invalidate the session token and redirect to the login page.",
        ],
        ["State Transition Testing"],
        ["unit", "api_functional"],
        "implemented", "Low", False, ["login", "session-management"],
    ),
    (
        "t10-2fa-enrollment", "User enrolls in 2FA (planned)", "LoggedIn", "LoggedIn",
        "enroll_2fa", "true",
        "When a logged-in user wants to enable two-factor authentication, they should be able to enroll.",
        "When the user opts into two-factor authentication, the login service shall initiate 2FA enrollment.",
        [],  # nothing to test yet -- planned, not built
        [],
        [],
        "planned", "Medium", False, ["login", "2fa"],
    ),
]


def build_login_example(session, r: random.Random, episode_fn, DEMO_TAG: str,
                         batch_merge_nodes, batch_merge_rels, edge_props_fn,
                         iso_fn, rand_past_fn) -> dict:
    """Returns {"nodes": {label: count}, "relationships": {rel_type: count},
    "requirements_written": int, "planned_transitions": int}."""
    node_counts: dict[str, int] = {}
    rel_counts: dict[str, int] = {}

    def add_nodes(label, rows):
        if rows:
            batch_merge_nodes(session, label, rows)
        node_counts[label] = node_counts.get(label, 0) + len(rows)

    def add_rels(from_label, to_label, rel_type, pairs):
        if pairs:
            batch_merge_rels(session, from_label, to_label, rel_type, pairs)
        rel_counts[rel_type] = rel_counts.get(rel_type, 0) + len(pairs)

    def revise(entity_id: str, properties: dict, source_episode_id: str):
        record_revision(session, entity_id, properties, source_episode_id)
        # record_revision creates one real :Revision node per call (every
        # call here is a genuine first revision, never a second one) --
        # counted here since it writes directly, bypassing add_nodes.
        node_counts["Revision"] = node_counts.get("Revision", 0) + 1
        rel_counts["HAS_REVISION"] = rel_counts.get("HAS_REVISION", 0) + 1

    tiering = ConfidenceTiering()
    requirements_written = 0
    planned_transitions = 0
    # States are shared across multiple Transitions (e.g. LoggedOut is the
    # from-state of t1/t2a/t4 and the to-state of t7/t8) -- functional_areas
    # is a real union across every Transition touching that State, computed
    # here and SET once at the end, not per-transition (which would only
    # ever reflect the LAST transition's tags, silently dropping the rest).
    state_areas: dict[str, set[str]] = {}

    # One real (demo-tagged) Repository/Class -- same "as if real" demo
    # convention the synthetic/grounded layers already use elsewhere in
    # this generator (real repo:path:name id convention, clearly
    # is_demo_data-tagged, never claimed to be actually-running code).
    # Needed so metis_mcp/pyramid_gap_check.py has a real
    # implementing_method_id to compute real coverage against for this
    # example -- omitting it entirely would make check_pyramid_gaps
    # report every login Transition as "not determinable", defeating the
    # point of proving the backbone against the platform's own real tools.
    login_episode = episode_fn()
    repo_row = {"id": REPO, "source_episode_id": login_episode, "name": REPO,
                "source_kind": "behavior_example", DEMO_TAG: True}
    add_nodes("Repository", [repo_row])
    class_path = "src/login/auth_service.py"
    class_id = f"{REPO}:{class_path}:AuthService"
    add_nodes("Class", [{"id": class_id, "source_episode_id": login_episode, "name": "AuthService",
                         "source_file": class_path, "source_kind": "behavior_example", DEMO_TAG: True}])
    add_rels("Repository", "Class", "DEFINES",
             [{"from": REPO, "to": class_id, "props": {}}])

    # Every node is written (add_nodes with a single-item list) and then
    # immediately revised (record_revision) before anything that
    # references it -- record_revision requires the entity to already
    # exist (it raises rather than silently no-op on a missing id, a real
    # bug temporal.py itself fixed in an earlier session), so nodes and
    # their edges/revisions can't be batched to the end of the function
    # the way the bulk synthetic/grounded layers do.
    for (tid, short_name, from_state, to_state, trigger, guard, intent_text, req_text, ac_texts,
         techniques, test_levels, impl_status, risk_tag, perf_critical,
         functional_areas) in _TRANSITIONS:
        episode_id = episode_fn()
        transition_id = f"demo:login:transition:{tid}"
        method_id = f"{REPO}:{class_path}:AuthService.handle_{tid.replace('-', '_')}"
        for state_id in (f"demo:login:state:{from_state}", f"demo:login:state:{to_state}"):
            state_areas.setdefault(state_id, set()).update(functional_areas)

        # Real Transition via the real, already-established load_transition()
        # (Session 6 precedent) -- creates/merges the real State nodes and
        # WHEN/THEN edges (renamed from FROM_STATE/TO_STATE, then LAUNCHES/
        # LANDS_IN, in a later session -- State-[:WHEN]->Transition-[:THEN]->
        # State mirrors the Given/When/Then shape a Transition already
        # structurally is); trigger/guard_expression are set directly as
        # Transition properties (a later session removed Trigger/Guard as
        # separate node types -- both are attributes of exactly one
        # Transition, not their own entities).
        # implementing_method_id points at the real (demo-tagged) Method
        # created below for `implemented` transitions -- omitted for
        # `planned` ones (no real code exists yet, so claiming one would be
        # fabricated corroboration evidence, REQ-METIS-BM-01).
        load_transition(
            session, transition_id, episode_id, f"demo:login:state:{from_state}",
            f"demo:login:state:{to_state}", trigger, guard,
            implementing_method_id=(method_id if impl_status == "implemented" else None),
            performance_sla_critical=perf_critical,
        )
        session.run(
            "MATCH (t:Transition {id: $id}) SET t.implementation_status = $status, "
            "t.functional_areas = $areas, t.is_demo_data = true, t.source_kind = 'behavior_example', "
            "t.name = $name",
            id=transition_id, status=impl_status, areas=functional_areas, name=short_name,
        ).consume()
        for state_id, state_key in ((f"demo:login:state:{from_state}", from_state),
                                     (f"demo:login:state:{to_state}", to_state)):
            session.run(
                "MATCH (s:State {id: $id}) SET s.implementation_status = $status, "
                "s.is_demo_data = true, s.source_kind = 'behavior_example', s.name = $name",
                id=state_id, status=impl_status, name=STATE_NAMES.get(state_key, state_key),
            ).consume()
        revise(transition_id, {"implementation_status": impl_status}, episode_id)

        # Intent: the atomic, informal statement -- the real hub. No longer
        # linked directly from Transition (see module docstring) --
        # AcceptanceCriterion-[:VALIDATES]->Transition below is the only
        # bridge back to real behavior, for `implemented` transitions only.
        # name = the same hand-authored short_name as its Transition (see
        # module docstring's "Display names" section) -- never a truncation
        # of `intent_text`.
        intent_id = f"demo:login:intent:{tid}"
        add_nodes("Intent", [{
            "id": intent_id, "source_episode_id": episode_id, "text": intent_text,
            "name": short_name, "revision": 1, "lifecycle_state": "Draft",
            "source_kind": "behavior_example", "functional_areas": functional_areas, DEMO_TAG: True,
        }])
        revise(intent_id, {"text": intent_text}, episode_id)

        # Requirement: EARS-formalized version of the Intent -- real,
        # re-validated through the unmodified checker, never force-tagged.
        ears = check_ears_conformance(req_text)
        if not ears.conformant:
            continue  # matches real Layer 2 behavior: never written
        confidence = r.uniform(0.9, 0.98)
        tier_result = tiering.evaluate(confidence=confidence, structural_valid=True, has_contradiction=False)
        if not tier_result.written_to_graph:
            continue

        req_id = f"demo:login:requirement:{tid}"
        add_nodes("Requirement", [{
            "id": req_id, "source_episode_id": episode_id, "text": req_text,
            "name": f"Requirement: {short_name}", "ears_pattern": ears.pattern, "revision": 1,
            "corroboration_count": 2, "risk_tag": risk_tag, "lifecycle_state": tier_result.lifecycle_state,
            "confidence_tier": tier_result.tier.value, "source_kind": "behavior_example",
            "functional_areas": functional_areas, DEMO_TAG: True,
        }])
        requirements_written += 1
        revise(req_id, {"lifecycle_state": tier_result.lifecycle_state, "revision": 1}, episode_id)
        add_rels("Requirement", "Intent", "TRACES_TO",
                 [{"from": req_id, "to": intent_id, "props": edge_props_fn(r, rand_past_fn(r))}])

        if impl_status == "implemented":
            add_nodes("Method", [{
                "id": method_id, "source_episode_id": episode_id,
                "name": f"handle_{tid.replace('-', '_')}", "source_file": class_path,
                "source_kind": "behavior_example", DEMO_TAG: True,
            }])
            add_rels("Class", "Method", "HAS_METHOD",
                     [{"from": class_id, "to": method_id, "props": {}}])
            add_rels("Method", "Requirement", "IMPLEMENTS",
                     [{"from": method_id, "to": req_id, "props": edge_props_fn(r, rand_past_fn(r))}])

        if impl_status == "planned":
            planned_transitions += 1
            continue  # deliberately no AC/TestDesign/TestCase -- nothing to test yet

        ac_ids = []
        for j, ac_text in enumerate(ac_texts):
            ac_id = f"{req_id}:ac-{j}"
            # name: short_name plus a 1-based index -- readable even when a
            # Transition has 2+ ACs (e.g. t1/t8), never a truncation of the
            # full Given/When/Then `ac_text`.
            add_nodes("AcceptanceCriterion", [{
                "id": ac_id, "source_episode_id": episode_id, "text": ac_text,
                "name": f"{short_name} — AC {j + 1}", "revision": 1, "source_kind": "behavior_example",
                "functional_areas": functional_areas, DEMO_TAG: True,
            }])
            revise(ac_id, {"text": ac_text}, episode_id)
            add_rels("Requirement", "AcceptanceCriterion", "HAS_AC",
                     [{"from": req_id, "to": ac_id, "props": edge_props_fn(r, rand_past_fn(r))}])
            add_rels("AcceptanceCriterion", "Intent", "TRACES_TO",
                     [{"from": ac_id, "to": intent_id, "props": edge_props_fn(r, rand_past_fn(r))}])
            # AcceptanceCriterion is the real bridge to the concrete
            # behavior it validates -- the only edge connecting the
            # Intent/Requirement backbone to this Transition now that
            # Transition no longer traces to Intent directly.
            add_rels("AcceptanceCriterion", "Transition", "VALIDATES",
                     [{"from": ac_id, "to": transition_id, "props": edge_props_fn(r, rand_past_fn(r))}])
            ac_ids.append(ac_id)

        # TestDesign: one per Intent, names the real technique(s), COVERS
        # every AC, PRODUCES the resulting TestCases. name uses the same
        # hand-authored short_name (was f"Test design: {tid}", the raw
        # transition id -- less readable than the real short label).
        design_id = f"demo:login:testdesign:{tid}"
        add_nodes("TestDesign", [{
            "id": design_id, "source_episode_id": episode_id,
            "name": f"Test design: {short_name}", "techniques": techniques,
            "revision": 1, "lifecycle_state": "Draft", "source_kind": "behavior_example",
            "functional_areas": functional_areas, DEMO_TAG: True,
        }])
        revise(design_id, {"techniques": techniques}, episode_id)
        add_rels("TestDesign", "Intent", "TRACES_TO",
                 [{"from": design_id, "to": intent_id, "props": edge_props_fn(r, rand_past_fn(r))}])
        add_rels("TestDesign", "AcceptanceCriterion", "COVERS",
                 [{"from": design_id, "to": aid, "props": edge_props_fn(r, rand_past_fn(r))} for aid in ac_ids])

        path = f"tests/login/test_{tid.replace('-', '_')}.py"
        for level in test_levels:
            test_name = f"test_{tid.replace('-', '_')}_{level}"
            tc_id = f"{REPO}:{path}:{test_name}"
            add_nodes("TestCase", [{
                "id": tc_id, "source_episode_id": episode_id, "name": test_name,
                "type": level, "lifecycle_state": "Draft", "source_kind": "behavior_example",
                "functional_areas": functional_areas, DEMO_TAG: True,
            }])
            revise(tc_id, {"type": level}, episode_id)
            add_rels("TestDesign", "TestCase", "PRODUCES",
                     [{"from": design_id, "to": tc_id, "props": edge_props_fn(r, rand_past_fn(r))}])
            # Every level verifies the first (primary) AC -- real, not every
            # level needs a distinct AC for a small, illustrative example.
            add_rels("TestCase", "AcceptanceCriterion", "VERIFIES",
                     [{"from": tc_id, "to": ac_ids[0], "props": edge_props_fn(r, rand_past_fn(r))}])

    # record_revision's real :Revision nodes don't carry is_demo_data
    # themselves (a generic mechanism with no notion of demo data) --
    # tagged here in one follow-up pass.
    session.run(
        "MATCH (n {source_kind: 'behavior_example'})-[:HAS_REVISION]->(rev:Revision) "
        "SET rev.is_demo_data = true, rev.source_kind = 'behavior_example'"
    ).consume()

    # Each State's functional_areas is the real UNION across every
    # Transition that touches it (built up in state_areas during the main
    # loop above) -- set once here, not inline per-transition, so a shared
    # State (e.g. LoggedOut, touched by t1/t2a/t4/t7/t8) ends up with every
    # real tag, not just whichever transition happened to SET it last.
    for state_id, areas in state_areas.items():
        session.run(
            "MATCH (s:State {id: $id}) SET s.functional_areas = $areas",
            id=state_id, areas=sorted(areas),
        ).consume()

    # State/Transition are created directly by the real load_transition()
    # (Session 6 precedent), bypassing add_nodes/add_rels -- MERGE-
    # deduplicates States shared across multiple Transitions, so their
    # real count can't be guessed inline; queried here for real instead.
    # Trigger/Guard are plain Transition properties now (a later session
    # removed them as separate node types), so there's nothing left to
    # count for them.
    for label in ("State", "Transition"):
        real_count = session.run(
            f"MATCH (n:{label} {{source_kind: 'behavior_example'}}) RETURN count(n) AS c"
        ).single()["c"]
        node_counts[label] = real_count
    for rel_type, pattern in (
        ("WHEN", "()-[r:WHEN]->(t:Transition {source_kind: 'behavior_example'})"),
        ("THEN", "(t:Transition {source_kind: 'behavior_example'})-[r:THEN]->()"),
    ):
        real_count = session.run(f"MATCH {pattern} RETURN count(r) AS c").single()["c"]
        rel_counts[rel_type] = real_count

    return {
        "nodes": node_counts,
        "relationships": rel_counts,
        "requirements_written": requirements_written,
        "planned_transitions": planned_transitions,
    }
