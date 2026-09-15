from __future__ import annotations

import subprocess
import re
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# HTCondor classad attributes we care about
_CONDOR_ATTRS = [
    "HoldReason",
    "HoldReasonCode",
    "HoldReasonSubCode",
    "RemoveReason",
    "RequestMemory",
    "RequestDisk",
    "RequestCpus",
    "MemoryUsage",
    "DiskUsage",
    "RemoteWallClockTime",
    "JobStatus",
    "ExitCode",
    "ExitSignal",
    "ExitBySignal",
    "LastJobStatus",
]


def query_condor_history(scheduler_id: str) -> dict[str, Any]:
    """
    Query HTCondor history for a completed job.

    Returns a dict of classad key → value.
    Falls back to an empty dict if condor_history is unavailable.

    NOTE: In production this requires condor_history to be on PATH and
    credentials to query the relevant schedd. For the MVP the FakePegasusRetryController
    provides synthetic values.
    """
    try:
        result = subprocess.run(
            ["condor_history", scheduler_id, "-long", "-format", "%s\n", "ClusterId"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return _parse_classads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warning("condor_history_unavailable", scheduler_id=scheduler_id, error=str(exc))
        return {}


def _parse_classads(output: str) -> dict[str, Any]:
    """Parse 'Key = Value' lines from condor_history -long output."""
    data: dict[str, Any] = {}
    for line in output.splitlines():
        m = re.match(r"^(\w+)\s*=\s*(.+)$", line.strip())
        if not m:
            continue
        key, raw_val = m.group(1), m.group(2).strip().strip('"')
        # Try numeric coercion
        try:
            data[key] = int(raw_val)
            continue
        except ValueError:
            pass
        try:
            data[key] = float(raw_val)
            continue
        except ValueError:
            pass
        if raw_val.lower() in ("true", "false"):
            data[key] = raw_val.lower() == "true"
        else:
            data[key] = raw_val
    return data


def extract_resource_request(classads: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_mb": classads.get("RequestMemory"),
        "disk_mb": classads.get("RequestDisk"),
        "cpus": classads.get("RequestCpus"),
    }


def extract_resource_usage(classads: dict[str, Any]) -> dict[str, Any]:
    return {
        "peak_memory_mb": classads.get("MemoryUsage"),
        "disk_used_mb": classads.get("DiskUsage"),
        "runtime_seconds": classads.get("RemoteWallClockTime"),
    }


def extract_hold_reason(classads: dict[str, Any]) -> tuple[str | None, str | None]:
    """Returns (scheduler_state, scheduler_reason)."""
    state = "Held" if classads.get("HoldReasonCode") else None
    reason = classads.get("HoldReason") or classads.get("RemoveReason")
    return state, str(reason) if reason else None
