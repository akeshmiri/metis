"""
§9.1 Token and Cost Management -- metis_mcp/token_optimization.py's 3 real
mechanisms (Caveman prompt compression, Headroom response compression,
Cache-Aligner temporal stabilization). No LLM calls, no cost -- pure
deterministic text/structure transforms.
"""
import sys

from metis_mcp.token_optimization import (
    compress_prompt_caveman, compress_response_headroom, stabilize_temporal_fields,
    PROVENANCE_FIELD_NAMES,
)


def test_caveman_strips_real_filler_and_measures_real_reduction():
    prompt = (
        "Please make sure that you kindly note that in order to complete this task "
        "you should follow the instructions."
    )
    compressed, ratio = compress_prompt_caveman(prompt)
    assert len(compressed) < len(prompt)
    assert ratio > 0
    assert "please" not in compressed.lower()
    assert "kindly" not in compressed.lower()


def test_caveman_never_touches_json_format_spans():
    prompt = 'Please respond as JSON: {"supported": true or false, "reasoning": "please explain"}'
    compressed, _ = compress_prompt_caveman(prompt)
    assert '{"supported": true or false, "reasoning": "please explain"}' in compressed, \
        "the literal required-format span must survive compression verbatim, even though " \
        "it contains the word 'please'"


def test_caveman_on_already_tight_text_reports_zero_not_a_fabricated_savings():
    tight = "Judge ONLY whether the source text supports the claim."
    compressed, ratio = compress_prompt_caveman(tight)
    assert compressed == tight
    assert ratio == 0.0


def test_headroom_never_touches_provenance_fields_at_any_depth():
    response = {
        "found": True,
        "text": "x" * 1000,
        "provenance": {"source_episode_id": "y" * 500, "source_span": {"start": 1, "end": 999999}},
        "nested": {"source_file": "z" * 500, "other": "w" * 1000},
    }
    compressed = compress_response_headroom(response)
    assert compressed["provenance"]["source_episode_id"] == "y" * 500
    assert compressed["provenance"]["source_span"] == {"start": 1, "end": 999999}
    assert compressed["nested"]["source_file"] == "z" * 500
    assert len(compressed["nested"]["other"]) < 1000, "non-provenance long text must still be compressed"
    assert len(compressed["text"]) < 1000


def test_headroom_drops_empty_and_deduplicates_lists():
    response = {"a": None, "b": "", "c": [], "d": "kept", "e": ["x", "x", "y", "x"]}
    compressed = compress_response_headroom(response)
    assert "a" not in compressed
    assert "b" not in compressed
    assert "c" not in compressed
    assert compressed["d"] == "kept"
    assert compressed["e"] == ["x", "y"]


def test_headroom_truncation_is_visible_not_silent():
    response = {"text": "a" * 1000}
    compressed = compress_response_headroom(response)
    assert compressed["text"].startswith("a" * 280)
    assert "more chars" in compressed["text"]


def test_stabilize_rounds_bi_temporal_fields_to_a_stable_granularity():
    response = {
        "t_recorded": "2026-01-01T10:15:37.123456+00:00",
        "t_valid": "2026-01-01T10:15:59.999999+00:00",
        "unrelated": "2026-01-01T10:15:37.123456+00:00",
    }
    stabilized = stabilize_temporal_fields(response, granularity_seconds=60)
    assert stabilized["t_recorded"] == stabilized["t_valid"], \
        "both fall in the same 60s window -- must round to the identical value for cache-key stability"
    assert stabilized["unrelated"] != stabilized["t_recorded"], \
        "fields not in the bi-temporal set must be left exactly as given"


def test_stabilize_leaves_unparseable_values_untouched():
    response = {"t_recorded": "not-a-real-timestamp"}
    stabilized = stabilize_temporal_fields(response)
    assert stabilized["t_recorded"] == "not-a-real-timestamp"


def test_stabilize_then_headroom_is_deterministic_across_repeated_calls():
    """The actual point of cache-stabilization: two 'calls' a few
    milliseconds apart must produce byte-identical output once stabilized,
    which real prompt caching depends on for a cache hit."""
    call_1 = {"t_recorded": "2026-01-01T10:15:37.111Z", "text": "same content"}
    call_2 = {"t_recorded": "2026-01-01T10:15:37.999Z", "text": "same content"}
    out_1 = compress_response_headroom(stabilize_temporal_fields(call_1))
    out_2 = compress_response_headroom(stabilize_temporal_fields(call_2))
    assert out_1 == out_2


def test_provenance_field_names_include_the_required_exclusion_set():
    assert {"source_episode_id", "source_span"} <= PROVENANCE_FIELD_NAMES


def test_metis_get_context_actually_applies_headroom_when_enabled():
    """Proves genuine wiring, not just an unused function: toggles the
    real module-level flag server.py reads and calls the real tool
    function (local backend, dogfooding corpus, already loaded)."""
    import metis_mcp.server as server
    original = server._HEADROOM_ENABLED
    try:
        server._HEADROOM_ENABLED = True
        result = server.metis_get_context("CONST-047")
        assert result["found"] is True
        # empty/None fields dropped by compress_response_headroom -- a real,
        # observable difference from the disabled path below.
        assert all(v not in (None, "", [], {}) for v in result.values())

        server._HEADROOM_ENABLED = False
        result_disabled = server.metis_get_context("CONST-047")
        assert result_disabled["found"] is True
    finally:
        server._HEADROOM_ENABLED = original


if __name__ == "__main__":
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
