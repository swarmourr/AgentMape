from __future__ import annotations

import os
from pathlib import Path

import structlog

from app.utils.config import settings
from app.utils.models.context import ArtifactRef

log = structlog.get_logger(__name__)


def _read_excerpt(path: Path, max_bytes: int) -> tuple[str, bool]:
    """Read up to max_bytes from a file. Returns (content, truncated)."""
    try:
        raw = path.read_bytes()
        if len(raw) > max_bytes:
            return raw[:max_bytes].decode("utf-8", errors="replace"), True
        return raw.decode("utf-8", errors="replace"), False
    except OSError as exc:
        log.warning("file_read_error", path=str(path), error=str(exc))
        return "", False


def _find_artifact(candidates: list[Path], max_bytes: int) -> ArtifactRef | None:
    for path in candidates:
        if path.exists():
            size = path.stat().st_size
            excerpt, truncated = _read_excerpt(path, max_bytes)
            return ArtifactRef(
                path=str(path),
                size_bytes=size,
                truncated=truncated,
                excerpt=excerpt if excerpt else None,
            )
    return None


def _glob_artifact(base: Path, pattern: str, max_bytes: int) -> ArtifactRef | None:
    """Find the first file matching a glob pattern under base."""
    matches = sorted(base.glob(pattern))
    if not matches:
        return None
    path = matches[0]
    size = path.stat().st_size
    excerpt, truncated = _read_excerpt(path, max_bytes)
    return ArtifactRef(
        path=str(path),
        size_bytes=size,
        truncated=truncated,
        excerpt=excerpt if excerpt else None,
    )


# ---------------------------------------------------------------------------
# Per-job file collectors
# Pegasus 5.x stores job files under:
#   {submit_dir}/00/00/{job_id}_ID{instance:07d}.{ext}
# Older versions and flat layouts are tried as fallbacks.
# ---------------------------------------------------------------------------

def collect_stdout(
    submit_dir: str,
    workflow_id: str,
    job_id: str,
    job_instance_id: int,
) -> ArtifactRef | None:
    """Locate and return a reference to the job's HTCondor stdout file."""
    sd = Path(submit_dir)
    candidates = [
        # Pegasus 5.x — 00/00/ subdirectory with _ID suffix
        sd / "00" / "00" / f"{job_id}_ID{job_instance_id:07d}.out",
        # Some versions use a flat 00/00/ without _ID
        sd / "00" / "00" / f"{job_id}.out",
        # Flat submit-dir with _ID suffix
        sd / f"{job_id}_ID{job_instance_id:07d}.out",
        # Legacy flat layout
        sd / f"{job_id}.out",
        # Older three-digit instance suffix
        sd / f"{job_id}.{job_instance_id:03d}.out",
    ]
    return _find_artifact(candidates, settings.log_excerpt_max_bytes)


def collect_stderr(
    submit_dir: str,
    workflow_id: str,
    job_id: str,
    job_instance_id: int,
) -> ArtifactRef | None:
    """Locate and return a reference to the job's HTCondor stderr file."""
    sd = Path(submit_dir)
    candidates = [
        sd / "00" / "00" / f"{job_id}_ID{job_instance_id:07d}.err",
        sd / "00" / "00" / f"{job_id}.err",
        sd / f"{job_id}_ID{job_instance_id:07d}.err",
        sd / f"{job_id}.err",
        sd / f"{job_id}.{job_instance_id:03d}.err",
    ]
    return _find_artifact(candidates, settings.log_excerpt_max_bytes)


def collect_kickstart(
    submit_dir: str,
    workflow_id: str,
    job_id: str,
    job_instance_id: int,
) -> ArtifactRef | None:
    """Locate and return a reference to the Pegasus/Kickstart XML record.

    In Pegasus 5.x, kickstart writes its XML to the HTCondor stdout (.out).
    Some deployments also write a separate .meta or .kickstart.xml file.
    """
    sd = Path(submit_dir)
    candidates = [
        # Separate kickstart XML file (some wrapper scripts extract it)
        sd / "00" / "00" / f"{job_id}_ID{job_instance_id:07d}.kickstart.out",
        sd / "00" / "00" / f"{job_id}.kickstart.xml",
        sd / f"{job_id}_ID{job_instance_id:07d}.kickstart.out",
        sd / f"{job_id}.{job_instance_id:03d}.kickstart.xml",
        sd / f"{job_id}.kickstart.xml",
    ]
    return _find_artifact(candidates, settings.kickstart_excerpt_max_bytes)


def collect_condor_event_log(
    submit_dir: str,
    job_id: str,
    job_instance_id: int,
) -> ArtifactRef | None:
    """Locate and return a reference to the HTCondor job event log (.log).

    The event log records submission, execution start, transfer, and
    completion events in HTCondor's ClassAd event format.
    """
    sd = Path(submit_dir)
    candidates = [
        sd / "00" / "00" / f"{job_id}_ID{job_instance_id:07d}.log",
        sd / "00" / "00" / f"{job_id}.log",
        sd / f"{job_id}_ID{job_instance_id:07d}.log",
        sd / f"{job_id}.log",
        sd / f"{job_id}.{job_instance_id:03d}.log",
    ]
    return _find_artifact(candidates, settings.log_excerpt_max_bytes)


def collect_submit_file(
    submit_dir: str,
    job_id: str,
    job_instance_id: int,
) -> ArtifactRef | None:
    """Locate and return a reference to the HTCondor submit file (.sub).

    The submit file is the ground-truth record of resource requests
    (RequestMemory, RequestDisk, RequestCpus, +ProjectName, etc.)
    as submitted to HTCondor.
    """
    sd = Path(submit_dir)
    candidates = [
        sd / "00" / "00" / f"{job_id}_ID{job_instance_id:07d}.sub",
        sd / "00" / "00" / f"{job_id}.sub",
        sd / f"{job_id}_ID{job_instance_id:07d}.sub",
        sd / f"{job_id}.sub",
        sd / f"{job_id}.{job_instance_id:03d}.sub",
    ]
    # Submit files are small — read them fully (cap at log_excerpt_max_bytes)
    return _find_artifact(candidates, settings.log_excerpt_max_bytes)


# ---------------------------------------------------------------------------
# Workflow-level log collectors
# ---------------------------------------------------------------------------

def collect_dagman_out(submit_dir: str, workflow_name: str | None = None) -> ArtifactRef | None:
    """Locate the DAGMan stdout log (*.dag.dagman.out or *.dagman.out).

    DAGMan records node start/finish events, retry decisions, and PRE/POST
    script outputs.  Useful for understanding workflow-level retry context.
    """
    sd = Path(submit_dir)
    # Prefer the 00/00/ subdirectory location first, then the submit_dir root.
    search_roots = [sd / "00" / "00", sd]

    # Named workflow first (fastest), then any dagman.out glob
    for root in search_roots:
        if not root.exists():
            continue
        if workflow_name:
            ref = _find_artifact(
                [root / f"{workflow_name}.dag.dagman.out"],
                settings.log_excerpt_max_bytes,
            )
            if ref:
                return ref
        ref = _glob_artifact(root, "*.dagman.out", settings.log_excerpt_max_bytes)
        if ref:
            return ref
    return None


def collect_dagman_err(submit_dir: str, workflow_name: str | None = None) -> ArtifactRef | None:
    """Locate the DAGMan stderr log (*.dag.dagman.err or *.dagman.err)."""
    sd = Path(submit_dir)
    search_roots = [sd / "00" / "00", sd]

    for root in search_roots:
        if not root.exists():
            continue
        if workflow_name:
            ref = _find_artifact(
                [root / f"{workflow_name}.dag.dagman.err"],
                settings.log_excerpt_max_bytes,
            )
            if ref:
                return ref
        ref = _glob_artifact(root, "*.dagman.err", settings.log_excerpt_max_bytes)
        if ref:
            return ref
    return None


def collect_workflow_log(submit_dir: str) -> ArtifactRef | None:
    """Locate the Pegasus workflow log (workflow.log).

    Written by pegasus-monitord; records stampede events, job state
    transitions, and Pegasus-level annotations.
    """
    sd = Path(submit_dir)
    candidates = [
        sd / "workflow.log",
        sd.parent / "workflow.log",
    ]
    return _find_artifact(candidates, settings.log_excerpt_max_bytes)


def collect_monitord_log(submit_dir: str) -> ArtifactRef | None:
    """Locate the pegasus-monitord daemon log (monitord.log).

    Records AMQP publish events, parsing errors, and connectivity issues
    that can cause silent monitoring failures.
    """
    sd = Path(submit_dir)
    candidates = [
        sd / "monitord.log",
        sd.parent / "monitord.log",
        # Some versions write it one level above submit_dir
        sd.parent.parent / "monitord.log",
    ]
    return _find_artifact(candidates, settings.log_excerpt_max_bytes)


# ---------------------------------------------------------------------------
# Input file accessibility check
# ---------------------------------------------------------------------------

def check_file_accessible(logical_filename: str, replica_paths: list[str]) -> bool:
    """Return True if at least one physical replica is readable."""
    for phys in replica_paths:
        if os.access(phys, os.R_OK):
            return True
    return False
