from Pegasus.api import *
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)

# we specify directories for inputs, executables and outputs
BASE_DIR        = Path(__file__).resolve().parent.parent
INPUT_DIR       = BASE_DIR / "input"
EXECUTABLES_DIR = BASE_DIR / "executables"
OUTPUT_DIR      = BASE_DIR / "output"

# the execution site where your job will run.
EXEC_SITE = "local"

# ── Healer ────────────────────────────────────────────────────────────────────
# Load the machine's existing Pegasus config and only overlay healer settings.
# Do NOT override pegasus.data.configuration or pegasus.gridstart — the
# machine's ~/.pegasusrc already has the correct values for this site.
import shutil as _sh, sys as _sys
_healer = (
    _sh.which("pegasus-healer")
    or str(Path(_sys.executable).parent / "pegasus-healer")
)
_PROPS_PATH = str(BASE_DIR / "pegasus.properties")
try:
    props = Properties.load(Path.home() / ".pegasusrc")
except Exception:
    props = Properties()
props["dagman.post"]                     = "pegasus-healer"
props["dagman.post.path.pegasus-healer"] = _healer
props["dagman.post.arguments"]           = "$RETURN $JOB $RETRY $MAX_RETRIES"
props["dagman.maxretries"]               = "3"
props["dagman.retry"]                    = "3"
props.write(_PROPS_PATH)

# generate a simple input file for the workflow
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
with open("{}/f.in".format(INPUT_DIR), "w") as f:
    f.write("This is the contents of the input file for the hello world workflow!")

# --- Workflow -----------------------------------------------------------------
wf = Workflow("hello-world")

fin   = File("f.in")
finter = File("f.inter")
fout  = File("f.out")

job_hello = Job("hello")\
                .add_args("-T", "3", "-i", fin, "-o", finter)\
                .add_inputs(fin)\
                .add_outputs(finter, stage_out=False)\
                .add_profiles(Namespace.CONDOR, key="request_memory", value="256")

job_world = Job("world")\
                .add_args("-T", "3", "-i", finter, "-o", fout)\
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
try:
    wf.plan(conf=_PROPS_PATH, input_dirs=[INPUT_DIR], sites=[EXEC_SITE],
            transformations_dir=EXECUTABLES_DIR,
            output_dir=OUTPUT_DIR, submit=True)
except PegasusClientError as e:
    print(e)
    sys.exit(1)
