"""
REQ-METIS-ONT-04: EARS (Easy Approach to Requirements Syntax) structural
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

Structural conformance only, per CONST-047's explicit distinction: this
does NOT check ISO/IEC/IEEE 29148's substantive characteristics (singular,
verifiable, etc.) -- a sentence can pass this and still fail that
checklist (deliberately out of scope here, a separate check).
"""
import re
from dataclasses import dataclass

_PATTERNS = [
    ("EventDriven", re.compile(r"^When (?P<trigger>.+?), the (?P<system>.+?) shall (?P<response>.+)\.$")),
    ("StateDriven", re.compile(r"^While (?P<state>.+?), the (?P<system>.+?) shall (?P<response>.+)\.$")),
    ("UnwantedBehavior", re.compile(r"^If (?P<condition>.+?), then the (?P<system>.+?) shall (?P<response>.+)\.$")),
    ("Optional", re.compile(r"^Where (?P<feature>.+?), the (?P<system>.+?) shall (?P<response>.+)\.$")),
    ("Ubiquitous", re.compile(r"^The (?P<system>.+?) shall (?P<response>.+)\.$")),
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
