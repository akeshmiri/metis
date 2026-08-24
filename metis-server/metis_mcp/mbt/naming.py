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


def split_criterion(text: str) -> tuple[str, str]:
    """`(when_clause, then_clause)` from an EARS-shaped criterion, or `("", "")`.

    One definition, because three call sites need this split and three regexes
    would drift. Anything not in `When … Then …` shape yields a pair of empty
    strings rather than a partial parse: half a criterion is not evidence.
    """
    when = re.search(r"\bwhen\b(.+?)(?:,\s*then\b|$)", text, re.IGNORECASE | re.DOTALL)
    then = re.search(r"\bthen\b(.+)$", text, re.IGNORECASE | re.DOTALL)
    if not (when and then):
        return "", ""
    return when.group(1), then.group(1)


def guard_wording_from_criterion(text: str) -> str:
    """X-7 tier 1 for a *condition*: the criterion's own When clause.

    A criterion's When is the business's statement of the precondition, written
    by a person. `guard_language.describe_guard` can only decode conventions the
    code already commits to -- it reaches "the payload is invalid" and never
    "the metric belongs to a project the caller cannot see". This does, because
    somebody wrote it down.

    Returned for display beside the raw guard, never in place of it: the guard is
    the anchored, auditable fact and a criterion is a second source about the
    same behaviour. Where they disagree that is a finding for §4.4's comparison,
    not something to resolve by overwriting one with the other.
    """
    when, _ = split_criterion(text)
    return _clip(re.sub(r"\s+", " ", when).strip(" ,.;:")) if when.strip() else ""


def transition_name_from_criterion(text: str) -> str:
    """X-7 tier 1 for an edge: name a transition from the criterion it validates.

    This is the route to genuinely *business* language for anything the code does
    not already commit to, and it is available only where a human confirmed a
    match.

    **The ceiling moved, and this docstring used to overstate it.** It said
    paraphrasing `t.isEmpty()` into "no metric exists" would be Métis inventing
    meaning. That is right about a free paraphrase and wrong about a decode:
    `unfolding.presence_sense` already reads that atom as "the resource is
    absent" and the M-6 pass already *acts* on it, building `MetricPresent` and
    re-parenting readers onto it. `guard_language` now says in words what the
    model had already committed to in structure — tier 2, and marked as such.

    What is still exclusive to tier 1 is meaning the code never states:
    `ex.getCause() instanceof ConstraintViolationException` is fifteen guards in
    this estate and no decoder can know it means a duplicate was submitted.
    """
    when_clause, then_clause = split_criterion(text)
    if not (when_clause and then_clause):
        return ""

    # `_phrase` strips status codes, which is right for a STATE name and
    # destructive here: the status *is* the outcome. Stripping it turned
    # "then 204 No Content is returned" into "is returned" -- a name that says
    # nothing, and a worse one than tier 2 produces. So the outcome side keeps
    # its words and only the leading article goes.
    left = _clip(_phrase(when_clause))
    right = _clip(_LEADING.sub("", re.sub(r"\s+", " ", then_clause).strip(" ,.;:")))
    if len(left) < 3 or len(right) < 3:
        # Degenerate after cleaning. Tier 2's readable shape beats a stub.
        return ""
    return f"{left} → {right}"


# A name is a label, not a paragraph. A criterion may run to several sentences
# (and a reviewer's edit may make it longer still); the first clause is what
# identifies the behaviour.
_NAME_LIMIT = 72


def _clip(text: str) -> str:
    """First sentence, then a hard limit — truncation marked, never silent."""
    first = re.split(r"(?<=[.;])\s+", text.strip(), maxsplit=1)[0].strip(" ,.;:")
    if len(first) <= _NAME_LIMIT:
        return first
    return first[:_NAME_LIMIT].rsplit(" ", 1)[0] + "…"


def transition_display_name(transition, states: dict | None = None,
                            criterion_text: str = "") -> str:
    """A readable name for a transition (spec D-8, X-7 applied to edges).

    **D-8 says `name` is display data, not identity** -- and landing was setting
    it to the id, so the graph showed a reviewer

        com.example.records.RecordController.one:
        org.springframework.http.ResponseEntity(java.lang.Long)::GET->NoContent204

    where it meant to show them a behaviour. The id is unchanged and still
    content-derived; only what a person reads changes.

    Deterministic, and it introduces no word that is not already in the trigger,
    the guard or the target state's own name (T-6). Where the target state has
    earned a business name through X-7's cascade, this inherits it -- so naming a
    state improves every transition into it, which is the point of the cascade.

    The guard is included because a transition is `(state, trigger, guard,
    target)` and two transitions on the same trigger differ *only* by their
    guard: dropping it would give both the same name, which is worse than an
    ugly one.

    Where a confirmed criterion is supplied it wins (tier 1) -- a person's own
    words beat a rearrangement of the code's.
    """
    if criterion_text:
        tier_one = transition_name_from_criterion(criterion_text)
        if tier_one:
            return tier_one

    trigger = (transition.trigger or "").strip() or "interaction"
    target = transition.target
    if states:
        state = states.get(target)
        if state is not None:
            target = state.name or target
    guard = (transition.guard or "").strip()
    return f"{trigger} → {target}" + (f" when {guard}" if guard else "")


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
