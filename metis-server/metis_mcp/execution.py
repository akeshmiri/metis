"""
The execution policy: the single place contact with the System Under Test is
permitted, refused, or recorded — and the change to X-7a.

**What X-7a said, and what is kept.** "Métis never executes anything against the
System Under Test": it read intake sources and wrote its own graph, and
`connectors/intakes.json` deliberately had no access mode that ran something.
That prohibition is lifted by an explicit product decision. What it was
protecting is not.

The rule the tiers exist to keep: **a model recovered from evidence and a model
confirmed by touching the system are different claims, and a report must never
present the second as the first.** Reading a log tells you what happened once. It
is not what the code says it does, and §8.7's staged-out execution labels are
staged out because ingesting one as the other is how a coverage figure becomes a
correctness claim (C-11).

    execution.py    this module — the one place SUT contact is permitted
    observers/      read a live system: logs, a query, a cluster's state
    runners/        make something happen: a load test, a suite

**Three tiers, and `off` is the default, structurally.** At `off` the observer
and runner modules are never imported, so a deployment nobody configured cannot
reach the system it models — the same property `METIS_MCP_WRITE=off` gives the
write half, and provable the same way, by a subprocess that asserts the modules
are absent from `sys.modules`.

  * `off`      — no contact. The default, because a system that starts able to
                 touch production is one nobody chose to make able to.
  * `observe`  — READ a live system. Queries, logs, cluster state. Nothing it
                 does changes the system under test.
  * `run`      — also MAKE SOMETHING HAPPEN: execute a suite, drive load.

`observe` before `run` is not decoration. Reading a replica is recoverable and a
load test against the wrong host is an outage, so they are different decisions
and cost different words.

**The dependencies are optional and that is the point.** A database driver and a
Kubernetes client are installed by `pip install metis[execute]`; a default
install has neither, which is what keeps the four-dependency, database-free
property the test suite depends on. `require()` names the missing package rather
than failing on an ImportError three frames down.

**Every contact is recorded** with the target it touched, the tier that allowed
it, and who asked — the same audit obligation a write carries (N-1). An
unrecorded read of a production system is indistinguishable afterwards from one
that never happened.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

EXECUTE_ENV = "METIS_EXECUTE"

# The literal a `run` costs, in the call that runs it. Distinct from the write
# gates' words on purpose: a confirmation typed to approve a model must not
# satisfy a request to drive load at somebody's staging environment.
RUN_LITERAL = "execute"

OFF, OBSERVE, RUN = "off", "observe", "run"
TIERS = (OFF, OBSERVE, RUN)

# What each optional capability needs, named so a refusal can say it. Kept here
# rather than caught as an ImportError at the call site: "No module named
# 'psycopg2'" three frames into a query builder tells a reader nothing about
# which extra to install.
REQUIREMENTS = {
    "sql": ("psycopg2", "pip install 'metis[execute]' — a PostgreSQL driver"),
    "kubernetes": ("kubernetes", "pip install 'metis[execute]' — a cluster client"),
    "load": ("locust", "pip install 'metis[load]' — the load-test runner"),
}


class ExecutionDisabled(Exception):
    """Raised when SUT contact is attempted on a deployment not configured for it."""


class CapabilityUnavailable(Exception):
    """Raised when the tier permits it and the dependency is not installed."""


class ExecutionRefused(Exception):
    """Raised when a `run` is attempted without its literal."""


def tier() -> str:
    """The configured execution tier. An unknown value halts, never defaults.

    Falling back to `off` would look safe and be wrong in the same way
    `policy.mode` describes: an operator who typed `METIS_EXECUTE=observ` would
    get a system that refuses every read for a reason nothing states.
    """
    value = os.environ.get(EXECUTE_ENV, OFF).strip().lower() or OFF
    if value not in TIERS:
        raise ExecutionDisabled(
            f"{EXECUTE_ENV}={value!r} is not one of {', '.join(TIERS)}.")
    return value


def may_observe() -> bool:
    return tier() in (OBSERVE, RUN)


def may_run() -> bool:
    return tier() == RUN


@dataclass
class Contact:
    """Permission for one piece of SUT contact, and the receipt it must produce."""

    target: str
    capability: str
    tier: str
    actor: str = ""
    recorded: list = field(default_factory=list)


def require(capability: str) -> None:
    """Refuse before the import fails, naming the extra that supplies it."""
    package, remedy = REQUIREMENTS.get(capability, (capability, "install it"))
    try:
        __import__(package)
    except ImportError:
        raise CapabilityUnavailable(
            f"{capability!r} needs {package!r}, which this install does not "
            f"have: {remedy}. It is an optional extra so that a default install "
            f"stays dependency-light and needs no database to test.") from None


def authorise(capability: str, target: str, *, writes: bool = False,
              confirmation: str = "", actor: str = "") -> Contact:
    """Permit one contact with the system under test, or refuse and say why.

    Three checks, in this order, because they fail for different reasons and the
    caller needs to know which: a deployment that forbids contact is a different
    problem from a missing driver, and both differ from a run with no literal.
    """
    current = tier()

    if current == OFF:
        raise ExecutionDisabled(
            f"this deployment does not touch the system under test: "
            f"{EXECUTE_ENV} is {OFF!r}. Set it to {OBSERVE!r} to read a live "
            f"system, or {RUN!r} to also make something happen. Nothing was "
            f"contacted.")

    if writes and current != RUN:
        raise ExecutionDisabled(
            f"{capability} would make something happen and {EXECUTE_ENV} is "
            f"{current!r}. Reading is permitted; running is not. Nothing was "
            f"contacted.")

    if writes and confirmation != RUN_LITERAL:
        # The same shape as G1/G2: the exact word, in this call. No default-yes,
        # no timeout-implies-yes, and no truthy value -- a caller that can pass
        # `True` by accident can pass it against production by accident.
        raise ExecutionRefused(
            f"{capability} against {target!r} needs the literal word "
            f"{RUN_LITERAL!r} in this call. Nothing was contacted.")

    require(capability)
    return Contact(target=target, capability=capability, tier=current,
                   actor=actor)


def record(contact: Contact, outcome: str, detail: dict | None = None) -> dict:
    """The receipt. An unrecorded touch of a live system is unaccountable.

    Returned rather than written to a store: the caller owns where its audit
    goes, and `policy.record` already owns the graph-write trail. What matters
    here is that the target and the tier travel with the result, so a figure
    derived from a live read can never be mistaken later for one derived from
    the model.
    """
    entry = {
        "surface": "execution",
        "target": contact.target,
        "capability": contact.capability,
        "tier": contact.tier,
        "actor": contact.actor or "unknown",
        "outcome": outcome,
        # Load-bearing, and the reason this module exists: everything downstream
        # must be able to tell a fact read from a running system from one
        # recovered from source. They are different claims (§8.7, C-11).
        "provenance": "observed_from_running_system",
    }
    if detail:
        entry["detail"] = detail
    contact.recorded.append(entry)
    return entry


def describe() -> dict:
    """What this deployment may touch, what it may not, and what is missing."""
    current = tier()
    available, missing = {}, {}
    for capability, (package, remedy) in sorted(REQUIREMENTS.items()):
        try:
            require(capability)
            available[capability] = package
        except CapabilityUnavailable:
            missing[capability] = remedy
    return {
        "tier": current,
        "may_observe": may_observe(),
        "may_run": may_run(),
        "installed": available or "none",
        "not_installed": missing or "none",
        "run_costs": f"the literal {RUN_LITERAL!r} in the call",
        "means": ("a fact observed from a running system is not a fact about "
                  "what the code says it does; both are kept, never merged "
                  "(§8.7, C-11)"),
    }
