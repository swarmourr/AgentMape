from Pegasus.api import *
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)

# we specify directories for inputs, executables and outputs
# - directory where to pick up the inputs from a directory.
# - directory where the executables that the workflow uses are placed.
# - directory where the outputs should be placed.

BASE_DIR        = Path(__file__).resolve().parent.parent
INPUT_DIR       = BASE_DIR / "input"
EXECUTABLES_DIR = BASE_DIR / "executables"
OUTPUT_DIR      = BASE_DIR / "output"
SCRATCH_DIR     = BASE_DIR / "scratch"

# the execution site where your job will run.
# local means the jobs run on the local machine.
EXEC_SITE = "local"

# ── Healer ────────────────────────────────────────────────────────────────────
# Load the machine's existing Pegasus config, then overlay healer settings.
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
# sharedfs: no pegasus-transfer needed; uses local OS file copies.
props["pegasus.data.configuration"]      = "sharedfs"
# Bypass PegasusLite wrapper — it always checks for .lof (list-of-files)
# infrastructure files even when no files are staged, causing exit 2.
# With gridstart=none jobs run directly; no .lof files needed.
props["pegasus.gridstart"]               = "none"
props.write(_PROPS_PATH)

# generate a simple input file for the workflow
INPUT_DIR.mkdir(parents=True, exist_ok=True)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
with open("{}/f.in".format(INPUT_DIR), "w") as f:
    f.write("This is the contents of the input file for the hello world workflow!")

# --- Site catalog -------------------------------------------------------------
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

# File objects used for naming; absolute paths are passed directly in add_args
# so Pegasus does not create staging jobs (.lof infrastructure) that fail on
# this machine.  Ordering is expressed via add_dependency instead.
fin   = File("f.in")
finter = File("f.inter")
fout  = File("f.out")

job_hello = Job("hello")\
                .add_args("-T", "3", "-i", str(INPUT_DIR / "f.in"), "-o", str(SCRATCH_DIR / "f.inter"))\
                .add_profiles(Namespace.CONDOR, key="request_memory", value="256")

job_world = Job("world")\
                .add_args("-T", "3", "-i", str(SCRATCH_DIR / "f.inter"), "-o", str(OUTPUT_DIR / "f.out"))

wf.add_jobs(job_hello, job_world)
wf.add_dependency(job_world, parents=[job_hello])

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
