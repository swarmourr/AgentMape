"""
disk_demo.py — Disk-exhaustion demo workflow for PegasusAgent healer.

Failure scenario
────────────────
  analyze fails on attempt 0:
    stderr → "No space left on device"
    exit   → 1

  Healer detects DISK_EXCEEDED via stderr pattern (confidence ≥ 0.95),
  increases request_disk in the .sub file (AUTO, no human approval),
  DAGMan retries → analyze succeeds → report runs → workflow completes.

Usage
─────
  cd /path/to/PegasusAgent
  python workflows/disk_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import logging
logging.basicConfig(level=logging.DEBUG)

from Pegasus.api import (
    File, Job, Namespace, PegasusClientError,
    TransformationCatalog, TransformationSite, Transformation, Workflow,
)

BASE_DIR        = Path(".").resolve()
INPUT_DIR       = (BASE_DIR / "input").resolve()
EXECUTABLES_DIR = (BASE_DIR / "executables").resolve()
OUTPUT_DIR      = (BASE_DIR / "output").resolve()

EXEC_SITE = "local"

# dagman.post = pegasus-healer is registered in ~/.pegasus/properties by
# activate.sh — Pegasus loads it automatically at plan time.

# ── Input file ────────────────────────────────────────────────────────────────
INPUT_DIR.mkdir(exist_ok=True)
(INPUT_DIR / "data.in").write_text(
    "Sample dataset for the disk-demo workflow.\n"
    "Each record requires significant scratch space to process.\n"
)

# ── Transformation catalog ────────────────────────────────────────────────────
tc = TransformationCatalog()
tc.add_transformations(
    Transformation("analyze").add_sites(
        TransformationSite("local", str(EXECUTABLES_DIR / "analyze"), is_stageable=False)
    ),
    Transformation("report").add_sites(
        TransformationSite("local", str(EXECUTABLES_DIR / "report"), is_stageable=False)
    ),
)

# ── Workflow ──────────────────────────────────────────────────────────────────
wf = Workflow("disk-demo")
wf.add_transformation_catalog(tc)

fin    = File("data.in")
finter = File("data.inter")
fout   = File("data.out")

# analyze: low request_disk so the healer has room to increase it
job_analyze = (
    Job("analyze")
        .add_args("-T", "2", "-i", fin, "-o", finter)
        .add_inputs(fin)
        .add_outputs(finter, stage_out=False)
        .add_profiles(Namespace.CONDOR, key="request_memory", value="256")
        .add_profiles(Namespace.CONDOR, key="request_disk",   value="512")   # 512 MB — intentionally small
)

job_report = (
    Job("report")
        .add_args("-T", "2", "-i", finter, "-o", fout)
        .add_inputs(finter)
        .add_outputs(fout)
        .add_profiles(Namespace.CONDOR, key="request_memory", value="256")
)

wf.add_jobs(job_analyze, job_report)

# ── Plan ──────────────────────────────────────────────────────────────────────
try:
    wf.write()
    wf.graph(include_files=True, label="xform-id", output="disk_demo_graph.png")
except PegasusClientError as e:
    print(e)

try:
    wf.plan(
        input_dirs=[INPUT_DIR],
        sites=[EXEC_SITE],
        output_dir=OUTPUT_DIR,
        submit=True,
    )
except PegasusClientError as e:
    print(e)
    sys.exit(1)
