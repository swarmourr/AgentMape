from __future__ import annotations

"""
ObservatorAgent — evidence-gathering subagent.

Runs a bounded ReAct loop using the same tool set as DiagnosisAgent
but with ONE goal: collect and summarise raw evidence.

It does NOT classify the failure — that is the Classifier's job.
Output: ObservationReport — structured findings from available data sources.
"""

import json
from typing import Any, Literal, get_args

import structlog
from pydantic import BaseModel, Field

from app.agents.tools import TOOL_DESCRIPTIONS, TOOL_MAP
from app.utils.llm.provider import LLMProvider
from app.utils.models.context import FailureContext
from app.utils.models.evidence import RawEvidence

log = structlog.get_logger(__name__)

MAX_STEPS = 5

ObservatorActionType = Literal[
    "parse_failure_summary",
    "get_stderr",
    "get_kickstart_data",
    "get_resource_requests",
    "get_condor_history",
    "get_event_log",
    "get_dagman_log",
    "get_workflow_log",
    "get_transformation_script",
    "get_input_validation",
    "report",   # replaces "conclude" — output facts, no classification
]


class ObservatorThoughtAction(BaseModel):
    """One step of the Observator ReAct loop."""
    thought: str = Field(description="What you found so far and what you need next")
    action: ObservatorActionType = Field(description="Tool to call, or 'report' when evidence is sufficient")
    # Populated only when action == "report"
    key_findings:            list[str]   = Field(default_factory=list, description="Bullet-point factual findings")
    stderr_signals:          list[str]   = Field(default_factory=list, description="Important stderr lines verbatim")
    resource_pressure:       str | None  = Field(default=None,         description="'memory' | 'runtime' | 'disk' | None")
    infrastructure_signals:  list[str]   = Field(default_factory=list, description="Shadow exceptions, evictions, holds")
    data_signals:            list[str]   = Field(default_factory=list, description="Missing files, staging errors, format errors")
    script_signals:          list[str]   = Field(default_factory=list, description="Import errors, missing modules, command not found")


class ObservationReport(BaseModel):
    """Structured evidence summary produced by ObservatorAgent."""
    key_findings:           list[str]  = Field(default_factory=list)
    stderr_signals:         list[str]  = Field(default_factory=list)
    resource_pressure:      str | None = None
    infrastructure_signals: list[str]  = Field(default_factory=list)
    data_signals:           list[str]  = Field(default_factory=list)
    script_signals:         list[str]  = Field(default_factory=list)
    sources_checked:        list[str]  = Field(default_factory=list)
    # Raw numeric context passed through for Classifier
    exit_code:              int | None   = None
    wall_time_s:            float | None = None
    peak_memory_mb:         float | None = None


_SYSTEM_PROMPT = f"""You are an evidence-gathering subagent for Pegasus WMS / HTCondor job failures.

Your ONLY responsibility is to collect raw evidence and report factual observations.
Do NOT classify the failure type. Do NOT suggest fixes.

Tools available:
{TOOL_DESCRIPTIONS}

When you have sufficient evidence call action='report' and populate:
  key_findings            — bullet-point factual findings (what you saw)
  stderr_signals          — verbatim important stderr lines
  resource_pressure       — 'memory' | 'runtime' | 'disk' | null
  infrastructure_signals  — shadow exceptions, evictions, holds
  data_signals            — missing scientific files, staging errors, format errors
  script_signals          — ImportError, ModuleNotFoundError, command not found lines

Rules:
  • Never call the same tool twice
  • Start with parse_failure_summary if pegasus_analyzer is available, else get_stderr
  • Stop as soon as you have enough facts to describe what happened — do not over-gather
  • Report facts only — no failure_type, no root cause guesses, no fix suggestions
  • Do NOT mention infrastructure files (*.lof, *.meta, pegasus-worker-*) as missing
"""


class ObservatorAgent:
    """
    Gathers evidence from Pegasus job files via a bounded ReAct loop.
    Outputs an ObservationReport — pure facts, no classification.
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def run(self, ctx: FailureContext, evidence: RawEvidence) -> ObservationReport:
        messages: list[dict[str, Any]] = [
            {"role": "system",  "content": _SYSTEM_PROMPT},
            {"role": "user",    "content": self._seed(ctx, evidence)},
        ]
        used_tools: set[str] = set()

        for step_num in range(MAX_STEPS):
            step: ObservatorThoughtAction = await self._llm.complete(  # type: ignore[assignment]
                messages=messages,
                response_model=ObservatorThoughtAction,
                temperature=0.0,
            )
            log.info(
                "observator_step",
                step=step_num + 1,
                action=step.action,
                incident_id=str(ctx.incident_id),
            )
            messages.append({
                "role": "assistant",
                "content": json.dumps({"thought": step.thought, "action": step.action}),
            })

            if step.action == "report":
                return self._build_report(step, used_tools, ctx)

            if step.action in used_tools:
                messages.append({
                    "role": "user",
                    "content": f"SYSTEM: You already called '{step.action}'. Call 'report' now with what you have.",
                })
                continue

            fn = TOOL_MAP.get(step.action)
            if fn:
                obs = fn(evidence)
                observation = json.dumps(obs, default=str, indent=2) if isinstance(obs, dict) else str(obs)
                used_tools.add(step.action)
            else:
                observation = f"Unknown tool '{step.action}'. Valid tools: {list(TOOL_MAP)}"

            messages.append({
                "role": "user",
                "content": f"OBSERVATION from {step.action}:\n{observation}",
            })

        # Force a report after max steps
        messages.append({
            "role": "user",
            "content": "SYSTEM: Maximum steps reached. Call 'report' now with everything you have.",
        })
        final: ObservatorThoughtAction = await self._llm.complete(  # type: ignore[assignment]
            messages=messages,
            response_model=ObservatorThoughtAction,
            temperature=0.0,
        )
        log.warning("observator_max_steps", incident_id=str(ctx.incident_id))
        return self._build_report(final, used_tools, ctx)

    def _build_report(
        self,
        step: ObservatorThoughtAction,
        used_tools: set[str],
        ctx: FailureContext,
    ) -> ObservationReport:
        return ObservationReport(
            key_findings=step.key_findings,
            stderr_signals=step.stderr_signals,
            resource_pressure=step.resource_pressure,
            infrastructure_signals=step.infrastructure_signals,
            data_signals=step.data_signals,
            script_signals=step.script_signals,
            sources_checked=sorted(used_tools),
            exit_code=ctx.exit_code,
            peak_memory_mb=ctx.measured_resources.peak_memory_mb,
            wall_time_s=float(ctx.measured_resources.runtime_seconds) if ctx.measured_resources.runtime_seconds else None,
        )

    def _seed(self, ctx: FailureContext, evidence: RawEvidence) -> str:
        return f"""== Job to observe ==
job_id:          {ctx.job_id}
exit_code:       {ctx.exit_code}
signal:          {ctx.termination_signal}
scheduler_state: {ctx.scheduler_state}
site:            {ctx.execution_site}
transformation:  {ctx.transformation}
memory_req_mb:   {ctx.requested_resources.memory_mb}
runtime_req_s:   {ctx.requested_resources.runtime_seconds}

Available data sources: {', '.join(evidence.available_sources) or 'none'}

Gather evidence now. Start with parse_failure_summary or get_stderr."""
