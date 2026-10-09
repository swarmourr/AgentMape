from Pegasus.api import *
import sys
from pathlib import Path

# we specify directories for inputs, executables and outputs
# - directory where to pick up the inputs from a directory.
# - directory where the executables that the workflow uses are placed.
# - directory where the outputs should be placed.

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
props["dagman.retry"]                     = "3"
# condorio: HTCondor transfers files natively — no pegasus-transfer binary needed
props["pegasus.data.configuration"]       = "condorio"
# Write to an absolute path so pegasus-plan always finds it regardless of CWD
_PROPS_PATH = str(Path(__file__).resolve().parent.parent / "pegasus.properties")
props.write(_PROPS_PATH)

BASE_DIR = Path(__file__).resolve().parent.parent  # project root
INPUT_DIR = BASE_DIR / "input"
EXECUTABLES_DIR = BASE_DIR / "executables"
OUTPUT_DIR = BASE_DIR / "output"

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

SCRATCH_DIR = BASE_DIR / "scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Site catalog -------------------------------------------------------------
# SHARED_SCRATCH is always required by Pegasus (worker package staging).
# LOCAL_STORAGE is where final output files land.
sc = SiteCatalog()
local_site = Site("local", arch=Arch.X86_64, os_type=OS.LINUX)
local_site.add_directories(
    Directory(Directory.SHARED_SCRATCH, str(SCRATCH_DIR))
        .add_file_servers(FileServer("file://" + str(SCRATCH_DIR), Operation.ALL)),
    Directory(Directory.LOCAL_STORAGE, str(OUTPUT_DIR))
        .add_file_servers(FileServer("file://" + str(OUTPUT_DIR), Operation.ALL)),
)
sc.add_sites(local_site)

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
wf.add_site_catalog(sc)
wf.add_transformation_catalog(tc)

fin = File("f.in")
finter = File("f.inter")
fout = File("f.out")

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
# dagman.post = pegasus-healer is already in pegasus.properties above,
# so Pegasus writes it into every job node of the .dag at plan time.
try:
    wf.plan(conf=_PROPS_PATH, input_dirs=[INPUT_DIR], sites=[EXEC_SITE],
            output_dir=OUTPUT_DIR, submit=True)
except PegasusClientError as e:
    print(e)
    sys.exit(1)
