from __future__ import annotations

"""
RemediationOrchestrator — multi-subagent coordinator.

Pipeline (per job):
  ① Clone cache check     — skip if same failure pattern already processed
  ② Observator            — gathers raw evidence via ReAct tool loop
  ③ Classifier            — determines failure_type (rules first, LLM fallback)
  ④ FixPlanningAgent      — proposes remediation action
  ⑤ PolicyEngine          — validates safety: AUTO / ASK / STOP / ESCALATE

Each subagent has one responsibility. The orchestrator owns sequencing,
clone deduplication, and result assembly.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from app.agents.classifier import ClassifierAgent
from app.agents.fix_planning import FixPlanningAgent
from app.agents.observator import ObservationReport, ObservatorAgent
from app.llm.provider import LLMProvider
from app.models.context import FailureContext
from app.models.diagnosis import Diagnosis
from app.models.evidence import RawEvidence
from app.models.fixes import FixProposal
from app.policies.engine import PolicyEngine
from app.policies.loader import load_policy

log = structlog.get_logger(__name__)


@dataclass
class OrchestratorResult:
    """Full result of one orchestrator run."""
    # ① Observations
    observations:          ObservationReport
    # ② Classification
    diagnosis:             Diagnosis
    # ③ Fix proposal
    fix_proposal:          FixProposal
    # ④ Policy decision
    policy_decision:       str            # AUTO | ASK | STOP | ESCALATE
    policy_reason:         str
    policy_checks_passed:  list[str] = field(default_factory=list)
    policy_checks_failed:  list[str] = field(default_factory=list)
    # Clone metadata
    cloned_from: str | None = None        # group_key if result was reused


class RemediationOrchestrator:
    """
    Orchestrates Observator → Classifier → FixPlanner → PolicyEngine.

    Clone cache:
      Keyed on a group_key (e.g. executable + failure_cat + exit_code).
      When a key is seen again the pipeline is skipped and the cached
      result is returned with cloned_from set — one LLM session per
      unique failure pattern, regardless of how many identical jobs failed.

    Instantiate once per workflow inspection session so the clone cache
    persists across all jobs in the run.
    """

    def __init__(
        self,
        llm: LLMProvider,
        policy_file: str = "policies/remediation.yaml",
        confidence_threshold: float = 0.80,
    ) -> None:
        self._observator    = ObservatorAgent(llm)
        self._classifier    = ClassifierAgent(llm)
        self._fix_planner   = FixPlanningAgent(llm)
        policy_cfg          = load_policy(policy_file)
        self._policy        = PolicyEngine(policy_cfg, confidence_threshold)
        self._clone_cache: dict[str, OrchestratorResult] = {}

    async def run(
        self,
        ctx: FailureContext,
        evidence: RawEvidence,
        group_key: str | None = None,
    ) -> OrchestratorResult:
        # ── ① Clone check ─────────────────────────────────────────────────────
        if group_key and group_key in self._clone_cache:
            cached = self._clone_cache[group_key]
            log.info("orchestrator_clone_hit", group_key=group_key, incident_id=str(ctx.incident_id))
            return OrchestratorResult(
                observations=cached.observations,
                diagnosis=cached.diagnosis,
                fix_proposal=cached.fix_proposal,
                policy_decision=cached.policy_decision,
                policy_reason=cached.policy_reason,
                policy_checks_passed=cached.policy_checks_passed,
                policy_checks_failed=cached.policy_checks_failed,
                cloned_from=group_key,
            )

        log.info("orchestrator_start", incident_id=str(ctx.incident_id), group_key=group_key)

        # ── ② Observator ──────────────────────────────────────────────────────
        observations = await self._observator.run(ctx, evidence)
        log.info(
            "orchestrator_observed",
            sources=observations.sources_checked,
            findings=len(observations.key_findings),
            incident_id=str(ctx.incident_id),
        )

        # ── ③ Classifier ──────────────────────────────────────────────────────
        diagnosis = await self._classifier.run(ctx, observations)
        log.info(
            "orchestrator_classified",
            failure_type=str(diagnosis.failure_type),
            confidence=diagnosis.confidence,
            incident_id=str(ctx.incident_id),
        )

        # ── ④ Fix Planner ─────────────────────────────────────────────────────
        fix_proposal = await self._fix_planner.run(ctx, diagnosis, raw_evidence=evidence)
        log.info(
            "orchestrator_fix_planned",
            action=fix_proposal.action.value,
            requires_approval=fix_proposal.requires_approval,
            incident_id=str(ctx.incident_id),
        )

        # ── ⑤ Policy Engine ───────────────────────────────────────────────────
        policy_record = self._policy.validate(fix_proposal, diagnosis, ctx)
        log.info(
            "orchestrator_policy",
            decision=policy_record.decision.value,
            checks_failed=policy_record.checks_failed,
            incident_id=str(ctx.incident_id),
        )

        result = OrchestratorResult(
            observations=observations,
            diagnosis=diagnosis,
            fix_proposal=fix_proposal,
            policy_decision=policy_record.decision.value,
            policy_reason=policy_record.reason,
            policy_checks_passed=policy_record.checks_passed,
            policy_checks_failed=policy_record.checks_failed,
        )

        # Store in clone cache for identical failure patterns
        if group_key:
            self._clone_cache[group_key] = result
            log.info("orchestrator_cached", group_key=group_key)

        return result
