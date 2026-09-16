from __future__ import annotations

"""
PegasusClient — unified scheduler + workflow-level client.

Wraps a SchedulerClient (HTCondor or SLURM) for job-level operations and
adds Pegasus workflow-level CLI commands that operate on submit directories.

                    ┌─────────────────────┐
                    │   PegasusClient     │
                    │                     │
   job-level ops ──►│  delegates to       │──► HTCondorClient
  (cluster_id)      │  SchedulerClient    │    or SLURMClient
                    │                     │
 workflow-level ──►│  pegasus-analyzer   │
   ops (submit_dir) │  pegasus-status     │
                    │  pegasus-remove     │
                    │  pegasus-run        │
                    └─────────────────────┘

Use get_pegasus_client() for a singleton that already wraps the
configured scheduler backend.
"""

import subprocess
from pathlib import Path
from typing import Any

import structlog

from app.utils.scheduler.base import JobHistory, JobStatus, SchedulerClient

log = structlog.get_logger(__name__)


def _run(cmd: list[str], timeout: int, log_key: str) -> subprocess.CompletedProcess | None:
    """Run a CLI command, returning None on missing binary or timeout."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        log.warning(f"{log_key}_not_found", cmd=cmd[0], note=f"{cmd[0]} not on PATH")
        return None
    except subprocess.TimeoutExpired:
        log.warning(f"{log_key}_timeout", timeout=timeout)
        return None


class PegasusClient:
    """
    Pegasus-aware scheduler client.

    Implements SchedulerClient by delegating to the wrapped backend
    (HTCondorClient or SLURMClient) and adds Pegasus workflow-level
    commands that operate on submit directories rather than cluster IDs.
    """

    def __init__(self, scheduler: SchedulerClient) -> None:
        self._scheduler = scheduler

    # ── SchedulerClient delegation ─────────────────────────────────────────

    def get_job_status(self, cluster_id: str) -> JobStatus | None:
        return self._scheduler.get_job_status(cluster_id)

    def update_job_resources(self, cluster_id: str, resources: dict[str, Any]) -> bool:
        return self._scheduler.update_job_resources(cluster_id, resources)

    def get_job_history(self, cluster_id: str) -> JobHistory:
        return self._scheduler.get_job_history(cluster_id)

    def cancel_job(self, cluster_id: str) -> bool:
        return self._scheduler.cancel_job(cluster_id)

    # ── Pegasus workflow-level commands ────────────────────────────────────

    def analyze_workflow(
        self,
        submit_dir: Path,
        job_id: str | None = None,
        *,
        timeout: int = 60,
    ) -> str | None:
        """
        Run pegasus-analyzer and return its stdout.

        With job_id: scoped to one job node (--job flag).
        Without:     full workflow analysis.

        Returns None when pegasus-analyzer is not on PATH or times out.
        """
        cmd = ["pegasus-analyzer", str(submit_dir)]
        if job_id:
            cmd += ["--job", job_id]
        result = _run(cmd, timeout, "pegasus_analyzer")
        if result is None:
            return None
        if result.returncode not in (0, 1):
            log.warning(
                "pegasus_analyzer_nonzero",
                rc=result.returncode,
                stderr=result.stderr[:300],
            )
        return result.stdout or None

    def get_workflow_status(
        self,
        submit_dir: Path,
        *,
        timeout: int = 30,
    ) -> str | None:
        """
        Run pegasus-status and return its stdout.

        Returns None when pegasus-status is not on PATH or times out.
        """
        cmd = ["pegasus-status", "--long", str(submit_dir)]
        result = _run(cmd, timeout, "pegasus_status")
        if result is None:
            return None
        if result.returncode != 0:
            log.warning(
                "pegasus_status_nonzero",
                rc=result.returncode,
                stderr=result.stderr[:300],
            )
        return result.stdout or None

    def remove_workflow(
        self,
        submit_dir: Path,
        *,
        timeout: int = 30,
    ) -> bool:
        """
        Run pegasus-remove to cancel a running workflow.

        Returns True on success (exit code 0).
        """
        cmd = ["pegasus-remove", str(submit_dir)]
        result = _run(cmd, timeout, "pegasus_remove")
        if result is None:
            return False
        success = result.returncode == 0
        if success:
            log.info("pegasus_remove_ok", submit_dir=str(submit_dir))
        else:
            log.warning(
                "pegasus_remove_failed",
                rc=result.returncode,
                stderr=result.stderr[:300],
            )
        return success

    def run_workflow(
        self,
        submit_dir: Path,
        *,
        timeout: int = 30,
    ) -> bool:
        """
        Run pegasus-run to (re)submit a workflow.

        Returns True on success (exit code 0).
        """
        cmd = ["pegasus-run", str(submit_dir)]
        result = _run(cmd, timeout, "pegasus_run")
        if result is None:
            return False
        success = result.returncode == 0
        if success:
            log.info("pegasus_run_ok", submit_dir=str(submit_dir))
        else:
            log.warning(
                "pegasus_run_failed",
                rc=result.returncode,
                stderr=result.stderr[:300],
            )
        return success


# ── Backwards-compatible standalone function ───────────────────────────────────

def run_pegasus_analyzer(
    submit_dir: Path,
    job_id: str | None = None,
    *,
    timeout: int = 60,
) -> str | None:
    """
    Standalone wrapper kept for backwards compatibility.
    Prefer PegasusClient.analyze_workflow() for new code.
    """
    from app.utils.scheduler.factory import get_scheduler_client
    return PegasusClient(get_scheduler_client()).analyze_workflow(
        submit_dir, job_id, timeout=timeout
    )
