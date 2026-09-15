from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.collectors import condor as condor_collector
from app.collectors import files as file_collector
from app.config import settings
from app.models.context import (
    ArtifactRef,
    DataCheck,
    DiagnosisSummary,
    FailureContext,
    FixSummary,
    PolicySnapshot,
    ResourceRequest,
    ResourceUsage,
)
from app.models.events import WorkflowEvent

log = structlog.get_logger(__name__)


async def collect_failure_context(
    event: WorkflowEvent,
    incident_id: uuid.UUID,
    attempt_number: int,
    previous_diagnoses: list[DiagnosisSummary],
    previous_fixes: list[FixSummary],
    policy_snapshot: PolicySnapshot | None,
    submit_dir: str | None = None,
    condor_classads: dict[str, Any] | None = None,
) -> FailureContext:
    """
    Collect all evidence for a failed job and build a FailureContext.

    submit_dir: path to Pegasus submit directory (contains .out/.err/.kickstart files).
    condor_classads: pre-fetched HTCondor classads (optional; queried live if not provided).
    """
    assert event.job_id is not None
    assert event.job_instance_id is not None

    missing_evidence: list[str] = []

    # ── HTCondor classads ─────────────────────────────────────────────────────
    if condor_classads is None and event.scheduler_id:
        condor_classads = condor_collector.query_condor_history(event.scheduler_id)

    if not condor_classads:
        missing_evidence.append("mandatory:condor_classads")
        condor_classads = {}

    scheduler_state, scheduler_reason = condor_collector.extract_hold_reason(condor_classads)
    resource_request_raw = condor_collector.extract_resource_request(condor_classads)
    resource_usage_raw = condor_collector.extract_resource_usage(condor_classads)

    # ── Exit code / signal ────────────────────────────────────────────────────
    exit_code = event.status
    termination_signal: int | None = None
    if condor_classads:
        if exit_code is None:
            exit_code = condor_classads.get("ExitCode")
        if condor_classads.get("ExitBySignal"):
            termination_signal = condor_classads.get("ExitSignal")
    if exit_code is None:
        missing_evidence.append("mandatory:exit_code")

    # ── Log files ──────────────────────────────────────────────────────────────
    stdout_ref: ArtifactRef | None = None
    stderr_ref: ArtifactRef | None = None
    kickstart_ref: ArtifactRef | None = None
    condor_event_log_ref: ArtifactRef | None = None
    submit_file_ref: ArtifactRef | None = None
    dagman_out_ref: ArtifactRef | None = None
    dagman_err_ref: ArtifactRef | None = None
    workflow_log_ref: ArtifactRef | None = None
    monitord_log_ref: ArtifactRef | None = None

    if submit_dir:
        stdout_ref = file_collector.collect_stdout(
            submit_dir, event.workflow_id, event.job_id, event.job_instance_id
        )
        stderr_ref = file_collector.collect_stderr(
            submit_dir, event.workflow_id, event.job_id, event.job_instance_id
        )
        kickstart_ref = file_collector.collect_kickstart(
            submit_dir, event.workflow_id, event.job_id, event.job_instance_id
        )
        condor_event_log_ref = file_collector.collect_condor_event_log(
            submit_dir, event.job_id, event.job_instance_id
        )
        submit_file_ref = file_collector.collect_submit_file(
            submit_dir, event.job_id, event.job_instance_id
        )
        # Workflow-level logs (not job-specific)
        dagman_out_ref = file_collector.collect_dagman_out(submit_dir, event.workflow_id)
        dagman_err_ref = file_collector.collect_dagman_err(submit_dir, event.workflow_id)
        workflow_log_ref = file_collector.collect_workflow_log(submit_dir)
        monitord_log_ref = file_collector.collect_monitord_log(submit_dir)
    else:
        missing_evidence.append("mandatory:submit_dir")

    # ── Requested resources ───────────────────────────────────────────────────
    requested = ResourceRequest(
        memory_mb=_int(resource_request_raw.get("memory_mb")),
        disk_mb=_int(resource_request_raw.get("disk_mb")),
        cpus=_int(resource_request_raw.get("cpus")),
        runtime_seconds=_int(resource_request_raw.get("runtime_seconds")),
    )
    if requested.memory_mb is None:
        missing_evidence.append("mandatory:requested_memory")

    # ── Measured resources ────────────────────────────────────────────────────
    measured = ResourceUsage(
        peak_memory_mb=_int(resource_usage_raw.get("peak_memory_mb")),
        disk_used_mb=_int(resource_usage_raw.get("disk_used_mb")),
        runtime_seconds=_int(resource_usage_raw.get("runtime_seconds")),
    )

    ctx = FailureContext(
        incident_id=incident_id,
        workflow_id=event.workflow_id,
        job_id=event.job_id,
        job_instance_id=event.job_instance_id,
        scheduler_id=event.scheduler_id,
        exit_code=exit_code,
        termination_signal=termination_signal,
        scheduler_state=scheduler_state,
        scheduler_reason=scheduler_reason,
        requested_resources=requested,
        measured_resources=measured,
        stdout_ref=stdout_ref,
        stderr_ref=stderr_ref,
        kickstart_ref=kickstart_ref,
        condor_event_log_ref=condor_event_log_ref,
        submit_file_ref=submit_file_ref,
        dagman_out_ref=dagman_out_ref,
        dagman_err_ref=dagman_err_ref,
        workflow_log_ref=workflow_log_ref,
        monitord_log_ref=monitord_log_ref,
        input_checks=[],      # populated by agent tools when needed
        output_checks=[],
        attempt_number=attempt_number,
        previous_diagnoses=previous_diagnoses,
        previous_fixes=previous_fixes,
        policy_snapshot=policy_snapshot,
        missing_evidence=missing_evidence,
    )

    log.info(
        "context_collected",
        incident_id=str(incident_id),
        missing_fields=missing_evidence,
        has_stderr=stderr_ref is not None,
        has_kickstart=kickstart_ref is not None,
        has_condor_log=condor_event_log_ref is not None,
        has_submit_file=submit_file_ref is not None,
        has_dagman_out=dagman_out_ref is not None,
        has_workflow_log=workflow_log_ref is not None,
    )
    return ctx


def _int(val: Any) -> int | None:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None
