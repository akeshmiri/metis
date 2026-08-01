"""
MicroRequirement decomposition -- genuinely needs an LLM per the spec's own
framing ("the atomic-behavior split is judgment, not parsing"): splitting a
bundled Requirement (one that fails ISO/IEC/IEEE 29148's "singular"
characteristic, per CONST-047) into atomic MicroRequirements, each
expressing exactly one testable behavior.

Real model calls via metis_mcp/llm_client.py (the `claude` CLI). Each
produced MicroRequirement is re-checked against the real, deterministic
EARS checker (metis_mcp/ears_checker.py) -- the LLM proposes the split,
deterministic code verifies the result is actually well-formed, per §9's
code-vs-LLM principle (never trust the judgment step to also self-certify
its own structural output).
"""
import json
import re
from dataclasses import dataclass

from metis_mcp.ears_checker import check_ears_conformance
from metis_mcp.llm_client import call_llm, LLMCallError

DECOMPOSITION_SYSTEM_PROMPT = (
    "You are a requirements engineer applying ISO/IEC/IEEE 29148's 'singular' "
    "characteristic. Given one Requirement statement that bundles multiple "
    "testable behaviors, split it into atomic MicroRequirements -- each one "
    "must express EXACTLY one testable behavior, and should follow EARS "
    "sentence structure (e.g. 'The <system> shall <response>.' or 'When "
    "<trigger>, the <system> shall <response>.') wherever the original "
    "requirement's structure allows it. Do not add behaviors that aren't in "
    "the original text, and do not drop any. Respond with STRICT JSON only, "
    'no markdown fences, no other text: {"micro_requirements": ["...", "..."]}'
)

_MAX_ATTEMPTS = 2


@dataclass
class MicroRequirement:
    text: str
    ears_conformant: bool
    ears_pattern: str | None


@dataclass
class DecompositionResult:
    original: str
    micro_requirements: list[MicroRequirement]
    cost_usd: float


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    if not m:
        raise LLMCallError(f"Decomposition response contained no JSON object: {text[:300]}")
    return json.loads(m.group(0))


def decompose_requirement(requirement_text: str, model: str = "sonnet") -> DecompositionResult:
    prompt = (
        f'Requirement: "{requirement_text}"\n\n'
        f"Split this into atomic MicroRequirements per the required JSON format."
    )

    last_error = None
    total_cost = 0.0
    for _ in range(_MAX_ATTEMPTS):
        response = call_llm(prompt, model=model, system_prompt=DECOMPOSITION_SYSTEM_PROMPT)
        total_cost += response.cost_usd
        try:
            parsed = _extract_json(response.text)
            texts = parsed["micro_requirements"]
            micro_reqs = []
            for t in texts:
                # Deterministic re-check, per §9 -- the LLM proposes, code verifies.
                ears = check_ears_conformance(t)
                micro_reqs.append(MicroRequirement(
                    text=t, ears_conformant=ears.conformant, ears_pattern=ears.pattern,
                ))
            return DecompositionResult(
                original=requirement_text, micro_requirements=micro_reqs, cost_usd=total_cost,
            )
        except (LLMCallError, KeyError, TypeError) as e:
            last_error = e
    raise LLMCallError(
        f"Decomposition failed to produce parseable JSON after {_MAX_ATTEMPTS} attempts: {last_error}"
    )
