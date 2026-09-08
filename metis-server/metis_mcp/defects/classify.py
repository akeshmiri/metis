"""What a failure is evidence *of*, from the failure itself.

**The gap this closes, and how narrow it turned out to be.** Filing a defect
already worked — `publishing/tracker_write.JiraWriter` was ported from the same
practice this taxonomy comes from, and it checks for an existing issue before it
creates one. What was missing is the step in front of it: a failing test says
`expected 200, got 403`, and somebody has to decide whether that is the system
being wrong, the test being wrong, or the environment being unavailable.

Getting that wrong is expensive in a specific way. A test-side failure filed as a
product defect goes to a team who cannot reproduce it; an environment outage
filed as a defect gets triaged, assigned and closed as *cannot reproduce* a week
later, by which time the outage is gone and the evidence with it.

**So the axis that matters is not severity — it is what the evidence points at.**
Atlas's table carries a priority column; this does not, deliberately. How urgent
a defect is depends on what it blocks and who is waiting, and neither is in a
stack trace. What *is* in a stack trace is which of three things broke.

**`unknown` is a verdict and never a default.** A failure matching no rule is
reported as unclassified with the evidence attached, because a wrong label is
worse than no label: it routes the defect to the wrong place with a confidence
nobody earned.

Pure: evidence in, a classification out. Nothing here files anything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: What the evidence points at. The axis that decides who the defect goes to,
#: which is the decision this module exists to inform.
SYSTEM = "the system under test"
TEST = "the test"
ENVIRONMENT = "the environment"
UNDECIDED = "undecided"

#: The classes, each with the evidence that raises it. Ported from the sibling
#: project's root-cause table; the labels are kept identical so a defect filed by
#: either is recognisable to the same people.
STATUS_MISMATCH = "http-status-mismatch"
URL_CHANGE = "api-url-change"
SERVICE_EXCEPTION = "service-exception"
TEST_DATA = "test-data-setup"
SCHEMA_DRIFT = "dto-schema-drift"
ASSERTION_DRIFT = "assertion-drift"
ENVIRONMENT_ISSUE = "environment-issue"
UNCLASSIFIED = "unclassified"

LABELS = (STATUS_MISMATCH, URL_CHANGE, SERVICE_EXCEPTION, TEST_DATA,
          SCHEMA_DRIFT, ASSERTION_DRIFT, ENVIRONMENT_ISSUE)


@dataclass(frozen=True)
class Classification:
    """One reading of a failure, with the evidence and the next thing to check."""

    label: str
    #: What in the evidence produced this. A classification a reader cannot
    #: audit is one they have to take on trust.
    because: str
    #: Which of the three the evidence points at.
    points_at: str
    #: The next thing to look at. A property of the CLASS, not a judgement about
    #: this incident — which is why it is a fixed string per label rather than
    #: something computed from the evidence.
    next_check: str

    def describe(self) -> str:
        return f"[{self.label}] {self.because} — points at {self.points_at}"


#: What to look at next, per class.
NEXT_CHECK = {
    STATUS_MISMATCH: "compare the expected status against the contract and the "
                     "recovered outcome: one of the three has moved",
    URL_CHANGE: "check whether the route still exists — a 404 on a path the test "
                "used to reach is a contract change until proven otherwise",
    SERVICE_EXCEPTION: "read the service log at the timestamp; a 5xx with a "
                       "trace is the system failing, not the test",
    TEST_DATA: "check the setup: the failure is before the assertion, so the "
               "test never reached what it was written to check",
    SCHEMA_DRIFT: "diff the DTO against the contract. The response changed shape "
                  "and the test's model did not",
    ASSERTION_DRIFT: "check whether the expected value was ever right. A "
                     "hardcoded constant that no longer matches is usually the "
                     "test, and occasionally the requirement",
    ENVIRONMENT_ISSUE: "confirm the environment was up. Filing this as a defect "
                       "spends somebody's week on an outage that has since gone",
}

_STATUS = re.compile(r"expected[:\s]+(\d{3}).{0,40}?actual[:\s]+(\d{3})",
                     re.I | re.S)
_ANY_5XX = re.compile(r"\b5\d{2}\b")
_TRACE = re.compile(r"\bat [\w.$]+\([\w.]+:\d+\)|Traceback \(most recent call",
                    re.I)
_UNAVAILABLE = re.compile(r"\b(502|503|504)\b|connection refused|timed? ?out|"
                          r"unknownhost|no route to host", re.I)
_SCHEMA = re.compile(r"unrecognized(?:property|field)|unknown property|"
                     r"missing required (?:creator|property)|"
                     r"cannot deserialize|jsonmappingexception", re.I)
_NULL_IN_SETUP = re.compile(r"nullpointerexception|AttributeError: .*NoneType",
                            re.I)
_SETUP_PHASE = re.compile(r"\b(setup|beforeeach|beforeclass|beforemethod|"
                          r"fixture|@before)\b", re.I)


def classify(evidence: str, *, expected: str = "", actual: str = "",
             phase: str = "") -> Classification:
    """One failure, read.

    `evidence` is the failure output — a message, a stack trace, or both.
    `expected` and `actual` are the two values where a runner reports them
    separately; `phase` is `setup` / `test` / `teardown` where it says.

    **Order matters and is deliberate.** An environment outage produces a 5xx
    and so does a service exception, so the outage is checked first: reading an
    outage as a service defect sends somebody hunting a bug that is not there,
    and reading a service defect as an outage loses a real one. The narrower
    evidence wins.
    """
    text = " ".join(part for part in (evidence, expected, actual, phase) if part)
    if not text.strip():
        return Classification(
            UNCLASSIFIED,
            "no failure evidence was supplied — there is nothing to read",
            UNDECIDED,
            "attach the runner's output. A defect filed from no evidence is a "
            "defect nobody can reproduce")

    if _UNAVAILABLE.search(text):
        return Classification(
            ENVIRONMENT_ISSUE,
            "the evidence shows an unreachable or unavailable dependency",
            ENVIRONMENT, NEXT_CHECK[ENVIRONMENT_ISSUE])

    if _SCHEMA.search(text):
        return Classification(
            SCHEMA_DRIFT,
            "the response could not be deserialised into the model the test "
            "expects",
            # Genuinely ambiguous, and saying so is the point: the contract may
            # have changed legitimately, or the service may have broken it.
            UNDECIDED, NEXT_CHECK[SCHEMA_DRIFT])

    if _ANY_5XX.search(text) and _TRACE.search(text):
        return Classification(
            SERVICE_EXCEPTION,
            "a 5xx with a stack trace: the service raised rather than answered",
            SYSTEM, NEXT_CHECK[SERVICE_EXCEPTION])

    if _NULL_IN_SETUP.search(text) and (_SETUP_PHASE.search(text)
                                        or phase.lower() == "setup"):
        return Classification(
            TEST_DATA,
            "a null dereference before the assertion — the test did not reach "
            "what it was written to check",
            TEST, NEXT_CHECK[TEST_DATA])

    match = _STATUS.search(text)
    pair = ((expected.strip(), actual.strip())
            if expected.strip() and actual.strip()
            else (match.group(1), match.group(2)) if match else None)
    if pair:
        want, got = pair
        if got == "404":
            return Classification(
                URL_CHANGE,
                f"expected {want} and the route answered 404 — the path the "
                f"test used is not there",
                UNDECIDED, NEXT_CHECK[URL_CHANGE])
        return Classification(
            STATUS_MISMATCH, f"expected {want}, got {got}",
            UNDECIDED, NEXT_CHECK[STATUS_MISMATCH])

    if re.search(r"assert|expected .* but", text, re.I):
        return Classification(
            ASSERTION_DRIFT,
            "an assertion failed with no status, exception or schema evidence "
            "beside it",
            UNDECIDED, NEXT_CHECK[ASSERTION_DRIFT])

    return Classification(
        UNCLASSIFIED,
        "no rule matched this evidence. A wrong label routes the defect to the "
        "wrong team with a confidence nobody earned, so none is given",
        UNDECIDED,
        "read the output yourself and classify it by hand; if the shape recurs, "
        "it is worth a rule")


def describe(evidence: str, **kwargs) -> dict:
    """One classification, for a tool."""
    found = classify(evidence, **kwargs)
    return {
        "label": found.label,
        "because": found.because,
        "points_at": found.points_at,
        "next_check": found.next_check,
        "classified": found.label != UNCLASSIFIED,
        "means": (
            "what the evidence points at, which decides who the defect goes to. "
            "**No priority is set**: how urgent a defect is depends on what it "
            "blocks and who is waiting, and neither is in a stack trace"),
    }
