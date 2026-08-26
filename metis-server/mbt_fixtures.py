"""
Shared test fixtures for the MBT engine, rendering and review suites.

The login model here is a real recovered model -- 10 states and 17 transitions,
of which 16 are `implemented` and 1 (2FA enrolment) is `planned`. Its shape was
extracted rather than invented, so assertions like "covers every implemented
transition" are checkable claims rather than self-fulfilling ones.

It was lifted from `demo_data/login_example.py`, which went with the v1 engine;
this file is the only copy now, which is why the shape is stated here rather
than by pointing at a path a reader cannot open.

Kept out of the test files themselves so three suites can share it without
importing each other.
"""
from metis_mcp.mbt.model import APPROVED, IMPLEMENTED, PLANNED, QUARANTINE, Model, State, Transition

# (state id, is_initial)
STATES = [
    ("LoggedOut", True), ("LoggedIn", False), ("Failed1", False), ("Failed2", False),
    ("Failed3", False), ("Failed4", False), ("AccountLocked", False),
    ("PasswordResetRequested", False), ("PasswordResetSent", False),
    ("SessionExpired", False),
]

# (id, source, trigger, target, guard, implementation_status)
TRANSITIONS = [
    ("t01", "LoggedOut", "submit_valid_credentials", "LoggedIn",
     "credentials_valid AND NOT account_locked", IMPLEMENTED),
    ("t02", "LoggedOut", "submit_invalid_credentials", "Failed1",
     "NOT credentials_valid", IMPLEMENTED),
    ("t03", "Failed1", "submit_invalid_credentials", "Failed2", "NOT credentials_valid", IMPLEMENTED),
    ("t04", "Failed2", "submit_invalid_credentials", "Failed3", "NOT credentials_valid", IMPLEMENTED),
    ("t05", "Failed3", "submit_invalid_credentials", "Failed4", "NOT credentials_valid", IMPLEMENTED),
    ("t06", "Failed4", "submit_invalid_credentials", "AccountLocked",
     "NOT credentials_valid", IMPLEMENTED),
    ("t07", "Failed1", "submit_valid_credentials", "LoggedIn",
     "credentials_valid AND NOT account_locked", IMPLEMENTED),
    ("t08", "Failed2", "submit_valid_credentials", "LoggedIn",
     "credentials_valid AND NOT account_locked", IMPLEMENTED),
    ("t09", "Failed3", "submit_valid_credentials", "LoggedIn",
     "credentials_valid AND NOT account_locked", IMPLEMENTED),
    ("t10", "Failed4", "submit_valid_credentials", "LoggedIn",
     "credentials_valid AND NOT account_locked", IMPLEMENTED),
    ("t11", "LoggedOut", "click_forgot_password", "PasswordResetRequested", "", IMPLEMENTED),
    ("t12", "PasswordResetRequested", "submit_reset_email", "PasswordResetSent",
     "email_registered", IMPLEMENTED),
    ("t13", "LoggedIn", "session_idle_timeout", "SessionExpired", "idle_exceeds_timeout", IMPLEMENTED),
    ("t14", "SessionExpired", "any_action_after_expiry", "LoggedOut", "", IMPLEMENTED),
    ("t15", "AccountLocked", "admin_unlock_or_lockout_elapsed", "LoggedOut",
     "admin_unlocked OR lockout_elapsed", IMPLEMENTED),
    ("t16", "LoggedIn", "click_logout", "LoggedOut", "", IMPLEMENTED),
    ("t17", "LoggedIn", "enroll_2fa", "LoggedIn", "", PLANNED),
]

IMPLEMENTED_IDS = {t[0] for t in TRANSITIONS if t[5] == IMPLEMENTED}


def login_model(approved: bool = True) -> Model:
    """The fixture, explicitly approved by default.

    Approval is stated rather than assumed: the dataclass default is
    `Quarantine` (spec S-4 -- every source produces candidates), so a model that
    generates must have been through a decision. `approved=False` gives the
    pre-review state, used to prove the G1 gate actually blocks.
    """
    lifecycle = APPROVED if approved else QUARANTINE
    return Model(
        id="login-api",
        states={sid: State(id=sid, name=sid, surface="api", is_initial=init,
                           lifecycle_state=lifecycle)
                for sid, init in STATES},
        transitions={t[0]: Transition(id=t[0], source=t[1], trigger=t[2], target=t[3],
                                      guard=t[4], implementation_status=t[5],
                                      lifecycle_state=lifecycle)
                     for t in TRANSITIONS},
    )


def login_model_source() -> dict:
    """The model as a source would emit it: structure only, no lifecycle."""
    return {
        "id": "login-api",
        "states": [{"id": s, "name": s, "surface": "api", "is_initial": i}
                   for s, i in STATES],
        "transitions": [{"id": t[0], "source": t[1], "trigger": t[2], "target": t[3],
                         "guard": t[4], "implementation_status": t[5]}
                        for t in TRANSITIONS],
    }
