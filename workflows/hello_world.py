#!/usr/bin/env python3
"""
Hello-world Pegasus workflow — local execution with PegasusAgent healer.

Generates all catalogs inline (no external .pegasusrc needed):
  - workflow.yml      — Abstract workflow
  - sites.yml         — Site catalog  (local site)
  - tc.yml            — Transformation catalog (hello / world executables)
  - rc.yml            — Replica catalog  (f.in input file)
  - pegasus.properties — Pegasus config + healer post script
  - graph.png         — Dependency graph visualisation

Run
───
    python workflows/hello_world.py
    python -m workflows.hello_world

Then plan and execute:
    pegasus-plan --conf pegasus.properties \\
                 --dir submit --dax workflow.yml \\
                 --exec-site local --submit
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from Pegasus.api import (
    Directory,
    File,
    FileServer,
    Job,
    Operation,
    PegasusClientError,
    Properties,
    ReplicaCatalog,
    Site,
    SiteCatalog,
    Transformation,
    TransformationCatalog,
    TransformationSite,
    Workflow,
)

from workflows.healer import add_healer_to_job, configure_healer_properties

logging.basicConfig(level=logging.WARNING)

# ── Directories ───────────────────────────────────────────────────────────────
BASE_DIR        = _ROOT
INPUT_DIR       = BASE_DIR / "input"
EXECUTABLES_DIR = BASE_DIR / "executables"
OUTPUT_DIR      = BASE_DIR / "output"
SCRATCH_DIR     = BASE_DIR / "scratch"
SUBMIT_DIR      = BASE_DIR / "submit"

MAX_RETRIES = 3


def generate() -> None:
    for d in (INPUT_DIR, OUTPUT_DIR, SCRATCH_DIR, SUBMIT_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # ── Input file ─────────────────────────────────────────────────────────────
    fin_path = INPUT_DIR / "f.in"
    fin_path.write_text(
        "This is the contents of the input file for the hello world workflow!\n"
    )

    # ── Site catalog ───────────────────────────────────────────────────────────
    sc = SiteCatalog()
    local = (
        Site("local")
        .add_directories(
            Directory(Directory.SHARED_SCRATCH, str(SCRATCH_DIR)).add_file_servers(
                FileServer(f"file://{SCRATCH_DIR}", Operation.ALL)
            ),
            Directory(Directory.LOCAL_STORAGE, str(OUTPUT_DIR)).add_file_servers(
                FileServer(f"file://{OUTPUT_DIR}", Operation.ALL)
            ),
        )
    )
    sc.add_sites(local)
    sc.write()

    # ── Transformation catalog ─────────────────────────────────────────────────
    tc = TransformationCatalog()
    tc.add_transformations(
        Transformation("hello").add_sites(
            TransformationSite(
                "local", str(EXECUTABLES_DIR / "hello"), is_stageable=False
            )
        ),
        Transformation("world").add_sites(
            TransformationSite(
                "local", str(EXECUTABLES_DIR / "world"), is_stageable=False
            )
        ),
    )
    tc.write()

    # ── Replica catalog ────────────────────────────────────────────────────────
    rc = ReplicaCatalog()
    rc.add_replica("local", "f.in", f"file://{fin_path}")
    rc.write()

    # ── Pegasus properties ─────────────────────────────────────────────────────
    props = Properties()
    props["pegasus.catalog.site.file"]           = "sites.yml"
    props["pegasus.catalog.transformation.file"] = "tc.yml"
    props["pegasus.catalog.replica.file"]        = "rc.yml"
    # "." = DAGMan CWD at runtime, which is always the run's submit directory
    configure_healer_properties(props, submit_dir=".", max_retries=MAX_RETRIES)
    props.write()

    # ── Files ──────────────────────────────────────────────────────────────────
    fin    = File("f.in")
    finter = File("f.inter")
    fout   = File("f.out")

    # ── Jobs ───────────────────────────────────────────────────────────────────
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

    try:
        wf.write()
        wf.graph(include_files=True, label="xform-id", output="graph.png")
    except PegasusClientError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    print("\nWorkflow generated successfully.")
    print("\nTo plan and run:")
    print(
        f"  pegasus-plan --conf pegasus.properties "
        f"--dir {SUBMIT_DIR} --dax workflow.yml "
        f"--exec-site local --submit"
    )


if __name__ == "__main__":
    generate()
