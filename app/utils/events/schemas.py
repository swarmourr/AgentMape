from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.utils.models.events import WorkflowEvent

# Mapping from raw Pegasus/Monitord stampede event names to our canonical EventType
_STAMPEDE_TYPE_MAP: dict[str, str] = {
    # job-instance events
    "stampede.job_inst.submit": "JOB_SUBMITTED",
    "stampede.job_inst.pre.start": "JOB_STARTED",
    "stampede.job_inst.main.start": "JOB_STARTED",
    "stampede.job_inst.held": "JOB_HELD",
    "stampede.job_inst.main.failure": "JOB_FAILED",
    "stampede.job_inst.main.success": "JOB_SUCCEEDED",
    "stampede.job_inst.end": "JOB_SUCCEEDED",
    # invocation events (execution-level)
    "stampede.inv.start": "JOB_STARTED",
    "stampede.inv.end": "JOB_SUCCEEDED",  # will be overridden by exit code check
    # workflow-level events
    "stampede.xwf.end": "WORKFLOW_SUCCEEDED",  # will be overridden by status check
    "stampede.xwf.fail": "WORKFLOW_FAILED",
}


def normalize_event(routing_key: str, payload: dict[str, Any]) -> WorkflowEvent | None:
    """
    Normalise a raw Pegasus Monitord AMQP message into a WorkflowEvent.

    Returns None if the event is not relevant to remediation (e.g. an
    informational progress event with no job-failure signal).
    """
    event_type = _resolve_event_type(routing_key, payload)
    if event_type is None:
        return None

    # For inv.end events, check exit code to determine success/failure
    if routing_key.startswith("stampede.inv.end") or routing_key.startswith("stampede.inv."):
        exit_code = payload.get("exitcode") or payload.get("exit_code")
        if exit_code is not None and int(exit_code) != 0:
            event_type = "JOB_FAILED"

    # For xwf.end, check status
    if routing_key == "stampede.xwf.end":
        status = payload.get("status")
        if status is not None and int(status) != 0:
            event_type = "WORKFLOW_FAILED"

    raw_id = (
        payload.get("event_id")
        or payload.get("job_inst_id")
        or payload.get("wf_id")
    )
    event_id = (
        str(raw_id)
        if raw_id
        else WorkflowEvent.make_event_id({**payload, "_routing_key": routing_key})
    )

    ts_raw = payload.get("ts") or payload.get("timestamp")
    if ts_raw:
        try:
            timestamp = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
        except (ValueError, TypeError):
            timestamp = datetime.now(tz=timezone.utc)
    else:
        timestamp = datetime.now(tz=timezone.utc)

    return WorkflowEvent(
        event_id=event_id,
        event_type=event_type,  # type: ignore[arg-type]
        workflow_id=str(
            payload.get("wf_id") or payload.get("workflow_id") or "unknown"
        ),
        job_id=_str_or_none(payload.get("job_id") or payload.get("job_name")),
        job_instance_id=_int_or_none(
            payload.get("job_inst_id") or payload.get("job_instance_id")
        ),
        scheduler_id=_str_or_none(
            payload.get("sched_id") or payload.get("condor_id")
        ),
        status=_int_or_none(payload.get("status") or payload.get("exitcode")),
        timestamp=timestamp,
        raw_event=payload,
    )


def _resolve_event_type(routing_key: str, payload: dict[str, Any]) -> str | None:
    # Exact match first
    if routing_key in _STAMPEDE_TYPE_MAP:
        return _STAMPEDE_TYPE_MAP[routing_key]
    # Prefix match
    for prefix, event_type in _STAMPEDE_TYPE_MAP.items():
        if routing_key.startswith(prefix):
            return event_type
    # Unknown routing key — drop silently
    return None


def _str_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None
