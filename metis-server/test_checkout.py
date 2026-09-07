"""
Obtaining a repository to analyse (Atlas's `git-repository-cloner`).

**A git URL is an execution vector**, which is why this module is not three
lines: `ext::sh -c '<cmd>'` runs the command, and a remote that is really an
option (`--upload-pack=...`) becomes a flag. Every test below is about refusing
those by shape rather than trusting the caller — the same stance
`observers/sql.assert_read_only` takes toward a statement it cannot prove reads.
"""
from __future__ import annotations

import subprocess

import pytest

from metis_mcp.checkout import (
    CheckoutFailed,
    UnsafeRemote,
    assert_fetchable,
    clone,
)


@pytest.fixture
def origin(tmp_path):
    src = tmp_path / "origin"
    src.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@example.com"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(src), *args], check=True,
                       capture_output=True)
    (src / "a.txt").write_text("hi")
    subprocess.run(["git", "-C", str(src), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(src), "commit", "-qm", "first"],
                   check=True, capture_output=True)
    return src


# --------------------------------------------------------------------------
# The execution vectors
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "ext::sh -c 'id'",                       # the documented RCE transport
    "--upload-pack=/bin/sh",                 # a remote that is really an option
    "-x",                                    # ditto, short form
    "file:///etc/passwd",                    # local transport by URL
    "https://host/repo\nid",                 # newline smuggling
    "",                                      # nothing
])
def test_an_execution_vector_is_refused_by_shape(url):
    with pytest.raises(UnsafeRemote):
        assert_fetchable(url)


@pytest.mark.parametrize("url", [
    "https://github.com/owner/repo.git",
    "ssh://git@host/owner/repo",
    "git@github.com:owner/repo.git",
])
def test_an_ordinary_remote_is_allowed(url):
    """The guard must not become a machine that only refuses."""
    assert_fetchable(url)


def test_an_unrecognised_form_is_refused_rather_than_allowed(tmp_path):
    """Default-deny. A path that is not a checkout is not a remote."""
    with pytest.raises(UnsafeRemote):
        assert_fetchable(str(tmp_path / "not-a-repo"))


def test_an_existing_local_checkout_is_allowed(origin):
    """Narrow on purpose: it must already BE a repository. Local transport runs
    nothing, and this is what makes the happy path testable with no network."""
    assert_fetchable(str(origin))


# --------------------------------------------------------------------------
# Cloning
# --------------------------------------------------------------------------

def test_a_clone_produces_a_working_tree(origin, tmp_path):
    out = clone(str(origin), tmp_path / "work")
    assert out["ok"] is True
    assert (tmp_path / "work" / "a.txt").read_text() == "hi"
    assert out["commit"] != "unknown"


def test_it_is_shallow_by_default(origin, tmp_path):
    """It exists to be read once and thrown away; full history is cost with no
    reader."""
    assert clone(str(origin), tmp_path / "w")["depth"] == 1
    assert clone(str(origin), tmp_path / "w2", depth=0)["depth"] == "full"


def test_it_refuses_to_overwrite_by_default(origin, tmp_path):
    """The one command here capable of destroying work."""
    clone(str(origin), tmp_path / "w")
    with pytest.raises(CheckoutFailed) as e:
        clone(str(origin), tmp_path / "w")
    assert "does not overwrite" in str(e.value)


def test_replace_refuses_a_directory_that_is_not_a_checkout(origin, tmp_path):
    """`replace=True` on a mistyped path could otherwise delete a home
    directory as easily as a scratch one."""
    victim = tmp_path / "precious"
    victim.mkdir()
    (victim / "work.txt").write_text("do not delete")
    with pytest.raises(CheckoutFailed) as e:
        clone(str(origin), victim, replace=True)
    assert "not a git checkout" in str(e.value)
    assert (victim / "work.txt").exists()


def test_replace_does_replace_an_actual_checkout(origin, tmp_path):
    clone(str(origin), tmp_path / "w")
    assert clone(str(origin), tmp_path / "w", replace=True)["ok"] is True


def test_a_failure_message_never_echoes_the_remote(tmp_path):
    """A URL may carry a token somebody put there despite PLT-005, and this
    string ends up in logs."""
    src = tmp_path / "repo"
    src.mkdir()
    (src / ".git").mkdir()                       # passes the shape check
    with pytest.raises(CheckoutFailed) as e:
        clone(str(src), tmp_path / "out")
    assert str(src) not in str(e.value)


def test_the_result_states_it_is_an_intake_source_not_the_sut(origin, tmp_path):
    """X-7a: reading a repository is not calling the service it builds, which is
    why this needs no execution tier."""
    assert "X-7a" in clone(str(origin), tmp_path / "w")["means"]
