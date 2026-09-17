from Pegasus.api import *
import sys
from pathlib import Path

import logging

logging.basicConfig(level=logging.DEBUG)

# we specify directories for inputs, executables and outputs
# - directory where to pick up the inputs from a directory.
# - directory where the executables that the workflow uses are placed.
# - directory where the outputs should be placed.

BASE_DIR = Path(".").resolve()
INPUT_DIR = Path(BASE_DIR /  "input").resolve()
EXECUTABLES_DIR = Path(BASE_DIR / ".." /  "executables").resolve()
OUTPUT_DIR = Path(BASE_DIR /  "output").resolve()

# the execution site where you job to run.
# local means the jobs run on ACCESS Pegasus itself.
#
# compute means the jobs execution on the compute site
# defined in your site catalog. In the ACCESS Pegasus
# setup, it means that jobs will run on a node provisioned
# from an ACCESS site such as jetstream.
EXEC_SITE = "local"

# What compute backend we are using based on Pegasus configuration
props = Properties.load(Path.home() / ".pegasusrc")
resource_site_catalog = props["pegasus.catalog.site.repo.file"]

# --- Healer post script -------------------------------------------------------
from workflows.healer import configure_healer_properties, add_healer_to_job

configure_healer_properties(props, submit_dir=".", max_retries=3)
props.write()

# generate a simple input file for the workflow
with open("{}/f.in".format(INPUT_DIR), "w") as f:
    f.write("This is the contents of the input file for the hello world workflow!")

# --- Workflow -----------------------------------------------------------------
wf = Workflow("hello-world")

fin = File("f.in")
finter = File("f.inter")
fout = File("f.out")

job_hello = add_healer_to_job(
    Job("hello")\
                    .add_args("-T", "3", "-i", fin, "-o {}".format(finter))\
                    .add_inputs(fin)\
                    .add_outputs(finter, stage_out=False)\
                    .add_profiles(Namespace.CONDOR, key="request_memory", value="1")
)

job_world = add_healer_to_job(
    Job("world")\
                    .add_args("-T", "3", "-i", finter, "-o {}".format(fout))\
                    .add_inputs(finter)\
                    .add_outputs(fout)
)

wf.add_jobs(job_hello, job_world)

# --- Visualize the Workflow ---------------------------------------------------
try:
    wf.write()
    wf.graph(include_files=True, label="xform-id", output="graph.png")
except PegasusClientError as e:
    print(e)

# --- Plan and Submit ----------------------------------------------------------
try:
    wf.plan(input_dirs=[INPUT_DIR], sites=[EXEC_SITE], transformations_dir=EXECUTABLES_DIR,\
            output_dir=OUTPUT_DIR, submit=True)
except PegasusClientError as e:
    print(e)
