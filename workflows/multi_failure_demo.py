"""
Multi-failure demo workflow.

Demonstrates the healer handling two distinct failure types in sequence
on the same job:

  Attempt 0 → exit 137 (OOM)          → healer increases memory  → retry
  Attempt 1 → exit 1   (disk full)    → healer increases disk    → retry
  Attempt 2 → success

HOW TO RUN
──────────
    python workflows/multi_failure_demo.py

Requirements:
  - Pegasus 5.x installed and on PATH
  - HTCondor running locally (or configured execution site)
  - executables/multi_fail is chmod +x
"""

from Pegasus.api import *
from pathlib import Path
import sys

BASE_DIR        = Path(".").resolve()
INPUT_DIR       = (BASE_DIR / "input").resolve()
EXECUTABLES_DIR = (BASE_DIR / "executables").resolve()
OUTPUT_DIR      = (BASE_DIR / "output").resolve()

EXEC_SITE = "local"

# dagman.post = pegasus-healer is registered in ~/.pegasus/properties by
# activate.sh — Pegasus loads it automatically at plan time.

# ── Input file ────────────────────────────────────────────────────────────────
INPUT_DIR.mkdir(parents=True, exist_ok=True)
(INPUT_DIR / "f.in").write_text(
    "Input data for the multi-failure demo workflow.\n"
)

# ── Transformation catalog ─────────────────────────────────────────────────────
tc = TransformationCatalog()
tc.add_transformations(
    Transformation("multi_fail").add_sites(
        TransformationSite(
            EXEC_SITE,
            str(EXECUTABLES_DIR / "multi_fail"),
            is_stageable=False,
        )
    ),
)

# ── Files ──────────────────────────────────────────────────────────────────────
fin  = File("f.in")
fout = File("f.out")

# ── Job — starts with conservative resources so both fixes are meaningful ──────
job = (
    Job("multi_fail")
    .add_args("-T", "2", "-i", fin, "-o", str(fout))
    .add_inputs(fin)
    .add_outputs(fout)
    .add_profiles(Namespace.CONDOR, key="request_memory", value="256")
    .add_profiles(Namespace.CONDOR, key="request_disk",   value="1024")
)

# ── Workflow ───────────────────────────────────────────────────────────────────
wf = Workflow("multi-failure-demo")
wf.add_transformation_catalog(tc)
wf.add_jobs(job)

try:
    wf.write()
    wf.graph(include_files=True, label="xform-id", output="graph.png")
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
