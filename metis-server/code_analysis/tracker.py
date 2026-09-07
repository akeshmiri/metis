"""
A tracker or wiki as an intake — Jira, Zephyr Scale, Confluence (spec §5.2b, X-7a).

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
# The schema pins this as a `const`, and the emitted "1.0" failed it while
# `intake_landing` accepted any `1.x` — so every document `metis intake fetch`
# wrote was invalid against the contract the intake skill points producers at,
# and nothing noticed because nothing validated.
UIF_VERSION = "1.0.0"

# `source_system` values, keyed as `intake_landing.ANCHORS` already keys them:
# Zephyr Scale's extractor writes "scale", not "zephyr", and renaming it here
# would silently detach every item from its `ZephyrItem` anchor.
JIRA = "jira"
ZEPHYR = "scale"
CONFLUENCE = "confluence"


class TrackerRefused(Exception):
    """The tracker could not be read — shape or access, not content."""


# The closed allowlist. A path not in here cannot be requested, and adding one
# is a reviewed change rather than an edit — the same bar `CATALOGUE_SOURCES`
# sets for a SQL statement.
ENDPOINTS: dict[str, str] = {
    JIRA: "{base}/rest/api/3/issue/{key}",
    ZEPHYR: "{base}/v2/testcases/{key}",
    # `expand` is part of the allowlisted path rather than a caller-supplied
    # option: the body is the whole reason to read a page, and a request that
    # omitted it would return a page with no content and look like an empty one.
    CONFLUENCE: "{base}/rest/api/content/{key}?expand=body.storage,metadata.labels",
}

# Where a human goes to read the item. Built from the base URL that was actually
# read, never from a template with a host in it -- the skill extractor this
# replaces hardcoded `https://confluence.example.com/...`, so every page it
# produced carried provenance pointing at a domain nobody owns.
BROWSE: dict[str, str] = {
    JIRA: "{base}/browse/{key}",
    CONFLUENCE: "{base}/pages/viewpage.action?pageId={key}",
}

# Systems whose description arrives as markup. Confluence stores XHTML, and
# landing that verbatim would put tag soup where the requirement text goes --
# `ears_pattern` would never match it and every page would land as a Finding.
MARKUP: frozenset = frozenset({CONFLUENCE})

# What each tracker calls the fields this reads. Declared rather than inlined so
# the mapping is inspectable, and so a deployment whose Jira renames a field can
# be diagnosed by reading one dict.
FIELDS: dict[str, dict[str, str]] = {
    JIRA: {"title": "summary", "description": "description",
           "item_type": "issuetype", "status": "status", "labels": "labels",
           # `scope.created_at` and `scope.last_updated_at` are REQUIRED by the
           # UIF schema and were produced by nothing, so every document Métis
           # wrote was invalid on two counts before it was read. The trackers
           # return them; the reader simply did not ask.
           "created_at": "created", "updated_at": "updated",
           # `metadata.priority` is in the schema and is one of the requirement
           # attributes the graph had no way to carry.
           "priority": "priority"},
    ZEPHYR: {"title": "name", "description": "objective",
             "item_type": "$static:TestCase", "status": "status",
             "labels": "labels",
             "created_at": "createdOn", "updated_at": "updatedOn",
             "priority": "priority"},
    # Dotted paths, because Confluence nests the body three deep. `status` is
    # the real `current`/`draft` the API returns rather than a static -- a page
    # still in draft is exactly the thing a reviewer needs to see flagged.
    CONFLUENCE: {"title": "title", "description": "body.storage.value",
                 "item_type": "$static:Page", "status": "status",
                 "labels": "metadata.labels.results",
                 "created_at": "history.createdDate",
                 "updated_at": "version.when",
                 "priority": "$static:"},
}


@dataclass(frozen=True)
class ItemLink:
    """One link a tracker item declares to another.

    **Provenance, not traceability.** The tracker asserts the relationship and
    Métis records that assertion; it is never inferred from wording, and
    `parent` is the only relation anything reads. The rest are carried so
    nothing is silently dropped and interpreted by nobody -- a `relates to` in
    Jira means whatever the team that clicked it meant.
    """

    relation: str
    target_id: str
    target_system: str = ""
    target_url: str = ""


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
    # Required by the UIF schema, and absent from every document this produced
    # until the intake workflow's validate stage said so.
    created_at: str = ""
    updated_at: str = ""
    # Optional in the schema, and the first requirement ATTRIBUTE the graph can
    # carry. Empty where the tracker states none -- never defaulted to a middle
    # value, which would be Métis asserting a priority nobody set.
    priority: str = ""
    # What this item says it is linked to. Read from the SAME response the
    # reader already fetches -- `fields.parent` and `fields.issuelinks` are in
    # the issue payload -- so no endpoint is added and `ENDPOINTS` stays the
    # closed GET allowlist it is (X-7a).
    links: tuple = ()


@dataclass(frozen=True)
class TrackerRead:
    system: str
    base_url: str
    items: tuple[TrackerItem, ...] = field(default_factory=tuple)

    def keys(self) -> set[str]:
        return {i.key for i in self.items}


# **Discovery, kept separate from reading, and separately allowlisted.**
#
# `intakes.json` said this reader "does NOT crawl a tracker", and named-keys-only
# does not survive a real backlog: nobody types 400 Jira keys. What was missing
# was never the ability to fetch an item -- `read` already does that -- but a way
# to ask the tracker WHICH items.
#
# So this is two steps rather than one bigger one. `search` resolves a query to
# a list of keys; `read` then fetches each of them through exactly the path it
# always used. "Named items only" still describes every item read; the query is
# what names them, and the two allowlists stay independently reviewable.
#
# `{query}` is URL-encoded by the caller, so a JQL string with spaces and quotes
# cannot smuggle a second parameter into the URL.
SEARCH_ENDPOINTS: dict[str, str] = {
    JIRA: "{base}/rest/api/3/search?jql={query}&maxResults={limit}&fields=key",
    # CQL rather than a bare space key: a team scoping intake to one space and a
    # team scoping it to a label need the same field, and `spaceKey=` cannot
    # express the second.
    CONFLUENCE: "{base}/rest/api/content/search?cql={query}&limit={limit}",
    ZEPHYR: "{base}/v2/testcases?projectKey={query}&maxResults={limit}",
}

# A crawl that silently stopped at a page boundary would under-report a backlog,
# and under-reporting is indistinguishable from a small backlog. So there is a
# cap, it is explicit, and `search` says when it was reached.
SEARCH_LIMIT = 100


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
    def pattern(template: str):
        return re.compile("^" + re.escape(template)
                          .replace(r"\{base\}", r".+")
                          .replace(r"\{key\}", r"[^/?#]+")
                          # A query is percent-encoded before it is substituted,
                          # so it can carry no `&` of its own — which is what
                          # stops a JQL string appending a parameter.
                          .replace(r"\{query\}", r"[^&#]*")
                          .replace(r"\{limit\}", r"\d+") + "$")

    templates = list(ENDPOINTS.values()) + list(SEARCH_ENDPOINTS.values())
    patterns = [pattern(t) for t in templates]
    allowed = ", ".join(sorted(templates))
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


def _dig(payload, path: str):
    """One dotted path into a nested response — `body.storage.value`.

    Returns None the moment the path leaves a dict, rather than raising. A
    Confluence read whose `expand` was dropped by a proxy has no `body`, and the
    honest result there is an empty description that `conformance` will flag,
    not a traceback three layers from the cause.
    """
    current = payload
    for segment in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


# Tags whose end marks a line break in the rendered text. Matched on the local
# name so Confluence's namespaced elements (`ac:layout-cell`) are treated like
# their plain counterparts.
_BLOCK: frozenset = frozenset({
    "p", "div", "br", "li", "tr", "td", "th", "pre", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6",
})

# Macro *configuration*, not prose. `<ac:parameter ac:name="title">Note</...>`
# holds the macro's settings, and letting it through drops the word "Note" into
# the middle of a requirement as though somebody had written it there.
_DROP: frozenset = frozenset({"ac:parameter", "ri:page", "ri:attachment"})


def storage_text(markup: str) -> str:
    """Confluence storage format (XHTML) as plain text.

    **Nothing is reconstructed**, the same rule `_text` applies to Jira's ADF:
    no bullet markers, no heading levels, no tables redrawn. Block elements
    become line breaks and everything else becomes its text, because a rendering
    that resembled the page without being it is worse than the plain text — a
    reviewer would compare it to Confluence and trust the difference away.

    Parsed rather than regexed. A `<[^>]+>` strip — which is what the extractor
    this replaces used — corrupts any body containing a `>` inside an attribute,
    and Confluence macros contain them routinely.
    """
    from html.parser import HTMLParser

    class _Reader(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []
            self.skipping = 0

        def handle_starttag(self, tag, attrs):
            if tag in _DROP:
                self.skipping += 1
            elif tag.split(":")[-1] in _BLOCK:
                self.parts.append("\n")

        # Confluence writes `<br/>` and `<ac:image/>`; without this a self-closed
        # `<br/>` produces no break at all, running two lines together.
        def handle_startendtag(self, tag, attrs):
            if tag.split(":")[-1] in _BLOCK:
                self.parts.append("\n")

        def handle_endtag(self, tag):
            if tag in _DROP:
                self.skipping = max(0, self.skipping - 1)
            elif tag.split(":")[-1] in _BLOCK:
                self.parts.append("\n")

        def handle_data(self, data):
            if not self.skipping:
                self.parts.append(data)

        # `<ac:plain-text-body><![CDATA[...]]></ac:plain-text-body>` is how a
        # code block is stored. HTMLParser reports it as an unknown declaration,
        # and ignoring it silently deletes the body of every code macro.
        def unknown_decl(self, data):
            if not self.skipping and data.startswith("CDATA["):
                self.parts.append(data[len("CDATA["):])

    reader = _Reader()
    reader.feed(markup or "")
    reader.close()

    lines = [" ".join(line.split())
             for line in "".join(reader.parts).splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _links_from(system: str, body: dict, base_url: str) -> tuple:
    """Links the payload declares, normalised. Pure.

    Jira only, for now: Zephyr Scale has no issue-link concept and Confluence's
    ancestry is a different shape that would need its own reading. An empty
    tuple for those is a fact about the tracker, not a gap in this function.

    **A parent is recorded as `parent`, whatever Jira called it.** `parent`
    (next-gen), `Epic Link` (classic) and an inward `is subtask of` all mean the
    same thing to a reader, and normalising them is what makes "which stories
    are under this epic" one question rather than three.
    """
    if system != JIRA or not isinstance(body, dict):
        return ()

    template = BROWSE.get(system, "")

    def url_for(target: str) -> str:
        return (template.format(base=base_url.rstrip("/"), key=target)
                if base_url and template and target else "")

    found: list[ItemLink] = []
    seen: set[tuple] = set()

    def add(relation: str, target: str) -> None:
        target = str(target or "").strip()
        if not target or (relation, target) in seen:
            return
        seen.add((relation, target))
        found.append(ItemLink(relation=relation, target_id=target,
                              target_system=system, target_url=url_for(target)))

    parent = body.get("parent")
    if isinstance(parent, dict):
        add("parent", parent.get("key", ""))

    for link in body.get("issuelinks") or ():
        if not isinstance(link, dict):
            continue
        # Jira states a link from one side; `inward`/`outward` says which. The
        # relation name is taken from the side the payload actually carries, so
        # a "blocks" and an "is blocked by" are not flattened into one claim.
        kind = link.get("type") or {}
        for side, name_key in (("inwardIssue", "inward"), ("outwardIssue", "outward")):
            issue = link.get(side)
            if isinstance(issue, dict) and issue.get("key"):
                relation = str(kind.get(name_key) or "relates to").strip().lower()
                # Classic Jira models an epic as a link rather than a parent.
                add("parent" if relation in _PARENT_RELATIONS else relation,
                    issue["key"])
    return tuple(found)


# Jira link names that mean "this item is beneath that one". Normalised to
# `parent` so decomposition is one relation rather than three spellings.
_PARENT_RELATIONS = frozenset({
    "is subtask of", "is child of", "is part of", "epic link",
})


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
        # `.get` rather than `[...]`: not every system declares every field, and
        # a KeyError here would refuse a whole tracker over one absent mapping.
        name = names.get(which, "")
        if not name:
            return None
        if name.startswith("$static:"):
            return name.split(":", 1)[1] or None
        return _dig(body, name)

    description = _text(pick("description"))
    if system in MARKUP:
        description = storage_text(description)

    # Through `_named` per element rather than `str()`: Jira's labels are plain
    # strings and Confluence's are `{"name": ...}` objects, and stringifying one
    # of those lands the repr of a dict as a label.
    labels = pick("labels") or ()
    if not isinstance(labels, (list, tuple)):
        labels = ()

    # Resolved ONCE and used for both the identity and the URL. Confluence
    # payloads carry `id` where Jira carries `key`, and using the raw parameter
    # for the URL produced `...?pageId=` with nothing after it — a link that
    # resolves to a search page, on every page fetched from a fixture.
    resolved = str(payload.get("key") or payload.get("id") or key)
    template = BROWSE.get(system, "")
    return TrackerItem(
        system=system,
        key=resolved,
        title=_text(pick("title")),
        description=description,
        item_type=_named(pick("item_type")),
        status=_named(pick("status")),
        labels=tuple(n for n in (_named(x) for x in labels) if n),
        source_url=(template.format(base=base_url.rstrip("/"), key=resolved)
                    if base_url and template else ""),
        created_at=_text(pick("created_at")),
        updated_at=_text(pick("updated_at")),
        priority=_named(pick("priority")),
        links=_links_from(system, body if isinstance(body, dict) else {}, base_url),
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


# How each tracker names an item in a search response. Declared rather than
# guessed per call: a shape that changed would otherwise surface as "0 items"
# from a query that matched hundreds.
_SEARCH_SHAPE: dict[str, tuple[str, str]] = {
    JIRA: ("issues", "key"),
    CONFLUENCE: ("results", "id"),
    ZEPHYR: ("values", "key"),
}


def search(system: str, base_url: str, query: str, get,
           limit: int = SEARCH_LIMIT) -> list[str]:
    """Resolve a query to item keys. Reading them is still `read`'s job.

    **Two steps on purpose.** "Named items only" remains true of every item
    fetched — this is what names them. Keeping discovery separate means the
    per-item read path, and the allowlist entry that guards it, are untouched by
    adding a crawl.

    **A truncated result is reported, never silently returned.** A backlog cut
    off at the page boundary looks exactly like a small backlog, and a coverage
    figure computed over half a backlog is worse than none. The caller gets a
    refusal naming the cap rather than a short list.
    """
    if system not in SEARCH_ENDPOINTS:
        raise TrackerRefused(
            f"{system!r} has no search endpoint. Searchable: "
            f"{', '.join(sorted(SEARCH_ENDPOINTS))}")
    if not base_url:
        raise TrackerRefused("no base_url — nothing says which tracker to read")
    if not (query or "").strip():
        raise TrackerRefused(
            "no query. Pass one, or name items with `keys` — this does not "
            "read a whole tracker by default")

    import urllib.parse

    url = SEARCH_ENDPOINTS[system].format(
        base=base_url.rstrip("/"),
        # `safe=""` so `&`, `=` and `?` inside a JQL string are encoded and
        # cannot become URL structure. The allowlist above then holds.
        query=urllib.parse.quote(query.strip(), safe=""),
        limit=int(limit))
    assert_read_only([url])

    payload = get(url)
    if not isinstance(payload, dict):
        raise TrackerRefused(
            f"{url}: expected a JSON object and got {type(payload).__name__}")

    field, key_name = _SEARCH_SHAPE[system]
    rows = payload.get(field)
    if not isinstance(rows, list):
        raise TrackerRefused(
            f"{url}: expected {field!r} to be a list and got "
            f"{type(rows).__name__}. The tracker's response shape has changed, "
            f"and reading it as empty would report a matching query as no match")

    total = payload.get("total")
    if isinstance(total, int) and total > len(rows):
        raise TrackerRefused(
            f"the query matched {total} item(s) and this read {len(rows)}. "
            f"Narrow the query, or raise the limit deliberately — a backlog "
            f"truncated at a page boundary is indistinguishable from a small "
            f"one, and every figure computed from it would be quietly wrong")

    keys = [str(r.get(key_name)) for r in rows if isinstance(r, dict)
            and r.get(key_name)]
    if len(keys) != len(rows):
        raise TrackerRefused(
            f"{url}: {len(rows) - len(keys)} row(s) carried no {key_name!r}. "
            f"Dropping them would under-report the query silently")
    return keys


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


# ---------------------------------------------------------------------------
# Normalisation — the UIF's vocabulary, not the tracker's
# ---------------------------------------------------------------------------
#
# **The schema is authoritative and the producer was not matching it.** Nothing
# validated between `intake fetch` and `intake land`, so documents Métis writes
# failed the schema Métis publishes for external producers, four ways:
# `metadata.status` was the tracker's raw string where an object is required,
# `scope.created_at` and `scope.last_updated_at` were required and absent, and
# `scope.primary_type` carried `Story` where a lowercase enum is declared.
#
# Normalising is what makes one query span Jira, Confluence and Zephyr: a
# reviewer asking "every story awaiting review" should not need to know that one
# system spells it `Story`, another `story`, and a third has no such concept.
#
# **Where a value does not map, it is omitted rather than guessed** (X-6e). A
# tracker's workflow states are per-project and arbitrary; deciding that
# somebody's `Awaiting Signoff` means `under_review` is an invention, and an
# invented status reads exactly like an observed one.

# Tracker item types -> the schema's `scope.primary_type` enum.
_ITEM_TYPES: dict[str, str] = {
    "story": "story", "user story": "story",
    "epic": "epic",
    "feature": "feature", "new feature": "feature",
    "task": "task", "sub-task": "task", "subtask": "task",
    "bug": "defect", "defect": "defect",
    "page": "page",
    "test case": "test_case", "testcase": "test_case", "test": "test_case",
}

# The one status axis a tracker's own workflow state maps onto:
# `normalized_status.summary_status`. The other axes (`approval_state`,
# `automation_status`, …) describe things a tracker does not track, and filling
# them from a workflow name would be fabrication.
_SUMMARY_STATUS: dict[str, str] = {
    "backlog": "draft", "draft": "draft", "to do": "draft", "open": "draft",
    "new": "draft",
    "in progress": "active", "in review": "active", "active": "active",
    "in development": "active", "current": "active",
    "done": "completed", "closed": "completed", "resolved": "completed",
    "complete": "completed", "completed": "completed",
    "deferred": "deferred", "on hold": "deferred",
    "blocked": "blocked",
}


# `metadata.priority` is an enum too, and for the same reason: "P1" in one
# project and "Highest" in another mean the same thing to a reader and nothing
# to a query.
_PRIORITIES: dict[str, str] = {
    "blocker": "critical", "critical": "critical", "highest": "critical",
    "p0": "critical",
    "high": "high", "major": "high", "p1": "high",
    "medium": "medium", "normal": "medium", "moderate": "medium", "p2": "medium",
    "low": "low", "minor": "low", "p3": "low",
    "lowest": "optional", "trivial": "optional", "optional": "optional",
    "p4": "optional",
}


def normalise_priority(raw: str) -> str:
    """A tracker's priority -> the schema's enum, or `""` where it does not map.

    Empty rather than `medium`. A middle value is the tempting default and it is
    a claim: it says somebody triaged this and decided it was ordinary, which is
    a different fact from nobody having said.
    """
    return _PRIORITIES.get((raw or "").strip().lower(), "")


def normalise_item_type(raw: str) -> str:
    """A tracker's type name -> the schema's enum, or `task` as the floor.

    `task` rather than an omission because `scope.primary_type` is REQUIRED: a
    document with no type at all is invalid, and refusing to produce one for an
    unrecognised type would mean a project's custom issue type could not be
    landed at all. `task` is the least-claiming member of the enum -- it asserts
    "a unit of work" and nothing about what kind.
    """
    return _ITEM_TYPES.get((raw or "").strip().lower(), "task")


def normalise_status(raw: str, updated_at: str = "") -> dict:
    """A tracker's workflow state -> a `normalized_status` object.

    `normalized_status` has no required properties, so `{}` is valid -- which is
    what makes omission possible. An unrecognised state yields an object
    carrying only what IS known (when it last changed), rather than a guess at
    what it means.
    """
    status: dict = {}
    mapped = _SUMMARY_STATUS.get((raw or "").strip().lower())
    if mapped:
        status["summary_status"] = mapped
    if updated_at:
        status["last_status_update"] = updated_at
    return status


def _raw_status_fact(item: "TrackerItem", stamp: str) -> dict:
    """The tracker's own status string, kept as an observed fact.

    Normalising loses the original wording, and the original wording is what a
    reviewer recognises -- "this is the ticket that says Awaiting Signoff". It
    goes to `facts.current_state` as an OBSERVATION with its source rather than
    into `metadata.status`, because the schema's status is a normalised
    vocabulary and this is a quotation.
    """
    return {
        "id": f"status-{item.key}",
        "type": "current_state",
        "name": "tracker status",
        "value": item.status,
        "confidence": "observed",
        "timestamp": stamp,
        "source_ref": {
            "source_system": item.system,
            "source_id": item.key,
            "source_url": item.source_url,
            "confidence": "direct",
            "extracted_at": stamp,
        },
    }


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
    metadata = {
        "title": item.title,
        "description": item.description,
        # The schema's normalised vocabulary, not the tracker's string. The raw
        # wording is not lost -- it rides in `facts.current_state` as an
        # observation with its source, because that is a quotation and this is a
        # classification, and putting a quotation where a classification belongs
        # is what made these documents invalid.
        "status": normalise_status(item.status, item.updated_at),
        # `tags` is the schema's name for these; `labels` was emitted under a
        # key `metadata` does not allow (`additionalProperties: false`) and
        # read by nothing downstream.
        "tags": list(item.labels),
    }
    priority = normalise_priority(item.priority)
    if priority:
        # Omitted rather than defaulted, on both branches: where the tracker
        # states none, and where it states one this vocabulary cannot express.
        # A middle value would be Métis asserting a priority nobody set.
        metadata["priority"] = priority

    scope = {
        "source_system": item.system,
        "primary_id": item.key,
        # A lowercase enum member, mapped. `Story` is what Jira calls it and
        # `story` is what the UIF calls it; carrying the first meant a query
        # spanning two trackers had to know both vocabularies.
        "primary_type": normalise_item_type(item.item_type),
        "uif_generated_at": stamp,
    }
    # Required by the schema. Emitted only where the tracker supplied them --
    # a fabricated `created_at` would be a claim about when somebody raised a
    # requirement, which is exactly the kind of invention X-6e forbids. A
    # document missing them is invalid, and that is the honest outcome: the
    # producer could not satisfy the contract for this item.
    if item.created_at:
        scope["created_at"] = item.created_at
    if item.updated_at:
        scope["last_updated_at"] = item.updated_at

    document = {
        "uif_version": UIF_VERSION,
        "scope": scope,
        "metadata": metadata,
        # The source url was emitted as `metadata.source_url`, which the schema
        # does not permit either — and provenance is not metadata. The schema
        # models it properly: a `source_reference` carrying the system, the id
        # and how the value was obtained. `direct` is the literal truth here;
        # this came out of the tracker's own response, not from inference.
        "traceability": {
            "source_references": [{
                "source_system": item.system,
                "source_id": item.key,
                "source_url": item.source_url,
                "confidence": "direct",
                "extracted_at": stamp,
            }],
        },
    }
    if item.status:
        document["facts"] = {"current_state": [_raw_status_fact(item, stamp)]}
    if item.links:
        # Emitted only where the tracker declared some. An empty `links` array
        # and an absent one both mean "none declared", and the absent form does
        # not invite a reader to conclude somebody checked.
        document["links"] = [
            {k: v for k, v in
             {"relation": link.relation, "target_id": link.target_id,
              "target_system": link.target_system,
              "target_url": link.target_url}.items() if v}
            for link in item.links
        ]
    return document


def describe(read_result: TrackerRead) -> str:
    """One line per item, for a caller deciding whether to land it."""
    lines = [f"{read_result.system}: {len(read_result.items)} item(s) from "
             f"{read_result.base_url or '(fixture)'}"]
    for item in read_result.items:
        lines.append(f"  {item.key:14} {item.item_type or '?':12} "
                     f"{(item.title or '(no title)')[:56]}")
    return "\n".join(lines)
