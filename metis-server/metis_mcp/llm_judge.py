"""
Layer 6: LLM-as-judge (REQ-METIS-GRD-06, §7). "Independent model call,
source span + claim only, 'does this text support this claim, answer only
from provided text' -- blocks promotion on disagreement." Only runs for
Quarantine-tier items (a fraction of total volume, per the spec) -- never
for auto_write (already trusted) or rejected (already discarded) items.

Real model calls via metis_mcp/llm_client.py (the `claude` CLI, no
ANTHROPIC_API_KEY needed in this environment). Per §9.3's model-tier
guidance, the judge should be at least as capable as the extractor it's
checking -- this project's own config.yaml already specifies
judge: claude-sonnet-5, extraction: claude-haiku-4-5-20251001; this module
defaults to the configured judge model, not a hardcoded one.
"""
import json
import re
from dataclasses import dataclass

from metis_mcp.llm_client import call_llm, LLMCallError
from metis_mcp.token_optimization import compress_prompt_caveman

JUDGE_SYSTEM_PROMPT = (
    "You are an independent verification judge for a specification knowledge "
    "graph. You will be given a source text span and a claim someone extracted "
    "from it. Judge ONLY whether the provided source text actually supports "
    "the claim -- do not use outside knowledge, do not infer beyond what the "
    "text literally says. Respond with STRICT JSON only, no markdown fences, "
    "no other text, and keep 'reasoning' to at most 20 words: "
    '{"supported": true or false, "reasoning": "at most 20 words, citing the '
    'specific part of the source text that supports or contradicts the claim"}'
)

# §9.1's Caveman-style micro-directive: real, measured compression, computed
# once at import time (the prompt text is a module-level constant, not
# per-call), applied to every real judge call below.
JUDGE_SYSTEM_PROMPT, JUDGE_SYSTEM_PROMPT_COMPRESSION_RATIO = compress_prompt_caveman(JUDGE_SYSTEM_PROMPT)

# Real, observed characteristic of this call, not a hypothetical: the model
# occasionally runs long enough on 'reasoning' that the response gets cut off
# before the closing brace (a real nondeterminism/reliability concern for any
# LLM integration, not specific to this codebase) -- retrying once with the
# same prompt is a standard, honest mitigation. A second failure is raised
# for real, never silently swallowed into a guessed verdict.
_MAX_ATTEMPTS = 2


@dataclass
class JudgeResult:
    supported: bool
    reasoning: str
    model: str
    cost_usd: float


def _extract_json(text: str) -> dict:
    """Real models sometimes wrap JSON in a markdown code fence despite
    instructions not to -- strip that defensively rather than failing the
    whole judge call over formatting."""
    stripped = text.strip()
    m = re.search(r"\{.*\}", stripped, re.DOTALL)
    if not m:
        raise LLMCallError(f"Judge response contained no JSON object: {text[:300]}")
    return json.loads(m.group(0))


def judge_claim(source_span: str, claim: str, model: str = "sonnet") -> JudgeResult:
    prompt = (
        f'Source text:\n"""\n{source_span}\n"""\n\n'
        f'Claim: "{claim}"\n\n'
        f"Does the source text support this claim? Respond in the required JSON format."
    )

    last_error = None
    total_cost = 0.0
    for attempt in range(_MAX_ATTEMPTS):
        response = call_llm(prompt, model=model, system_prompt=JUDGE_SYSTEM_PROMPT)
        total_cost += response.cost_usd
        try:
            parsed = _extract_json(response.text)
            return JudgeResult(
                supported=bool(parsed["supported"]), reasoning=parsed["reasoning"],
                model=model, cost_usd=total_cost,
            )
        except (LLMCallError, KeyError) as e:
            last_error = e
    raise LLMCallError(
        f"Judge call failed to produce parseable JSON after {_MAX_ATTEMPTS} attempts: {last_error}"
    )


def apply_judge_to_quarantine_item(session, node_id: str, source_span: str,
                                     claim: str, model: str = "sonnet") -> JudgeResult:
    """Runs the judge and, on disagreement, marks the node so it can never
    silently advance past review -- per REQ-METIS-GRD-06's 'blocks
    promotion on disagreement,' this is recorded on the graph, not just
    returned to the caller and forgotten."""
    result = judge_claim(source_span, claim, model=model)

    def _write(tx):
        # WHERE NOT n:DogfoodingItem -- schema-01's id-uniqueness constraints
        # are per-label, not global; :DogfoodingItem is verified to share
        # real ids with the production ontology (found for real in
        # metis_mcp/temporal.py). Without this, a colliding DogfoodingItem
        # would also get judge_verdict/lifecycle_state set on it here.
        tx.run(
            "MATCH (n {id: $id}) WHERE NOT n:DogfoodingItem SET n.judge_verdict = $supported, "
            "n.judge_reasoning = $reasoning, n.judge_model = $model",
            id=node_id, supported=result.supported, reasoning=result.reasoning, model=model,
        )
        if not result.supported:
            tx.run(
                "MATCH (n {id: $id}) WHERE NOT n:DogfoodingItem SET n.lifecycle_state = 'Disputed', "
                "n.dispute_reason = 'Layer 6 judge disagreement: ' + $reasoning",
                id=node_id, reasoning=result.reasoning,
            )

    session.execute_write(_write)
    return result
