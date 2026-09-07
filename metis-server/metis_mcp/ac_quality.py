"""Whether an acceptance criterion is precise enough for a test to assert.

**Ported from Atlas** (`.agents/skills/shared/scripts/ac_quality.py`), whose
docstring names the gap exactly: *"'No unresolved ambiguities' was a gate in two
skills with no definition behind it, so nothing could enforce it."* Métis had the
same gap in a narrower place. `ac_drafting` tracks atomicity for the criteria it
drafts **from code** (`DraftSet.not_atomic`), and nothing at all checked the ones
`knowledge-capture` writes from prose — which is where a person's own words enter
the graph, and so the place ambiguity actually gets in.

What did not cross, and why
---------------------------
Atlas's `AC-TITLE-IS-SCENARIO` and `AC-MISSING-SCENARIO` are **deliberately not
here**. They rest on Atlas's split between an AC's *statement* (its name, one
sentence) and its *scenario* (separate given/when/then fields), and they flag
text that mixes the two. Métis has no such split: a criterion's text **is** the
Given/When/Then sentence — `ac_drafting.DraftCriterion.text` renders exactly
`"Given ..., when ..., then ..."`. Porting those two rules would have reported
every criterion Métis itself drafts as defective, which is how a checker gets
switched off. The BDD parse still crossed, because it is needed to segment a
sentence for the atomicity check: a `Given` may legitimately carry two
preconditions without the criterion asserting two behaviours.

What this is not
----------------
**Not the EARS check.** `ears_checker` asks whether a sentence has one of the
five EARS shapes; §2.6 draws the line and says structural conformance is not
substantive quality. A sentence can pass one and fail the other, in both
directions.

**Not a gate.** Every finding here is advisory. A criterion that fails every rule
still lands at `Quarantine` like everything else (S-4) and a human settles it.
Nothing in this module rewrites a criterion to make it pass — that is the line
`ac_mining` refuses to cross (S-13), and a checker that silently fixed its own
findings would be worse than none.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    detail: str
    suggestion: str

    def describe(self) -> str:
        return f"[{self.severity}] {self.rule}: {self.detail} -> {self.suggestion}"


# Words that describe a quality without saying how it is measured. Each one makes
# a criterion untestable: two engineers will disagree on whether "properly" was
# achieved, and so will write two different tests.
VAGUE_TERMS = {
    "appropriately", "appropriate", "properly", "correctly", "adequate",
    "adequately", "sufficient", "sufficiently", "reasonable", "reasonably",
    "suitable", "suitably", "acceptable", "acceptably", "various", "several",
    "some", "many", "certain", "relevant", "robust", "seamless", "seamlessly",
    "efficient", "efficiently", "optimal", "optimally", "quick", "quickly",
    "fast", "timely", "normal", "typical", "generally", "usually", "mostly",
    "largely", "curated", "strong", "strict", "clear", "clearly", "well",
    "good", "nice", "simple", "easy", "flexible", "scalable", "meaningful",
    "significant", "significantly", "minor", "major", "high-confidence",
    "conservative", "conservatively", "carefully",
}

# Phrases that leave the requirement open-ended.
OPEN_ENDED_PATTERNS = [
    (re.compile(r"\betc\.?", re.I), "etc."),
    (re.compile(r"\band so on\b", re.I), "and so on"),
    (re.compile(r"\band more\b", re.I), "and more"),
    (re.compile(r"\band others\b", re.I), "and others"),
    (re.compile(r"\bas needed\b", re.I), "as needed"),
    (re.compile(r"\bif needed\b", re.I), "if needed"),
    (re.compile(r"\bif necessary\b", re.I), "if necessary"),
    (re.compile(r"\bas necessary\b", re.I), "as necessary"),
    (re.compile(r"\bwhere applicable\b", re.I), "where applicable"),
    (re.compile(r"\bas expected\b", re.I), "as expected"),
    (re.compile(r"\bas required\b", re.I), "as required"),
    (re.compile(r"\.\.\.\s*$"), "trailing ellipsis"),
]

# A criterion states what the system does, not what it might do. Note "shall" is
# absent on purpose: it is EARS's own modal and the required word there.
WEAK_MODALS = re.compile(
    r"\b(should|may|might|could|would|ought to|possibly|perhaps)\b", re.I)

# The angle-bracket form must start with a word character: '<->' and '<=' are
# notation, not placeholders, and flagging them trains people to ignore the check.
#
# This does not collide with X-6e's accepted-space placeholders
# (`<string, length 3..40, required>`): those are rendered into curl recipes and
# payload shapes, never into criterion text. A `<...>` in a criterion is an
# unresolved hole, which is what this catches.
PLACEHOLDERS = re.compile(
    r"(\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|\?\?\?|<[A-Za-z_][^>]{0,40}>|\bN/?A\b)",
    re.I)

AND_OR = re.compile(r"\band\s*/\s*or\b", re.I)

PRONOUN_START = re.compile(r"^\s*(it|this|that|these|those|they)\b", re.I)

# Words asserting a change in magnitude. Without a number they cannot be verified.
CHANGE_TERMS = re.compile(
    r"\b(increase[sd]?|decrease[sd]?|improve[sd]?|reduce[sd]?|faster|slower|"
    r"better|worse|higher|lower|more|fewer|greater|less)\b", re.I)
_NUMBER_WORDS = ("one|two|three|four|five|six|seven|eight|nine|ten|zero|"
                 "single|double|triple|first|second|third")
# A quantity may be a digit or a spelled-out number: "two or more consecutive
# spaces" is precise, and flagging its "more" would be wrong.
HAS_NUMBER = re.compile(rf"(\d|\b(?:{_NUMBER_WORDS})\b)", re.I)

# Verbs that sound like a requirement but name no observable result. A test
# cannot assert that something was "respected"; it can assert what the system did.
NON_OBSERVABLE = re.compile(
    r"\b(respected|honou?red|handled|supported|considered|addressed|ensured|"
    r"maintained|observed|accounted for|taken into account|catered for|"
    r"dealt with|managed)\b", re.I)

# Deliberately NOT flagging passive voice. "A vendor with the flag set is
# excluded from auto-verification" is passive, names its subject, and is
# perfectly testable. The real defect in the passive examples is the
# non-observable predicate, which NON_OBSERVABLE already catches; a passive rule
# on top of it only produces noise, and a checker that cries wolf gets ignored.

MIN_WORDS = 5

_BDD_SPLIT = re.compile(
    r"^\s*given\s+(?P<given>.+?)[,;]?\s*\bwhen\b\s+(?P<when>.+?)[,;]?\s*"
    r"\bthen\b\s+(?P<then>.+)$", re.I | re.S)

_QUOTED_SPAN = re.compile(r"'[^']*'|\"[^\"]*\"")


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", text)


def _strip_quoted(text: str) -> str:
    """Blank out quoted literals so their contents are not read as prose.

    A criterion quoting the tokens under test — "' & ' and ' and ' are rejected"
    — would otherwise have those counted as conjunctions joining assertions.
    """
    return _QUOTED_SPAN.sub(" ", text)


def clauses(text: str) -> dict | None:
    """Split a criterion into Given/When/Then, or None if it is not in that form.

    Métis's own drafted criteria always are (`ac_drafting.DraftCriterion.text`);
    an authored one may not be, and that is not itself a defect.
    """
    match = _BDD_SPLIT.match((text or "").strip())
    if match is None:
        return None
    return {k: v.strip().rstrip(".").strip()
            for k, v in match.groupdict().items()}


def assess(text: str) -> list[Finding]:
    """Every clarity defect found in one acceptance criterion. Advisory."""
    findings: list[Finding] = []
    raw = (text or "").strip()

    if not raw:
        return [Finding("AC-EMPTY", ERROR, "the criterion is empty",
                        "write one testable statement of what the system does")]

    words = _words(raw)
    lowered = {w.lower() for w in words}
    parts = clauses(raw)

    non_observable = NON_OBSERVABLE.search(raw)
    if non_observable:
        findings.append(Finding(
            "AC-NON-OBSERVABLE", ERROR,
            f"asserts an intention, not a result "
            f"({non_observable.group(0)!r})",
            "state what the system does, e.g. 'the flag is respected' -> "
            "'a flagged record is excluded from the batch'"))

    placeholder = PLACEHOLDERS.search(raw)
    if placeholder:
        findings.append(Finding(
            "AC-PLACEHOLDER", ERROR,
            f"contains an unresolved placeholder {placeholder.group(0)!r}",
            "resolve it before the criterion is used; a placeholder cannot "
            "be tested"))

    vague = sorted(lowered & VAGUE_TERMS)
    if vague:
        findings.append(Finding(
            "AC-VAGUE-TERM", ERROR,
            "uses unmeasurable qualifier(s): "
            + ", ".join(repr(v) for v in vague),
            "replace with the observable condition, e.g. 'properly' -> the "
            "exact expected value"))

    for pattern, label in OPEN_ENDED_PATTERNS:
        if pattern.search(raw):
            findings.append(Finding(
                "AC-OPEN-ENDED", ERROR,
                f"leaves the requirement open-ended via {label!r}",
                "enumerate the cases explicitly, or split them into "
                "separate criteria"))
            break

    modal = WEAK_MODALS.search(raw)
    if modal:
        findings.append(Finding(
            "AC-WEAK-MODAL", ERROR,
            f"states a possibility, not a requirement ({modal.group(0)!r})",
            "assert the definite behaviour, e.g. 'should reject' -> 'rejects'"))

    if AND_OR.search(raw):
        findings.append(Finding(
            "AC-AMBIGUOUS-CONJUNCTION", ERROR,
            "uses 'and/or', which permits two readings",
            "state whether both, either, or exactly one applies"))

    if PRONOUN_START.match(raw):
        findings.append(Finding(
            "AC-PRONOUN-START", ERROR,
            "opens with a pronoun that has no antecedent here",
            "name the subject explicitly; a criterion is read on its own"))

    # Evaluated per clause for Given/When/Then text: a Given may legitimately
    # list two preconditions, and the clause separators are not assertion
    # joiners. This is the check `atomic` is read from.
    for segment in (list(parts.values()) if parts else [raw]):
        unquoted = _strip_quoted(segment)
        if (";" in unquoted
                or sum(1 for w in _words(unquoted) if w.lower() == "and") >= 2):
            findings.append(Finding(
                "AC-MULTI-ASSERT", WARNING,
                "a clause appears to assert more than one behaviour",
                "split into one criterion per assertion so each maps to its "
                "own test"))
            break

    change = CHANGE_TERMS.search(raw)
    if change and not HAS_NUMBER.search(raw):
        findings.append(Finding(
            "AC-UNQUANTIFIED-CHANGE", WARNING,
            f"claims a change ({change.group(0)!r}) with no measurable quantity",
            "state the target value or baseline, e.g. 'increases by 15-20%'"))

    if len(words) < MIN_WORDS:
        findings.append(Finding(
            "AC-TOO-SHORT", WARNING, f"is only {len(words)} word(s) long",
            "state subject, action and expected outcome in full"))

    return findings


def is_atomic(findings: list) -> bool:
    """Whether the criterion carries exactly one assertion.

    Read from the findings rather than recomputed, so the boolean and the
    finding that explains it cannot disagree — the failure mode `ontology.facts`
    exists to prevent for the encoder and decoder.
    """
    return not any(f.rule == "AC-MULTI-ASSERT" for f in findings)
