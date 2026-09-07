"""
A live `Transport` for Zephyr Scale (spec T-20, T-21, C3).

**The first thing here that leaves Métis.** Every other write in this system
lands at `Quarantine` in a graph the project owns and can throw away; this one
creates records in somebody else's tracker, and they stay there. That asymmetry
is why the gate in front of it is two keys rather than one.

`DryRunTransport` remains the default and is not replaced. Selecting this one is
an explicit act, and even then `Transport.check_permitted` refuses unless
`METIS_ALLOW_EXTERNAL_WRITES=yes` on the installation. The reason that second switch
exists is written in `publish.py` and is worth repeating, because it is the whole
argument for how this is gated:

    A G2 confirmation is not enough on its own: the literal can be supplied by
    whatever is driving the run, including an agent.

So a real write needs a word supplied in the run *and* a deployment somebody
configured to permit one. An agent can produce the first and cannot produce the
second.

**Credentials never come from an argument** (PLT-005). `METIS_ZEPHYR_TOKEN`
names the token the way `METIS_NEO4J_PASSWORD` does: a secret on a command line
is in the shell history, the process listing, and any log that captures argv.

**It checks before it creates, and an unverifiable check blocks.** The ledger is
not enough on its own: nothing populated `PublicationLedger.published` until
`drift.record_publication` was written, so the first live run against an existing
dry-run ledger sees every case as new. A search that fails is not evidence of
absence -- reading a timed-out lookup as "nothing there" is exactly how a
duplicate gets created -- so a failed search refuses the operation.

**stdlib only, deliberately.** Métis has four runtime dependencies and `requests`
is not one of them; adding an HTTP library to send a handful of JSON documents
would be the fifth, paid for by everyone who never publishes anything.

Ported from Atlas (`.agents/skills/test-case-reporter`), which owned the seven
Zephyr Scale actions. What crossed is the action set and the endpoint shapes.
What did not: its Python client, its config resolution, and its approval prompt —
Métis already has G2, and a second confirmation would be a second thing to keep
correct.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from metis_mcp.publishing.publish import CREATE, DEPRECATE, UPDATE, Operation, Transport

BASE_URL_ENV = "METIS_ZEPHYR_BASE_URL"
TOKEN_ENV = "METIS_ZEPHYR_TOKEN"        # the secret itself, from the environment
PROJECT_ENV = "METIS_ZEPHYR_PROJECT"

# The subset of Atlas's seven actions that a Métis publication can produce.
# `Batch` only ever emits create / update / deprecate (`publish._ACTION_FOR`),
# so the read actions -- folder creation, cycle search, result posting -- have no
# caller here and are deliberately absent rather than written and unreachable.
_ENDPOINT = {
    CREATE: ("POST", "/testcase"),
    UPDATE: ("PUT", "/testcase/{key}"),
    DEPRECATE: ("PUT", "/testcase/{key}"),
}

TIMEOUT_SECONDS = 30


class PublicationFailed(Exception):
    """The tracker refused or could not be reached. Nothing further is sent."""


class ZephyrScaleTransport(Transport):
    """Creates and updates Zephyr Scale test cases.

    `is_dry_run` is False, which is what arms `check_permitted` -- the base class
    treats a dry run as always allowed and everything else as needing the
    installation switch.
    """

    name = "zephyr-scale"
    is_dry_run = False

    def __init__(self, base_url: str = "", project_key: str = "",
                 token: str | None = None,
                 skip_duplicate_check: bool = False) -> None:
        self.base_url = (base_url or os.environ.get(BASE_URL_ENV, "")).rstrip("/")
        self.project_key = project_key or os.environ.get(PROJECT_ENV, "")
        # Read once, at construction, so a half-configured installation fails
        # before a batch is confirmed rather than between two of its operations.
        self._token = token if token is not None else os.environ.get(TOKEN_ENV, "")
        self.sent: list[tuple[str, str]] = []          # (case_id, published id)
        # For a batch already verified unique. Never the default, and it is
        # reported rather than assumed -- a flag that silently disables a safety
        # check is worse than not having the check.
        self.skip_duplicate_check = skip_duplicate_check

    def check_permitted(self) -> None:
        """The installation switch first, then whether this can work at all.

        Configuration is checked here rather than in `send` because a batch is
        confirmed as one decision (T-19). Discovering a missing base URL on
        operation four would leave three records created and the rest not.
        """
        super().check_permitted()                # METIS_ALLOW_EXTERNAL_WRITES
        missing = [name for name, value in
                   ((BASE_URL_ENV, self.base_url), (TOKEN_ENV, self._token),
                    (PROJECT_ENV, self.project_key)) if not value]
        if missing:
            raise PublicationFailed(
                f"{self.name} is not configured: {', '.join(missing)} unset. "
                f"Nothing was sent.")

    def _existing_key(self, name: str) -> str | None:
        """The key of an existing case with this name, or None.

        Raises `PublicationFailed` when the lookup itself could not run. That
        distinction is the point: `None` means "searched, found nothing" and an
        exception means "could not tell", and only the first is safe to create
        on.
        """
        query = (f'projectKey = "{self.project_key}" AND name = '
                 f'"{name}"'.replace("\n", " "))
        request = urllib.request.Request(
            f"{self.base_url}/testcase/search?query="
            f"{urllib.parse.quote(query)}",
            method="GET",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                document = json.loads(response.read().decode("utf-8") or "{}")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                json.JSONDecodeError) as e:
            raise PublicationFailed(
                f"could not check whether {name!r} already exists: {e}. "
                f"A failed lookup is not evidence of absence, so nothing was "
                f"created. Fix the lookup or pass an explicit decision.") from None

        values = document.get("values") or document.get("results") or []
        for candidate in values:
            if str(candidate.get("name", "")).strip() == name.strip():
                return str(candidate.get("key") or candidate.get("id") or "")
        return None

    def send(self, operation: Operation) -> str:
        """Perform one write and return the published id.

        The returned id is what `DryRunTransport` structurally cannot produce,
        and it is what populates `PublicationLedger.published` -- so the
        `MANUALLY_EDITED` and `OBSOLETE` drift classes have a live source of
        published content for the first time.
        """
        method, template = _ENDPOINT[operation.action]

        # **Check before creating.** Only a create can duplicate: update and
        # deprecate address an existing record by id.
        if operation.action == CREATE and not self.skip_duplicate_check:
            name = str(operation.payload.get("name", "")).strip()
            if not name:
                raise PublicationFailed(
                    f"{operation.case_id} has no name to check for duplicates "
                    f"against; nothing was created")
            existing = self._existing_key(name)
            if existing:
                raise PublicationFailed(
                    f"a Zephyr case named {name!r} already exists as "
                    f"{existing}. Nothing was created: whether to update it or "
                    f"add a second one is a decision for a person, not for "
                    f"this transport.")
        if "{key}" in template and not operation.published_id:
            raise PublicationFailed(
                f"{operation.action} on {operation.case_id} needs the id of an "
                f"existing case and the ledger holds none")
        path = template.replace("{key}", operation.published_id or "")

        body = dict(operation.payload)
        body["projectKey"] = self.project_key
        if operation.action == DEPRECATE:
            # Deprecation is a status change, never a delete: a published case
            # somebody may have run is evidence, and removing it destroys the
            # record of what was verified.
            body["status"] = "Deprecated"

        published = self._request(method, path, body)
        self.sent.append((operation.case_id, published))
        return published

    # --- the four actions a publication batch never produces -----------------
    #
    # `Batch` only ever emits create / update / deprecate, so these have no
    # caller in the publish path. They exist because organising and reporting
    # cases is half of what a tracker is for, and a transport that could only
    # create left that half on the CLI of another project.
    #
    # Each one is a write outside Métis and goes through the same
    # `check_permitted` as a send: the installation switch is not per-method.

    def create_folder(self, name: str, parent_id: str = "") -> str:
        """A folder to put cases in. Returns its id."""
        self.check_permitted()
        body = {"projectKey": self.project_key, "name": name,
                "folderType": "TEST_CASE"}
        if parent_id:
            body["parentId"] = parent_id
        return self._request("POST", "/folder", body)

    def search_cycles(self, query: str = "") -> list:
        """Test cycles matching a TQL query. A read, and still gated: it needs
        the same credential, and a caller that cannot write has no use for it."""
        self.check_permitted()
        return self._search("/testcycle/search", query or
                            f'projectKey = "{self.project_key}"')

    def add_to_cycle(self, cycle_key: str, case_key: str,
                     status: str = "Not Executed") -> str:
        """Put an existing case into a cycle. Returns the created run id.

        **Not an execution result.** Métis ingests none (§8.7), so the status is
        the tracker's own scheduling state and never a claim that anything ran.
        """
        return self._request(
            "POST", f"/testexecution",
            {"projectKey": self.project_key, "testCycleKey": cycle_key,
             "testCaseKey": case_key, "statusName": status})

    def update_status(self, case_key: str, status: str) -> str:
        """Change a case's own status — active, deprecated, draft."""
        return self._request("PUT", f"/testcase/{case_key}",
                             {"projectKey": self.project_key, "status": status})

    def _search(self, path: str, query: str) -> list:
        request = urllib.request.Request(
            f"{self.base_url}{path}?query={urllib.parse.quote(query)}",
            method="GET",
            headers={"Authorization": f"Bearer {self._token}"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                document = json.loads(response.read().decode("utf-8") or "{}")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                json.JSONDecodeError) as e:
            # Not an empty list. A search that could not run is `unknown`, and
            # returning `[]` is how the duplicate guard gets defeated.
            raise PublicationFailed(
                f"search of {path} could not run: {e}. An empty result and a "
                f"failed lookup are different answers.") from None
        return document.get("values") or document.get("results") or []

    def _request(self, method: str, path: str, body: dict) -> str:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            method=method,
            headers={"Authorization": f"Bearer {self._token}",
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as e:
            # The status and the tracker's own message, and never the request
            # body: it carries the Authorization header's neighbourhood and the
            # case content, and this string ends up in logs.
            raise PublicationFailed(
                f"{method} {path} refused with {e.code}: "
                f"{e.reason}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise PublicationFailed(
                f"{method} {path} could not be reached: {e}. Whether the write "
                f"landed is UNKNOWN -- check the tracker before retrying, "
                f"because a retry would create a duplicate.") from None

        try:
            document = json.loads(raw)
        except json.JSONDecodeError:
            raise PublicationFailed(
                f"{method} {path} returned a body that is not JSON") from None

        published = document.get("key") or document.get("id")
        if not published:
            # The write may well have succeeded. Saying so plainly beats
            # inventing an id, which would put a fiction in the ledger.
            raise PublicationFailed(
                f"{method} {path} succeeded and returned no `key` or `id`, so "
                f"the published id is unknown and cannot be recorded")
        return str(published)
