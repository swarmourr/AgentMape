"""
sibling_demo.py — Sibling-fix demo workflow for PegasusAgent healer.

Failure scenario
────────────────
  Three parallel compute jobs (A, B, C) all use the same transformation
  and all share the same intentionally-low request_memory=256 MB.

  compute_A fails on attempt 0:
    stderr → "Killed" / "out of memory (signal 9)"
    exit   → 137

  Healer detects OUT_OF_MEMORY via exit code 137 (confidence ≥ 0.95),
  increases request_memory in compute_A.sub (AUTO, no human approval),
  AND broadcasts the same patch to compute_B.sub and compute_C.sub
  (sibling broadcast via sibling_fixer).

  compute_B / compute_C may still fail with exit 137 if they were
  already running when the broadcast happened — but their .sub files
  are already patched, so the fast path kicks in:
    marker exists + .sub patched + exit 137 → skip agent → exit 1 (retry)

  After all three succeed, merge aggregates their outputs → workflow
  completes (SUCCESS=*).

Usage
─────
  cd /path/to/PegasusAgent
  python workflows/sibling_demo.py
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
props["dagman.post"]           = _healer
props["dagman.post.arguments"] = "$RETURN $JOB $RETRY $MAX_RETRIES"
props["dagman.maxretries"]     = "3"
props.write()

BASE_DIR        = Path(".").resolve()
INPUT_DIR       = (BASE_DIR / "input").resolve()
EXECUTABLES_DIR = (BASE_DIR / "executables").resolve()
OUTPUT_DIR      = (BASE_DIR / "output").resolve()

EXEC_SITE = "local"


# ── Input file ────────────────────────────────────────────────────────────────
INPUT_DIR.mkdir(exist_ok=True)
(INPUT_DIR / "data.in").write_text(
    "Shared input dataset for the sibling-demo workflow.\n"
    "All three compute jobs consume this same file.\n"
)

# ── Transformation catalog ────────────────────────────────────────────────────
tc = TransformationCatalog()
tc.add_transformations(
    Transformation("compute").add_sites(
        TransformationSite("local", str(EXECUTABLES_DIR / "compute"), is_stageable=False)
    ),
    Transformation("merge").add_sites(
        TransformationSite("local", str(EXECUTABLES_DIR / "merge"), is_stageable=False)
    ),
)

# ── Workflow ──────────────────────────────────────────────────────────────────
wf = Workflow("sibling-demo")
wf.add_transformation_catalog(tc)

fin = File("data.in")

# Three intermediate outputs — one per sibling
fa = File("A.out")
fb = File("B.out")
fc = File("C.out")

# Final aggregated output
fout = File("merged.out")

# compute_A / B / C: same transformation, same low memory so healer must patch
# each one.  Sibling broadcast means only compute_A triggers the full agent;
# compute_B and compute_C use the fast path on their first retry failure.
_MEM = "256"   # intentionally below what the job needs

job_a = (
    Job("compute", _id="compute_A")
        .add_args("-T", "2", "-i", fin, "-o", fa)
        .add_inputs(fin)
        .add_outputs(fa, stage_out=False)
        .add_profiles(Namespace.CONDOR, key="request_memory", value=_MEM)
)

job_b = (
    Job("compute", _id="compute_B")
        .add_args("-T", "2", "-i", fin, "-o", fb)
        .add_inputs(fin)
        .add_outputs(fb, stage_out=False)
        .add_profiles(Namespace.CONDOR, key="request_memory", value=_MEM)
)

job_c = (
    Job("compute", _id="compute_C")
        .add_args("-T", "2", "-i", fin, "-o", fc)
        .add_inputs(fin)
        .add_outputs(fc, stage_out=False)
        .add_profiles(Namespace.CONDOR, key="request_memory", value=_MEM)
)

job_merge = (
    Job("merge")
        .add_args("-T", "2", "-i", fa, "-i", fb, "-i", fc, "-o", fout)
        .add_inputs(fa, fb, fc)
        .add_outputs(fout)
        .add_profiles(Namespace.CONDOR, key="request_memory", value="512")
)

wf.add_jobs(job_a, job_b, job_c, job_merge)

# ── Plan ──────────────────────────────────────────────────────────────────────
try:
    wf.write()
    wf.graph(include_files=True, label="xform-id", output="sibling_demo_graph.png")
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
