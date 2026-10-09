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

# ── Healer — opt in by keeping this block ─────────────────────────────────────
# Registers pegasus-healer as the DAGMan POST script via pegasus.properties.
# Pegasus loads this file at plan time — no .dag patching needed.
# Remove this block if you do not want the healer.
import shutil as _sh, sys as _sys
_healer = (
    _sh.which("pegasus-healer")
    or str(Path(_sys.executable).parent / "pegasus-healer")
)
props = Properties()
# dagman.post = TYPE name; dagman.post.path.TYPE = actual binary path.
# Pegasus resolves the path via POST.PATH.{TYPE} in the Dagman namespace.
props["dagman.post"]                      = "pegasus-healer"
props["dagman.post.path.pegasus-healer"]  = _healer
props["dagman.post.arguments"]            = "$RETURN $JOB $RETRY $MAX_RETRIES"
props["dagman.maxretries"]                = "3"
props.write()

BASE_DIR        = Path(".").resolve()
INPUT_DIR       = (BASE_DIR / "input").resolve()
EXECUTABLES_DIR = (BASE_DIR / "executables").resolve()
OUTPUT_DIR      = (BASE_DIR / "output").resolve()

EXEC_SITE = "local"


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
