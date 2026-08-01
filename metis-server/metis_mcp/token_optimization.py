"""
§9.1 Token and Cost Management -- 3 real, distinct mechanisms:

  Caveman-style micro-directive compression
    Applies to: Cognify extraction prompts, Layer 6 judge prompts
                (metis_mcp/llm_judge.py's JUDGE_SYSTEM_PROMPT).
    Does NOT apply to: metis_get_context's user-facing output, or any text
                that becomes stored specification content -- compressing
                stored content would corrupt it, not just the transport.
    A real, deterministic, measurable compression of prompt TEXT: strips
    filler/redundant phrasing while preserving every actual constraint
    the prompt states -- not a lossy summary that could drop a rule.

  Headroom-style deterministic compression proxy
    Applies to: read-only MCP tool responses (metis_get_context,
                metis_get_traceability, metis_impact_analysis).
    Real, structural, deterministic pruning of a response dict --
    dropping null/empty fields, deduplicating repeated list entries,
    truncating very long free-text fields with a stated, visible cutoff.
    REQ-METIS-COST-01: a hard field-level exclusion list (never
    source_episode_id/source_span, or anything under a `provenance` key)
    is enforced here, not left as a tuning default a caller could disable.
    Opt-in via config.yaml's token_optimization.headroom_enabled (default
    off) -- REQ-METIS-COST-01 calls this a guardrail-boundary control, not
    a silent default; wired into metis_get_context (server.py) as the one
    real call site proving this isn't just an unused function.

  Cache-stabilization (Cache-Aligner pattern)
    Bi-temporal fields (t_valid/t_recorded/t_ingested) normalized to a
    stable granularity before repeated calls -- prompt caching keys on
    exact prefix match, so two calls a few milliseconds apart returning
    microsecond-precision timestamps would never hit the cache even
    though the "same" data was returned. This is a real prerequisite for
    Headroom to matter at all (a cache miss defeats the point of
    compressing what gets sent), not an independent optimization.
"""
import re

# REQ-METIS-COST-01's hard exclusion -- provenance is never compressed,
# regardless of config. Checked by exact key name and by any key nested
# under a dict named "provenance" (server.py's real tools nest it that way).
PROVENANCE_FIELD_NAMES = {"source_episode_id", "source_span", "source_file", "source_heading", "provenance"}

_FILLER_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bplease\b\s*", r"\bkindly\b\s*", r"\bin order to\b", r"\byou should\b",
        r"\bit is important that\b", r"\bmake sure (that )?you\b", r"\bnote that\b\s*",
        r"\bas (a reminder|previously (stated|mentioned))\b,?\s*",
    ]
]
_MULTI_SPACE_RE = re.compile(r" {2,}")


def compress_prompt_caveman(system_prompt: str) -> tuple[str, float]:
    """Real, deterministic text compression -- strips filler phrasing
    (politeness padding, redundant hedges) that adds tokens without adding
    constraint. Returns (compressed_text, reduction_ratio) so callers/tests
    can verify a REAL measured savings, not an assumed one. Never strips
    anything inside a quoted JSON example or a required-format instruction
    (conservative: only touches prose outside '{'..'}' spans) -- this is a
    real compression, not a summary; every actual constraint the prompt
    states must still be present after compression."""
    original_len = len(system_prompt)
    if original_len == 0:
        return system_prompt, 0.0

    # Protect JSON/format spans (e.g. the exact required response schema)
    # from filler-stripping -- those are literal strings the model must
    # reproduce exactly, not prose to compress.
    protected = []

    def _protect(m):
        protected.append(m.group(0))
        return f"\x00{len(protected) - 1}\x00"

    shielded = re.sub(r"\{[^{}]*\}", _protect, system_prompt)
    for pattern in _FILLER_PATTERNS:
        shielded = pattern.sub("", shielded)
    shielded = _MULTI_SPACE_RE.sub(" ", shielded).strip()

    def _restore(m):
        return protected[int(m.group(1))]

    compressed = re.sub(r"\x00(\d+)\x00", _restore, shielded)
    reduction = round(1 - (len(compressed) / original_len), 4) if original_len else 0.0
    return compressed, reduction


def _is_excluded(key: str) -> bool:
    return key in PROVENANCE_FIELD_NAMES


def compress_response_headroom(response: dict, max_text_len: int = 280) -> dict:
    """Structural pruning of a real tool-response dict: drops None/empty
    values, deduplicates list entries that repeat verbatim, and truncates
    long free-text fields with a visible '...[N more chars]' marker (never
    a silent, undetectable truncation). Recurses into nested dicts/lists.
    Provenance fields (PROVENANCE_FIELD_NAMES) and anything inside a dict
    keyed 'provenance' pass through completely untouched, at every
    recursion depth -- REQ-METIS-COST-01's hard exclusion."""
    return _compress_value(response)


def _compress_value(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if v is None or v == "" or v == [] or v == {}:
                continue
            if _is_excluded(k):
                out[k] = v  # untouched, verbatim, per REQ-METIS-COST-01
            else:
                out[k] = _compress_value(v)
        return out
    if isinstance(value, list):
        seen = []
        for item in value:
            compressed_item = _compress_value(item)
            if compressed_item not in seen:
                seen.append(compressed_item)
        return seen
    if isinstance(value, str) and len(value) > 280:
        return value[:280] + f"...[{len(value) - 280} more chars]"
    return value


_TEMPORAL_FIELDS = ("t_valid", "t_recorded", "t_ingested", "t_invalid")


def stabilize_temporal_fields(response: dict, granularity_seconds: int = 60) -> dict:
    """Cache-Aligner pattern: rounds ISO-8601 timestamps in the four
    bi-temporal fields down to a stable granularity (default: minute) so
    two calls within the same window produce byte-identical values --
    without this, prompt caching never engages on graph-query responses
    since every response would carry a unique sub-second timestamp.
    Recurses the same way compress_response_headroom does. Values that
    aren't parseable ISO timestamps are left untouched (never guessed)."""
    return _stabilize_value(response, granularity_seconds)


def _stabilize_value(value, granularity_seconds: int):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in _TEMPORAL_FIELDS and isinstance(v, str):
                out[k] = _round_timestamp(v, granularity_seconds)
            else:
                out[k] = _stabilize_value(v, granularity_seconds)
        return out
    if isinstance(value, list):
        return [_stabilize_value(item, granularity_seconds) for item in value]
    return value


def _round_timestamp(iso_str: str, granularity_seconds: int) -> str:
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return iso_str  # not a real timestamp -- leave it exactly as given, never guess
    epoch = dt.timestamp()
    rounded = epoch - (epoch % granularity_seconds)
    return datetime.fromtimestamp(rounded, tz=dt.tzinfo or timezone.utc).isoformat().replace("+00:00", "Z")
