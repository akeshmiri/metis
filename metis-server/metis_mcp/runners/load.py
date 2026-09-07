"""
Drive a load test (run tier).

Ported from Atlas's `locust-workflow`. What crossed is the shape — a scenario
built from a contract Métis already holds, run against a named host, reported as
observation. What did not is Atlas's project layout, its wrappers and its
performance report format.

**This is the sharpest edge in Métis.** Everything else the system does is either
read-only or lands at `Quarantine` in a graph that can be thrown away. A load
test makes real requests at a real host, and no gate downstream can undo one that
has already been sent. Hence: the `run` tier, the literal, and a host that must
be named explicitly and is never inferred from a model or a config.

**What comes back is an observation, not a verdict.** A latency figure says what
happened on one run against one environment. It is not a statement that the
system meets a target, and R8 still holds for the artefact: the scenario is
specification, and the runner executes it.
"""
from __future__ import annotations

from metis_mcp.execution import RUN_LITERAL, authorise, record


def run_scenario(host: str, scenario_path: str, *, users: int = 1,
                 spawn_rate: int = 1, run_time: str = "30s",
                 confirmation: str = "", actor: str = "") -> dict:
    """Execute a load scenario against `host` and report what was observed.

    `host` is required and never defaulted. A load runner that inferred its
    target from a config file is one keystroke away from pointing at production
    because somebody's environment variable was still set from yesterday.
    """
    if not host.strip():
        raise ValueError(
            "a load test needs an explicit host. It is never inferred: the "
            "inferred one is production more often than anybody expects")

    contact = authorise("load", host, writes=True, confirmation=confirmation,
                        actor=actor)

    import subprocess

    result = subprocess.run(
        ["locust", "--headless", "--only-summary",
         "-f", scenario_path, "--host", host,
         "-u", str(users), "-r", str(spawn_rate), "-t", run_time],
        capture_output=True, text=True, timeout=_timeout_for(run_time))

    record(contact, f"ran {users} user(s) for {run_time}",
           {"exit_code": result.returncode})
    return {
        "ok": result.returncode == 0,
        "host": host,
        "users": users,
        "run_time": run_time,
        "summary": result.stdout[-4000:],
        # Kept even when empty is falsy: a run that failed for an environmental
        # reason and one that failed on assertions are different answers.
        "stderr": result.stderr[-2000:] or "none",
        "provenance": "observed_from_running_system",
        "means": ("what happened on one run against one environment. Not a "
                  "statement that the system meets a target (C-11)"),
        "gate": f"required {RUN_LITERAL!r} in the call, and METIS_EXECUTE=run",
    }


def _timeout_for(run_time: str) -> int:
    """A wall-clock ceiling a little past the requested duration.

    Without one a hung run holds the process open indefinitely, and the caller
    cannot tell a long test from a stuck one.
    """
    units = {"s": 1, "m": 60, "h": 3600}
    value, unit = run_time[:-1], run_time[-1:].lower()
    try:
        return int(float(value) * units.get(unit, 1)) + 60
    except ValueError:
        return 360
