"""
Writes that leave Métis: Jira, GitLab, and the shared client under them.

**No test here makes a network call.** `urlopen` is replaced. What is asserted is
the gate, the duplicate check, and what a failure says — because a test needing a
real tracker would either be skipped forever or leave records somebody has to
clean up, and this is the one part of Métis whose mistakes are not disposable.
"""
from __future__ import annotations

import json
import urllib.error

import pytest

from metis_mcp.publishing import outward
from metis_mcp.publishing.outward import OutwardWriteFailed, Unverifiable
from metis_mcp.publishing.publish import ExternalWritesDisabled
from metis_mcp.publishing.tracker_write import GitLabWriter, JiraWriter


@pytest.fixture
def configured(monkeypatch):
    for name, value in (
        ("METIS_JIRA_BASE_URL", "https://tracker.example.com"),
        ("METIS_JIRA_TOKEN", "jira-token"),
        ("METIS_GITLAB_BASE_URL", "https://git.example.com"),
        ("METIS_GITLAB_TOKEN", "gitlab-token"),
        ("METIS_ALLOW_EXTERNAL_WRITES", "yes"),
    ):
        monkeypatch.setenv(name, value)


def _responds(monkeypatch, by_url):
    """`by_url` maps a substring of the URL to the document returned."""
    def _fake(request, timeout=None):
        body = {}
        for fragment, document in by_url.items():
            if fragment in request.full_url:
                body = document
                break

        class _R:
            def read(self):
                return json.dumps(body).encode()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        _fake.last = request
        return _R()
    monkeypatch.setattr(outward.urllib.request, "urlopen", _fake)
    return _fake


def _fails(monkeypatch, error=None):
    def _boom(request, timeout=None):
        raise error or urllib.error.URLError("unreachable")
    monkeypatch.setattr(outward.urllib.request, "urlopen", _boom)


# --------------------------------------------------------------------------
# The installation switch
# --------------------------------------------------------------------------

def test_neither_writer_works_without_the_installation_switch(monkeypatch,
                                                              configured):
    """A credential is not permission. The switch is set by a person on a
    machine; a token is set by whatever is driving the run."""
    monkeypatch.delenv("METIS_ALLOW_EXTERNAL_WRITES", raising=False)
    with pytest.raises(ExternalWritesDisabled):
        JiraWriter("DEMO").create_issue("s", "d")
    with pytest.raises(ExternalWritesDisabled):
        GitLabWriter("7").create_merge_request("a", "main", "t", "d")


def test_a_secret_never_comes_from_an_argument(monkeypatch):
    """PLT-005. Neither constructor takes a token; both read the environment."""
    import inspect

    for cls in (JiraWriter, GitLabWriter):
        params = inspect.signature(cls.__init__).parameters
        assert not any("token" in p for p in params), cls.__name__


def test_a_missing_credential_says_which_variable(monkeypatch):
    monkeypatch.delenv("METIS_JIRA_TOKEN", raising=False)
    monkeypatch.setenv("METIS_JIRA_BASE_URL", "https://tracker.example.com")
    with pytest.raises(OutwardWriteFailed) as e:
        JiraWriter("DEMO")
    assert "METIS_JIRA_TOKEN" in str(e.value)


# --------------------------------------------------------------------------
# Check before you create
# --------------------------------------------------------------------------

def test_an_already_filed_defect_is_not_filed_twice(monkeypatch, configured):
    _responds(monkeypatch, {"/search": {
        "issues": [{"key": "DEMO-11", "fields": {"summary": "Login fails"}}]}})
    with pytest.raises(OutwardWriteFailed) as e:
        JiraWriter("DEMO").create_issue("Login fails", "evidence")
    assert "DEMO-11" in str(e.value)


def test_a_failed_jira_search_blocks_rather_than_filing(monkeypatch, configured):
    """**The rule.** Two defects for one failure is what a retry produces when
    the second run could not see the first."""
    _fails(monkeypatch)
    with pytest.raises(Unverifiable) as e:
        JiraWriter("DEMO").create_issue("Login fails", "evidence")
    assert "not evidence of absence" in str(e.value)


def test_a_clean_search_files_the_defect(monkeypatch, configured):
    """The guard must not become a machine that only refuses."""
    _responds(monkeypatch, {"/search": {"issues": []},
                            "/issue": {"key": "DEMO-12"}})
    out = JiraWriter("DEMO").create_issue("Login fails", "evidence")
    assert out["key"] == "DEMO-12" and "DEMO-12" in out["url"]


def test_an_open_merge_request_is_not_opened_twice(monkeypatch, configured):
    _responds(monkeypatch, {"/merge_requests": [{"iid": 9}]})
    with pytest.raises(OutwardWriteFailed) as e:
        GitLabWriter("7").create_merge_request("feat/x", "main", "t", "d")
    assert "!9" in str(e.value)


# --------------------------------------------------------------------------
# The review gate
# --------------------------------------------------------------------------

def test_blocking_findings_stop_the_merge_request(monkeypatch, configured):
    """Ported from merge-request-creator: an MR raised over known blockers asks
    a reviewer to re-find what was already found."""
    _responds(monkeypatch, {"/merge_requests": []})
    with pytest.raises(OutwardWriteFailed) as e:
        GitLabWriter("7").create_merge_request(
            "feat/x", "main", "t", "d",
            blocking_findings=("SQL injection in RecordController",))
    assert "blocking finding" in str(e.value)
    assert "SQL injection" in str(e.value)


def test_no_findings_opens_the_merge_request(monkeypatch, configured):
    _responds(monkeypatch, {"/merge_requests": []})
    fake = _responds(monkeypatch, {"/merge_requests": []})
    # The create returns the MR; the lookup returns a list. Distinguish by method.
    def _fake(request, timeout=None):
        body = {"iid": 5, "web_url": "https://git.example.com/mr/5"} \
            if request.method == "POST" else []

        class _R:
            def read(self):
                return json.dumps(body).encode()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        return _R()
    monkeypatch.setattr(outward.urllib.request, "urlopen", _fake)
    out = GitLabWriter("7").create_merge_request("feat/x", "main", "t", "d")
    assert out["iid"] == 5


# --------------------------------------------------------------------------
# What a failure says
# --------------------------------------------------------------------------

def test_an_unreachable_remote_says_the_outcome_is_unknown(monkeypatch,
                                                           configured):
    """A caller told "failed" retries; a retry after a write that landed creates
    a duplicate."""
    _fails(monkeypatch)
    with pytest.raises(OutwardWriteFailed) as e:
        outward.request("POST", "https://x.example.com/a", token="t", body={})
    assert "UNKNOWN" in str(e.value) and "duplicate" in str(e.value)


def test_a_failure_message_carries_no_request_body_or_token(monkeypatch,
                                                            configured):
    """It ends up in logs, beside an Authorization header."""
    import io

    _fails(monkeypatch, urllib.error.HTTPError(
        "https://x.example.com/a?secret=leak", 401, "Unauthorized", {},
        io.BytesIO(b"")))
    with pytest.raises(OutwardWriteFailed) as e:
        outward.request("POST", "https://x.example.com/a?secret=leak",
                        token="sensitive-token", body={"field": "sensitive"})
    assert "sensitive" not in str(e.value)
    assert "secret=leak" not in str(e.value)
