from __future__ import annotations

from typing import Any, Literal, TypedDict


class RemediationState(TypedDict, total=False):
    # ── Identity ──────────────────────────────────────────────────────────────
    incident_id: str
    workflow_id: str
    job_id: str
    source_job_instance_id: int

    # ── Diagnostic loop ───────────────────────────────────────────────────────
    failure_event: dict[str, Any]       # serialised WorkflowEvent
    context: dict[str, Any]             # serialised FailureContext
    raw_evidence: dict[str, Any]        # serialised RawEvidence (file contents)
    retrieved_memories: list[dict[str, Any]]
    diagnosis: dict[str, Any]           # serialised Diagnosis

    # ── Action loop ───────────────────────────────────────────────────────────
    proposed_fix: dict[str, Any]        # serialised FixProposal
    policy_decision: Literal["AUTO", "ASK", "STOP", "ESCALATE"]
    policy_record: dict[str, Any]       # serialised PolicyDecisionRecord
    overlay: dict[str, Any]             # serialised AppliedOverlay
    fix_id: str
    retry_job_instance_id: int
    retry_outcome: str                  # FixOutcome value

    # ── Loop control ──────────────────────────────────────────────────────────
    attempt: int
    errors: list[str]
    insufficient_evidence_fields: list[str]
    terminal: bool                      # True = graph is done
