from Pegasus.api import *
import sys
from pathlib import Path

import logging

logging.basicConfig(level=logging.DEBUG)

# we specify directories for inputs, executables and outputs
# - directory where to pick up the inputs from a directory.
# - directory where the executables that the workflow uses are placed.
# - directory where the outputs should be placed.

# ── Healer — opt in by keeping this block ─────────────────────────────────────
# Registers pegasus-healer as the DAGMan POST script via pegasus.properties.
# Pegasus loads this file at plan time — no .dag patching needed.
# Remove this block if you do not want the healer.
props = Properties()
props["dagman.post"]           = "pegasus-healer"
props["dagman.post.arguments"] = "$RETURN $JOB $RETRY $MAX_RETRIES"
props["dagman.maxretries"]     = "3"
props.write()

BASE_DIR = Path(".").resolve()
INPUT_DIR = Path(BASE_DIR /  "input").resolve()
EXECUTABLES_DIR = Path(BASE_DIR / "executables").resolve()
OUTPUT_DIR = Path(BASE_DIR /  "output").resolve()

# the execution site where you job to run.
# local means the jobs run on ACCESS Pegasus itself.
#
# compute means the jobs execution on the compute site
# defined in your site catalog. In the ACCESS Pegasus
# setup, it means that jobs will run on a node provisioned
# from an ACCESS site such as jetstream.
EXEC_SITE = "local"

# code needed.

# generate a simple input file for the workflow
INPUT_DIR.mkdir(parents=True, exist_ok=True)
with open("{}/f.in".format(INPUT_DIR), "w") as f:
    f.write("This is the contents of the input file for the hello world workflow!")

# --- Transformation catalog ---------------------------------------------------
tc = TransformationCatalog()
tc.add_transformations(
    Transformation("hello").add_sites(
        TransformationSite("local", str(EXECUTABLES_DIR / "hello"), is_stageable=False)
    ),
    Transformation("world").add_sites(
        TransformationSite("local", str(EXECUTABLES_DIR / "world"), is_stageable=False)
    ),
)

# --- Workflow -----------------------------------------------------------------
wf = Workflow("hello-world")
wf.add_transformation_catalog(tc)

fin = File("f.in")
finter = File("f.inter")
fout = File("f.out")

job_hello = Job("hello")\
                    .add_args("-T", "3", "-i", fin, "-o {}".format(finter))\
                    .add_inputs(fin)\
                    .add_outputs(finter, stage_out=False)\
                    .add_profiles(Namespace.CONDOR, key="request_memory", value="256")

job_world = Job("world")\
                    .add_args("-T", "3", "-i", finter, "-o {}".format(fout))\
                    .add_inputs(finter)\
                    .add_outputs(fout)

wf.add_jobs(job_hello, job_world)

# --- Visualize the Workflow ---------------------------------------------------
try:
    wf.write()
    wf.graph(include_files=True, label="xform-id", output="graph.png")
except PegasusClientError as e:
    print(e)

# --- Plan and submit ----------------------------------------------------------
# dagman.post = pegasus-healer is already in pegasus.properties above,
# so Pegasus writes it into every job node of the .dag at plan time.
try:
    wf.plan(input_dirs=[INPUT_DIR], sites=[EXEC_SITE],
            output_dir=OUTPUT_DIR, submit=True)
except PegasusClientError as e:
    print(e)
    sys.exit(1)
