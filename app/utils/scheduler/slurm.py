from __future__ import annotations

"""
SLURM implementation of SchedulerClient.

Wraps: squeue / scontrol / sacct / scancel
"""

import subprocess
from typing import Any

import structlog

from app.utils.scheduler.base import JobHistory, JobState, JobStatus

log = structlog.get_logger(__name__)

# SLURM job state string → our JobState
_STATUS_MAP: dict[str, JobState] = {
    "PENDING":       "idle",
    "RUNNING":       "running",
    "SUSPENDED":     "running",
    "COMPLETING":    "running",
    "COMPLETED":     "completed",
    "FAILED":        "completed",
    "CANCELLED":     "removed",
    "TIMEOUT":       "completed",
    "NODE_FAIL":     "completed",
    "PREEMPTED":     "completed",
    "OUT_OF_MEMORY": "completed",
    "REQUEUED":      "idle",
    "RESIZING":      "running",
}

# FixProposal config key → scontrol update field
_RESOURCE_ATTR: dict[str, str] = {
    "memory_mb": "MinMemoryNode",
    "cpus":      "NumCPUs",
    # disk_mb has no direct SLURM equivalent — skipped
    # runtime_seconds handled specially (minutes conversion)
}


def _run(cmd: list[str], timeout: int = 20) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


class SLURMClient:
    """SchedulerClient backed by SLURM CLI tools."""

    def get_job_status(self, cluster_id: str) -> JobStatus | None:
        out = _run([
            "squeue", "-j", cluster_id,
            "--format=%T|%R|%m|%C|%M",
            "--noheader",
        ])
        line = out.strip()
        if not line:
            return None
        parts = line.split("|")
        slurm_state = parts[0].strip() if parts else "UNKNOWN"
        reason      = parts[1].strip() if len(parts) > 1 else None
        state: JobState = _STATUS_MAP.get(slurm_state, "unknown")
        return JobStatus(
            state=state,
            hold_reason=reason if reason and reason != "None" else None,
            raw={"slurm_state": slurm_state, "reason": reason},
        )

    def update_job_resources(self, cluster_id: str, resources: dict[str, Any]) -> bool:
        updates: list[str] = []
        for key, value in resources.items():
            if value is None:
                continue
            if key == "memory_mb":
                updates.append(f"MinMemoryNode={int(value)}M")
            elif key == "cpus":
                updates.append(f"NumCPUs={int(value)}")
            elif key == "runtime_seconds":
                # SLURM TimeLimit is in minutes
                minutes = max(1, int(value) // 60)
                updates.append(f"TimeLimit={minutes}")
            # disk_mb: no SLURM equivalent — skip silently

        if not updates:
            return True
        try:
            cmd = ["scontrol", "update", f"JobId={cluster_id}"] + updates
            subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=True)
            log.info("scontrol_update_ok", cluster_id=cluster_id, updates=updates)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired) as exc:
            log.warning("scontrol_update_failed", cluster_id=cluster_id,
                        updates=updates, error=str(exc))
            return False

    def get_job_history(self, cluster_id: str) -> JobHistory:
        out = _run([
            "sacct", "-j", cluster_id,
            "--format=JobID,ExitCode,MaxRSS,MaxDiskRead,ElapsedRaw,State",
            "--noheader", "--parsable2",
        ])
        lines = [l for l in out.strip().splitlines()
                 if l.strip() and "batch" not in l.lower()]
        if not lines:
            return JobHistory()

        fields = lines[0].split("|")
        # ExitCode format: "code:signal"
        exit_raw = fields[1] if len(fields) > 1 else "0:0"
        parts = exit_raw.split(":")
        exit_code  = int(parts[0]) if parts[0].isdigit() else None
        exit_signal = (
            int(parts[1])
            if len(parts) > 1 and parts[1].isdigit() and parts[1] != "0"
            else None
        )

        # MaxRSS in KB (sacct default) → MB
        max_rss_kb = fields[2].rstrip("K") if len(fields) > 2 else ""
        memory_mb: int | None = None
        try:
            memory_mb = int(max_rss_kb) // 1024
        except ValueError:
            pass

        elapsed_raw = fields[4] if len(fields) > 4 else ""
        wall_time: float | None = None
        try:
            wall_time = float(elapsed_raw)
        except ValueError:
            pass

        return JobHistory(
            exit_code=exit_code,
            exit_signal=exit_signal,
            memory_usage_mb=memory_mb,
            wall_time_seconds=wall_time,
            raw={"sacct_line": lines[0]},
        )

    def cancel_job(self, cluster_id: str) -> bool:
        try:
            subprocess.run(
                ["scancel", cluster_id],
                capture_output=True, text=True, timeout=15, check=True,
            )
            log.info("scancel_ok", cluster_id=cluster_id)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired) as exc:
            log.warning("scancel_failed", cluster_id=cluster_id, error=str(exc))
            return False
