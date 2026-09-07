"""
§2.6: EARS (Easy Approach to Requirements Syntax) structural
conformance -- deterministic regex, per §9's code-vs-LLM allocation table
("EARS check" is explicitly listed as deterministic code, not judgment).

The five patterns, exact wording from metis-specification.md §4.3:
  Ubiquitous:        "The <system> shall <response>."
  Event-driven:       "When <trigger>, the <system> shall <response>."
  State-driven:       "While <state>, the <system> shall <response>."
  Unwanted-behavior:  "If <condition>, then the <system> shall <response>."
  Optional:           "Where <feature is included>, the <system> shall <response>."

Checked in this order (comma-clause patterns before the bare Ubiquitous
fallback) because Ubiquitous's pattern is a strict subset shape of the
other four's tail clause -- checking it first would misclassify every
Event/State/Unwanted/Optional sentence as Ubiquitous.

Structural conformance only, per §2.6's explicit distinction: this
does NOT check ISO/IEC/IEEE 29148's substantive characteristics (singular,
verifiable, etc.) -- a sentence can pass this and still fail that
checklist (deliberately out of scope here, a separate check).
"""
import re
from dataclasses import dataclass

# **The terminal full stop is OPTIONAL, and that is a fix, not a loosening.**
#
# Every pattern here required `\.$`, transcribed from the templates in
# `metis-specification.md` §4.3 -- a v1 document that no longer exists, and whose
# templates carry a period because they are written as sentences rather than
# because EARS requires one. The surviving definition, in the academy's own
# glossary, states the shape with no punctuation at all: *When <trigger>, the
# system shall <response>*.
#
# The consequence was measured on realistic ticket titles, and it is not small:
# **six well-formed EARS requirements scored 0/6** because a Jira summary does
# not end with a full stop. Every one of them landed as a `Finding` -- correctly
# reported as "not EARS-conformant", which is the most misleading possible way to
# be right. On a real backlog that is the difference between most requirements
# arriving as `Requirement` and almost none.
#
# Nothing about the STRUCTURE is relaxed: the trigger clause, the comma, `the
# <system> shall` and a non-empty response are all still required, and prose
# still fails. Only the punctuation is now allowed to be absent, and a trailing
# `.`, `!` or `?` is still accepted so a sentence written properly is unaffected.
_END = r"[.!?]?$"

_PATTERNS = [
    ("EventDriven", re.compile(r"^When (?P<trigger>.+?), the (?P<system>.+?) shall (?P<response>.+?)" + _END)),
    ("StateDriven", re.compile(r"^While (?P<state>.+?), the (?P<system>.+?) shall (?P<response>.+?)" + _END)),
    ("UnwantedBehavior", re.compile(r"^If (?P<condition>.+?), then the (?P<system>.+?) shall (?P<response>.+?)" + _END)),
    ("Optional", re.compile(r"^Where (?P<feature>.+?), the (?P<system>.+?) shall (?P<response>.+?)" + _END)),
    ("Ubiquitous", re.compile(r"^The (?P<system>.+?) shall (?P<response>.+?)" + _END)),
]


@dataclass
class EARSResult:
    conformant: bool
    pattern: str | None
    reason: str
    groups: dict


def check_ears_conformance(text: str) -> EARSResult:
    text = text.strip()
    for pattern_name, regex in _PATTERNS:
        m = regex.match(text)
        if m:
            return EARSResult(
                conformant=True, pattern=pattern_name,
                reason=f"Matches the {pattern_name} EARS pattern.",
                groups=m.groupdict(),
            )
    return EARSResult(
        conformant=False, pattern=None,
        reason="Does not match any of the five EARS sentence patterns "
               "(Ubiquitous, Event-driven, State-driven, Unwanted-behavior, Optional) -- "
               "structural conformance check, not a substantive quality judgment.",
        groups={},
    )
