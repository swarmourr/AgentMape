"""
hello_world_oom.py — Pegasus healer OOM validation workflow.

Demonstrates the healer's OUT_OF_MEMORY auto-fix loop:

  Attempt 1  request_memory=256 MB  →  OOM (exit 137)  →  healer patches .sub → 384 MB
  Attempt 2  request_memory=384 MB  →  OOM (exit 137)  →  healer patches .sub → 576 MB
  Attempt 3  request_memory=576 MB  →  succeeds ✓

The trick: the submit file sets JOB_MEMORY_MB=$(request_memory) in the
environment line.  HTCondor expands $(request_memory) to the current value
*before* the job starts, so the oom_alloc executable always knows its budget.
When the healer patches request_memory, the next retry automatically gets the
updated value — no script changes needed.
"""

from Pegasus.api import *
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)

BASE_DIR        = Path(__file__).resolve().parent.parent
INPUT_DIR       = BASE_DIR / "input"
EXECUTABLES_DIR = BASE_DIR / "executables"
OUTPUT_DIR      = BASE_DIR / "output"

EXEC_SITE = "local"

# ── Healer properties (same as hello_world.py) ────────────────────────────────
import shutil as _sh, sys as _sys
# Prefer bin/pegasus-healer (bash wrapper) — it always sets POLICY_FILE and
# PYTHONPATH correctly regardless of whether activate.sh was sourced.
_healer = (
    str(BASE_DIR / "bin" / "pegasus-healer")
    if (BASE_DIR / "bin" / "pegasus-healer").exists()
    else (_sh.which("pegasus-healer") or str(Path(_sys.executable).parent / "pegasus-healer"))
)
_PROPS_PATH = str(BASE_DIR / "pegasus.properties")
try:
    props = Properties.load(Path.home() / ".pegasusrc")
except Exception:
    props = Properties()

props["dagman.post"]                              = "pegasus-healer"
props["dagman.post.path.pegasus-healer"]          = _healer
props["dagman.post.arguments"]                    = "$RETURN $JOB $RETRY $MAX_RETRIES"
props["dagman.maxretries"]                        = "3"
props["dagman.retry"]                             = "3"
# sharedfs: plain cp staging — no pegasus-transfer needed.
props["pegasus.data.configuration"]               = "sharedfs"
# Disable strict worker-package version check for dev builds.
props["pegasus.transfer.worker.package.strict"]   = "false"
props.write(_PROPS_PATH)

# ── Input / output files ───────────────────────────────────────────────────────
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

with open(INPUT_DIR / "oom_trigger.txt", "w") as f:
    f.write("OOM test input\n")

# ── Workflow ───────────────────────────────────────────────────────────────────
wf = Workflow("hello-world-oom")

fin  = File("oom_trigger.txt")
fout = File("oom_result.txt")

job_oom = (
    Job("oom_alloc")
    .add_args("-o", fout)
    .add_inputs(fin)
    .add_outputs(fout)
    # Start with 256 MB — below the 400 MB the executable needs.
    # The healer will bump this 1.5× each retry until the job succeeds.
    .add_profiles(Namespace.CONDOR, key="request_memory", value="256")
    # Pass the current request_memory into the job environment so oom_alloc
    # can read its own budget.  HTCondor expands $(request_memory) before
    # the job starts; the healer patches request_memory in the .sub file,
    # so the next retry automatically gets the updated value.
    .add_profiles(Namespace.ENV, key="JOB_MEMORY_MB", value="$(request_memory)")
)

wf.add_jobs(job_oom)

# ── Visualize ─────────────────────────────────────────────────────────────────
try:
    wf.write()
    wf.graph(include_files=True, label="xform-id", output="graph_oom.png")
except PegasusClientError as e:
    print(e)

# ── Plan and submit ────────────────────────────────────────────────────────────
try:
    wf.plan(
        conf=_PROPS_PATH,
        input_dirs=[INPUT_DIR],
        sites=[EXEC_SITE],
        transformations_dir=EXECUTABLES_DIR,
        output_dir=OUTPUT_DIR,
        submit=True,
    )
except PegasusClientError as e:
    print(e)
    sys.exit(1)
