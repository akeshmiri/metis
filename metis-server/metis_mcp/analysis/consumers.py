"""Who reads what a behaviour produces, from what was recovered.

**Why this changes a test design.** A behaviour whose output feeds a report is
tested differently from one that feeds another system: a report tolerates a
missing optional field and a caller parsing a contract does not; a paged listing
has boundaries an integration payload has none of. Knowing the consumer changes
the level, the data conditions and the obligations — so it is a gathered input
rather than a note.

**Classified from evidence, never from a name.** The practice this comes from
detects consumers by reading ticket prose and attaching a confidence level:
`REPORT` because somebody wrote "report". That is inference from wording, and it
is the failure X-6 names — a route called `/export` is a name, and a handler
returning `text/csv` is a fact.

So every signal here is a recovered one: the declared media type, the response
body's shape, the presence of paging parameters, whether the call writes. Where
none of them fires the answer is `unknown`, and `unknown` is reported rather than
resolved to the most plausible guess.

**One behaviour may have several consumers and that is not a contradiction.** An
endpoint returning a paged JSON listing over HTTP is plausibly feeding both a
grid and an integration; both are recorded, because collapsing to one would be a
choice nothing supports.

**What this deliberately does not do.** It does not read the ticket. A consumer
somebody *stated* is a better fact than one Métis inferred, and it belongs in the
intake as a claim — not in a classifier that would then have two sources for one
answer and no way to say which won.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The consumer kinds, closed. Taken from the practice this was compared
#: against, minus the two it detects only from prose (`SCHEDULED_JOB`, `AUDIT`)
#: — Métis has no recovered signal for either, and carrying a kind it can never
#: emit would make the vocabulary a promise it does not keep.
REPORT = "REPORT"
EXPORT = "EXPORT"
GRID = "GRID"
INTEGRATION = "INTEGRATION"
NOTIFICATION = "NOTIFICATION"
UNKNOWN = "unknown"

KINDS = (REPORT, EXPORT, GRID, INTEGRATION, NOTIFICATION)

#: Media types that say what the caller is going to do with the answer. A CSV or
#: a spreadsheet is not being parsed by another service; it is being downloaded.
_EXPORT_TYPES = ("text/csv", "application/vnd.ms-excel", "application/pdf",
                 "text/tab-separated-values",
                 "application/vnd.openxmlformats-officedocument")
_INTEGRATION_TYPES = ("application/json", "application/xml", "application/hal+json",
                      "application/problem+json")
_NOTIFICATION_TYPES = ("text/event-stream",)

#: Parameter names that make a response a page of something. The same list
#: `viability` uses for volume sensitivity, because it is the same fact read for
#: a different purpose — and two copies would drift.
_PAGING = ("page", "size", "limit", "offset", "cursor", "per_page", "pagesize",
           "top", "skip", "count", "max")

#: Response-body type fragments that carry many of a thing.
_COLLECTION = ("page", "list", "collection", "[]", "set<", "iterable", "array")


@dataclass(frozen=True)
class Consumer:
    """One consumer kind, and the recovered fact that says so."""

    kind: str
    #: The evidence. A classification a reader cannot audit is one they have to
    #: take on trust, which is the objection T-9a makes about an unanchored guard.
    because: str

    def describe(self) -> str:
        return f"{self.kind}: {self.because}"


def _media_types(transition) -> tuple[str, ...]:
    return tuple(str(m).lower() for m in (getattr(transition, "media_types", ())
                                          or ()) if m)


def _has_paging(transition) -> list[str]:
    found = []
    for parameter in getattr(transition, "inputs", ()) or ():
        name = str((parameter or {}).get("name") or "").lower()
        if name in _PAGING:
            found.append(name)
    return found


def _returns_collection(transition) -> bool:
    body = str(getattr(transition, "response_body", "") or "").lower()
    return any(fragment in body for fragment in _COLLECTION)


def classify(transition) -> list[Consumer]:
    """Every consumer kind the recovered facts support, with the fact.

    Empty means `unknown` — see `describe_one`, which is what a caller should
    render. Returning an empty list rather than an `unknown` member keeps the
    two states distinguishable in code: *no kind fired* and *a kind called
    unknown fired* are different things, and only the first is true here.
    """
    found: list[Consumer] = []
    media = _media_types(transition)
    paging = _has_paging(transition)
    collection = _returns_collection(transition)

    for kind, types in ((EXPORT, _EXPORT_TYPES),
                        (NOTIFICATION, _NOTIFICATION_TYPES)):
        matched = [m for m in media if any(m.startswith(t) for t in types)]
        if matched:
            found.append(Consumer(
                kind, f"declares {', '.join(sorted(matched))}"))

    if paging and (collection or media):
        found.append(Consumer(
            GRID,
            f"pages its result ({', '.join(sorted(paging))}), which is a "
            f"consumer displaying it a screen at a time"))

    if collection and not paging:
        found.append(Consumer(
            REPORT,
            "returns a collection with no paging parameter — the caller takes "
            "the whole set at once"))

    if any(any(m.startswith(t) for t in _INTEGRATION_TYPES) for m in media):
        found.append(Consumer(
            INTEGRATION,
            "declares a machine-readable media type, so something is parsing "
            "the response rather than reading it"))

    return found


def describe_one(transition) -> dict:
    """One behaviour's consumers, or the reason there is no answer."""
    found = classify(transition)
    if found:
        return {
            "consumers": [c.kind for c in found],
            "because": [c.describe() for c in found],
            "means": ("more than one kind is not a contradiction: a paged JSON "
                      "listing plausibly feeds a grid and an integration, and "
                      "collapsing to one would be a choice nothing supports"),
        }
    return {
        "consumers": [UNKNOWN],
        "because": [],
        "means": (
            "no recovered fact says who reads this. Naming a consumer from the "
            "route or the requirement's wording would be inference from a name "
            "(X-6) — and a stated consumer is a better fact than an inferred "
            "one, so it belongs in the intake as a claim rather than here"),
    }


def describe(model) -> dict:
    """Every behaviour in a model, classified.

    Reports the `unknown` count beside the classified ones, deliberately. A
    consumer map that listed only what it could name would read as complete —
    the same overstatement `coverage_report`'s `unmeasured` field exists to
    prevent.
    """
    if model is None:
        return {"by_transition": {}, "unknown": 0,
                "means": "no model in scope"}

    by_transition: dict[str, list[str]] = {}
    reasons: dict[str, list[str]] = {}
    unknown = 0
    for tid in sorted(model.transitions):
        one = describe_one(model.transitions[tid])
        by_transition[tid] = one["consumers"]
        if one["because"]:
            reasons[tid] = one["because"]
        else:
            unknown += 1

    distribution: dict[str, int] = {kind: 0 for kind in KINDS}
    for kinds in by_transition.values():
        for kind in kinds:
            if kind in distribution:
                distribution[kind] += 1

    return {
        "by_transition": by_transition,
        "because": reasons,
        "distribution": distribution,
        "unknown": unknown,
        "means": (
            f"{unknown} of {len(by_transition)} behaviour(s) have no recovered "
            f"signal saying who reads them. That is reported rather than "
            f"resolved: a consumer somebody STATED is a better fact than one "
            f"inferred, and it belongs in the intake"),
    }
