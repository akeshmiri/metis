"""
Real LLM client for the pieces of this pipeline that genuinely need model
judgment (Layer 6 LLM-as-judge, MicroRequirement decomposition) — per §9's
code-vs-LLM allocation, these are the ~4 of 14 pipeline steps that are
irreducibly judgment-based, not deterministic.

No ANTHROPIC_API_KEY is available in this environment. What IS available:
the `claude` CLI (Claude Code) is installed and already authenticated
(independent of a raw API key -- likely OAuth/subscription-based). This
module shells out to it with `--print --model <model> --system-prompt
<...> --output-format json`, which is a REAL, automatable call to a real
Anthropic model -- not a canned/fake response. `--output-format json`
returns real cost/token accounting (`total_cost_usd`, `usage`), which is
exactly what `schema/metis-graph-03-single-db-consolidation.cypher`'s
Episode cost-tracking properties (`extraction_cost_usd`, etc.) are for.

Real cost is genuinely incurred per call (a trivial test call during
development cost ~$0.04-0.09) -- callers of this module should be
deliberate about call volume, not call it in a tight loop without reason.
"""
import json
import subprocess
from dataclasses import dataclass


class LLMCallError(Exception):
    pass


@dataclass
class LLMResponse:
    text: str
    model: str
    cost_usd: float
    input_tokens: int
    output_tokens: int


def call_llm(prompt: str, model: str, system_prompt: str, timeout: int = 60) -> LLMResponse:
    """Real subprocess call to the `claude` CLI. Raises LLMCallError on any
    failure (missing binary, non-zero exit, malformed output) -- callers
    must not treat a failed call as an empty/default judgment; that would
    silently substitute a guess for a real answer, the exact thing this
    project's Forbidden Substitutions rule prohibits."""
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", model,
             "--system-prompt", system_prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as e:
        raise LLMCallError(f"'claude' CLI not found: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise LLMCallError(f"claude CLI call timed out after {timeout}s") from e

    if proc.returncode != 0:
        raise LLMCallError(f"claude CLI exited {proc.returncode}: {proc.stderr.strip()}")

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise LLMCallError(f"claude CLI returned non-JSON output: {proc.stdout[:500]}") from e

    if payload.get("is_error"):
        raise LLMCallError(f"claude CLI reported an error: {payload}")

    usage = payload.get("usage", {})
    return LLMResponse(
        text=payload["result"],
        model=model,
        cost_usd=payload.get("total_cost_usd", 0.0),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )
