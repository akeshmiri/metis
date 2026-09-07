"""
The execution policy — the change to X-7a (spec §8.7, C-11, N-1).

X-7a said Métis never touches the system it models. That is now a tier, off by
default, and these tests are what make it a guarantee rather than a claim: the
same shape `test_mcp_write_policy.py` gives the write half.

The one that matters most is `test_the_off_default_is_structural`. Everything
else here is a runtime check, and a runtime check can be bypassed by a caller
that forgets to make it. That one asserts the modules are not importable at all.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

from metis_mcp import execution
from metis_mcp.execution import (
    CapabilityUnavailable,
    ExecutionDisabled,
    ExecutionRefused,
    authorise,
)

PACKAGE = pathlib.Path(__file__).parent / "metis_mcp"


# --------------------------------------------------------------------------
# The tiers
# --------------------------------------------------------------------------

def test_the_default_is_no_contact(monkeypatch):
    """A system that starts able to touch production is one nobody chose to
    make able to."""
    monkeypatch.delenv(execution.EXECUTE_ENV, raising=False)
    assert execution.tier() == execution.OFF
    assert not execution.may_observe() and not execution.may_run()


def test_an_unknown_tier_halts_rather_than_defaulting(monkeypatch):
    """`METIS_EXECUTE=observ` must not silently become `off` — that is a system
    refusing every read for a reason nothing states."""
    monkeypatch.setenv(execution.EXECUTE_ENV, "observ")
    with pytest.raises(ExecutionDisabled) as e:
        execution.tier()
    assert "observ" in str(e.value)


def test_off_refuses_before_anything_is_contacted(monkeypatch):
    monkeypatch.setenv(execution.EXECUTE_ENV, execution.OFF)
    with pytest.raises(ExecutionDisabled) as e:
        authorise("sql", "postgres://somewhere/db")
    assert "Nothing was contacted" in str(e.value)


def test_observe_may_read_and_may_not_run(monkeypatch):
    """Reading a replica is recoverable; driving load at the wrong host is an
    outage. Different decisions, different tiers."""
    monkeypatch.setenv(execution.EXECUTE_ENV, execution.OBSERVE)
    with pytest.raises(ExecutionDisabled) as e:
        authorise("load", "https://staging.example.com", writes=True,
                  confirmation=execution.RUN_LITERAL)
    assert "running is not" in str(e.value)


def test_a_run_costs_the_literal_in_the_call(monkeypatch):
    """The same shape as G1/G2: no default-yes, no truthy value. A caller that
    can pass `True` by accident can pass it against production by accident."""
    monkeypatch.setenv(execution.EXECUTE_ENV, execution.RUN)
    for given in ("", "yes", "y", "true", "1", "run", "EXECUTE"):
        with pytest.raises(ExecutionRefused):
            authorise("load", "https://staging.example.com", writes=True,
                      confirmation=given)


def test_a_missing_extra_names_the_package_not_an_import_error(monkeypatch):
    """`No module named 'psycopg2'` three frames into a query builder tells a
    reader nothing about which extra to install."""
    monkeypatch.setenv(execution.EXECUTE_ENV, execution.OBSERVE)
    with pytest.raises(CapabilityUnavailable) as e:
        authorise("sql", "postgres://somewhere/db")
    assert "psycopg2" in str(e.value) and "metis[execute]" in str(e.value)


# --------------------------------------------------------------------------
# The structural guarantee
# --------------------------------------------------------------------------

def test_the_off_default_is_structural():
    """**The load-bearing one.** With no tier configured, the observer and
    runner modules must not be importable through the server at all — not merely
    refused at call time. A runtime check can be forgotten by one caller.
    """
    probe = (
        "import os, sys\n"
        "os.environ.pop('METIS_EXECUTE', None)\n"
        "import metis_mcp.server\n"
        "bad = [m for m in sys.modules\n"
        "       if m.startswith('metis_mcp.observers')\n"
        "       or m.startswith('metis_mcp.runners')]\n"
        "print(','.join(sorted(bad)))\n"
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, cwd=pathlib.Path(__file__).parent)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", (
        f"SUT-contact modules reachable at the default tier: {out.stdout}")


def test_execution_never_imports_a_sut_client_at_module_level():
    """The policy module decides whether contact is allowed. If importing it
    pulled in a database driver, `off` would already have loaded the thing it
    exists to withhold."""
    tree = ast.parse((PACKAGE / "execution.py").read_text())
    top_level = {
        alias.name.split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in getattr(node, "names", [])
    }
    for forbidden in ("psycopg2", "kubernetes", "locust", "requests"):
        assert forbidden not in top_level


# --------------------------------------------------------------------------
# Provenance — the rule the tiers exist to keep
# --------------------------------------------------------------------------

def test_every_contact_is_recorded_with_what_it_touched(monkeypatch):
    """N-1. An unrecorded read of a live system is indistinguishable afterwards
    from one that never happened."""
    monkeypatch.setenv(execution.EXECUTE_ENV, execution.OBSERVE)
    contact = execution.Contact(target="cluster/ns", capability="kubernetes",
                                tier=execution.OBSERVE, actor="dana")
    entry = execution.record(contact, "read 12 log lines")
    assert entry["target"] == "cluster/ns" and entry["actor"] == "dana"
    assert entry["tier"] == execution.OBSERVE


def test_an_observed_fact_is_labelled_as_observed(monkeypatch):
    """**The whole reason this module exists.** A fact read from a running
    system is not a fact about what the code says it does. Merging them is how a
    coverage figure becomes a correctness claim (§8.7, C-11)."""
    contact = execution.Contact(target="t", capability="sql", tier="observe")
    assert execution.record(contact, "ok")["provenance"] == \
        "observed_from_running_system"


def test_describe_names_what_is_missing_rather_than_only_what_works(monkeypatch):
    """A capability map that lists only successes is how somebody discovers a
    missing driver at the moment they need it."""
    monkeypatch.setenv(execution.EXECUTE_ENV, execution.OBSERVE)
    described = execution.describe()
    assert described["tier"] == execution.OBSERVE
    assert "not_installed" in described
    assert "observed" in described["means"]
