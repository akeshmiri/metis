"""
Tests for the classification gate -- each test is written against a specific
CONST-051/052/053 requirement, not generic code coverage.
"""
from metis_mcp.classification_gate import ClassificationGate, Classification, GateDecision


def test_const052_unclassified_repo_fails_closed():
    """An unclassified repository must default to Confidential, not Public/Internal."""
    gate = ClassificationGate(zdr_confirmed=False)
    result = gate.check("some-new-repo-nobody-classified-yet")
    assert result.effective_classification == Classification.CONFIDENTIAL
    assert not result.allowed
    assert result.decision == GateDecision.BLOCK_NEEDS_ZDR


def test_const051_confidential_blocked_without_zdr():
    """Confidential content is blocked at the gate, not merely flagged, without ZDR."""
    gate = ClassificationGate(zdr_confirmed=False)
    gate.set_classification("payments-service", Classification.CONFIDENTIAL)
    result = gate.check("payments-service")
    assert not result.allowed
    assert result.decision == GateDecision.BLOCK_NEEDS_ZDR


def test_const051_confidential_allowed_with_zdr():
    """Once ZDR is confirmed, Confidential content is permitted to proceed."""
    gate = ClassificationGate(zdr_confirmed=True)
    gate.set_classification("payments-service", Classification.CONFIDENTIAL)
    result = gate.check("payments-service")
    assert result.allowed
    assert result.decision == GateDecision.ALLOW


def test_public_internal_never_needs_zdr():
    """Public/Internal content proceeds regardless of ZDR status."""
    gate = ClassificationGate(zdr_confirmed=False)
    gate.set_classification("public-docs-site", Classification.PUBLIC_INTERNAL)
    result = gate.check("public-docs-site")
    assert result.allowed


def test_restricted_never_allowed_even_with_zdr():
    """Restricted content NEVER reaches an LLM call, even if ZDR is confirmed --
    this is a stronger rule than Confidential's, and ZDR must not accidentally
    relax it."""
    gate = ClassificationGate(zdr_confirmed=True)
    gate.set_classification("credentials-vault-repo", Classification.RESTRICTED)
    result = gate.check("credentials-vault-repo")
    assert not result.allowed
    assert result.decision == GateDecision.BLOCK_RESTRICTED


def test_const053_gate_defaults_to_unconfirmed():
    """The gate itself must default to zdr_confirmed=False if not explicitly passed --
    there must be no code path where ZDR is silently assumed true."""
    gate = ClassificationGate()  # no argument passed
    assert gate.zdr_confirmed is False
    gate.set_classification("any-repo", Classification.CONFIDENTIAL)
    assert not gate.check("any-repo").allowed


def test_cannot_set_unclassified_directly():
    """UNCLASSIFIED is the fail-closed default state, not a settable tier --
    calling code must not be able to explicitly assign it as if it were a
    real, deliberate classification choice."""
    gate = ClassificationGate()
    try:
        gate.set_classification("x", Classification.UNCLASSIFIED)
        assert False, "should have raised"
    except ValueError:
        pass


def test_from_config_integration_with_real_project_file():
    """The actual integration point: ClassificationGate.from_config() against
    this repo's own real .metis/config.yaml, not a mock -- proves the "no
    configuration in code" directive actually holds end to end."""
    from metis_mcp.config_manager import ConfigManager
    cm = ConfigManager()  # resolves this project's real .metis/config.yaml
    gate = ClassificationGate.from_config(cm)
    assert gate.zdr_confirmed is False  # this project's real, current decision
    result = gate.check("metis-self")  # explicitly classified public_internal in the real file
    assert result.allowed
    assert result.effective_classification == Classification.PUBLIC_INTERNAL


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
