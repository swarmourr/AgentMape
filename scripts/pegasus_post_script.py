#!/usr/bin/env python3
"""
Pegasus/DAGMan POST script for agentic failure remediation.

Responsibilities
────────────────
1. Collect all diagnostic evidence from the Pegasus submit directory:
     • Run pegasus-analyzer  → structured failure summary
     • Read raw files        → .err / .out / .sub / .log / dagman.out / workflow.log
     • Run condor_history    → resource usage classads
2. POST everything to the remediation service (/diagnose-and-fix)
3. Exit with the right code so DAGMan retries or stops

EXIT CODE CONTRACT
──────────────────
  0  → DAGMan marks node DONE/SUCCESS (no more automatic retries)
  1  → DAGMan marks node FAILED (will retry if RETRY count allows)

decision → exit code:
  RETRY    → 1  (.sub already patched; DAGMan retries with new resources)
  ASK      → 0  (fix ready but needs human approval)
  STOP     → 0  (terminal; no value in retrying)
  ESCALATE → 0  (operator notified)

Service unreachable → passes through original exit code unchanged.

USAGE
─────
In pegasus.properties:
    pegasus.dagman.post=/path/to/pegasus_post_script.py
    pegasus.dagman.post.arguments=$RETURN $JOB $RETRY $MAX_RETRIES \\
        /path/to/submit_dir ${wf.uuid}

Or in the .dag file:
    SCRIPT POST job_name /path/to/pegasus_post_script.py \\
        $RETURN $JOB $RETRY $MAX_RETRIES /submit_dir WORKFLOW_ID

Environment variables:
    PEGASUS_REMEDIATION_URL      service base URL (default: http://localhost:8000)
    PEGASUS_REMEDIATION_TIMEOUT  HTTP timeout in seconds (default: 120)
    PEGASUS_REMEDIATION_MODE     path|inline (default: inline)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Add project root to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.collectors.submit_dir import collect_evidence, parse_instance_id
from app.reporters.agent_report import generate_report, write_report

# ── Configuration ──────────────────────────────────────────────────────────────
SERVICE_URL = os.environ.get("PEGASUS_REMEDIATION_URL", "http://localhost:8000")
REQUEST_TIMEOUT = int(os.environ.get("PEGASUS_REMEDIATION_TIMEOUT", "120"))
TAG = "[pegasus-remediation]"


# ── Logging ────────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"{TAG} {msg}", file=sys.stderr, flush=True)


# ── HTTP call ─────────────────────────────────────────────────────────────────

def _call_service(payload: dict[str, Any]) -> dict[str, Any] | None:
    url = f"{SERVICE_URL}/diagnose-and-fix"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        _log(f"service HTTP {exc.code}: {exc.reason}")
        try:
            _log(f"  body: {exc.read().decode('utf-8', errors='replace')[:400]}")
        except Exception:
            pass
        return None
    except urllib.error.URLError as exc:
        _log(f"service unreachable: {exc.reason}")
        return None
    except Exception as exc:
        _log(f"unexpected error: {exc}")
        return None


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pegasus/DAGMan POST script — agentic failure remediation"
    )
    parser.add_argument("exit_code",     type=int, help="Job exit code ($RETURN)")
    parser.add_argument("job_id",                  help="DAGMan node name ($JOB)")
    parser.add_argument("retry_number",  type=int, help="Current retry number ($RETRY)")
    parser.add_argument("max_retries",   type=int, help="Max retries ($MAX_RETRIES)")
    parser.add_argument("submit_dir",              help="Pegasus submit directory")
    parser.add_argument("workflow_id",             help="Pegasus workflow ID (wf_uuid)")
    parser.add_argument("--job-instance-id", type=int, default=None,
                        help="Instance ID (parsed from job_id if omitted)")
    parser.add_argument("--condor-job-id",   default=None,
                        help="HTCondor cluster.proc (e.g. '1234.0')")
    parser.add_argument("--execution-site",  default=None)
    parser.add_argument("--transformation",  default=None)
    args = parser.parse_args()

    # Job succeeded — nothing to do
    if args.exit_code == 0:
        return 0

    instance_id = args.job_instance_id or parse_instance_id(args.job_id)
    submit_dir = Path(args.submit_dir)

    _log(
        f"job_id={args.job_id} instance={instance_id} "
        f"exit_code={args.exit_code} retry={args.retry_number}/{args.max_retries}"
    )

    # Retry budget exhausted on our side — let DAGMan handle it
    if args.retry_number >= args.max_retries:
        _log(f"retry budget exhausted, skipping service call")
        return args.exit_code

    # ── Collect all evidence ──────────────────────────────────────────────────
    _log("collecting evidence from submit directory...")
    evidence = collect_evidence(
        submit_dir=submit_dir,
        job_id=args.job_id,
        instance_id=instance_id,
        condor_job_id=args.condor_job_id,
    )
    raw_evidence = evidence.model_dump()
    sources = evidence.available_sources
    _log(f"evidence collected: {sources}")

    # ── Build request payload ─────────────────────────────────────────────────
    payload: dict[str, Any] = {
        "job_id":           args.job_id,
        "job_instance_id":  instance_id,
        "workflow_id":      args.workflow_id,
        "exit_code":        args.exit_code,
        "submit_dir":       str(submit_dir),
        "condor_job_id":    args.condor_job_id,
        "retry_number":     args.retry_number,
        "max_retries":      args.max_retries,
        "execution_site":   args.execution_site,
        "transformation":   args.transformation,
        "raw_evidence":     raw_evidence,
    }

    _log(f"calling service: POST {SERVICE_URL}/diagnose-and-fix")
    result = _call_service(payload)

    if result is None:
        _log("service unreachable — passing through original exit code")
        return args.exit_code

    # ── Parse response ────────────────────────────────────────────────────────
    decision         = result.get("decision", "ESCALATE")
    incident_id      = result.get("incident_id", "unknown")
    failure_type     = result.get("failure_type")
    confidence       = result.get("confidence")
    explanation      = result.get("explanation")
    evidence_sources = result.get("evidence_sources", [])
    missing_evidence = result.get("missing_evidence", [])
    fix_id           = result.get("fix_id")
    fix_proposed     = result.get("fix_proposed")
    approval_url     = result.get("approval_url")
    justification    = result.get("justification", "")

    _log(
        f"incident={incident_id} failure_type={failure_type} "
        f"confidence={confidence} decision={decision}"
    )

    # ── Write agent report to submit directory ────────────────────────────────
    try:
        report = generate_report(
            job_id=args.job_id,
            workflow_id=args.workflow_id,
            submit_dir=str(submit_dir),
            incident_id=incident_id,
            exit_code=args.exit_code,
            attempt=args.retry_number + 1,
            max_retries=args.max_retries,
            decision=decision,
            failure_type=failure_type,
            confidence=confidence,
            explanation=explanation,
            evidence_sources=evidence_sources,
            fix_proposed=fix_proposed,
            approval_url=approval_url,
            service_url=SERVICE_URL,
            missing_evidence=missing_evidence,
        )
        report_path = write_report(report, submit_dir, args.job_id)
        _log(f"report written → {report_path}")
    except Exception as exc:
        _log(f"warning: could not write agent report: {exc}")

    # ── Decide DAGMan exit code ───────────────────────────────────────────────
    if decision == "RETRY":
        _log("exiting 1 → DAGMan will retry with patched submit file")
        return 1

    if decision == "ASK":
        _log(
            "HUMAN APPROVAL REQUIRED — see agent report for instructions\n"
            f"  Report: {submit_dir}/{args.job_id}.agent_report\n"
            f"  Approve: POST {SERVICE_URL}{approval_url}"
        )
        return 0

    if decision == "STOP":
        _log(
            f"STOP — terminal failure ({failure_type})\n"
            f"  Report: {submit_dir}/{args.job_id}.agent_report"
        )
        return 0

    # ESCALATE or unknown
    _log(
        f"ESCALATE — could not resolve ({failure_type or 'UNKNOWN'})\n"
        f"  Report: {submit_dir}/{args.job_id}.agent_report"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
