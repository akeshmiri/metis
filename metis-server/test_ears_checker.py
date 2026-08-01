"""
Tests for the EARS conformance checker (REQ-METIS-ONT-04) -- against real
text pulled directly from metis-specification.md §4.3, not synthetic
examples invented to be easy to parse.
"""
from metis_mcp.ears_checker import check_ears_conformance

# Real examples, copied verbatim from metis-specification.md §4.3's table.
REAL_UBIQUITOUS = "The billing service shall reject invoices with a negative amount."
REAL_EVENT_DRIVEN = "When a payment webhook is received, the system shall update order status."
REAL_STATE_DRIVEN = "While an order is in Shipped state, the system shall reject cancellation requests."
REAL_UNWANTED_BEHAVIOR = "If the refund amount exceeds the original charge, then the system shall reject the refund."
REAL_OPTIONAL = "Where multi-currency is enabled, the system shall display the settlement currency."

# A real sentence from this same document (metis-specification.md §7, the
# guardrail layer table's own prose) -- real text, genuinely not EARS-shaped
# (no "shall", no trigger/state/condition clause), used as the "rejects a
# real malformed requirement" case per Phase 8's acceptance bar.
REAL_NON_EARS_TEXT = (
    "Ten layers, defense-in-depth (full rationale in v2 §5; requirements formalized here)."
)


def test_real_ubiquitous_example_conformant():
    r = check_ears_conformance(REAL_UBIQUITOUS)
    assert r.conformant
    assert r.pattern == "Ubiquitous"


def test_real_event_driven_example_conformant():
    r = check_ears_conformance(REAL_EVENT_DRIVEN)
    assert r.conformant
    assert r.pattern == "EventDriven"
    assert r.groups["trigger"] == "a payment webhook is received"


def test_real_state_driven_example_conformant():
    r = check_ears_conformance(REAL_STATE_DRIVEN)
    assert r.conformant
    assert r.pattern == "StateDriven"


def test_real_unwanted_behavior_example_conformant():
    r = check_ears_conformance(REAL_UNWANTED_BEHAVIOR)
    assert r.conformant
    assert r.pattern == "UnwantedBehavior"


def test_real_optional_example_conformant():
    r = check_ears_conformance(REAL_OPTIONAL)
    assert r.conformant
    assert r.pattern == "Optional"


def test_real_non_ears_text_rejected():
    """The specific acceptance bar: rejects real (non-synthetic) malformed
    text, not just a contrived example."""
    r = check_ears_conformance(REAL_NON_EARS_TEXT)
    assert not r.conformant
    assert r.pattern is None


def test_event_driven_not_misclassified_as_ubiquitous():
    """The reason the check order matters: an Event-driven sentence also
    contains '... the system shall ...' as a tail clause -- checking
    Ubiquitous first would wrongly match it."""
    r = check_ears_conformance(REAL_EVENT_DRIVEN)
    assert r.pattern != "Ubiquitous"


if __name__ == "__main__":
    import sys
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
