"""
Write to Jira and GitLab (spec T-20, and the reason `code_analysis/tracker.py`
could not do it).

**Why this is a separate module from the reader.** `tracker.ENDPOINTS` is a
closed allowlist of GET paths and `assert_read_only` checks every URL before it
is issued, so a reader that grew a write fails in the test suite rather than in
front of somebody's tracker. That guarantee is worth keeping exactly as it is.
Writing therefore lives here, with its own client, its own credential, and its
own gate — rather than by loosening the thing that made the reader safe.

Ported from Atlas's `bug-reporter` and `merge-request-creator`. What crossed:
filing a defect with its evidence, opening a merge request behind a review gate,
and the duplicate check both do first. What did not: Atlas's project keys, its
board configuration, its Teams notifications, and its AI-authorship labelling.

**Every create checks first, and an unverifiable check blocks.** Two defects for
one failure is the common outcome of a retry, and the second one is filed by
somebody who could not see the first.
"""
from __future__ import annotations

from metis_mcp.publishing.outward import (
    OutwardWriteFailed,
    Unverifiable,
    credential,
    lookup,
    quote,
    request,
)
from metis_mcp.publishing.publish import Transport

JIRA_URL_ENV = "METIS_JIRA_BASE_URL"
JIRA_TOKEN_ENV = "METIS_JIRA_TOKEN"
GITLAB_URL_ENV = "METIS_GITLAB_BASE_URL"
GITLAB_TOKEN_ENV = "METIS_GITLAB_TOKEN"


class _Gated(Transport):
    """Borrows `Transport.check_permitted` for its installation switch.

    Not because these are publication transports — they are not, and no `Batch`
    routes through them — but because the gate is the same gate, and a second
    implementation of "may this installation write outward" is a second thing
    that can be wrong.
    """

    is_dry_run = False

    def send(self, operation):                      # pragma: no cover - not a batch
        raise NotImplementedError(
            f"{self.name} is not a publication transport; call its own methods")


class JiraWriter(_Gated):
    """File and update Jira issues."""

    name = "jira"

    def __init__(self, project: str = ""):
        self.base_url = credential(JIRA_URL_ENV, "filing a Jira issue").rstrip("/")
        self._token = credential(JIRA_TOKEN_ENV, "filing a Jira issue")
        self.project = project

    def existing_issue(self, summary: str) -> str | None:
        """The key of an open issue with this summary, or None.

        Raises `Unverifiable` when the search itself could not run — which is
        the case that must never be read as "no duplicate".
        """
        jql = (f'project = "{self.project}" AND summary ~ '
               f'"\\"{summary}\\"" AND resolution = Unresolved')
        found = lookup("GET",
                       f"{self.base_url}/rest/api/2/search?jql={quote(jql)}"
                       f"&maxResults=5",
                       token=self._token)
        for issue in found.get("issues", []):
            if issue.get("fields", {}).get("summary", "").strip() == summary.strip():
                return issue.get("key")
        return None

    def create_issue(self, summary: str, description: str, *,
                     issue_type: str = "Bug", labels: tuple = (),
                     skip_duplicate_check: bool = False) -> dict:
        """File one issue, after checking that it is not already filed."""
        self.check_permitted()
        if not skip_duplicate_check:
            existing = self.existing_issue(summary)
            if existing:
                raise OutwardWriteFailed(
                    f"an unresolved issue with this summary already exists as "
                    f"{existing}. Nothing was filed: whether to update it or "
                    f"file a second is a decision for a person.")

        created = request(
            "POST", f"{self.base_url}/rest/api/2/issue", token=self._token,
            body={"fields": {
                "project": {"key": self.project},
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
                "labels": list(labels),
            }})
        return {"ok": True, "key": created.get("key"),
                "url": f"{self.base_url}/browse/{created.get('key')}"}


    def update_issue_summary(self, key: str, summary: str) -> dict:
        """Rewrite one issue's summary. **Never its description or status.**

        Deliberately the narrowest possible write. A requirement is the summary
        line; a description carries a tester's notes, reproduction steps and
        links, and a status is somebody's workflow. Métis has an opinion about
        exactly one of those three, and a PUT that sent all of them would
        destroy the other two while looking like a wording fix.

        **The caller has already decided this is safe.** `plan_writeback`
        classifies a hand-edited ticket as `MANUALLY_EDITED` and proposes
        nothing for it (T-15), so anything reaching here is a ticket that still
        says what Métis last wrote.
        """
        self.check_permitted()
        if not (key or "").strip():
            raise OutwardWriteFailed("no issue key — nothing says which to update")
        if not (summary or "").strip():
            raise OutwardWriteFailed(
                "refusing to write an empty summary. A requirement with no text "
                "has nothing to be true or false about")

        request("PUT", f"{self.base_url}/rest/api/2/issue/{quote(key)}",
                token=self._token, body={"fields": {"summary": summary}})
        return {"ok": True, "key": key,
                "url": f"{self.base_url}/browse/{key}"}


class GitLabWriter(_Gated):
    """Open and update merge requests."""

    name = "gitlab"

    def __init__(self, project_id: str = ""):
        self.base_url = credential(GITLAB_URL_ENV, "opening a merge request").rstrip("/")
        self._token = credential(GITLAB_TOKEN_ENV, "opening a merge request")
        self.project_id = project_id

    def _api(self, path: str) -> str:
        return f"{self.base_url}/api/v4/projects/{quote(self.project_id)}{path}"

    def existing_merge_request(self, source_branch: str) -> str | None:
        found = lookup(
            "GET",
            self._api(f"/merge_requests?state=opened&source_branch="
                      f"{quote(source_branch)}"),
            token=self._token, auth_scheme="Bearer")
        for mr in found if isinstance(found, list) else []:
            return str(mr.get("iid"))
        return None

    def create_merge_request(self, source_branch: str, target_branch: str,
                             title: str, description: str, *,
                             blocking_findings: tuple = (),
                             skip_duplicate_check: bool = False) -> dict:
        """Open one merge request, gated on review findings.

        **The review gate is the ported half that matters.** Atlas's
        `merge-request-creator` runs a code review first and blocks on Critical
        or Major findings, because an MR opened over known blockers asks a
        reviewer to re-find what was already found. The findings are passed in
        rather than computed here: this module writes, and deciding what counts
        as blocking is not a write.
        """
        self.check_permitted()
        if blocking_findings:
            raise OutwardWriteFailed(
                f"{len(blocking_findings)} blocking finding(s) — nothing was "
                f"opened. An MR raised over known blockers asks a reviewer to "
                f"re-find what was already found: "
                f"{'; '.join(str(f)[:80] for f in blocking_findings[:3])}")

        if not skip_duplicate_check:
            existing = self.existing_merge_request(source_branch)
            if existing:
                raise OutwardWriteFailed(
                    f"an open merge request from {source_branch!r} already "
                    f"exists as !{existing}. Nothing was opened.")

        created = request(
            "POST", self._api("/merge_requests"), token=self._token,
            body={"source_branch": source_branch, "target_branch": target_branch,
                  "title": title, "description": description})
        return {"ok": True, "iid": created.get("iid"),
                "url": created.get("web_url", "")}
