#!/usr/bin/env python3
"""
Pegasus/DAGMan POST script — direct LangGraph remediation.

Runs the remediation graph in-process. No API server needed.
State persists across DAGMan invocations via SQLite checkpointer,
keyed on thread_id = workflow_id / source_job_instance_id.

EXECUTION MODEL
───────────────
Each invocation is one pass through the graph:

  Invocation 1  (first failure, $RETRY=0)
    Fresh thread → diagnose → fix → apply
    → AUTO : patch .sub + broadcast siblings → exit 1  (DAGMan retries)
    → ASK  : write proposal report            → exit 0  (human applies manually)
    → STOP : write report                     → exit 0

  Invocation 2+  (retried job fails/succeeds)
    Thread resumes → evaluate outcome
    → EFFECTIVE   : write memory → exit 0
    → INEFFECTIVE : re-diagnose (attempt+1) → new fix → exit 1
    → LIMIT       : escalate → exit 0

SIBLING FAST PATH
─────────────────
When a sibling was RUNNING during the broadcast, its .sub was patched but
it ran with the old ClassAd. If it fails with the same error:
  .healer_{transformation}_{failure_type}.applied marker exists
  + this job's .sub already has the patched value
  + exit code matches the failure type
→ skip agent entirely → exit 1 (retry with patched .sub)

EXIT CODE CONTRACT
──────────────────
  1 → DAGMan retries (AUTO fix applied / fast path)
  0 → DAGMan stops   (ASK, STOP, ESCALATE, success)

USAGE
─────
In pegasus.properties:
    pegasus.dagman.post=/path/to/pegasus_post_script.py
    pegasus.dagman.post.arguments=$RETURN $JOB $RETRY $MAX_RETRIES \\
        /path/to/submit_dir ${wf.uuid}
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

# Project root on path for app.* imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Load project .env so LLM credentials are available in DAGMan POST context.
# DAGMan inherits the environment from condor_submit_dag at submission time,
# which may not include the user's shell exports or virtualenv .env vars.
_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv as _load_dotenv
        _load_dotenv(_ENV_FILE, override=False)   # don't override explicit shell exports
    except ImportError:
        pass   # python-dotenv not installed; env vars must be exported in the shell

TAG = "[pegasus-healer]"

# File-based log in the submit dir (set in main() once args are parsed).
# DAGMan discards POST script stderr, so this is the only reliable trace.
_log_file = None  # Optional[TextIO], opened in main()


def _log(msg: str) -> None:
    line = f"{TAG} {msg}"
    print(line, file=sys.stderr, flush=True)
    if _log_file is not None:
        print(line, file=_log_file, flush=True)


def _open_log(submit_dir: Path, job_id: str) -> None:
    """Open (or append to) {submit_dir}/{job_id}.healer.log."""
    global _log_file
    try:
        _log_file = open(submit_dir / f"{job_id}.healer.log", "a")
    except OSError:
        pass  # if we can't open it, stderr is still there


# ── Marker fast path ──────────────────────────────────────────────────────────

def _marker_fast_path(
    submit_dir: Path,
    transformation: str | None,
    exit_code: int,
    sub_content: str | None,
) -> bool:
    """
    Return True when a family fix was already broadcast to this sibling and
    the current failure is consistent with that fix.
    No agent run needed — just retry with the already-patched .sub.
    """
    if not transformation or not sub_content:
        return False

    from app.utils.pegasus.sibling_fixer import check_fast_path
    from app.utils.pegasus.sub_file import read_resource_requests
    import tempfile

    # Parse current resource values from .sub content
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sub", delete=False) as tmp:
        tmp.write(sub_content)
        tmp_path = Path(tmp.name)
    try:
        current_resources = read_resource_requests(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return check_fast_path(submit_dir, transformation, exit_code, current_resources)


# ── Thread file ───────────────────────────────────────────────────────────────

def _resolve_thread(
    submit_dir: Path,
    job_id: str,
    workflow_id: str,
    instance_id: int,
) -> tuple[str, bool]:
    """
    Return (thread_id, is_resume).

    Thread file: {submit_dir}/{job_id}.healer_thread
    Written on first invocation, read on subsequent ones.
    Anchored to source_job_instance_id so thread_id is globally unique
    even when multiple workflows share the same job_id string.
    """
    thread_file = submit_dir / f"{job_id}.healer_thread"
    if thread_file.exists():
        return thread_file.read_text().strip(), True
    thread_id = f"{workflow_id}/{instance_id}"
    thread_file.write_text(thread_id)
    return thread_id, False


# ── Graph runner ──────────────────────────────────────────────────────────────

async def _run(args: argparse.Namespace) -> int:
    from app.utils.collectors.submit_dir import collect_evidence, parse_instance_id, parse_healer_tags
    from app.utils.policies.loader import load_policy
    from app.utils.policies.engine import PolicyEngine
    from app.utils.pegasus.dagman_retry_controller import DAGManRetryController
    from app.utils.pegasus.sibling_fixer import _parse_transformation_from_content
    from app.utils.llm.universal_provider import UniversalProvider
    from app.graph.graph import create_graph_with_checkpointer

    submit_dir = Path(args.submit_dir)
    instance_id = args.job_instance_id or parse_instance_id(args.job_id)

    # ── Collect evidence ──────────────────────────────────────────────────────
    _log("collecting evidence...")
    evidence = collect_evidence(
        submit_dir=submit_dir,
        job_id=args.job_id,
        instance_id=instance_id,
        condor_job_id=args.condor_job_id,
    )
    _log(f"evidence: {evidence.available_sources}")

    # Resolve transformation (arg takes priority, then .sub file)
    transformation = args.transformation
    if not transformation and evidence.sub_file_content:
        transformation = _parse_transformation_from_content(evidence.sub_file_content)

    # ── Healer tag early exit ─────────────────────────────────────────────────
    # 'stop' and 'stop-jobs' are also enforced inside the graph's validate_policy
    # node, but checking here avoids an unnecessary full graph run.
    if evidence.sub_file_content:
        tags = parse_healer_tags(evidence.sub_file_content)
        if "stop" in tags:
            _log("tag 'stop': terminal — aborting workflow")
            return 0
        if "no-fix" in tags:
            _log("tag 'no-fix': diagnose-only run")
            # Let graph run but policy will block fix; fall through to full run

    # ── Sibling marker fast path ──────────────────────────────────────────────
    # This job may be a sibling that was RUNNING when the first fix was broadcast.
    # If its .sub is already patched and exit code matches the failure type,
    # skip agent entirely — just retry with the patched .sub.
    if _marker_fast_path(submit_dir, transformation, args.exit_code,
                         evidence.sub_file_content):
        _log("marker fast path: fix already applied → retrying with patched .sub")
        return 1

    # ── Thread ID (incident continuity) ──────────────────────────────────────
    thread_id, is_resume = _resolve_thread(submit_dir, args.job_id,
                                           args.workflow_id, instance_id)
    _log(f"{'resuming' if is_resume else 'fresh'} thread: {thread_id}")

    # ── Services ──────────────────────────────────────────────────────────────
    policy = load_policy(
        os.environ.get("POLICY_FILE")
        or str(_PROJECT_ROOT / "policies" / "remediation.yaml")
    )
    policy_engine = PolicyEngine(policy)

    retry_ctrl = DAGManRetryController(
        submit_dir=str(submit_dir),
        job_id=args.job_id,
        job_instance_id=instance_id,
    )

    def _llm(model_env: str, key_env: str, url_env: str) -> UniversalProvider:
        return UniversalProvider(
            model=os.environ.get(model_env) or os.environ.get("LLM_MODEL", ""),
            api_key=os.environ.get(key_env) or os.environ.get("LLM_API_KEY", ""),
            base_url=os.environ.get(url_env) or os.environ.get("LLM_BASE_URL", ""),
        )

    llm           = _llm("LLM_MODEL",           "LLM_API_KEY",           "LLM_BASE_URL")
    diagnosis_llm = _llm("DIAGNOSIS_LLM_MODEL",  "DIAGNOSIS_LLM_API_KEY", "DIAGNOSIS_LLM_BASE_URL")
    fix_llm       = _llm("FIX_PLANNING_LLM_MODEL","FIX_PLANNING_LLM_API_KEY","FIX_PLANNING_LLM_BASE_URL")

    # HEALER_CHECKPOINT overrides the default; SQLITE_PATH from .env is for the
    # main app and may be a relative path, so it is intentionally not used here.
    _default_checkpoint = str(Path.home() / ".pegasus_healer_checkpoint.db")
    graph = await create_graph_with_checkpointer(
        sqlite_path=os.environ.get("HEALER_CHECKPOINT", _default_checkpoint),
    )

    config = {
        "configurable": {
            "thread_id":        thread_id,
            "llm":              llm,
            "diagnosis_llm":    diagnosis_llm,
            "fix_planning_llm": fix_llm,
            "policy":           policy,
            "policy_engine":    policy_engine,
            "retry_controller": retry_ctrl,
            "submit_dir":       str(submit_dir),
            "raw_evidence":     evidence.model_dump(),
        }
    }

    # ── Graph input ───────────────────────────────────────────────────────────
    if is_resume:
        # Invocation 2+: the retried job just finished — inject its outcome
        outcome = "EFFECTIVE" if args.exit_code == 0 else "INEFFECTIVE"
        input_data: dict = {"retry_outcome": outcome}
        _log(f"retry outcome: {outcome}")
    else:
        # Invocation 1: put job identity directly in state — no WorkflowEvent needed
        input_data = {
            "incident_id":            str(uuid4()),
            "workflow_id":            args.workflow_id,
            "job_id":                 args.job_id,
            "source_job_instance_id": instance_id,
            "exit_code":              args.exit_code,
            "scheduler_id":           args.condor_job_id,
            "attempt":                1,
        }

    # ── Run graph ─────────────────────────────────────────────────────────────
    _log("running remediation graph...")
    final_state = await graph.ainvoke(input_data, config=config)

    decision = final_state.get("policy_decision")
    _log(f"decision={decision} terminal={final_state.get('terminal', False)}")

    # ── Agent report ──────────────────────────────────────────────────────────
    try:
        from app.utils.reporters.agent_report import generate_report, write_report
        report = generate_report(
            job_id=args.job_id,
            workflow_id=args.workflow_id,
            submit_dir=str(submit_dir),
            incident_id=final_state.get("incident_id", "unknown"),
            exit_code=args.exit_code,
            attempt=final_state.get("attempt", 1),
            max_retries=args.max_retries,
            decision=decision,
            failure_type=(final_state.get("diagnosis") or {}).get("failure_type"),
            confidence=(final_state.get("diagnosis") or {}).get("confidence"),
            explanation=(final_state.get("diagnosis") or {}).get("explanation"),
            evidence_sources=evidence.available_sources,
            fix_proposed=final_state.get("proposed_fix"),
            approval_url=None,
            service_url=None,
            missing_evidence=final_state.get("insufficient_evidence_fields", []),
        )
        report_path = write_report(report, submit_dir, args.job_id)
        _log(f"report → {report_path}")
    except Exception as exc:
        _log(f"warning: could not write report: {exc}")

    # ── Exit code ─────────────────────────────────────────────────────────────
    # AUTO: fix applied to .sub (and siblings) → exit 1 so DAGMan retries
    # ASK:  proposal written to report, human applies manually → exit 0
    # STOP / ESCALATE / effective outcome → exit 0
    if decision == "AUTO":
        _log("exit 1 → DAGMan retries with patched .sub")
        return 1

    if decision == "ASK":
        _log("exit 0 → proposal in report; apply manually and re-submit")
        return 0

    _log("exit 0 → terminal")
    return 0


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pegasus/DAGMan POST script — direct LangGraph remediation"
    )
    parser.add_argument("exit_code",    type=int, help="Job exit code ($RETURN)")
    parser.add_argument("job_id",                 help="DAGMan node name ($JOB)")
    parser.add_argument("retry_number", type=int, help="Current retry ($RETRY)")
    parser.add_argument("max_retries",  type=int, help="Max retries ($MAX_RETRIES)")
    parser.add_argument("submit_dir",             help="Pegasus submit directory")
    parser.add_argument("workflow_id",            help="Pegasus workflow UUID (wf_uuid)")
    parser.add_argument("--job-instance-id", type=int, default=None,
                        help="HTCondor job instance ID (parsed from job_id if omitted)")
    parser.add_argument("--condor-job-id",   default=None,
                        help="HTCondor cluster.proc (e.g. '1234.0')")
    parser.add_argument("--execution-site",  default=None)
    parser.add_argument("--transformation",  default=None)
    args = parser.parse_args()
    _open_log(Path(args.submit_dir), args.job_id)
    _log(f"invoked: exit_code={args.exit_code} retry={args.retry_number}/{args.max_retries} job={args.job_id}")

    # Job succeeded on this invocation
    if args.exit_code == 0:
        # Could still be a resume invocation (successful retry) — let graph evaluate
        # Only skip if there is no thread file (truly no prior incident)
        submit_dir = Path(args.submit_dir)
        thread_file = submit_dir / f"{args.job_id}.healer_thread"
        if not thread_file.exists():
            return 0
        # Resume: graph records EFFECTIVE outcome + writes memory
        return _run_graph(args)

    # Retry budget exhausted — hand back to DAGMan
    if args.retry_number >= args.max_retries:
        _log("retry budget exhausted — no agent run")
        return args.exit_code

    return _run_graph(args)


def _run_graph(args: argparse.Namespace) -> int:
    """Run the remediation graph, logging any crash to stderr (→ dagman.out)."""
    try:
        return asyncio.run(_run(args))
    except Exception as exc:
        import traceback
        _log(f"ERROR: remediation graph raised {type(exc).__name__}: {exc}")
        traceback.print_exc(file=sys.stderr)
        if _log_file is not None:
            traceback.print_exc(file=_log_file)
        return args.exit_code   # preserve job failure so DAGMan can retry


if __name__ == "__main__":
    sys.exit(main())
