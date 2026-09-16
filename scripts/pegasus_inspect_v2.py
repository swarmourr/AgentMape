#!/usr/bin/env python3
"""
pegasus_inspect_v2.py — Pegasus run directory inspector (subagent architecture).

Uses a four-subagent pipeline instead of the monolithic DiagnosisAgent:
  ① Observator    — gathers raw evidence via ReAct tool loop
  ② Classifier    — determines failure_type (rules first, LLM fallback)
  ③ Fix Planner   — proposes fix action + configuration changes
  ④ Policy Engine — validates safety (AUTO / ASK / STOP / ESCALATE)
  ⑤ Clone cache   — reuses result for identical failure patterns

Static analysis (file parsing, resource bars, kickstart records) is
identical to v1 — this file only replaces the agent pipeline.

Usage
─────
    python scripts/pegasus_inspect_v2.py  /path/to/submit_dir
    python scripts/pegasus_inspect_v2.py  /path/to/submit_dir  --agent
    python scripts/pegasus_inspect_v2.py  /path/to/submit_dir  --agent --verbose
    python scripts/pegasus_inspect_v2.py  /path/to/submit_dir  --job mifaser_mifaser_ARS --agent
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

# ── Re-use all static-analysis infrastructure from v1 ─────────────────────────
# v1 is guarded by  if __name__ == "__main__"  so importing is safe.
_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from pegasus_inspect import (   # noqa: E402
    BAR_WIDTH, MAX_STDERR, W, WARN_MEMORY, WARN_RUNTIME,
    JobReport,
    _bar, _c, _find_job_dirs, _fmt_seconds, _job_group_key,
    _load_dotenv, _print_block, _print_summary, _sec, _wrap,
    _discover_failed_jobs, _discover_jobs,
    inspect_job,
)


# ── Verbose LLM wrapper (labels each call by subagent) ────────────────────────

class _VerboseLLMProvider:
    """Wraps any LLMProvider and prints each call with its subagent label."""

    def __init__(self, inner, model: str, label: str = "") -> None:
        self._inner = inner
        self._model = model
        self._label = label
        self._step  = 0

    def for_agent(self, label: str) -> "_VerboseLLMProvider":
        """Return a copy labelled for a specific subagent."""
        v = _VerboseLLMProvider(self._inner, self._model, label)
        v._step = self._step
        return v

    async def complete(self, messages, response_model, *, temperature=0.0):
        self._step += 1
        tag = f"[{self._label}  step {self._step}]" if self._label else f"[step {self._step}]"

        last = messages[-1] if messages else {}
        _print_block(
            _c("bold", _c("blue", f"── Prompt {tag} ──")),
            str(last.get("content", "")),
            "blue",
            max_chars=500,
        )
        print(
            f"\n  {_c('cyan', tag)}  model={_c('bold', self._model)}"
            f"  msgs={len(messages)}",
            flush=True,
        )

        result = await self._inner.complete(messages, response_model, temperature=temperature)

        action     = getattr(result, "action", None)
        thought    = getattr(result, "thought", "") or ""
        confidence = getattr(result, "confidence", None)

        if thought:
            _print_block(_c("bold", _c("yellow", "── Thought ──")), thought, "yellow", max_chars=600)

        if action:
            ac = "red" if action in ("conclude", "report") else "green"
            cs = f"  confidence={confidence:.2f}" if confidence is not None else ""
            print(f"  {_c('cyan', tag)} → action={_c(ac, _c('bold', action))}{cs}", flush=True)

        return result


# ── Orchestrator runner ────────────────────────────────────────────────────────

async def _run_orchestrator(
    submit_dir: Path,
    report: JobReport,
    orchestrator,        # RemediationOrchestrator instance (shared across jobs)
    model: str,
    verbose: bool,
) -> dict:
    import logging
    logging.disable(logging.WARNING)

    from uuid import uuid4
    from app.utils.collectors.submit_dir import collect_evidence, parse_instance_id
    from app.utils.models.context import FailureContext, ResourceRequest, ResourceUsage

    ks  = report.kickstart[-1] if report.kickstart else None
    req = report.requests
    instance_id = parse_instance_id(report.job_id)
    group_key   = _job_group_key(report)

    ctx = FailureContext(
        incident_id=uuid4(),
        workflow_id=str(submit_dir.name),
        job_id=report.job_id,
        job_instance_id=instance_id,
        exit_code=report.exit_code,
        requested_resources=ResourceRequest(
            memory_mb=req.memory_mb,
            disk_mb=req.disk_mb,
            cpus=req.cpus,
            runtime_seconds=req.runtime_seconds,
        ),
        measured_resources=ResourceUsage(
            peak_memory_mb=int(ks.peak_memory_mb) if ks and ks.peak_memory_mb else None,
            runtime_seconds=int(ks.wall_time_s) if ks and ks.wall_time_s else None,
        ),
    )
    evidence = collect_evidence(
        submit_dir=str(submit_dir),
        job_id=report.job_id,
        instance_id=instance_id,
    )

    if verbose:
        sources = evidence.available_sources
        print(f"    [evidence] sources: {', '.join(sources) or 'none'}", flush=True)

    result = await orchestrator.run(ctx, evidence, group_key=group_key)

    # Collect script patches from fix proposal
    patches = [
        {
            "file_path":         p.file_path,
            "patch_description": p.patch_description,
            "original_content":  p.original_content,
            "patched_content":   p.patched_content,
        }
        for p in result.fix_proposal.script_patches
    ]

    return {
        # Observations
        "observations": {
            "key_findings":           result.observations.key_findings,
            "stderr_signals":         result.observations.stderr_signals,
            "resource_pressure":      result.observations.resource_pressure,
            "infrastructure_signals": result.observations.infrastructure_signals,
            "data_signals":           result.observations.data_signals,
            "script_signals":         result.observations.script_signals,
            "sources_checked":        result.observations.sources_checked,
        },
        # Diagnosis
        "failure_type":          str(result.diagnosis.failure_type.value),
        "confidence":            result.diagnosis.confidence,
        "explanation":           result.diagnosis.explanation or "",
        "requires_human_review": result.diagnosis.requires_human_review,
        "missing_evidence":      result.diagnosis.missing_evidence,
        # Fix plan
        "fix_action":                 result.fix_proposal.action.value,
        "fix_justification":          result.fix_proposal.justification,
        "fix_parameters":             result.fix_proposal.parameters or {},
        "fix_proposed_configuration": result.fix_proposal.proposed_configuration or {},
        "fix_confidence":             result.fix_proposal.confidence,
        "fix_requires_approval":      result.fix_proposal.requires_approval,
        "script_patches":             patches,
        # Policy
        "policy_decision":     result.policy_decision,
        "policy_reason":       result.policy_reason,
        "policy_checks_failed": result.policy_checks_failed,
        # Clone
        "cloned_from": result.cloned_from,
    }


# ── Renderer ──────────────────────────────────────────────────────────────────

def _print_v2_diagnosis(diag: dict) -> None:
    cloned_from = diag.get("cloned_from")

    # ── Observations ──────────────────────────────────────────────────────────
    obs = diag.get("observations", {})
    findings = obs.get("key_findings", [])
    if findings or obs.get("sources_checked"):
        _sec(_c("bold", _c("magenta", "Observations")),
             f"sources: {', '.join(obs.get('sources_checked', []))}")
        for f in findings:
            print(f"  • {f}")
        for s in obs.get("stderr_signals", []):
            print(f"  stderr  : {_c('dim', s)}")
        if obs.get("resource_pressure"):
            print(f"  pressure: {obs['resource_pressure']}")
        for s in obs.get("infrastructure_signals", []):
            print(f"  infra   : {_c('yellow', s)}")
        for s in obs.get("data_signals", []):
            print(f"  data    : {_c('yellow', s)}")
        for s in obs.get("script_signals", []):
            print(f"  script  : {_c('yellow', s)}")

    # ── AI Diagnosis ──────────────────────────────────────────────────────────
    conf_pct = f"{diag['confidence']:.0%}" if diag.get("confidence") is not None else "—"
    _sec(_c("bold", _c("yellow", "AI Diagnosis")), conf_pct)
    if cloned_from:
        print(f"  {_c('dim', f'reused from {cloned_from}')}")
    ft_color = "green" if diag["failure_type"] == "SUCCESS" else "red"
    print(f"  type    : {_c('bold', _c(ft_color, diag['failure_type']))}")
    if diag.get("explanation"):
        _wrap(diag["explanation"], "  reason  : ")
    if diag.get("requires_human_review"):
        print(f"  {_c('red', '⚠  requires human review')}")
    for ev in diag.get("missing_evidence", [])[:3]:
        print(f"  missing : {_c('dim', ev)}")

    # ── Fix Plan ──────────────────────────────────────────────────────────────
    if diag.get("fix_action"):
        fix_conf = diag.get("fix_confidence")
        fix_conf_str = f"{fix_conf:.0%}" if fix_conf is not None else ""
        _sec(_c("bold", _c("cyan", "Fix Plan")), fix_conf_str)
        approval     = diag.get("fix_requires_approval")
        approval_tag = _c("yellow", "[ASK]") if approval else _c("green", "[AUTO]")
        print(f"  action  : {_c('bold', diag['fix_action'])}  {approval_tag}")
        if diag.get("fix_justification"):
            _wrap(diag["fix_justification"], "  reason  : ")
        changes = {**(diag.get("fix_parameters") or {}), **(diag.get("fix_proposed_configuration") or {})}
        if changes:
            print(f"  changes :")
            for k, v in changes.items():
                print(f"    {_c('dim', k)} = {_c('bold', str(v))}")

    # ── Policy ────────────────────────────────────────────────────────────────
    pd = diag.get("policy_decision")
    if pd:
        dc = {"AUTO": "green", "ASK": "yellow", "STOP": "red", "ESCALATE": "red"}.get(pd, "white")
        _sec(_c("bold", "Policy"), _c("bold", _c(dc, f"→ {pd}")))
        reason = diag.get("policy_reason", "")
        if reason and reason != "All policy checks passed.":
            _wrap(reason, "  ")
        for chk in diag.get("policy_checks_failed", []):
            print(f"  {_c('red', '✗')} {chk}")

    # ── Script patches ────────────────────────────────────────────────────────
    for patch in diag.get("script_patches", []):
        import difflib
        _sec(_c("bold", _c("cyan", "Suggested Patch")))
        print(f"  file    : {patch['file_path']}")
        print(f"  desc    : {patch['patch_description']}")
        print(f"  {_c('dim', '⚠  requires human approval before applying')}")
        diff = list(difflib.unified_diff(
            patch["original_content"].splitlines(),
            patch["patched_content"].splitlines(),
            fromfile="original", tofile="patched", lineterm="",
        ))
        if diff:
            print()
            for line in diff:
                if line.startswith("+") and not line.startswith("+++"):
                    print(f"  {_c('green', line)}")
                elif line.startswith("-") and not line.startswith("---"):
                    print(f"  {_c('red', line)}")
                else:
                    print(f"  {_c('dim', line)}")


def _print_report_v2(report: JobReport, agent_diag: dict | None = None) -> None:
    """Same static sections as v1, AI sections replaced with v2 renderer."""
    r   = report
    ks  = r.kickstart[-1] if r.kickstart else None
    ok  = r.failure_cat == "SUCCESS"
    req = r.requests

    flag = _c("green", "✓") if ok else _c("red", "✗")
    print(f"\n{'═' * W}")
    print(f"  {flag}  {_c('bold', r.job_id)}")
    print(f"{'═' * W}")

    _sec("Job")
    cat_color = "green" if ok else "red"
    print(f"  exit_code  : {r.exit_code}    category : {_c(cat_color, _c('bold', r.failure_cat))}")
    if r.sub_path:
        print(f"  sub_file   : {r.sub_path}")

    _sec("Resources", "(last attempt)")
    used_mem = ks.peak_memory_mb if ks else None
    warn_m   = _c("red", "  ⚠ HIGH") if r.has_memory_warning else ""
    print(f"  memory   {_bar(used_mem, req.memory_mb)}  {used_mem or '—'} / {req.memory_mb or '—'} MB{warn_m}")
    used_rt = ks.wall_time_s if ks else None
    warn_t  = _c("red", "  ⚠ NEAR LIMIT") if r.has_walltime_warning else ""
    print(f"  runtime  {_bar(used_rt, req.runtime_seconds)}  {_fmt_seconds(used_rt)} / {_fmt_seconds(req.runtime_seconds)}{warn_t}")
    if req.disk_mb:
        print(f"  disk     {req.disk_mb} MB requested")
    if req.cpus:
        print(f"  cpus     {req.cpus} requested  │  cpu_time={_fmt_seconds(ks.cpu_time_s if ks else None)}")

    if r.kickstart:
        _sec("Attempts", f"({len(r.kickstart)} total)")
        for k in r.kickstart:
            last = _c("dim", "  ← last") if k is r.kickstart[-1] else ""
            print(f"  {k.attempt:02d}  exit={k.exit_code}  wall={_fmt_seconds(k.wall_time_s)}  mem={k.peak_memory_mb or '—'} MB{last}")
            for f in k.input_files[:4]:
                print(f"      input: {f}")
            if len(k.input_files) > 4:
                print(f"      … and {len(k.input_files) - 4} more")

    has_tf  = bool(req.transfer_inputs)
    has_stg = bool(r.staging)
    if has_tf or has_stg:
        missing_tf  = sum(1 for f in req.transfer_inputs if not Path(f).exists())
        missing_stg = sum(1 for e in r.staging if e.exists_local is False)
        err_stg     = sum(1 for e in r.staging if e.staging_error)
        issues      = missing_tf + missing_stg + err_stg
        _sec("Input Files", _c("red", f"⚠ {issues} issue(s)") if issues else "")
        if has_tf:
            print(f"  transfer_input_files  ({len(req.transfer_inputs)}):")
            for f in req.transfer_inputs[:6]:
                exists = Path(f).exists()
                mark   = _c("green", "✓") if exists else _c("red", "✗ MISSING")
                size   = f"  ({Path(f).stat().st_size // 1024} KB)" if exists else ""
                print(f"    {mark}  {f}{size}")
            if len(req.transfer_inputs) > 6:
                print(f"    {_c('dim', f'… and {len(req.transfer_inputs) - 6} more')}")
        if has_stg:
            print(f"  staging  ({len(r.staging)} file(s)):")
            for entry in r.staging[:10]:
                mark = (_c("red", "✗ MISSING") if entry.exists_local is False
                        else (_c("green", "✓") if entry.exists_local else _c("dim", "~")))
                size_str = f"  ({entry.size_bytes // 1024} KB)" if entry.size_bytes else ""
                chk_str  = f"  sha256:{entry.checksum[:12]}…" if entry.checksum else ""
                print(f"    {mark}  {entry.lfn}{size_str}{chk_str}")
                pfn_base = entry.pfn.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
                if pfn_base != entry.lfn:
                    print(f"         pfn: {_c('dim', entry.pfn)}")
                if entry.staging_error:
                    print(f"         {_c('red', '⚠')}  {entry.staging_error}")
            if len(r.staging) > 10:
                print(f"    {_c('dim', f'… and {len(r.staging) - 10} more')}")

    if not ok:
        tail = r.stderr_tail.strip()
        if tail and tail != "(no stderr)":
            lines = tail.splitlines()
            show  = lines[-15:]
            _sec("Stderr", f"(last {len(show)} lines)")
            for line in show:
                print(f"  {line}")

    if agent_diag is not None:
        _print_v2_diagnosis(agent_diag)

    print(f"\n{'═' * W}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pegasus inspector v2 — four-subagent pipeline (Observator / Classifier / FixPlanner / Policy)"
    )
    parser.add_argument("submit_dir")
    parser.add_argument("--job",   metavar="JOB_ID", default=None)
    parser.add_argument("--all",   dest="show_all", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--agent", action="store_true",
                        help="Run subagent pipeline (requires app package + LLM config)")
    parser.add_argument("--model",    metavar="MODEL", default=None)
    parser.add_argument("--api-key",  metavar="KEY",   default=None)
    parser.add_argument("--base-url", metavar="URL",   default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    submit_dir = Path(args.submit_dir)
    if not submit_dir.is_dir():
        print(f"ERROR: not a directory: {submit_dir}", file=sys.stderr)
        return 1

    # ── Agent setup ───────────────────────────────────────────────────────────
    agent_enabled   = False
    orchestrator    = None
    agent_model     = ""
    agent_api_key   = None
    agent_base_url  = None

    if args.agent:
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        _load_dotenv(project_root)

        agent_model   = args.model   or os.environ.get("LLM_MODEL", "") or "ollama/llama3.3:70b"
        agent_api_key = args.api_key or os.environ.get("LLM_API_KEY") or None
        agent_base_url = args.base_url or os.environ.get("LLM_BASE_URL") or None
        policy_file   = os.environ.get("POLICY_FILE", "policies/remediation.yaml")
        conf_thresh   = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.80"))

        try:
            from app.utils.llm.universal_provider import UniversalProvider
            from app.agents.orchestrator import RemediationOrchestrator

            llm_base = UniversalProvider(model=agent_model, api_key=agent_api_key, base_url=agent_base_url)
            llm      = _VerboseLLMProvider(llm_base, agent_model) if args.verbose else llm_base

            # One orchestrator instance — clone cache persists across all jobs
            orchestrator  = RemediationOrchestrator(llm, policy_file=policy_file, confidence_threshold=conf_thresh)
            agent_enabled = True
        except ImportError as exc:
            print(f"WARNING: --agent disabled — {exc}", file=sys.stderr)

    print(f"\npegasus_inspect_v2  →  {submit_dir}")
    if agent_enabled:
        print(f"Agent model        :  {agent_model}")
        print(f"Architecture       :  Observator → Classifier → FixPlanner → Policy")

    # ── Job discovery ─────────────────────────────────────────────────────────
    if args.job:
        inspect_ids = [args.job]
        all_ids     = inspect_ids
        _at_risk: list[str] = []
    else:
        all_ids, fast_failed_ids, status_source = _discover_failed_jobs(submit_dir)
        if not all_ids:
            print(f"No jobs found in {submit_dir}", file=sys.stderr)
            return 1
        print(f"Jobs total      : {len(all_ids)}")
        print(f"Status source   : {status_source}")
        if fast_failed_ids:
            print(f"Failed detected : {len(fast_failed_ids)}"
                  f"  (skipping {len(all_ids) - len(fast_failed_ids)} succeeded)")
        inspect_ids = fast_failed_ids if (fast_failed_ids and not args.show_all) else all_ids
        _failed_fam = {re.sub(r"[_-]?\d+$", "", j) for j in (fast_failed_ids or [])}
        _at_risk    = [j for j in all_ids if j not in set(inspect_ids)
                       and re.sub(r"[_-]?\d+$", "", j) in _failed_fam]

    # ── Inspect + (optionally) run subagent pipeline ──────────────────────────
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
            agent_diag: dict | None = None

            if agent_enabled and rep.failure_cat != "SUCCESS" and orchestrator is not None:
                group_key  = _job_group_key(rep)
                is_clone   = group_key in orchestrator._clone_cache
                clone_note = f"  (clone of {orchestrator._clone_cache[group_key].observations.sources_checked})" if is_clone else ""
                print(f"\n  [v2-pipeline] {rep.job_id}{clone_note} …", end="", flush=True)
                try:
                    agent_diag = asyncio.run(
                        _run_orchestrator(submit_dir, rep, orchestrator, agent_model, args.verbose)
                    )
                    pd = agent_diag.get("policy_decision", "?")
                    print(f" done  [{pd}]")
                except Exception as exc:
                    print(f" ERROR: {exc}")
                    agent_diag = {
                        "failure_type": "AGENT_ERROR", "confidence": 0.0,
                        "explanation": str(exc), "observations": {},
                        "fix_action": None, "policy_decision": None,
                        "script_patches": [], "missing_evidence": [],
                        "policy_checks_failed": [], "cloned_from": None,
                    }

            _print_report_v2(rep, agent_diag=agent_diag)

    _print_summary(reports)

    if _at_risk:
        print(f"{'━' * W}")
        print(f"  ⚠  AT-RISK  —  same transformation as a failing group")
        print(f"{'━' * W}")
        for jid in _at_risk:
            family = re.sub(r"[_-]?\d+$", "", jid)
            sib    = next((r for r in failed_reports if re.sub(r"[_-]?\d+$", "", r.job_id) == family), None)
            ft     = sib.failure_cat if sib else "unknown"
            print(f"  {jid}  →  sibling failed with: {ft}")
        print(f"{'━' * W}\n")

    return 1 if failed_reports else 0


if __name__ == "__main__":
    sys.exit(main())
