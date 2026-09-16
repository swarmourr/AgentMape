from __future__ import annotations

"""
ClassifierAgent — failure classification subagent.

Receives an ObservationReport + FailureContext.
Strategy:
  1. Try deterministic rules (app.rules.classifier) — fast, no LLM cost
  2. If rules fire with confidence >= 0.85 → return immediately
  3. Otherwise → single LLM call using the observation report as context

Output: Diagnosis with failure_type, confidence, explanation.
"""

from typing import Any

import structlog
from pydantic import BaseModel, Field

from app.pipeline.observator import ObservationReport
from app.llm.provider import LLMProvider
from app.models.context import FailureContext
from app.models.diagnosis import FAILURE_FIX_CATEGORY, Diagnosis, FailureType
from app.rules.classifier import classify

log = structlog.get_logger(__name__)

RULE_CONFIDENCE_THRESHOLD = 0.85


class ClassificationOutput(BaseModel):
    failure_type:         FailureType
    confidence:           float = Field(ge=0.0, le=1.0)
    explanation:          str
    requires_human_review: bool = False
    missing_evidence:     list[str] = Field(default_factory=list)


_SYSTEM_PROMPT = """You are a failure classifier for Pegasus WMS / HTCondor jobs.

You receive a structured observation report produced by an evidence-gathering agent.
Your job: classify the failure type. Do NOT suggest fixes.

Failure types:
  OUT_OF_MEMORY          — OOM kill, exit 137, peak memory near or over limit
  DISK_EXCEEDED          — "No space left on device"
  WALLTIME_EXCEEDED      — runtime exceeded request, exit 140
  TRANSIENT_INFRASTRUCTURE — shadow exception, eviction, network blip
  SCHEDULER_ADMISSION    — job held, admit failure
  MISSING_INPUT          — scientific input file not found (not infrastructure files)
  DATA_MISMATCH          — wrong format, mismatched dimensions, corrupt input
  SCRIPT_ERROR           — ImportError, ModuleNotFoundError, command not found, wrong env
  APPLICATION_ERROR      — application crash unrelated to resources/data/env
  LOGIC_VALIDATION       — scientific logic issue requiring human review
  UNKNOWN                — not enough evidence to classify

PegasusLite exit codes:
  71 = user application exited 1 → focus on WHY the app failed
  72 = PegasusLite setup failure
  73 = data staging failure
  74 = output transfer failure

Rules:
  • exit_code=137 or signal=9 + memory pressure → OUT_OF_MEMORY
  • "No space left" in stderr_signals → DISK_EXCEEDED
  • resource_pressure='runtime' → WALLTIME_EXCEEDED
  • infrastructure_signals (shadow exception, eviction) → TRANSIENT_INFRASTRUCTURE
  • data_signals with scientific files missing → MISSING_INPUT
  • data_signals with format/dimension errors → DATA_MISMATCH
  • script_signals present → SCRIPT_ERROR
  • Traceback with no resource/data/env pressure → APPLICATION_ERROR
  • Do NOT classify *.lof, *.meta, pegasus-worker-*.tar.gz as MISSING_INPUT

Set confidence 0.0–1.0. Use missing_evidence for anything that would increase confidence.
"""


class ClassifierAgent:
    """
    Classifies a Pegasus job failure from an ObservationReport.

    Uses deterministic rules first (zero LLM cost), falls back to a
    single structured LLM call when rules don't fire confidently.
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def run(self, ctx: FailureContext, observations: ObservationReport) -> Diagnosis:
        # ── 1. Deterministic rules ────────────────────────────────────────────
        rule_result = classify(ctx)
        if rule_result is not None and rule_result.confidence >= RULE_CONFIDENCE_THRESHOLD:
            log.info(
                "classifier_rule_hit",
                failure_type=rule_result.failure_type,
                confidence=rule_result.confidence,
                incident_id=str(ctx.incident_id),
            )
            return rule_result

        # ── 2. LLM classification ─────────────────────────────────────────────
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": self._build_prompt(ctx, observations, rule_result)},
        ]
        output: ClassificationOutput = await self._llm.complete(  # type: ignore[assignment]
            messages=messages,
            response_model=ClassificationOutput,
            temperature=0.0,
        )
        log.info(
            "classifier_llm",
            failure_type=output.failure_type,
            confidence=output.confidence,
            incident_id=str(ctx.incident_id),
        )
        return Diagnosis(
            failure_type=output.failure_type,
            confidence=output.confidence,
            explanation=output.explanation,
            requires_human_review=output.requires_human_review,
            missing_evidence=output.missing_evidence,
            recommended_fix_category=FAILURE_FIX_CATEGORY.get(output.failure_type),
            evidence_ids=[],
            source="LLM",
            rule_version=None,
        )

    def _build_prompt(
        self,
        ctx: FailureContext,
        obs: ObservationReport,
        rule_hint: Diagnosis | None,
    ) -> str:
        lines = [
            "## Job context",
            f"exit_code:           {ctx.exit_code}",
            f"termination_signal:  {ctx.termination_signal}",
            f"execution_site:      {ctx.execution_site}",
            f"transformation:      {ctx.transformation}",
            f"memory_requested_mb: {ctx.requested_resources.memory_mb}",
            f"memory_peak_mb:      {ctx.measured_resources.peak_memory_mb}",
            f"runtime_requested_s: {ctx.requested_resources.runtime_seconds}",
            f"runtime_actual_s:    {ctx.measured_resources.runtime_seconds}",
            "",
            "## Observation report",
        ]

        if obs.key_findings:
            lines.append("key_findings:")
            for f in obs.key_findings:
                lines.append(f"  - {f}")

        if obs.stderr_signals:
            lines.append("stderr_signals:")
            for s in obs.stderr_signals:
                lines.append(f"  {s}")

        if obs.resource_pressure:
            lines.append(f"resource_pressure: {obs.resource_pressure}")

        if obs.infrastructure_signals:
            lines.append("infrastructure_signals:")
            for s in obs.infrastructure_signals:
                lines.append(f"  {s}")

        if obs.data_signals:
            lines.append("data_signals:")
            for s in obs.data_signals:
                lines.append(f"  {s}")

        if obs.script_signals:
            lines.append("script_signals:")
            for s in obs.script_signals:
                lines.append(f"  {s}")

        lines.append(f"sources_checked: {', '.join(obs.sources_checked) or 'none'}")

        if rule_hint:
            lines += [
                "",
                f"Rule classifier hint: {rule_hint.failure_type} "
                f"(confidence={rule_hint.confidence:.2f}) — below threshold, needs LLM confirmation",
            ]

        lines += ["", "Classify the failure type now."]
        return "\n".join(lines)
