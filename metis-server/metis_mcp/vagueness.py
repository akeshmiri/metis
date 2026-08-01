"""
Shared vagueness/unfalsifiability heuristic -- used by both CONST-047's
"unambiguous" 29148 characteristic (metis_mcp/requirement_quality.py) and
Layer 8's own vagueness check (REQ-METIS-GRD-08, DQ-004: "vagueness/
unfalsifiability rate ... count(AcceptanceCriterion flagged by §7 Layer 8
heuristic)"). One real implementation, not two independently-drifting
copies of the same term list.

Real, recognized category of ambiguous/unverifiable requirements language
(vague adjectives/adverbs with no measurable threshold, weak/undefined
verbs, open-ended quantifiers, and unresolved placeholders) -- a
deterministic, disclosed heuristic per §9's code-vs-LLM allocation
("vagueness detection" is listed as a checkable heuristic, not free-text
LLM judgment). This flags candidates for human/LLM review; it does not
itself decide a requirement is bad.
"""
import re
from dataclasses import dataclass, field

VAGUE_TERMS = [
    # Unmeasurable quality adjectives -- no falsifiable threshold implied.
    "appropriate", "adequate", "sufficient", "reasonable", "acceptable",
    "user-friendly", "user friendly", "intuitive", "easy to use", "seamless",
    "robust", "flexible", "efficient", "effective", "optimal", "optimum",
    "state of the art", "state-of-the-art", "best practice", "best practices",
    "high quality", "high-quality", "fast", "quick", "slow", "responsive",
    "scalable", "secure" , "reliable", "maintainable", "minimal impact",
    # Open-ended quantifiers -- no bound given.
    "several", "many", "some", "few", "most", "various", "numerous",
    "a lot of", "a number of",
    # Weak/undefined verbs -- no observable behavior specified.
    "support", "handle", "manage", "deal with", "address", "consider",
    "as needed", "as necessary", "as appropriate", "if necessary",
    "where applicable", "in a timely manner", "as soon as possible",
    # Unresolved placeholders -- the statement is not actually complete.
    "tbd", "to be determined", "todo", "fixme", "xxx", "???",
    # Ambiguous joiners -- masks which behavior is actually required.
    "and/or", "etc", "etc.", "and so on",
]

_TERM_PATTERNS = [(t, re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE)) for t in VAGUE_TERMS]


@dataclass
class VaguenessResult:
    vague: bool
    matched_terms: list = field(default_factory=list)
    reason: str = ""


def detect_vagueness(text: str) -> VaguenessResult:
    matched = [term for term, pattern in _TERM_PATTERNS if pattern.search(text)]
    if matched:
        return VaguenessResult(
            vague=True, matched_terms=matched,
            reason=f"Contains {len(matched)} unmeasurable/unfalsifiable term(s): {matched}. "
                   f"Each lacks an observable, testable threshold -- e.g. 'fast' vs a stated "
                   f"latency bound.",
        )
    return VaguenessResult(
        vague=False, matched_terms=[],
        reason="No known vague/unfalsifiable term matched -- a real but bounded heuristic "
               "(this list, VAGUE_TERMS); absence of a match is not proof of full clarity, "
               "just absence of this specific known failure pattern.",
    )
