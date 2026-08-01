"""
REQ-METIS-COST-08: "Any action Métis initiates that would trigger a
materially larger-than-typical batch of LLM calls ... shows the proposed
plan and stage count up front and requires explicit confirmation before
starting -- mirroring Atlas's exact 'Confirm to proceed? [yes/no]' pattern
shown before a multi-stage workflow begins, not just between stages once
it's already running."

REQ-METIS-COST-09 ("model choice per stage is configuration, not code")
is already satisfied elsewhere (config_manager.py's get_model_config()) --
not re-addressed here.

`TYPICAL_BATCH_SIZE` is a real, disclosed, chosen threshold -- the spec
doesn't pin an exact number ("materially larger than typical" is
qualitative), so this names one rather than leaving the gate unable to
ever actually fire. `ESTIMATED_COST_PER_CALL_USD` is grounded in this
project's own real, observed per-call costs (llm_client.py's docstring:
"~$0.04-0.09" for a trivial call; guardrails/calibration.py's real 229-case
run) -- an estimate, disclosed as one, not a promise.
"""
from dataclasses import dataclass

TYPICAL_BATCH_SIZE = 20
ESTIMATED_COST_PER_CALL_USD = 0.05


@dataclass
class BatchPlan:
    item_count: int
    stage_count: int
    estimated_cost_usd: float
    requires_confirmation: bool
    prompt: str


class BatchNotConfirmedError(Exception):
    """Raised, never silently swallowed into 'proceed anyway' -- a caller
    hitting this must make an explicit, deliberate choice (pass
    confirmed=True) to continue, the same real gate a human would hit
    typing 'yes' at Atlas's own confirmation prompt."""
    pass


def plan_batch(item_count: int, stage_count: int = 1,
               typical_batch_size: int = TYPICAL_BATCH_SIZE,
               cost_per_item_usd: float = ESTIMATED_COST_PER_CALL_USD) -> BatchPlan:
    requires_confirmation = item_count > typical_batch_size
    estimated_cost = round(item_count * cost_per_item_usd, 2)
    prompt = (
        f"This action will run {item_count} real model call(s) across {stage_count} "
        f"stage(s), estimated cost ~${estimated_cost:.2f} (a real, disclosed estimate, "
        f"not a guarantee). This is materially larger than the typical batch size "
        f"({typical_batch_size}). Confirm to proceed? [yes/no]"
        if requires_confirmation else ""
    )
    return BatchPlan(
        item_count=item_count, stage_count=stage_count, estimated_cost_usd=estimated_cost,
        requires_confirmation=requires_confirmation, prompt=prompt,
    )


def gate_batch(item_count: int, confirmed: bool, stage_count: int = 1, **kwargs) -> BatchPlan:
    """The actual gate. A batch at or below the typical size proceeds
    without ceremony (this mirrors Atlas's own real distinction -- routine
    work doesn't get a confirmation prompt, only materially-larger work
    does). A batch above threshold with confirmed=False raises
    BatchNotConfirmedError carrying the real plan/prompt -- the caller
    (a skill's Stage Confirmation Protocol step, a CLI runner, an MCP tool
    handler) is responsible for actually surfacing that prompt to a human
    and re-calling with confirmed=True once they say yes; this function
    doesn't read stdin itself, since it's a library call reachable from
    contexts (MCP tool calls, test harnesses) that don't have a real
    interactive console."""
    plan = plan_batch(item_count, stage_count, **kwargs)
    if plan.requires_confirmation and not confirmed:
        raise BatchNotConfirmedError(plan.prompt)
    return plan
