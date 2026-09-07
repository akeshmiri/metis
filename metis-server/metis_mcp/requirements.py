"""
Authoring a requirement inside Métis — create, revise, retire.

**The gap this closes.** Three paths already produced a `Requirement`: a UIF from
a tracker (`intake land`), a knowledge file (`metis knowledge`), and a Spec Kit
document plus an EARS statement (`metis spec-requirement`). Every one of them
needs a document that already exists somewhere else. Nothing let a person state a
requirement, correct its wording, or retire it — which is most of what requirement
management IS, and it was the largest hole in the claim that Métis handles it.

**Nothing here is new machinery.** `identity.claim_id` already digests the text
into the id so a reworded requirement is a NEW claim rather than a mutated one;
`landing.plan_supersession` already closes the previous window; `ears_checker`
already decides `Requirement` vs `Finding` (S-13) and `ac_quality` already reports
what is unmeasurable without blocking. This composes them and adds a verb.

**Three rules it does not bend:**

  * **Everything lands at `Quarantine` (S-4).** Authoring is not approving, and
    the author of a requirement is exactly the person N-10 says may not approve
    it.
  * **A revision is a new node, not an edit.** *shall reject* and *shall refresh*
    are two claims. The prior revision keeps its own lifecycle and stays readable
    (I-19), so "what did we believe in March" survives a correction.
  * **Retiring closes a window; it deletes nothing** (T-16). A requirement that
    stopped being true and one that never existed are different, and only one of
    them can be audited.

**EARS is checked and not enforced here, which differs from intake.** Free prose
from a tracker becomes a `Finding` because nobody chose to write a requirement.
A person typing into this verb HAS chosen, so refusing them would be pedantry:
the check runs, the result is reported, and non-conformant text is landed as a
`Finding` with the same S-13 wording, so the two surfaces agree about what a
requirement is.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Authored:
    """One authored claim, ready to land. Pure — nothing here touches a graph."""

    logical_key: str
    node_id: str
    text: str
    label: str                       # "Requirement" or "Finding"
    ears_pattern: str | None
    advisories: tuple = ()


@dataclass
class AuthoringRefused(Exception):
    """The claim was not landed, and the reason a person can act on."""

    reason: str

    def __str__(self) -> str:            # pragma: no cover - trivial
        return self.reason


def compose(logical_key: str, text: str, *, check_quality: bool = True) -> Authored:
    """A requirement, as it would land. **Pure.**

    Separated from landing for the reason `plan` is separated from `land`
    everywhere else: the decision about what a claim IS must be assertable with
    no database, and the write must be the only part that needs one.
    """
    from metis_mcp.ears_checker import check_ears_conformance
    from metis_mcp.identity.keys import claim_id, normalise_claim

    statement = normalise_claim(text)
    if not statement:
        raise AuthoringRefused(
            "a requirement needs text. An empty claim has nothing to be true or "
            "false about, and `ears_pattern` has no empty form (S-13)")
    if not (logical_key or "").strip():
        raise AuthoringRefused(
            "a requirement needs a key to be a revision OF — an author-chosen id "
            "like `REQ-3`. Without one, a later correction cannot be recognised "
            "as the same claim and would land as an unrelated second one")

    ears = check_ears_conformance(statement)
    advisories: list[str] = []
    if not ears.conformant:
        advisories.append(
            "the text is not EARS-conformant, so this lands as a Finding "
            "pointing at knowledge-capture and NOT as a Requirement (S-13). "
            "Rewrite it as `When <trigger>, the system shall <response>`")

    if check_quality and ears.conformant:
        # Advisory and blocking nothing (S-4). `ac_quality.assess` reports
        # unmeasurable qualifiers and non-atomicity; a person writing a
        # requirement should see that and must not be stopped by it.
        #
        # Called directly, not behind a `try`. The first version of this guessed
        # the function name, wrapped it in `except Exception: pass`, and would
        # have reported zero quality findings forever while looking like it
        # checked -- the exact silent-success shape this repository hunts. If
        # `assess` moves, this raises and somebody fixes it.
        from metis_mcp.ac_quality import assess

        advisories.extend(finding.describe() for finding in assess(statement))

    return Authored(
        logical_key=logical_key.strip(),
        node_id=claim_id(logical_key.strip(), statement),
        text=statement,
        label="Requirement" if ears.conformant else "Finding",
        ears_pattern=ears.pattern,
        advisories=tuple(advisories),
    )


def describe(authored: Authored) -> str:
    """What a person needs to see before this is landed."""
    lines = [
        f"  {authored.node_id}",
        f"    lands as   {authored.label}"
        + (f" ({authored.ears_pattern})" if authored.ears_pattern else ""),
        f"    text       {authored.text}",
        "    lifecycle  Quarantine — authoring is not approving (S-4), and the "
        "author may not approve it (N-10)",
    ]
    lines.append(
        "    revision   decided at landing, from the graph — reusing the key "
        "makes this a revision, and a plan builder cannot know the history")
    for advisory in authored.advisories:
        lines.append(f"    advisory:  {advisory}")
    return "\n".join(lines)
