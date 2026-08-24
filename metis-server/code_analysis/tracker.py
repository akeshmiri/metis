"""
An issue tracker as an intake — Jira and Zephyr Scale (spec §5.2b, X-7a).

**The half that was missing.** `intake_landing.ANCHORS` has mapped `jira ->
JiraItem` and `scale -> ZephyrItem` since the evidence layer landed, and
`metis intake land` carries a UIF into the graph — but nothing produced the UIF.
The skill's `jira_extractor` calls `jira_client.issue(key).raw` if it is handed a
client and **nothing constructed one**; `scale_extractor` raised
`NotImplementedError("API client not yet implemented")` outright. So both
trackers were reachable in principle and unreachable in practice.

Shaped deliberately like `db_catalogue`, because that split is what keeps the
suite honest:

    from_fixture()   a captured response — what the test suite exercises
    read()           a live read, against a transport THE CALLER opened

**The transport is the caller's**, exactly as the database connection is, and
for the same reason: a credential is not this module's business. The profile
names an environment variable and the value never reaches an argument
(PLT-005). `get` is any callable taking a URL and returning parsed JSON, so
`requests`, `httpx` or a stub all work and none of them is a dependency here.

**Read-only by construction, not by intention.** `ENDPOINTS` is a closed
allowlist of GET paths — v1's connector manifest carried a `tool_allowlist` for
the same reason — and `assert_read_only` checks every URL before it is issued,
the way `assert_no_row_reads` checks every statement. A reader that grew a POST
fails here rather than in front of somebody's tracker.

X-7a is untouched: a tracker Métis reads to learn what somebody *said* the
system should do is an intake source. It is not the System Under Test, and
nothing here writes to it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

TRACKER_VERSION = "metis.tracker-item/1"
UIF_VERSION = "1.0"

# `source_system` values, keyed as `intake_landing.ANCHORS` already keys them:
# Zephyr Scale's extractor writes "scale", not "zephyr", and renaming it here
# would silently detach every item from its `ZephyrItem` anchor.
JIRA = "jira"
ZEPHYR = "scale"


class TrackerRefused(Exception):
    """The tracker could not be read — shape or access, not content."""


# The closed allowlist. A path not in here cannot be requested, and adding one
# is a reviewed change rather than an edit — the same bar `CATALOGUE_SOURCES`
# sets for a SQL statement.
ENDPOINTS: dict[str, str] = {
    JIRA: "{base}/rest/api/3/issue/{key}",
    ZEPHYR: "{base}/v2/testcases/{key}",
}

# What each tracker calls the fields this reads. Declared rather than inlined so
# the mapping is inspectable, and so a deployment whose Jira renames a field can
# be diagnosed by reading one dict.
FIELDS: dict[str, dict[str, str]] = {
    JIRA: {"title": "summary", "description": "description",
           "item_type": "issuetype", "status": "status", "labels": "labels"},
    ZEPHYR: {"title": "name", "description": "objective",
             "item_type": "$static:TestCase", "status": "status",
             "labels": "labels"},
}


@dataclass(frozen=True)
class TrackerItem:
    """One issue or test case, normalised.

    Deliberately thin. What a tracker holds that Métis has no use for is not
    carried: a fact serves the model or it is not landed (X-6d), and an
    intake that hoards its source's every field makes the graph a second copy
    of the tracker rather than a model of the system.
    """

    system: str
    key: str
    title: str = ""
    description: str = ""
    item_type: str = ""
    status: str = ""
    labels: tuple[str, ...] = ()
    source_url: str = ""


@dataclass(frozen=True)
class TrackerRead:
    system: str
    base_url: str
    items: tuple[TrackerItem, ...] = field(default_factory=tuple)

    def keys(self) -> set[str]:
        return {i.key for i in self.items}


def assert_read_only(urls) -> None:
    """Every URL must be an allowlisted GET path. Raises otherwise.

    The analogue of `db_catalogue.assert_no_row_reads`, and it exists for the
    same reason: the discipline that matters is the one a test can fail, not the
    one a docstring asserts.
    """
    import re

    # **Whole-URL, not substring.** A substring test accepts
    # `/rest/api/3/issue/X/transitions` — the endpoint that MOVES a ticket —
    # because the allowed read path is a prefix of it. The key is one segment
    # and nothing may follow it.
    patterns = [
        re.compile("^" + re.escape(template)
                   .replace(r"\{base\}", r".+")
                   .replace(r"\{key\}", r"[^/?#]+") + "$")
        for template in ENDPOINTS.values()]
    allowed = ", ".join(sorted(ENDPOINTS.values()))
    for url in urls:
        if not any(p.match(url) for p in patterns):
            raise TrackerRefused(
                f"{url!r} is not an allowlisted read path. This intake may "
                f"only GET {allowed} — adding a path is a reviewed change, "
                f"and a write is not available at all (X-7a)")


def _collapse(text: str) -> str:
    """Runs of whitespace to one space. An ADF text node carries its own
    trailing space and joining on another produces a double."""
    return " ".join(text.split())


def _text(value) -> str:
    """Jira's ADF description, or a plain string, as text.

    Atlassian Document Format is a nested node tree. Only the text nodes are
    taken and **nothing is reconstructed** — no bullet markers, no headings.
    A rendering that looked like the original but was not it is worse than the
    plain text, because a reviewer would compare it to the ticket and trust it.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        if "text" in value and isinstance(value["text"], str):
            return value["text"]
        return _collapse(" ".join(
            t for t in (_text(c) for c in value.get("content", ())) if t))
    if isinstance(value, (list, tuple)):
        return _collapse(" ".join(t for t in (_text(v) for v in value) if t))
    return str(value)


def _named(value) -> str:
    """`{"name": "Story"}` / `{"value": "Done"}` / `"Story"` — all to a string."""
    if isinstance(value, dict):
        return str(value.get("name") or value.get("value") or "")
    return str(value or "")


def item_from_payload(system: str, key: str, payload: dict,
                      base_url: str = "") -> TrackerItem:
    """One tracker response object, normalised. Pure."""
    if system not in FIELDS:
        raise TrackerRefused(
            f"unknown tracker {system!r}. Known: {', '.join(sorted(FIELDS))}. "
            f"Adding one needs an anchor label in `intake_landing.ANCHORS`, "
            f"which is an ontology change under D-2")
    names = FIELDS[system]
    # Jira nests everything under `fields`; Zephyr Scale is flat.
    body = payload.get("fields") if isinstance(payload.get("fields"), dict) else payload

    def pick(which: str):
        name = names[which]
        if name.startswith("$static:"):
            return name.split(":", 1)[1]
        return body.get(name)

    labels = pick("labels") or ()
    return TrackerItem(
        system=system,
        key=str(payload.get("key") or key),
        title=_text(pick("title")),
        description=_text(pick("description")),
        item_type=_named(pick("item_type")),
        status=_named(pick("status")),
        labels=tuple(str(x) for x in labels if x),
        source_url=(f"{base_url.rstrip('/')}/browse/{key}"
                    if base_url and system == JIRA else ""),
    )


def from_fixture(path: str | Path) -> TrackerRead:
    """A captured tracker response — what the suite exercises.

    `read()` produces the same shape, so everything downstream is tested against
    this and the transport is the only untested part. The same split
    `db_catalogue` and the query packs use.
    """
    data = json.loads(Path(path).read_text())
    version = data.get("tracker_version")
    if version != TRACKER_VERSION:
        raise TrackerRefused(
            f"unknown tracker_version {version!r}; this build reads "
            f"{TRACKER_VERSION!r}")
    system = data.get("system", "")
    base_url = data.get("base_url", "")
    return TrackerRead(
        system=system, base_url=base_url,
        items=tuple(item_from_payload(system, p.get("key", ""), p, base_url)
                    for p in data.get("items", ())))


def read(system: str, base_url: str, keys, get) -> TrackerRead:
    """A live read, through a transport the caller opened.

    `get` takes a URL and returns parsed JSON. Anything satisfying that works —
    `requests.Session().get(...).json()`, `httpx`, a stub — so no HTTP library
    is a dependency of Métis and the suite keeps running with none installed.

    **The credential never comes through here.** The caller's `get` already
    carries whatever auth it needs, named by the profile as an environment
    variable (PLT-005).
    """
    if system not in ENDPOINTS:
        raise TrackerRefused(
            f"unknown tracker {system!r}. Known: {', '.join(sorted(ENDPOINTS))}")
    if not base_url:
        raise TrackerRefused("no base_url — nothing says which tracker to read")

    wanted = [k for k in (keys or []) if k]
    if not wanted:
        raise TrackerRefused("no keys — this reads named items, it does not "
                             "crawl a tracker")

    urls = [ENDPOINTS[system].format(base=base_url.rstrip("/"), key=k)
            for k in wanted]
    assert_read_only(urls)

    items = []
    for key, url in zip(wanted, urls):
        payload = get(url)
        if not isinstance(payload, dict):
            raise TrackerRefused(
                f"{url}: expected a JSON object and got "
                f"{type(payload).__name__}")
        items.append(item_from_payload(system, key, payload, base_url))
    return TrackerRead(system=system, base_url=base_url, items=tuple(items))


def to_uif(item: TrackerItem, *, generated_at: str = "") -> dict:
    """One item as a UIF document, ready for `metis intake land`.

    **Nothing is claimed that the tracker did not say.** In particular no
    `acceptance_criteria` key is emitted even where the description obviously
    contains some: a criterion asserted by the document that raised the
    requirement is not independent evidence of it, landing refuses to trust one
    (S-13), and mining it is `ac_mining`'s job with its own provenance.

    The text lands as a `Requirement` only if it is EARS-conformant, and as a
    `Finding` pointing at knowledge-capture otherwise. That is the intake's
    decision, not this function's — which is why the description is carried
    verbatim rather than reshaped into something that would pass.
    """
    stamp = generated_at or datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    return {
        "uif_version": UIF_VERSION,
        "scope": {
            "source_system": item.system,
            "primary_id": item.key,
            "primary_type": item.item_type or "Item",
            "uif_generated_at": stamp,
        },
        "metadata": {
            "title": item.title,
            "description": item.description,
            "status": item.status,
            "labels": list(item.labels),
            "source_url": item.source_url,
        },
    }


def describe(read_result: TrackerRead) -> str:
    """One line per item, for a caller deciding whether to land it."""
    lines = [f"{read_result.system}: {len(read_result.items)} item(s) from "
             f"{read_result.base_url or '(fixture)'}"]
    for item in read_result.items:
        lines.append(f"  {item.key:14} {item.item_type or '?':12} "
                     f"{(item.title or '(no title)')[:56]}")
    return "\n".join(lines)
