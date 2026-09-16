#!/usr/bin/env python3
"""
pegasus_tags.py — Inspect +PegasusHealerTags across a Pegasus submit directory.

Scans every .sub file, extracts healer tags, and shows what behaviour
the self-healer agent will apply for each tagged job.

Usage
─────
    python scripts/pegasus_tags.py  /path/to/submit_dir
    python scripts/pegasus_tags.py  /path/to/submit_dir  --all      # include untagged jobs
    python scripts/pegasus_tags.py  /path/to/submit_dir  --tag stop  # filter by tag
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── ANSI helpers ──────────────────────────────────────────────────────────────

W = 72

COLORS = {
    "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
    "cyan": "\033[36m", "bold": "\033[1m", "dim": "\033[2m", "reset": "\033[0m",
}


def _c(color: str, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def _sec(title: str, suffix: str = "") -> None:
    gap   = W - len(re.sub(r"\033\[[0-9;]*m", "", title)) - len(suffix) - 4
    right = f" {suffix}" if suffix else ""
    print(f"\n{_c('dim', '──')} {title} {_c('dim', '─' * max(gap, 2))}{right}")


# ── Tag definitions ───────────────────────────────────────────────────────────

KNOWN_TAGS: dict[str, dict] = {
    "no-fix": {
        "color":       "yellow",
        "description": "Diagnose only — no fix proposed or applied.",
        "effect":      "PolicyEngine → STOP (diagnosis report only)",
    },
    "stop": {
        "color":       "red",
        "description": "Abort the entire workflow if this job fails.",
        "effect":      "PolicyEngine → STOP + workflow abort signal",
    },
    "stop-jobs": {
        "color":       "red",
        "description": "Stop all jobs of the same transformation family.",
        "effect":      "PolicyEngine → STOP + family stop signal",
    },
}


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse_tags(sub_content: str) -> list[str]:
    m = re.search(
        r'^\s*\+PegasusHealerTags\s*=\s*["\']?([^"\'#\n]+)["\']?',
        sub_content,
        re.MULTILINE | re.IGNORECASE,
    )
    if not m:
        return []
    return [t.strip().lower() for t in m.group(1).split(",") if t.strip()]


def _parse_transformation(sub_content: str) -> str | None:
    m = re.search(r'^\s*#\s*transformation\s*[=:]\s*(.+)$', sub_content,
                  re.MULTILINE | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fallback: read executable basename
    m = re.search(r'^\s*executable\s*=\s*(.+)$', sub_content,
                  re.MULTILINE | re.IGNORECASE)
    if m:
        return Path(m.group(1).strip()).name
    return None


# ── Scanner ───────────────────────────────────────────────────────────────────

def scan_submit_dir(submit_dir: Path) -> list[dict]:
    """
    Walk all .sub files under submit_dir and extract tag information.
    Returns a list of dicts, one per job.
    """
    results = []
    sub_files = sorted(submit_dir.rglob("*.sub"))

    for sub_path in sub_files:
        # Skip DAGMan .dag.sub files
        if sub_path.name.endswith(".dag.sub"):
            continue
        try:
            content = sub_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        tags           = _parse_tags(content)
        transformation = _parse_transformation(content)
        job_id         = sub_path.stem  # filename without .sub

        results.append({
            "job_id":         job_id,
            "sub_path":       str(sub_path.relative_to(submit_dir)),
            "tags":           tags,
            "transformation": transformation,
            "unknown_tags":   [t for t in tags if t not in KNOWN_TAGS],
        })

    return results


# ── Renderer ──────────────────────────────────────────────────────────────────

def _print_job(job: dict) -> None:
    tags = job["tags"]
    if not tags:
        print(f"  {_c('dim', job['job_id'])}  {_c('dim', '(no tags)')}")
        return

    tag_str = "  ".join(
        _c(KNOWN_TAGS.get(t, {}).get("color", "dim"), f"[{t}]")
        for t in tags
    )
    print(f"  {_c('bold', job['job_id'])}")
    if job["transformation"]:
        print(f"    transformation : {_c('dim', job['transformation'])}")
    print(f"    tags           : {tag_str}")
    print(f"    sub file       : {_c('dim', job['sub_path'])}")

    for tag in tags:
        info = KNOWN_TAGS.get(tag)
        if info:
            print(f"    {_c(info['color'], tag):30s} {info['description']}")
            print(f"      {_c('dim', info['effect'])}")
        else:
            print(f"    {_c('yellow', tag):30s} {_c('yellow', 'unknown tag — ignored by agent')}")


def _print_summary(jobs: list[dict]) -> None:
    tagged   = [j for j in jobs if j["tags"]]
    no_fix   = [j for j in jobs if "no-fix"    in j["tags"]]
    stop     = [j for j in jobs if "stop"      in j["tags"]]
    stopjobs = [j for j in jobs if "stop-jobs" in j["tags"]]
    unknown  = [j for j in jobs if j["unknown_tags"]]

    print(f"\n{'━' * W}")
    print(f"  Total jobs   : {len(jobs)}")
    print(f"  Tagged       : {len(tagged)}")
    if no_fix:
        print(f"  no-fix       : {len(no_fix)}")
    if stop:
        print(f"  stop         : {_c('red', str(len(stop)))}  (workflow abort on failure)")
    if stopjobs:
        print(f"  stop-jobs    : {_c('red', str(len(stopjobs)))}  (family stop on failure)")
    if unknown:
        names = ", ".join(t for j in unknown for t in j["unknown_tags"])
        print(f"  {_c('yellow', 'unknown tags')} : {names}")
    print(f"{'━' * W}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect +PegasusHealerTags in a Pegasus submit directory."
    )
    parser.add_argument("submit_dir")
    parser.add_argument("--all",  dest="show_all", action="store_true",
                        help="Include untagged jobs in output")
    parser.add_argument("--tag",  metavar="TAG", default=None,
                        help="Show only jobs with this specific tag")
    args = parser.parse_args()

    submit_dir = Path(args.submit_dir)
    if not submit_dir.is_dir():
        print(f"ERROR: not a directory: {submit_dir}", file=sys.stderr)
        return 1

    jobs = scan_submit_dir(submit_dir)
    if not jobs:
        print(f"No .sub files found in {submit_dir}", file=sys.stderr)
        return 1

    # Filter
    if args.tag:
        jobs = [j for j in jobs if args.tag.lower() in j["tags"]]
        if not jobs:
            print(f"No jobs with tag '{args.tag}' found.")
            return 0

    tagged   = [j for j in jobs if j["tags"]]
    untagged = [j for j in jobs if not j["tags"]]

    print(f"\npegasus_tags  →  {submit_dir}")
    print(f"Jobs scanned  :  {len(jobs)}")

    if not tagged:
        print(f"\n  {_c('dim', 'No healer tags found.')}")
        print(f"  {_c('dim', 'Agent will run the full pipeline for every failure:')}")
        print(f"  {_c('dim', '  diagnose → plan fix → policy check → AUTO / ASK / STOP')}")
    else:
        _sec(_c("bold", "Tagged Jobs"), f"({len(tagged)})")
        for job in tagged:
            _print_job(job)
            print()

    if args.show_all and untagged:
        _sec(_c("dim", "Untagged Jobs"), f"({len(untagged)})")
        for job in untagged:
            _print_job(job)

    _print_summary(jobs)

    has_stop = any("stop" in j["tags"] or "stop-jobs" in j["tags"] for j in jobs)
    return 1 if has_stop else 0


if __name__ == "__main__":
    sys.exit(main())
