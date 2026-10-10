from Pegasus.api import *
import sys
from pathlib import Path

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
props["dagman.post"]                      = "pegasus-healer"
props["dagman.post.path.pegasus-healer"]  = _healer
props["dagman.post.arguments"]            = "$RETURN $JOB $RETRY $MAX_RETRIES"
props["dagman.maxretries"]                = "3"
props["dagman.retry"]                     = "3"
# sharedfs: Pegasus stages files using local OS copies — no pegasus-transfer needed.
props["pegasus.data.configuration"]       = "sharedfs"
# Write to an absolute path so pegasus-plan always finds it regardless of CWD
_PROPS_PATH = str(Path(__file__).resolve().parent.parent / "pegasus.properties")
props.write(_PROPS_PATH)

BASE_DIR = Path(__file__).resolve().parent.parent  # project root
INPUT_DIR = BASE_DIR / "input"
EXECUTABLES_DIR = BASE_DIR / "executables"
OUTPUT_DIR = BASE_DIR / "output"

# the execution site where your job will run.
# local means the jobs run on the local machine.
EXEC_SITE = "local"

# generate a simple input file for the workflow
INPUT_DIR.mkdir(parents=True, exist_ok=True)
with open("{}/f.in".format(INPUT_DIR), "w") as f:
    f.write("This is the contents of the input file for the hello world workflow!")

SCRATCH_DIR = BASE_DIR / "scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Site catalog -------------------------------------------------------------
# SHARED_SCRATCH is required by Pegasus (worker package staging).
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

# --- Replica catalog ----------------------------------------------------------
# Register f.in with its absolute path so Pegasus can locate it on sharedfs.
rc = ReplicaCatalog()
rc.add_replica("local", "f.in", "file://" + str(INPUT_DIR / "f.in"))

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
wf.add_replica_catalog(rc)
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
# sharedfs is set in pegasus.properties above.
# Pass conf= so pegasus-plan picks up our properties file.
try:
    wf.plan(conf=_PROPS_PATH, sites=[EXEC_SITE],
            output_dir=str(OUTPUT_DIR), submit=True)
except PegasusClientError as e:
    print(e)
    sys.exit(1)
