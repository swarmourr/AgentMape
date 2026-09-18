from __future__ import annotations

"""
ReAct agent tool functions — operate on RawEvidence already in memory.

Each function takes a RawEvidence object and returns either a string
(for log excerpts) or a dict (for structured data). The DiagnosisAgent
calls these by name based on the LLM's chosen action at each step.

No filesystem access, no subprocess calls — the POST script already
collected everything and sent it in the HTTP payload.
"""

import json
import re
import xml.etree.ElementTree as ET
from typing import Any

from app.utils.models.evidence import RawEvidence


# ── 1. parse_failure_summary ──────────────────────────────────────────────────

def parse_failure_summary(evidence: RawEvidence) -> dict[str, Any]:
    """
    Extract structured failure information from pegasus-analyzer output.

    Returns: last_state, site, failed_jobs list, stderr excerpt visible
             in analyzer, kickstart summary visible in analyzer.
    """
    output = evidence.pegasus_analyzer_output or ""
    if not output:
        return {"error": "pegasus_analyzer output not available"}

    result: dict[str, Any] = {
        "last_state": None,
        "site": None,
        "failed_jobs": [],
        "analyzer_stderr_excerpt": None,
        "analyzer_kickstart_excerpt": None,
        "raw_summary": "",
    }

    # Extract the summary block (first ~30 lines)
    lines = output.splitlines()
    result["raw_summary"] = "\n".join(lines[:40])

    # last state: POST_SCRIPT_FAILED / JOB_FAILURE / etc.
    m = re.search(r"last state:\s*(\S+)", output, re.IGNORECASE)
    if m:
        result["last_state"] = m.group(1)

    # site: condorpool / local / etc.
    m = re.search(r"^\s+site:\s*(\S+)", output, re.MULTILINE | re.IGNORECASE)
    if m:
        result["site"] = m.group(1)

    # Failed job section headers: ===jobname===
    result["failed_jobs"] = re.findall(r"={3,}(\S+?)={3,}", output)

    # Stderr excerpt shown by analyzer (between "stderr of jobname:" and blank line)
    m = re.search(
        r"stderr of \S+:\s*\n(.*?)(?:\n\n|\Z)",
        output,
        re.DOTALL,
    )
    if m:
        result["analyzer_stderr_excerpt"] = m.group(1).strip()[:1000]

    # Kickstart stdout shown by analyzer
    m = re.search(
        r"stdout of \S+:\s*\n(.*?)(?:\n\n|\Z)",
        output,
        re.DOTALL,
    )
    if m:
        result["analyzer_kickstart_excerpt"] = m.group(1).strip()[:1000]

    return result


# ── 2. get_stderr ─────────────────────────────────────────────────────────────

def get_stderr(evidence: RawEvidence, max_chars: int = 6000) -> str:
    """
    Full stderr content from the .err file.

    Returns the last max_chars characters (tail of stderr is usually most
    informative — OOM messages, final tracebacks, disk errors).
    """
    content = evidence.stderr_content or ""
    if not content:
        # Fall back to what pegasus-analyzer showed
        if evidence.pegasus_analyzer_output:
            m = re.search(
                r"stderr of \S+:\s*\n(.*?)(?:\n\n|\Z)",
                evidence.pegasus_analyzer_output,
                re.DOTALL,
            )
            if m:
                return m.group(1).strip()
        return "(stderr not available)"

    # Return tail — errors are usually at the bottom
    if len(content) > max_chars:
        return f"[... {len(content) - max_chars} chars truncated ...]\n" + content[-max_chars:]
    return content


# ── 3. get_kickstart_data ─────────────────────────────────────────────────────

def get_kickstart_data(evidence: RawEvidence) -> dict[str, Any]:
    """
    Parse kickstart XML from the .out file.

    Returns: peak_memory_mb, cpu_time_s, wall_time_s, exit_code,
             input_files (list), per-task breakdown.
    """
    content = evidence.stdout_content or ""
    result: dict[str, Any] = {
        "peak_memory_mb": None,
        "cpu_time_s": None,
        "wall_time_s": None,
        "main_job_exit_code": None,
        "input_files": [],
        "raw_excerpt": content[:600] if content else "(stdout not available)",
    }

    if not content:
        return result

    # Try full XML parse first
    try:
        xml_match = re.search(r"(<invocation\b.*?</invocation>)", content, re.DOTALL)
        if xml_match:
            root = ET.fromstring(xml_match.group(1))

            usage = root.find(".//usage")
            if usage is not None:
                maxrss = usage.get("maxrss")
                if maxrss:
                    # maxrss is in KB on Linux
                    result["peak_memory_mb"] = round(int(maxrss) / 1024, 1)
                utime = float(usage.get("utime") or 0)
                stime = float(usage.get("stime") or 0)
                result["cpu_time_s"] = round(utime + stime, 2)

            mainjob = root.find(".//mainjob")
            if mainjob is not None:
                result["main_job_exit_code"] = mainjob.get("exit")
                dur = mainjob.get("duration")
                if dur:
                    result["wall_time_s"] = round(float(dur), 2)

            result["input_files"] = [
                f.get("name", "") for f in root.findall(".//file")
                if f.get("linkage") in ("input", "in") or f.get("type") == "input"
            ]
    except ET.ParseError:
        pass

    # Regex fallback for memory if XML failed
    if result["peak_memory_mb"] is None:
        m = re.search(r"maxrss[=:\s\"]+(\d+)", content, re.IGNORECASE)
        if m:
            result["peak_memory_mb"] = round(int(m.group(1)) / 1024, 1)

    return result


# ── 4. get_resource_requests ──────────────────────────────────────────────────

def get_resource_requests(evidence: RawEvidence) -> dict[str, Any]:
    """
    Parse resource requests from the HTCondor .sub file.

    Returns: memory_mb, disk_mb, cpus, runtime_seconds.
    These are the REQUESTED values — ground truth from the submit file.
    """
    content = evidence.sub_file_content or ""
    result: dict[str, Any] = {
        "memory_mb": None,
        "disk_mb": None,
        "cpus": None,
        "runtime_seconds": None,
        "universe": None,
        "executable": None,
    }

    if not content:
        return result

    # Each key maps to a list of patterns tried in order.
    # Pegasus-generated submit files use pegasus_* attributes;
    # standard HTCondor uses request_* attributes.
    patterns: dict[str, list[tuple[str, type]]] = {
        "memory_mb": [
            (r"request_memory\s*=\s*(\d+)", int),       # HTCondor standard — healer patches this
            (r"pegasus_memory_mb\s*=\s*(\d+)", int),    # Pegasus metadata — fallback only
        ],
        "disk_mb": [
            (r"request_disk\s*=\s*(\d+)", int),
            (r"pegasus_diskspace_mb\s*=\s*(\d+)", int),
        ],
        "cpus": [
            (r"request_cpus\s*=\s*(\d+)", int),
            (r"pegasus_cores\s*=\s*(\d+)", int),
        ],
        "runtime_seconds": [
            (r"\+MaxRuntime\s*=\s*(\d+)", int),
            (r"pegasus_job_runtime\s*=\s*(\d+)", int),  # Pegasus walltime (seconds)
        ],
        "universe":   [(r"universe\s*=\s*(\S+)", str)],
        "executable": [(r"executable\s*=\s*(.+)", str)],
    }

    for key, pattern_list in patterns.items():
        for pattern, cast in pattern_list:
            m = re.search(pattern, content, re.IGNORECASE)
            if m:
                try:
                    result[key] = cast(m.group(1).strip())
                    break   # first match wins for this key
                except (ValueError, TypeError):
                    pass

    return result


# ── 5. get_condor_history ─────────────────────────────────────────────────────

def get_condor_history(evidence: RawEvidence) -> dict[str, Any]:
    """
    Parse condor_history classads (JSON from condor_history -json).

    Returns: exit_code, memory_usage_mb, disk_usage_mb, hold_reason,
             remote_wallclock_s, exit_signal, job_status.
    """
    raw = evidence.condor_classads_raw or ""
    result: dict[str, Any] = {
        "exit_code": None,
        "memory_usage_mb": None,
        "disk_usage_mb": None,
        "hold_reason": None,
        "remote_wallclock_s": None,
        "exit_signal": None,
        "job_status": None,
    }

    if not raw:
        return result

    try:
        data = json.loads(raw)
        ad: dict = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})

        result["exit_code"] = ad.get("ExitCode") or ad.get("ExitStatus")
        result["exit_signal"] = ad.get("ExitSignal")
        result["memory_usage_mb"] = ad.get("MemoryUsage")
        result["disk_usage_mb"] = ad.get("DiskUsage")
        result["hold_reason"] = ad.get("HoldReason")
        result["remote_wallclock_s"] = ad.get("RemoteWallClockTime")
        result["job_status"] = ad.get("JobStatus")
    except (json.JSONDecodeError, IndexError, KeyError):
        # Text classad format fallback: key = value or key = "value"
        for line in raw.splitlines():
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"')
            mapping = {
                "ExitCode": "exit_code",
                "ExitStatus": "exit_code",
                "ExitSignal": "exit_signal",
                "MemoryUsage": "memory_usage_mb",
                "DiskUsage": "disk_usage_mb",
                "HoldReason": "hold_reason",
                "RemoteWallClockTime": "remote_wallclock_s",
                "JobStatus": "job_status",
            }
            if k in mapping:
                result[mapping[k]] = int(v) if v.isdigit() else v

    return result


# ── 6. get_event_log ─────────────────────────────────────────────────────────

def get_event_log(evidence: RawEvidence, max_chars: int = 4000) -> str:
    """
    HTCondor event log — shows eviction, holds, image size updates,
    shadow exceptions, preemption events.
    Returns the tail (most recent events).
    """
    content = evidence.event_log_content or ""
    if not content:
        return "(HTCondor event log not available)"
    if len(content) > max_chars:
        return f"[... truncated, showing last {max_chars} chars ...]\n" + content[-max_chars:]
    return content


# ── 7. get_dagman_log ─────────────────────────────────────────────────────────

def get_dagman_log(evidence: RawEvidence, max_chars: int = 3000) -> str:
    """
    DAGMan log — retry history, PRE/POST script outputs, workflow control.
    Returns the tail (most recent decisions).
    """
    content = evidence.dagman_log_content or ""
    if not content:
        return "(DAGMan log not available)"
    if len(content) > max_chars:
        return f"[... truncated, showing last {max_chars} chars ...]\n" + content[-max_chars:]
    return content


# ── 8. get_workflow_log ───────────────────────────────────────────────────────

def get_workflow_log(evidence: RawEvidence, max_chars: int = 3000) -> str:
    """
    Pegasus workflow log — job state transitions written by monitord.
    Shows when each job was submitted, started, failed.
    """
    content = evidence.workflow_log_content or ""
    if not content:
        return "(Pegasus workflow log not available)"
    if len(content) > max_chars:
        return f"[... truncated, showing last {max_chars} chars ...]\n" + content[-max_chars:]
    return content


# ── 9. get_transformation_script ─────────────────────────────────────────────

def get_transformation_script(evidence: RawEvidence) -> dict[str, Any]:
    """
    Return the transformation script content and its path on the submit host.

    Only available when the executable declared in the .sub file points to a
    file accessible from the submit host (absolute or relative path that exists).
    Use this to detect script bugs, missing modules, wrong arguments, or
    environment issues.
    """
    if not evidence.transformation_script_content:
        return {
            "available": False,
            "reason": (
                "Transformation script is not accessible from the submit host. "
                "It may be a remote executable, a container image, or a bare command name."
            ),
        }
    content = evidence.transformation_script_content
    truncated = len(content) > 5000
    return {
        "available": True,
        "path": evidence.transformation_script_path,
        "content": content[:5000],
        "truncated": truncated,
        "total_chars": len(content),
    }


# ── 10. get_input_validation ──────────────────────────────────────────────────

def get_input_validation(evidence: RawEvidence) -> dict[str, Any]:
    """
    Return the validation results for all files listed in transfer_input_files.

    Checks which input files exist on the submit host, their sizes, and whether
    any are empty.  Use this when stderr shows FileNotFoundError, permission
    denied, or format errors that might indicate the wrong file was staged.
    """
    if not evidence.input_validation:
        return {
            "available": False,
            "reason": (
                "No transfer_input_files found in submit file, "
                "or submit file was not collected."
            ),
        }
    files = [f.model_dump() for f in evidence.input_validation]
    missing = [f for f in files if not f["exists"]]
    empty   = [f for f in files if f.get("is_empty")]
    return {
        "available": True,
        "total_files": len(files),
        "missing_count": len(missing),
        "empty_count": len(empty),
        "all_present": len(missing) == 0,
        "files": files,
        "missing_files": missing,
        "empty_files": empty,
    }


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOL_MAP: dict[str, Any] = {
    "parse_failure_summary":      parse_failure_summary,
    "get_stderr":                 get_stderr,
    "get_kickstart_data":         get_kickstart_data,
    "get_resource_requests":      get_resource_requests,
    "get_condor_history":         get_condor_history,
    "get_event_log":              get_event_log,
    "get_dagman_log":             get_dagman_log,
    "get_workflow_log":           get_workflow_log,
    "get_transformation_script":  get_transformation_script,
    "get_input_validation":       get_input_validation,
}

TOOL_DESCRIPTIONS = """
Available tools (call in priority order):
  parse_failure_summary     — structured summary from pegasus-analyzer: last_state, site, failed jobs
  get_stderr                — full .err file content: "Killed", tracebacks, "No space left on device"
  get_kickstart_data        — .out file: peak_memory_mb, wall_time_s, per-task exit codes
  get_resource_requests     — .sub file: exact requested memory_mb, disk_mb, cpus, runtime_seconds
  get_condor_history        — condor classads: actual memory_usage_mb, disk_usage_mb, hold_reason
  get_event_log             — .log file: eviction, shadow exceptions, preemption
  get_dagman_log            — dagman.out: retry history, PRE/POST script results
  get_workflow_log          — workflow.log: Pegasus state transitions
  get_transformation_script — read the transformation script source (if local): detect bugs/env issues
  get_input_validation      — check transfer_input_files: which inputs are missing, empty, or wrong
"""
