#!/usr/bin/env python3
"""
Hello-world Pegasus workflow with PegasusAgent healer post script.

Generates:
  - workflow.yml      — Abstract workflow (DAX)
  - graph.png         — Dependency graph visualisation
  - pegasus.properties — Pegasus configuration (healer post script baked in)

Run
───
    python workflows/hello_world.py
    python -m workflows.hello_world
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Allow running as a plain script (python workflows/hello_world.py)
# as well as a module (python -m workflows.hello_world)
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from Pegasus.api import File, Job, PegasusClientError, Properties, Workflow

from workflows.healer import add_healer_to_job, configure_healer_properties

logging.basicConfig(level=logging.DEBUG)

# ── Directories ───────────────────────────────────────────────────────────────
BASE_DIR        = Path(".").resolve()
INPUT_DIR       = (BASE_DIR / "input").resolve()
EXECUTABLES_DIR = (BASE_DIR / ".." / "executables").resolve()
OUTPUT_DIR      = (BASE_DIR / "output").resolve()
SUBMIT_DIR      = (BASE_DIR / "submit").resolve()   # Pegasus submit directory

# ── Execution site ─────────────────────────────────────────────────────────────
# "local"   → jobs run on this machine
# "compute" → jobs run on the provisioned ACCESS/HTCondor site
EXEC_SITE = "local"

# ── Healer settings ────────────────────────────────────────────────────────────
MAX_RETRIES = 3


def generate() -> None:
    # ── Directories ────────────────────────────────────────────────────────────
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SUBMIT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Pegasus properties ─────────────────────────────────────────────────────
    # Load existing ~/.pegasusrc (site catalog, replica catalog, etc.)
    # then add the healer post script on top.
    props = Properties.load(Path.home() / ".pegasusrc")
    configure_healer_properties(props, submit_dir=SUBMIT_DIR, max_retries=MAX_RETRIES)
    props.write()

    # ── Input file ─────────────────────────────────────────────────────────────
    (INPUT_DIR / "f.in").write_text(
        "This is the contents of the input file for the hello world workflow!"
    )

    # ── Files ──────────────────────────────────────────────────────────────────
    fin    = File("f.in")
    finter = File("f.inter")
    fout   = File("f.out")

    # ── Jobs ───────────────────────────────────────────────────────────────────
    # add_healer_to_job() sets the DAGMan RETRY count so the healer post
    # script gets invoked on each failure up to MAX_RETRIES times.
    job_hello = add_healer_to_job(
        Job("hello")
        .add_args("-T", "3", "-i", fin, "-o", finter)
        .add_inputs(fin)
        .add_outputs(finter, stage_out=False),
        max_retries=MAX_RETRIES,
    )

    job_world = add_healer_to_job(
        Job("world")
        .add_args("-T", "3", "-i", finter, "-o", fout)
        .add_inputs(finter)
        .add_outputs(fout),
        max_retries=MAX_RETRIES,
    )

    # ── Workflow ────────────────────────────────────────────────────────────────
    wf = Workflow("hello-world")
    wf.add_jobs(job_hello, job_world)

    # ── Write + visualise ──────────────────────────────────────────────────────
    try:
        wf.write()
        wf.graph(include_files=True, label="xform-id", output="graph.png")
    except PegasusClientError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    print("Workflow written.  Next steps:")
    print(f"  pegasus-plan --dir {SUBMIT_DIR} --dax workflow.yml --exec-site {EXEC_SITE}")
    print(f"  pegasus-run  {SUBMIT_DIR}")


if __name__ == "__main__":
    generate()
