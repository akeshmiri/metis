"""
Resolving names from the acceptance-criteria vocabulary (spec §5.4; X-7..X-12).

X-7 defines a three-tier cascade for a state's name:

    tier 1   the AC-mined model's vocabulary      an evidence-based alignment
    tier 2   a naming convention in code          an enum, a discriminator
    tier 3   a human, at review                   always the backstop

**Only tier 2 was ever implemented.** `synthesis.state_name` builds `Ok200`,
`NoContent204`, `Created201` from the response helper -- correct, deterministic,
and unreadable to anyone who does not work on the service. A stakeholder opening
§18's generated specification reads "Given the user is Ready, When they get
/{id}, Then they are NoContent204", which is the implementation's vocabulary, not
the business's. That is a real gap against R11 and M-2, not a matter of taste.

This module supplies tier 1 from confirmed `VALIDATES` links: the criterion that
validates a transition was written by a person, in their language, and its
`Then` clause names the situation the transition arrives at.

**Three rules keep this honest.**

  * **X-11/X-12 -- naming is not agreement.** Taking a code-derived state's name
    from an acceptance criterion is NOT evidence that the code model and the AC
    model agree. If it were treated as such, comparison would discover only its
    own naming step. `NameProposal.is_evidence_of_agreement` exists solely to be
    False, and the two facts are recorded separately.
  * **X-9 -- alignment must be evidence-based.** A name is proposed only from a
    criterion a human CONFIRMED validates that transition (X-18). Wording
    similarity alone never proposes a name.
  * **X-10 / F-7 -- proposed, never applied.** A rename is a human fact (I-14);
    extraction may propose one and never overwrite one. Nothing here mutates a
    model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from metis_mcp.mbt.model import Model

# X-8: every name records which tier produced it. A name is not a neutral label;
# its provenance determines how much weight it carries.
TIER_AC_VOCABULARY = "ac_vocabulary"
TIER_CODE_CONVENTION = "code_convention"
TIER_HUMAN = "human"

# Noise a criterion carries that is not part of a business name.
_STATUS = re.compile(r"\b[1-5]\d{2}\b\s*(OK|Created|No Content|Accepted|Bad Request)?",
                     re.IGNORECASE)
_LEADING = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)
_HTTP_VERB = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH)\b\s*", re.IGNORECASE)
_TRAILING = re.compile(r"\s*(is|are)\s+returned\s*$", re.IGNORECASE)


def _phrase(text: str) -> str:
    """Reduce a criterion clause to a short business phrase. Deterministic.

    Only removes: status codes, HTTP verbs, leading articles, and a trailing
    "is returned". It never paraphrases and never introduces a word that was not
    in the criterion -- T-6's rule applies to names as much as to prose.
    """
    t = _STATUS.sub("", text)
    t = _HTTP_VERB.sub("", t)
    t = _TRAILING.sub("", t)
    t = _LEADING.sub("", t.strip())
    t = re.sub(r"\s+", " ", t).strip(" ,.;:")
    return t


@dataclass(frozen=True)
class NameProposal:
    """A proposed name, with the evidence and tier that produced it (X-8)."""

    element_id: str
    kind: str                    # "state" | "transition"
    current_name: str
    proposed_name: str
    tier: str
    criterion_id: str
    evidence: str

    @property
    def is_evidence_of_agreement(self) -> bool:
        """Always False, and deliberately so (spec X-11).

        Naming a code-derived state from an acceptance criterion is a
        *presentation* decision. Treating it as semantic agreement would make
        §4.4's comparison discover its own naming step and report agreement
        everywhere -- destroying the one thing that makes code extraction worth
        doing (§4.1).
        """
        return False

    def describe(self) -> str:
        return (f"{self.kind} {self.element_id}: {self.current_name!r} -> "
                f"{self.proposed_name!r}  [{self.tier}, from {self.criterion_id}]")


def propose_from_criteria(model: Model,
                          confirmed: dict[str, tuple[str, str, str]],
                          titles: dict[str, str] | None = None
                          ) -> list[NameProposal]:
    """Propose tier-1 names from CONFIRMED criteria (spec X-7, X-9).

    `confirmed` maps a transition id to `(criterion_id, when_clause, then_clause)`
    for a criterion a human confirmed validates it. Unconfirmed proposals are not
    accepted as evidence (X-18), so they never reach this function.

    Returns proposals for the transition's **trigger** (from the When) and its
    **target state** (from the Then). A state reached by several transitions
    collects several proposals; that is a real conflict for a human to settle,
    not something to average away.
    """
    proposals: list[NameProposal] = []
    for transition_id, (criterion_id, when, then) in sorted(confirmed.items()):
        transition = model.transitions.get(transition_id)
        if transition is None:
            continue

        # The criterion's TITLE is already a business name -- "Metric Point
        # Query" -- whereas its When clause is a sentence. Reducing a sentence to
        # a name needs judgement this module deliberately does not have, so the
        # title is preferred and the clause is only a fallback.
        trigger_name = (titles or {}).get(criterion_id) or _phrase(when)
        if trigger_name and trigger_name.lower() != transition.trigger.lower():
            proposals.append(NameProposal(
                element_id=transition_id, kind="transition",
                current_name=transition.trigger, proposed_name=trigger_name,
                tier=TIER_AC_VOCABULARY, criterion_id=criterion_id, evidence=when))

        state = model.states.get(transition.target)
        state_name = _phrase(then)
        if state is not None and state_name and state_name.lower() != state.name.lower():
            proposals.append(NameProposal(
                element_id=state.id, kind="state",
                current_name=state.name, proposed_name=state_name,
                tier=TIER_AC_VOCABULARY, criterion_id=criterion_id, evidence=then))
    return proposals


def conflicts(proposals: list[NameProposal]) -> dict[str, list[NameProposal]]:
    """Elements with more than one distinct proposed name.

    Reported rather than resolved. Two criteria describing one state in different
    words is a real disagreement about what that state *is*, and picking one
    silently would bury it (S-10's discipline, applied to names).
    """
    by_element: dict[str, list[NameProposal]] = {}
    for p in proposals:
        by_element.setdefault(p.element_id, []).append(p)
    return {e: ps for e, ps in by_element.items()
            if len({p.proposed_name for p in ps}) > 1}


def format_proposals(proposals: list[NameProposal], model: Model) -> str:
    clashes = conflicts(proposals)
    lines = [f"Name proposals — {len(proposals)} from the AC vocabulary (X-7 tier 1)",
             ""]
    for p in proposals:
        flag = "  [CONFLICT]" if p.element_id in clashes else ""
        lines.append(f"  {p.describe()}{flag}")
    if clashes:
        lines += ["", f"  {len(clashes)} element(s) have competing names — a human",
                  "  settles which, because two criteria describing one state in",
                  "  different words disagree about what it IS (S-10)."]
    lines += ["",
              "  PROPOSED, never applied (X-10, F-7). And per X-11 none of this is",
              "  evidence that the code model and the AC model AGREE: naming",
              "  alignment and semantic agreement are separate facts (X-12)."]
    return "\n".join(lines)
