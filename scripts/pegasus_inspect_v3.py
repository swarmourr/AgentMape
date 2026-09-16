#!/usr/bin/env python3
"""
pegasus_inspect_v3.py — Pegasus run directory inspector (LangGraph pipeline).

Runs the full LangGraph remediation graph directly — no HTTP API, no AMQP.
All LangGraph features are available: conditional edges, checkpointing,
interrupt/resume for ASK decisions, and state persistence across runs.

Differences from v2
───────────────────
  v2  uses RemediationOrchestrator (plain Python, linear pipeline)
  v3  uses the LangGraph graph directly (loops, checkpointing, all nodes)

Usage
─────
    python scripts/pegasus_inspect_v3.py  /path/to/submit_dir
    python scripts/pegasus_inspect_v3.py  /path/to/submit_dir  --agent
    python scripts/pegasus_inspect_v3.py  /path/to/submit_dir  --agent --verbose
    python scripts/pegasus_inspect_v3.py  /path/to/submit_dir  --agent --job myjob_ID0000001
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

# ── Re-use static analysis from v1 ────────────────────────────────────────────
_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from pegasus_inspect import (   # noqa: E402
    W, JobReport,
    _bar, _c, _fmt_seconds, _job_group_key,
    _load_dotenv, _print_summary, _sec, _wrap,
    _discover_failed_jobs,
    inspect_job,
)


# ── Inspector-local scheduler client ─────────────────────────────────────────
# ContextCollector requires a SchedulerClient injected via services.
# In the inspector there is no live scheduler, so we build one from the
# already-parsed JobReport (kickstart + .sub requests).

class _ReportSchedulerClient:
    """
    Fake SchedulerClient backed by the parsed JobReport.

    Satisfies the SchedulerClient Protocol without any CLI calls — returns
    real data from kickstart XML and the .sub file that inspect_job() already
    parsed.
    """

    def __init__(self, report: JobReport) -> None:
        from app.utils.scheduler.base import JobHistory, JobStatus
        ks = report.kickstart[-1] if report.kickstart else None
        req = report.requests
        self._history = JobHistory(
            exit_code=report.exit_code,
            memory_usage_mb=int(ks.peak_memory_mb) if ks and ks.peak_memory_mb else None,
            wall_time_seconds=ks.wall_time_s if ks else None,
            raw={
                # RequestMemory / RequestDisk / RequestCpus are read by
                # ContextCollector._extract_requested() via history.raw
                "RequestMemory": req.memory_mb,
                "RequestDisk":   req.disk_mb,
                "RequestCpus":   req.cpus,
            },
        )

    def get_job_status(self, cluster_id: str):
        return None  # not in queue — inspector runs post-failure

    def update_job_resources(self, cluster_id: str, resources: dict) -> bool:
        return False

    def get_job_history(self, cluster_id: str):
        return self._history

    def cancel_job(self, cluster_id: str) -> bool:
        return False


# ── Node label colours ─────────────────────────────────────────────────────────

_NODE_COLORS: dict[str, str] = {
    "collect_context":              "dim",
    "run_rule_classifier":          "cyan",
    "retrieve_memories":            "dim",
    "run_diagnosis_agent":          "yellow",
    "lookup_fix_catalog":           "dim",
    "run_fix_planner":              "yellow",
    "validate_policy":              "cyan",
    "apply_fix":                    "green",
    "authorize_retry":              "green",
    "generate_proposal_report":     "yellow",
    "evaluate_outcome":             "dim",
    "write_memory":                 "dim",
    "handle_insufficient_evidence": "red",
    "escalate":                     "red",
}


def _node_label(name: str) -> str:
    color = _NODE_COLORS.get(name, "white")
    return _c(color, _c("bold", name))


# ── LangGraph runner ──────────────────────────────────────────────────────────

async def _run_graph(
    submit_dir: Path,
    report: JobReport,
    services: dict,
    verbose: bool,
    checkpoint_path: str,
) -> dict:
    """
    Run the LangGraph remediation graph for one failed job.
    Job identity is passed directly in state — no WorkflowEvent/AMQP needed.
    """
    from app.langgraph import create_graph_with_checkpointer
    from app.utils.collectors.submit_dir import collect_evidence, parse_healer_tags

    instance_id = int(re.search(r"_ID(\d+)$", report.job_id).group(1)) \
                  if re.search(r"_ID(\d+)$", report.job_id) else 1

    evidence = collect_evidence(
        submit_dir=str(submit_dir),
        job_id=report.job_id,
        instance_id=instance_id,
    )

    tags = parse_healer_tags(evidence.sub_file_content)
    if verbose and tags:
        print(f"    [tags] {', '.join(tags)}", flush=True)

    svc = {
        **services,
        "scheduler_client": _ReportSchedulerClient(report),
        "raw_evidence":     evidence.model_dump(mode="json"),
        "submit_dir":       str(submit_dir),
        "job_tags":         tags,
    }

    graph = await create_graph_with_checkpointer(sqlite_path=checkpoint_path)

    thread_id = f"{submit_dir.name}/{report.job_id}"
    config = {"configurable": {**svc, "thread_id": thread_id}}

    initial_state = {
        "incident_id":            str(uuid4()),
        "workflow_id":            submit_dir.name,
        "job_id":                 report.job_id,
        "source_job_instance_id": instance_id,
        "exit_code":              report.exit_code,
        "scheduler_id":           None,   # no live scheduler in inspector
        "attempt":                1,
    }

    final_state: dict = {}

    if verbose:
        # Stream node-by-node outputs
        async for chunk in graph.astream(initial_state, config=config):
            for node_name, node_output in chunk.items():
                print(f"\n  {_node_label(node_name)}")
                # Show key state changes
                for key in ("diagnosis", "proposed_fix", "policy_decision", "overlay"):
                    if key in node_output:
                        val = node_output[key]
                        if isinstance(val, dict):
                            short = {k: v for k, v in list(val.items())[:4]}
                            print(f"    {_c('dim', key)}: {short}")
                        else:
                            print(f"    {_c('dim', key)}: {val}")
                final_state.update(node_output)
    else:
        final_state = await graph.ainvoke(initial_state, config=config)

    return final_state


# ── Renderer ──────────────────────────────────────────────────────────────────

def _print_v3_result(state: dict) -> None:
    """Render the final LangGraph state."""

    # ── Diagnosis ─────────────────────────────────────────────────────────────
    diag = state.get("diagnosis") or {}
    if diag:
        ft      = diag.get("failure_type", "UNKNOWN")
        conf    = diag.get("confidence", 0.0)
        source  = diag.get("source", "")
        ft_col  = "green" if ft == "SUCCESS" else "red"
        _sec(_c("bold", _c("yellow", "Diagnosis")), f"{conf:.0%}  [{source}]")
        print(f"  type    : {_c('bold', _c(ft_col, ft))}")
        if diag.get("explanation"):
            _wrap(diag["explanation"], "  reason  : ")
        if diag.get("requires_human_review"):
            print(f"  {_c('red', 'requires human review')}")
        for ev in (diag.get("missing_evidence") or [])[:3]:
            print(f"  missing : {_c('dim', ev)}")

    # ── Fix proposal ──────────────────────────────────────────────────────────
    fix = state.get("proposed_fix") or {}
    if fix:
        action   = fix.get("action", "")
        fix_conf = fix.get("confidence")
        conf_str = f"{fix_conf:.0%}" if fix_conf is not None else ""
        approval = fix.get("requires_approval", True)
        tag      = _c("yellow", "[ASK]") if approval else _c("green", "[AUTO]")
        _sec(_c("bold", _c("cyan", "Fix Plan")), conf_str)
        print(f"  action  : {_c('bold', action)}  {tag}")
        if fix.get("justification"):
            _wrap(fix["justification"], "  reason  : ")
        changes = {**(fix.get("parameters") or {}), **(fix.get("proposed_configuration") or {})}
        if changes:
            print("  changes :")
            for k, v in changes.items():
                print(f"    {_c('dim', k)} = {_c('bold', str(v))}")

    # ── Policy ────────────────────────────────────────────────────────────────
    pd = state.get("policy_decision")
    if pd:
        pr = state.get("policy_record") or {}
        dc = {"AUTO": "green", "ASK": "yellow", "STOP": "red", "ESCALATE": "red"}.get(pd, "white")
        _sec(_c("bold", "Policy"), _c("bold", _c(dc, f"→ {pd}")))
        reason = pr.get("reason", "")
        if reason and reason != "All policy checks passed.":
            _wrap(reason, "  ")
        for chk in (pr.get("checks_failed") or []):
            print(f"  {_c('red', 'x')} {chk}")

    # ── Tags ──────────────────────────────────────────────────────────────────
    ctx = state.get("context") or {}
    tags = ctx.get("job_tags") or []
    if tags:
        _sec(_c("bold", "Healer Tags"))
        for tag in tags:
            colors = {"no-fix": "yellow", "stop": "red", "stop-jobs": "red"}
            print(f"  {_c(colors.get(tag, 'dim'), tag)}")

    # ── Applied overlay (AUTO path) ───────────────────────────────────────────
    overlay = state.get("overlay") or {}
    if overlay:
        _sec(_c("bold", _c("green", "Applied Fix")))
        if overlay.get("hash_before") and overlay.get("hash_after"):
            print(f"  config hash: {overlay['hash_before'][:8]}… → {overlay['hash_after'][:8]}…")
        new_cfg = overlay.get("new_config") or {}
        for k, v in new_cfg.items():
            print(f"  {_c('dim', k)} = {_c('bold', str(v))}")
        siblings = state.get("siblings_patched")
        if siblings is not None:
            print(f"  siblings    : {siblings} patched proactively")

    # ── ASK path — proposal report generated, not applied ────────────────────
    if state.get("terminal") and pd == "ASK":
        _sec(_c("bold", _c("yellow", "Proposal Report")))
        print(f"  {_c('yellow', 'Fix proposal generated — not applied (scope=ASK)')}")
        print(f"  Apply manually or re-run with broader policy scope.")

    # ── Terminal state ────────────────────────────────────────────────────────
    if state.get("terminal") and pd not in ("ASK",):
        _sec(_c("bold", "Done"))
        print(f"  {_c('dim', 'graph complete — no further action')}")


def _print_report_v3(report: JobReport, state: dict | None) -> None:
    """Full job report — static sections + LangGraph result."""
    r   = report
    ks  = r.kickstart[-1] if r.kickstart else None
    ok  = r.failure_cat == "SUCCESS"
    req = r.requests

    flag = _c("green", "✓") if ok else _c("red", "✗")
    print(f"\n{'═' * W}")
    print(f"  {flag}  {_c('bold', r.job_id)}")
    print(f"{'═' * W}")

    _sec("Job")
    cat_col = "green" if ok else "red"
    print(f"  exit_code : {r.exit_code}    category : {_c(cat_col, _c('bold', r.failure_cat))}")
    if r.sub_path:
        print(f"  sub_file  : {r.sub_path}")

    _sec("Resources", "(last attempt)")
    used_mem = ks.peak_memory_mb if ks else None
    warn_m   = _c("red", "  HIGH") if r.has_memory_warning else ""
    print(f"  memory   {_bar(used_mem, req.memory_mb)}  {used_mem or '—'} / {req.memory_mb or '—'} MB{warn_m}")
    used_rt  = ks.wall_time_s if ks else None
    warn_t   = _c("red", "  NEAR LIMIT") if r.has_walltime_warning else ""
    print(f"  runtime  {_bar(used_rt, req.runtime_seconds)}  {_fmt_seconds(used_rt)} / {_fmt_seconds(req.runtime_seconds)}{warn_t}")

    if not ok:
        tail = r.stderr_tail.strip()
        if tail and tail != "(no stderr)":
            lines = tail.splitlines()[-15:]
            _sec("Stderr", f"(last {len(lines)} lines)")
            for line in lines:
                print(f"  {line}")

    if state is not None:
        _print_v3_result(state)

    print(f"\n{'═' * W}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pegasus inspector v3 — full LangGraph pipeline, no API"
    )
    parser.add_argument("submit_dir")
    parser.add_argument("--job",          metavar="JOB_ID", default=None)
    parser.add_argument("--all",          dest="show_all", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--agent",        action="store_true",
                        help="Run LangGraph pipeline (requires app package + LLM config)")
    parser.add_argument("--model",     metavar="MODEL", default=None)
    parser.add_argument("--api-key",   metavar="KEY",   default=None)
    parser.add_argument("--base-url",  metavar="URL",   default=None)
    parser.add_argument("--checkpoint", metavar="PATH", default="checkpoints.db",
                        help="SQLite checkpoint file (default: checkpoints.db)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    submit_dir = Path(args.submit_dir)
    if not submit_dir.is_dir():
        print(f"ERROR: not a directory: {submit_dir}", file=sys.stderr)
        return 1

    # ── Agent setup ───────────────────────────────────────────────────────────
    agent_enabled = False
    services: dict = {}
    model = ""

    if args.agent:
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        _load_dotenv(project_root)
        logging.disable(logging.WARNING)

        model       = args.model    or os.environ.get("LLM_MODEL", "ollama/llama3.3:70b")
        api_key     = args.api_key  or os.environ.get("LLM_API_KEY")
        base_url    = args.base_url or os.environ.get("LLM_BASE_URL")
        policy_file = os.environ.get("POLICY_FILE", "policies/remediation.yaml")
        conf_thresh = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.80"))

        try:
            from app.utils.llm.universal_provider import UniversalProvider
            from app.utils.policies.loader import load_policy
            from app.utils.policies.engine import PolicyEngine
            from app.utils.pegasus.fake import FakePegasusRetryController

            llm              = UniversalProvider(model=model, api_key=api_key, base_url=base_url)
            diagnosis_llm    = UniversalProvider(
                model=os.environ.get("DIAGNOSIS_LLM_MODEL") or model,
                api_key=os.environ.get("DIAGNOSIS_LLM_API_KEY") or api_key,
                base_url=os.environ.get("DIAGNOSIS_LLM_BASE_URL") or base_url,
            )
            fix_planning_llm = UniversalProvider(
                model=os.environ.get("FIX_PLANNING_LLM_MODEL") or model,
                api_key=os.environ.get("FIX_PLANNING_LLM_API_KEY") or api_key,
                base_url=os.environ.get("FIX_PLANNING_LLM_BASE_URL") or base_url,
            )
            policy_cfg    = load_policy(policy_file)
            policy_engine = PolicyEngine(policy_cfg, conf_thresh)

            services = {
                "llm":               llm,
                "diagnosis_llm":     diagnosis_llm,
                "fix_planning_llm":  fix_planning_llm,
                "policy":            policy_cfg,
                "policy_engine":     policy_engine,
                "retry_controller":  FakePegasusRetryController(),
            }
            agent_enabled = True
        except ImportError as exc:
            print(f"WARNING: --agent disabled — {exc}", file=sys.stderr)

    print(f"\npegasus_inspect_v3  →  {submit_dir}")
    if agent_enabled:
        print(f"Model              :  {model}")
        print(f"Pipeline           :  LangGraph (collect→classify→fix→policy)")
        print(f"Checkpoint         :  {args.checkpoint}")

    # ── Job discovery ─────────────────────────────────────────────────────────
    if args.job:
        inspect_ids = [args.job]
    else:
        all_ids, failed_ids, status_src = _discover_failed_jobs(submit_dir)
        if not all_ids:
            print(f"No jobs found in {submit_dir}", file=sys.stderr)
            return 1
        print(f"Jobs total      : {len(all_ids)}")
        print(f"Status source   : {status_src}")
        inspect_ids = failed_ids if (failed_ids and not args.show_all) else all_ids

    # ── Inspect ───────────────────────────────────────────────────────────────
    all_reports: list[JobReport] = []
    for jid in inspect_ids:
        rep = inspect_job(submit_dir, jid)
        if rep is not None:
            all_reports.append(rep)

    failed_reports = [r for r in all_reports if r.failure_cat != "SUCCESS"]
    reports        = all_reports if args.show_all else failed_reports

    if not reports:
        print("\nAll jobs succeeded (use --all to show them).")
        return 0

    if not args.summary_only:
        for rep in reports:
            state: dict | None = None

            if agent_enabled and rep.failure_cat != "SUCCESS":
                label = rep.job_id
                print(f"\n  [v3-pipeline] {label} …", end="", flush=True)
                try:
                    state = asyncio.run(
                        _run_graph(
                            submit_dir=submit_dir,
                            report=rep,
                            services=services,
                            verbose=args.verbose,
                            checkpoint_path=args.checkpoint,
                        )
                    )
                    pd = state.get("policy_decision", "?")
                    print(f" done  [{pd}]")
                except Exception as exc:
                    print(f" ERROR: {exc}")

            _print_report_v3(rep, state)

    _print_summary(reports)
    return 1 if failed_reports else 0


if __name__ == "__main__":
    sys.exit(main())
