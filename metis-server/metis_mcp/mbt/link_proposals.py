"""
Proposing `INVOKES`/`TRIGGERS` links from a frontend pack's own facts (M-5a).

**Why this is a module and not eight lines in a rebuild script.** It was the
latter, and in that form it carried four defects at once, none of which any test
could see: `LinkSet` and `InvokesLink` were both constructed without required
arguments (so the stage raised `TypeError` and had never once run), `triggers`
was never populated (so `persist_triggers` faithfully wrote zero while the caller
printed it as a TRIGGERS count), and the join key compared a screen NAME against
a transition ID.

That last one is the instructive failure. A `UiAction` id is an opaque namespaced
hash — `records-ui::9983f5be80990421` — so asking whether `"RecordListPage"` is a
substring of it is not merely wrong, it is *never* true. The stage reported a
confident `0 INVOKES`, which reads as "the surfaces genuinely share nothing"
rather than "the join matched nothing". The script's own comment warned about
exactly this class of bug, having been bitten by it once before with a stale
mapping file.

So the rule this module exists to hold: **a derivation that finds nothing must be
able to say which side found nothing.** `propose` returns its misses rather than
folding them into a zero, and the caller reports them.

Pure — no session, no driver, no I/O. The graph rows and the pack facts are
parameters, which is what makes the join key assertable at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from metis_mcp.mbt.cross_surface import InvokesLink, LinkSet


def _text_of(row) -> str:
    """Everything on a UI row that could carry a screen name.

    `name` and `trigger`, never `id`: see the module docstring.
    """
    return f"{row.get('name') or ''} {row.get('trigger') or ''}"


def api_ids_for(api_rows, endpoint: str) -> list[str]:
    """API transition ids whose trigger path ends with `endpoint`.

    Suffix matching, because a controller may be dual-mounted and a gateway may
    strip a prefix. Both sides lose a trailing slash first: the pack reports
    `/record/` where the controller declares `/record`, and a bare `endswith`
    made those two different endpoints.
    """
    wanted = (endpoint or "").rstrip("/")
    if not wanted:
        return []
    out = []
    for row in api_rows:
        parts = (row.get("trigger") or "").split(None, 1)
        if len(parts) == 2 and parts[1].rstrip("/").endswith(wanted):
            out.append(row["id"])
    return out


def ui_ids_for(ui_rows, screen: str) -> list[str]:
    """UI transition ids belonging to `screen`, matched on name/trigger."""
    if not screen:
        return []
    return [r["id"] for r in ui_rows if screen in _text_of(r)]


@dataclass
class Proposal:
    """What the derivation found, and what it did not.

    `unmatched_*` are the point: a caller that prints only `len(links)` cannot
    tell "these surfaces share nothing" from "my join key is wrong".
    """

    links: list[InvokesLink] = field(default_factory=list)
    unmatched_screens: list[str] = field(default_factory=list)
    unmatched_endpoints: list[str] = field(default_factory=list)

    def link_set(self, journey: str) -> LinkSet:
        """Both edge types from one derivation.

        A pack fact — *this screen calls this endpoint* — is evidence the page
        STARTS the call, which is `TRIGGERS`. That it renders any particular
        outcome is the stronger `INVOKES` claim. Both are proposals and neither
        credits anything until a human confirms it (M-5g, F-7).
        """
        return LinkSet(journey=journey, links=list(self.links),
                       triggers=list(self.links))


def propose(ui_rows, api_rows, api_calls, *, proposed_by: str) -> Proposal:
    """`Proposal` from a frontend pack's `api_calls` against the landed rows."""
    result = Proposal()
    for call in api_calls:
        screen = call.get("screen") or ""
        endpoint = (call.get("endpoint") or "").rstrip("/")
        ui_ids = ui_ids_for(ui_rows, screen)
        api_ids = api_ids_for(api_rows, endpoint)
        if screen and not ui_ids:
            result.unmatched_screens.append(screen)
        if endpoint and not api_ids:
            result.unmatched_endpoints.append(endpoint)
        for ui_id in ui_ids:
            for api_id in api_ids:
                result.links.append(InvokesLink(
                    ui_transition_id=ui_id, api_transition_id=api_id,
                    proposed_by=proposed_by,
                    evidence={"screen": screen, "endpoint": endpoint,
                              "anchor": call.get("anchor", {})}))
    return result
