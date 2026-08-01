"""
CONST-047 (metis-standards-integration.md §3, Article XIII): every
Requirement/MicroRequirement reaching Approved MUST be scored against ISO/
IEC/IEEE 29148's requirement quality characteristics -- unambiguous,
complete, singular, feasible, verifiable, correct, necessary, consistent --
"as a structured checklist attached to the entity, not a free-text
judgment call." This extends DQ-002/EARS conformance (structure) with a
substantive check: "a requirement can pass EARS structural conformance and
still fail this checklist ... both checks are required, neither
substitutes for the other."

Per §9's code-vs-LLM allocation, 4 of the 8 are genuinely deterministic and
4 are genuinely judgment:

  unambiguous  deterministic  -- metis_mcp/vagueness.py's shared heuristic
  complete     deterministic  -- EARS-conformant + every captured EARS
                                  clause is non-empty + no unresolved
                                  placeholder marker
  singular     deterministic  -- exactly one top-level 'shall' clause, no
                                  bundled 'and'-joined second obligation
  consistent   deterministic  -- cross-checks this requirement's extracted
                                  numeric threshold(s) against other real
                                  Requirement nodes sharing the same EARS
                                  pattern + system + response shape,
                                  reusing behavior_model.py's real interval-
                                  overlap logic (same technique as Guard
                                  conflict detection, applied to prose
                                  numbers instead of guard expressions) --
                                  a real, disclosed heuristic: no
                                  comparable sibling found -> consistent
                                  by default (absence of evidence, not
                                  fabricated confidence either way)
  verifiable   LLM judgment   -- "can this be objectively tested?" needs
  feasible     LLM judgment      real interpretation of engineering/
  correct      LLM judgment      business plausibility -- one real,
  necessary    LLM judgment      deliberate, costed model call
                                  (metis_mcp/llm_client.py), never
                                  automatic, same convention as
                                  llm_judge.py/microrequirement.py
"""
import json
import re
from dataclasses import dataclass, field

from metis_mcp.ears_checker import check_ears_conformance
from metis_mcp.vagueness import detect_vagueness
from metis_mcp.llm_client import call_llm, LLMCallError

_PLACEHOLDER_RE = re.compile(r"\b(TBD|TODO|FIXME|XXX)\b|\?\?\?", re.IGNORECASE)
_SHALL_RE = re.compile(r"\bshall\b", re.IGNORECASE)
# " and " directly joining what look like two independent verb clauses --
# a real, bounded signal for a bundled (non-singular) requirement, not a
# claim of perfect natural-language parsing.
_BUNDLED_AND_RE = re.compile(r"\bshall\b.*\band\b.*\bshall\b", re.IGNORECASE)
_NUMBER_UNIT_RE = re.compile(
    r"(?P<num>-?\d+(?:\.\d+)?)\s*(?P<unit>seconds?|secs?|ms|milliseconds?|minutes?|mins?|"
    r"hours?|hrs?|%|percent|days?|requests?(?:/s| per second)?)", re.IGNORECASE,
)

JUDGMENT_SYSTEM_PROMPT = (
    "You are scoring one requirement sentence against 4 of ISO/IEC/IEEE 29148's "
    "requirement quality characteristics. Judge ONLY from the text given -- no "
    "outside assumptions about the system. Definitions: "
    "verifiable = there is an objective way to test/measure whether this was met; "
    "feasible = achievable within reasonable engineering/business constraints as stated; "
    "correct = the statement is technically sound and doesn't contradict itself; "
    "necessary = the requirement traces to a real need, isn't gold-plating or an "
    "implementation detail masquerading as a requirement. "
    "Respond with STRICT JSON only, no markdown fences, no other text: "
    '{"verifiable": true/false, "feasible": true/false, "correct": true/false, '
    '"necessary": true/false, "reasoning": "at most 30 words covering any false verdict"}'
)


@dataclass
class ChecklistResult:
    requirement_id: str
    text: str
    unambiguous: bool
    complete: bool
    singular: bool
    consistent: bool
    verifiable: bool | None = None
    feasible: bool | None = None
    correct: bool | None = None
    necessary: bool | None = None
    reasons: dict = field(default_factory=dict)
    judgment_scored: bool = False
    judgment_model: str | None = None
    judgment_cost_usd: float = 0.0

    @property
    def all_scored_pass(self) -> bool:
        """CONST-047 requires all 8 characteristics. False until the
        judgment half has actually been scored -- an unscored judgment
        characteristic must never be silently counted as a pass; that
        would let a Requirement claim full 29148 conformance on the
        strength of only its 4 deterministic checks."""
        if not self.judgment_scored:
            return False
        det = self.unambiguous and self.complete and self.singular and self.consistent
        return det and bool(self.verifiable) and bool(self.feasible) \
            and bool(self.correct) and bool(self.necessary)


def _check_unambiguous(text: str, reasons: dict) -> bool:
    result = detect_vagueness(text)
    reasons["unambiguous"] = result.reason
    return not result.vague


def _check_complete(text: str, ears, reasons: dict) -> bool:
    if not ears.conformant:
        reasons["complete"] = "Not EARS-conformant -- an incomplete sentence structurally " \
                               "cannot be a complete requirement (extends DQ-002)."
        return False
    if _PLACEHOLDER_RE.search(text):
        reasons["complete"] = "Contains an unresolved placeholder marker (TBD/TODO/FIXME/XXX/???)."
        return False
    empty_groups = [k for k, v in ears.groups.items() if k != "system" and not v.strip()]
    if empty_groups:
        reasons["complete"] = f"EARS clause(s) captured but empty: {empty_groups}."
        return False
    reasons["complete"] = f"EARS-conformant ({ears.pattern}), no placeholder markers, all clauses non-empty."
    return True


def _check_singular(text: str, reasons: dict) -> bool:
    shall_count = len(_SHALL_RE.findall(text))
    if shall_count > 1:
        reasons["singular"] = f"Contains {shall_count} 'shall' obligations -- bundles multiple " \
                               f"requirements into one statement."
        return False
    if _BUNDLED_AND_RE.search(text):
        reasons["singular"] = "Matches a bundled 'shall ... and ... shall' shape -- two joined obligations."
        return False
    reasons["singular"] = "Exactly one obligation clause, no bundled second 'shall'."
    return True


def _extract_numbers(text: str) -> list[tuple[float, str]]:
    return [(float(m.group("num")), m.group("unit").lower()) for m in _NUMBER_UNIT_RE.finditer(text)]


def _response_shape(text: str, ears) -> str:
    """A coarse comparison key: the response clause with numbers stripped,
    lowercased -- two requirements sharing this shape are 'about the same
    thing' closely enough to compare thresholds. Real, disclosed
    limitation: purely lexical, not semantic -- won't catch paraphrases."""
    response = ears.groups.get("response", text) if ears.conformant else text
    return _NUMBER_UNIT_RE.sub("<N>", response).strip().lower()


def _check_consistent(session, requirement_id: str, text: str, ears, reasons: dict) -> bool:
    numbers = _extract_numbers(text)
    if not numbers or not ears.conformant:
        reasons["consistent"] = "No comparable numeric threshold extracted -- nothing to " \
                                 "cross-check, so scored consistent by default (absence of " \
                                 "evidence, not a fabricated pass)."
        return True

    shape = _response_shape(text, ears)
    siblings = session.run(
        "MATCH (r:Requirement) WHERE r.id <> $id AND r.ears_pattern = $pattern "
        "RETURN r.id AS id, r.text AS text",
        id=requirement_id, pattern=ears.pattern,
    ).data()

    conflicts = []
    for sib in siblings:
        sib_ears = check_ears_conformance(sib["text"])
        if not sib_ears.conformant or _response_shape(sib["text"], sib_ears) != shape:
            continue
        sib_numbers = _extract_numbers(sib["text"])
        for num, unit in numbers:
            for sib_num, sib_unit in sib_numbers:
                if unit == sib_unit and num != sib_num:
                    conflicts.append((sib["id"], num, sib_num, unit))

    if conflicts:
        reasons["consistent"] = (
            f"Same response shape as {len(conflicts)} other real Requirement(s) but a "
            f"different numeric threshold, e.g. {conflicts[0][3]}={conflicts[0][1]} here vs "
            f"{conflicts[0][3]}={conflicts[0][2]} in '{conflicts[0][0]}' -- real, specific "
            f"disagreement, not a guess."
        )
        return False
    reasons["consistent"] = f"No conflicting numeric threshold found among {len(siblings)} " \
                             f"same-pattern Requirement(s) checked."
    return True


def score_deterministic(session, requirement_id: str, text: str) -> ChecklistResult:
    ears = check_ears_conformance(text)
    reasons: dict = {}
    unambiguous = _check_unambiguous(text, reasons)
    complete = _check_complete(text, ears, reasons)
    singular = _check_singular(text, reasons)
    consistent = _check_consistent(session, requirement_id, text, ears, reasons)
    return ChecklistResult(
        requirement_id=requirement_id, text=text,
        unambiguous=unambiguous, complete=complete, singular=singular, consistent=consistent,
        reasons=reasons,
    )


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    if not m:
        raise LLMCallError(f"29148 judgment response contained no JSON object: {text[:300]}")
    return json.loads(m.group(0))


def score_judgment(result: ChecklistResult, model: str = "sonnet") -> ChecklistResult:
    """Deliberate, explicit, real-costed call -- never invoked automatically
    by score_deterministic. Mutates and returns the same ChecklistResult
    for a single combined checklist object."""
    prompt = f'Requirement: "{result.text}"\n\nScore it per the 4 characteristics. Respond in the required JSON format.'
    response = call_llm(prompt, model=model, system_prompt=JUDGMENT_SYSTEM_PROMPT)
    parsed = _extract_json(response.text)
    result.verifiable = bool(parsed["verifiable"])
    result.feasible = bool(parsed["feasible"])
    result.correct = bool(parsed["correct"])
    result.necessary = bool(parsed["necessary"])
    result.reasons["judgment"] = parsed.get("reasoning", "")
    result.judgment_scored = True
    result.judgment_model = model
    result.judgment_cost_usd = response.cost_usd
    return result


def write_checklist(session, result: ChecklistResult) -> None:
    """Attaches the checklist to the entity as a structured property, per
    CONST-047's explicit wording ('a structured checklist attached to the
    entity, not a free-text judgment call') -- JSON-serialized since Neo4j
    node properties are flat, not nested objects."""
    payload = {
        "unambiguous": result.unambiguous, "complete": result.complete,
        "singular": result.singular, "consistent": result.consistent,
        "verifiable": result.verifiable, "feasible": result.feasible,
        "correct": result.correct, "necessary": result.necessary,
        "reasons": result.reasons, "judgment_scored": result.judgment_scored,
        "judgment_model": result.judgment_model, "all_pass": result.all_scored_pass,
    }

    def _write(tx):
        tx.run(
            "MATCH (r:Requirement {id: $id}) SET r.iso29148_checklist = $checklist, "
            "r.iso29148_checklist_pass = $all_pass",
            id=result.requirement_id, checklist=json.dumps(payload), all_pass=result.all_scored_pass,
        )
    session.execute_write(_write)
