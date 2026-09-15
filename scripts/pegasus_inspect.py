#!/usr/bin/env python3
"""
pegasus_inspect.py — Pegasus run directory inspector.

Analyses every failed job in a Pegasus submit directory and reports:
  • exit code and failure category
  • memory requested vs peak used  (with % bar + warning if > 85%)
  • disk   requested vs used
  • runtime requested vs actual    (with % bar + WARNING if > 90%)
  • last stderr lines
  • kickstart invocation data from .out.00* files (all retry attempts)

Usage
─────
    python scripts/pegasus_inspect.py  /path/to/run/submit_dir
    python scripts/pegasus_inspect.py  /path/to/run/submit_dir  --job mifaser_mifaser_ARS
    python scripts/pegasus_inspect.py  /path/to/run/submit_dir  --all    # include succeeded jobs

The script is self-contained — no imports from the app package.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────────────

BAR_WIDTH    = 30
WARN_RUNTIME = 0.90   # warn if job used >= 90% of requested runtime
WARN_MEMORY  = 0.85   # warn if job used >= 85% of requested memory
MAX_STDERR   = 2000   # chars of stderr tail to show


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class ResourceRequests:
    memory_mb:       int | None = None
    disk_mb:         int | None = None
    cpus:            int | None = None
    runtime_seconds: int | None = None
    executable:      str | None = None
    transfer_inputs: list[str] = field(default_factory=list)


@dataclass
class KickstartRecord:
    """Data parsed from one kickstart .out file."""
    attempt:        int = 0     # 0-based index of the .out.00N file
    exit_code:      int | None = None
    wall_time_s:    float | None = None
    cpu_time_s:     float | None = None
    peak_memory_mb: float | None = None
    input_files:    list[str] = field(default_factory=list)
    raw_excerpt:    str = ""


@dataclass
class JobReport:
    job_id:       str
    exit_code:    int | None
    failure_cat:  str
    requests:     ResourceRequests
    kickstart:    list[KickstartRecord]   # one per .out.00* attempt, last = most recent
    stderr_tail:  str
    sub_path:     str | None
    has_walltime_warning: bool = False
    has_memory_warning:   bool = False


# ── File discovery ─────────────────────────────────────────────────────────────

def _find_job_dirs(submit_dir: Path) -> list[Path]:
    """
    Pegasus 5.x stores job files under 00/00/.
    Fall back to the submit_dir root for older layouts.
    """
    deep = submit_dir / "00" / "00"
    return [deep] if deep.is_dir() else [submit_dir]


def _find_file(dirs: list[Path], job_id: str, ext: str) -> Path | None:
    """Find the first readable file matching common Pegasus naming conventions."""
    for d in dirs:
        candidates = sorted(d.glob(f"{job_id}_ID*.{ext}"), reverse=True)
        if candidates:
            return candidates[0]
        for name in (f"{job_id}.{ext}.000", f"{job_id}.{ext}"):
            p = d / name
            if p.exists():
                return p
    return None


def _find_out_files(dirs: list[Path], job_id: str) -> list[Path]:
    """
    Find ALL .out.00* kickstart files for a job, sorted by attempt number.
    Covers both:
      - {job}_ID{n:07d}.out          (HTCondor/Pegasus 5.x standard)
      - {job}.out.000, .out.001, ... (BLAH/grid retries)
    """
    found: list[Path] = []
    for d in dirs:
        # Standard: one .out per _ID suffix — treat each as one attempt
        id_outs = sorted(d.glob(f"{job_id}_ID*.out"))
        if id_outs:
            found.extend(id_outs)
            continue
        # BLAH: .out.000, .out.001, ...
        blah_outs = sorted(d.glob(f"{job_id}.out.[0-9]*"))
        if blah_outs:
            found.extend(blah_outs)
            continue
        # Plain fallback
        plain = d / f"{job_id}.out"
        if plain.exists():
            found.append(plain)
    return found


def _read(path: Path | None, max_bytes: int = 200_000) -> str:
    if path is None or not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_bytes:
            return f"[… {len(text) - max_bytes} chars truncated …]\n" + text[-max_bytes:]
        return text
    except OSError:
        return ""


# ── Parsers ────────────────────────────────────────────────────────────────────

def _parse_sub(content: str) -> ResourceRequests:
    r = ResourceRequests()
    if not content:
        return r

    patterns = {
        "memory_mb":       [(r"pegasus_memory_mb\s*=\s*(\d+)", int),
                            (r"request_memory\s*=\s*(\d+)", int)],
        "disk_mb":         [(r"pegasus_diskspace_mb\s*=\s*(\d+)", int),
                            (r"request_disk\s*=\s*(\d+)", int)],
        "cpus":            [(r"pegasus_cores\s*=\s*(\d+)", int),
                            (r"request_cpus\s*=\s*(\d+)", int)],
        "runtime_seconds": [(r"pegasus_job_runtime\s*=\s*(\d+)", int),
                            (r"\+MaxRuntime\s*=\s*(\d+)", int)],
        "executable":      [(r"executable\s*=\s*(.+)", str)],
    }
    for attr, pats in patterns.items():
        for pat, cast in pats:
            m = re.search(pat, content, re.IGNORECASE)
            if m:
                try:
                    setattr(r, attr, cast(m.group(1).strip()))
                    break
                except (ValueError, TypeError):
                    pass

    # transfer_input_files (may span lines with backslash continuation)
    m = re.search(
        r"^\s*transfer_input_files\s*=\s*(.+?)(?=\n\S|\Z)",
        content, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if m:
        raw = m.group(1).replace("\\\n", " ")
        r.transfer_inputs = [f.strip() for f in raw.split(",") if f.strip()]

    return r


def _parse_kickstart(content: str, attempt: int) -> KickstartRecord:
    rec = KickstartRecord(attempt=attempt, raw_excerpt=content[:400])
    if not content:
        return rec

    # Try XML parse
    try:
        xml_m = re.search(r"(<invocation\b.*?</invocation>)", content, re.DOTALL)
        if xml_m:
            root = ET.fromstring(xml_m.group(1))

            usage = root.find(".//usage")
            if usage is not None:
                maxrss = usage.get("maxrss")
                if maxrss:
                    rec.peak_memory_mb = round(int(maxrss) / 1024, 1)
                utime = float(usage.get("utime") or 0)
                stime = float(usage.get("stime") or 0)
                rec.cpu_time_s = round(utime + stime, 2)

            mainjob = root.find(".//mainjob")
            if mainjob is not None:
                rec.exit_code  = int(mainjob.get("exitcode") or mainjob.get("exit") or 0)
                dur = mainjob.get("duration")
                if dur:
                    rec.wall_time_s = round(float(dur), 2)

            rec.input_files = [
                f.get("name", "") for f in root.findall(".//file")
                if f.get("linkage") in ("input", "in") or f.get("type") == "input"
            ]
    except ET.ParseError:
        pass

    # Regex fallbacks
    if rec.peak_memory_mb is None:
        m = re.search(r"maxrss[=:\s\"]+(\d+)", content, re.IGNORECASE)
        if m:
            rec.peak_memory_mb = round(int(m.group(1)) / 1024, 1)

    if rec.wall_time_s is None:
        m = re.search(r"duration[=:\s\"]+([0-9.]+)", content, re.IGNORECASE)
        if m:
            rec.wall_time_s = round(float(m.group(1)), 2)

    if rec.exit_code is None:
        m = re.search(r"exitcode[=:\s\"]+(-?\d+)", content, re.IGNORECASE)
        if m:
            rec.exit_code = int(m.group(1))

    return rec


def _parse_exit_code(stderr: str, sub: str) -> int | None:
    m = re.search(r"PegasusLite:\s+exitcode\s+(-?\d+)", stderr)
    if m:
        return int(m.group(1))
    m = re.search(r"exit_code\s*=\s*(-?\d+)", sub, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _categorise(exit_code: int | None, stderr: str, requests: ResourceRequests,
                ks: KickstartRecord | None) -> str:
    if exit_code == 0:
        return "SUCCESS"
    s = stderr.lower()
    if "oom" in s or "killed" in s or exit_code == 137:
        if ks and requests.memory_mb and ks.peak_memory_mb:
            ratio = ks.peak_memory_mb / requests.memory_mb
            if ratio >= 0.80:
                return "OUT_OF_MEMORY"
        if exit_code == 137:
            return "OUT_OF_MEMORY (signal 9)"
    if "no space left" in s or "errno 28" in s:
        return "DISK_EXCEEDED"
    if "time limit" in s or "walltime" in s or exit_code == 140:
        return "WALLTIME_EXCEEDED"
    if "filenotfounderror" in s or "no such file or directory" in s:
        return "MISSING_INPUT"
    if "modulenotfounderror" in s or "importerror" in s or "command not found" in s:
        return "SCRIPT_ERROR"
    if "expected" in s and ("format" in s or "got" in s or "fasta" in s or "fastq" in s):
        return "DATA_MISMATCH"
    if exit_code == 139:
        return "SEGFAULT"
    if exit_code is not None and exit_code != 0:
        return f"APPLICATION_ERROR (exit {exit_code})"
    return "UNKNOWN"


# ── DAG scanner ────────────────────────────────────────────────────────────────

def _discover_jobs(submit_dir: Path) -> list[str]:
    """
    Find all job IDs from .dag files. Falls back to scanning .sub files.
    """
    job_ids: list[str] = []
    for dag_file in sorted(submit_dir.glob("*.dag")):
        for line in dag_file.read_text(errors="replace").splitlines():
            m = re.match(r"^\s*JOB\s+(\S+)", line, re.IGNORECASE)
            if m:
                job_ids.append(m.group(1))
    if not job_ids:
        # Fallback: scan for .sub files
        dirs = _find_job_dirs(submit_dir)
        for d in dirs:
            for sub in d.glob("*.sub"):
                job_ids.append(sub.stem.split("_ID")[0])
    return list(dict.fromkeys(job_ids))   # deduplicate, preserve order


# ── Report builder ─────────────────────────────────────────────────────────────

def inspect_job(submit_dir: Path, job_id: str) -> JobReport | None:
    dirs = _find_job_dirs(submit_dir)

    sub_path = _find_file(dirs, job_id, "sub")
    err_path = _find_file(dirs, job_id, "err")
    out_files = _find_out_files(dirs, job_id)

    sub_content = _read(sub_path)
    err_content = _read(err_path)

    if not sub_content and not err_content and not out_files:
        return None   # job files not found

    requests = _parse_sub(sub_content)
    kickstart_records = [
        _parse_kickstart(_read(p), attempt=i)
        for i, p in enumerate(out_files)
    ]

    last_ks = kickstart_records[-1] if kickstart_records else None
    exit_code = (
        last_ks.exit_code if last_ks and last_ks.exit_code is not None
        else _parse_exit_code(err_content, sub_content)
    )

    failure_cat = _categorise(exit_code, err_content, requests, last_ks)
    stderr_tail = err_content[-MAX_STDERR:] if err_content else "(no stderr)"

    # Warnings
    has_walltime_warn = False
    has_memory_warn   = False
    if last_ks and requests.runtime_seconds and last_ks.wall_time_s:
        ratio = last_ks.wall_time_s / requests.runtime_seconds
        has_walltime_warn = ratio >= WARN_RUNTIME
    if last_ks and requests.memory_mb and last_ks.peak_memory_mb:
        ratio = last_ks.peak_memory_mb / requests.memory_mb
        has_memory_warn = ratio >= WARN_MEMORY

    return JobReport(
        job_id=job_id,
        exit_code=exit_code,
        failure_cat=failure_cat,
        requests=requests,
        kickstart=kickstart_records,
        stderr_tail=stderr_tail,
        sub_path=str(sub_path) if sub_path else None,
        has_walltime_warning=has_walltime_warn,
        has_memory_warning=has_memory_warn,
    )


# ── Renderer ───────────────────────────────────────────────────────────────────

W = 70   # line width

def _bar(used: float | None, total: float | None, width: int = BAR_WIDTH) -> str:
    if used is None or total is None or total == 0:
        return "[" + "?" * width + "]"
    ratio = min(used / total, 1.0)
    filled = round(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    pct = ratio * 100
    return f"[{bar}] {pct:.0f}%"


def _fmt_seconds(s: float | None) -> str:
    if s is None:
        return "—"
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{sec:02d}s"
    if m:
        return f"{m}m{sec:02d}s"
    return f"{sec}s"


def _print_report(report: JobReport) -> None:
    r = report
    ks = r.kickstart[-1] if r.kickstart else None   # most recent attempt

    ok   = r.failure_cat == "SUCCESS"
    flag = "✓" if ok else "✗"

    print(f"\n{'═' * W}")
    print(f"  {flag}  {r.job_id}")
    print(f"{'─' * W}")
    print(f"  exit_code  : {r.exit_code}")
    print(f"  category   : {r.failure_cat}")
    if r.sub_path:
        print(f"  sub_file   : {r.sub_path}")

    # ── Resource utilisation ──────────────────────────────────────────────────
    req = r.requests
    print(f"\n  Resource utilisation  (last attempt):")

    # Memory
    used_mem = ks.peak_memory_mb if ks else None
    warn_m   = " ⚠ HIGH" if r.has_memory_warning else ""
    print(
        f"    memory   : {_bar(used_mem, req.memory_mb)}"
        f"  {used_mem or '—'} / {req.memory_mb or '—'} MB{warn_m}"
    )

    # Runtime
    used_rt = ks.wall_time_s if ks else None
    warn_t  = " ⚠ NEAR LIMIT" if r.has_walltime_warning else ""
    print(
        f"    runtime  : {_bar(used_rt, req.runtime_seconds)}"
        f"  {_fmt_seconds(used_rt)} / {_fmt_seconds(req.runtime_seconds)}{warn_t}"
    )

    # Disk (only if available)
    if req.disk_mb:
        print(f"    disk     : {req.disk_mb} MB requested  (actual usage not in kickstart)")

    # CPUs
    if req.cpus:
        cpu_time = ks.cpu_time_s if ks else None
        print(f"    cpus     : {req.cpus} requested  |  cpu_time={_fmt_seconds(cpu_time)}")

    # ── Kickstart attempts ────────────────────────────────────────────────────
    if r.kickstart:
        print(f"\n  Kickstart records  ({len(r.kickstart)} attempt(s), newest last):")
        for k in r.kickstart:
            suffix = "  ← LAST" if k is r.kickstart[-1] else ""
            print(
                f"    attempt {k.attempt:02d}"
                f"  exit={k.exit_code}"
                f"  wall={_fmt_seconds(k.wall_time_s)}"
                f"  mem={k.peak_memory_mb or '—'} MB"
                f"{suffix}"
            )
            if k.input_files:
                for f in k.input_files[:4]:
                    print(f"      input: {f}")
                if len(k.input_files) > 4:
                    print(f"      … and {len(k.input_files) - 4} more")
    else:
        print("\n  Kickstart records  : none found (.out / .out.00* not available)")

    # ── Transfer inputs ───────────────────────────────────────────────────────
    if req.transfer_inputs:
        print(f"\n  transfer_input_files  ({len(req.transfer_inputs)}):")
        for f in req.transfer_inputs[:6]:
            exists = Path(f).exists()
            mark   = "✓" if exists else "✗ MISSING"
            size   = f"  ({Path(f).stat().st_size // 1024} KB)" if exists else ""
            print(f"    {mark}  {f}{size}")
        if len(req.transfer_inputs) > 6:
            print(f"    … and {len(req.transfer_inputs) - 6} more")

    # ── Stderr tail ───────────────────────────────────────────────────────────
    if not ok:
        tail = r.stderr_tail.strip()
        if tail and tail != "(no stderr)":
            lines = tail.splitlines()
            # Show last 15 lines
            show = lines[-15:]
            print(f"\n  stderr (last {len(show)} lines):")
            for line in show:
                print(f"    {line}")

    print(f"{'═' * W}")


# ── Summary table ──────────────────────────────────────────────────────────────

def _print_summary(reports: list[JobReport]) -> None:
    print(f"\n{'━' * W}")
    print(f"  SUMMARY  —  {len(reports)} job(s)")
    print(f"{'━' * W}")
    col = "{:<45} {:<25} {:>5}"
    print(col.format("JOB", "CATEGORY", "EXIT"))
    print("  " + "─" * 68)
    for r in reports:
        warn = ""
        if r.has_walltime_warning:
            warn += " ⚠RT"
        if r.has_memory_warning:
            warn += " ⚠MEM"
        ok = r.failure_cat == "SUCCESS"
        flag = "✓" if ok else "✗"
        print(col.format(
            f"  {flag} {r.job_id[:43]}",
            r.failure_cat[:24] + warn,
            str(r.exit_code or "—"),
        ))
    print(f"{'━' * W}\n")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a Pegasus submit directory — resources, runtime, kickstart records."
    )
    parser.add_argument("submit_dir", help="Path to the Pegasus submit directory (run dir)")
    parser.add_argument(
        "--job", metavar="JOB_ID", default=None,
        help="Inspect only this specific job ID (DAG node name)",
    )
    parser.add_argument(
        "--all", dest="show_all", action="store_true",
        help="Include succeeded jobs (default: failed only)",
    )
    parser.add_argument(
        "--summary-only", action="store_true",
        help="Print only the summary table, no per-job details",
    )
    args = parser.parse_args()

    submit_dir = Path(args.submit_dir)
    if not submit_dir.is_dir():
        print(f"ERROR: not a directory: {submit_dir}", file=sys.stderr)
        return 1

    # Discover jobs
    if args.job:
        job_ids = [args.job]
    else:
        job_ids = _discover_jobs(submit_dir)
        if not job_ids:
            print(f"No jobs found in {submit_dir}", file=sys.stderr)
            return 1

    print(f"\npegasus_inspect  →  {submit_dir}")
    print(f"Jobs discovered : {len(job_ids)}")

    reports: list[JobReport] = []
    for jid in job_ids:
        rep = inspect_job(submit_dir, jid)
        if rep is None:
            continue
        if not args.show_all and rep.failure_cat == "SUCCESS":
            continue
        reports.append(rep)

    if not reports:
        print("\nAll jobs succeeded (use --all to show them).")
        return 0

    if not args.summary_only:
        for rep in reports:
            _print_report(rep)

    _print_summary(reports)

    # Exit non-zero if any failures
    return 1 if any(r.failure_cat != "SUCCESS" for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
