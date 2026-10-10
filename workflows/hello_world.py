from Pegasus.api import *
import sys
from pathlib import Path

# ── Healer — opt in by keeping this block ─────────────────────────────────────
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
# sharedfs: no pegasus-transfer needed; local OS copies only.
props["pegasus.data.configuration"]       = "sharedfs"
_PROPS_PATH = str(Path(__file__).resolve().parent.parent / "pegasus.properties")
props.write(_PROPS_PATH)

BASE_DIR       = Path(__file__).resolve().parent.parent
INPUT_DIR      = BASE_DIR / "input"
EXECUTABLES_DIR = BASE_DIR / "executables"
OUTPUT_DIR     = BASE_DIR / "output"
SCRATCH_DIR    = BASE_DIR / "scratch"
EXEC_SITE      = "local"

# Create directories and input file
INPUT_DIR.mkdir(parents=True, exist_ok=True)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
(INPUT_DIR / "f.in").write_text(
    "This is the contents of the input file for the hello world workflow!"
)

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
# Pass absolute paths directly — no File objects on jobs so PegasusLite does
# not create .lof staging infrastructure files, eliminating staging failures.
INTER = str(SCRATCH_DIR / "f.inter")

wf = Workflow("hello-world")
wf.add_site_catalog(sc)
wf.add_transformation_catalog(tc)

job_hello = (
    Job("hello")
    .add_args("-T", "3", "-i", str(INPUT_DIR / "f.in"), "-o", INTER)
    .add_profiles(Namespace.CONDOR, key="request_memory", value="256")
)

job_world = (
    Job("world")
    .add_args("-T", "3", "-i", INTER, "-o", str(OUTPUT_DIR / "f.out"))
)

wf.add_jobs(job_hello, job_world)
wf.add_dependency(job_world, parents=[job_hello])

# --- Visualize ----------------------------------------------------------------
try:
    wf.write()
    wf.graph(include_files=True, label="xform-id", output="graph.png")
except PegasusClientError as e:
    print(e)

# --- Plan and submit ----------------------------------------------------------
try:
    wf.plan(conf=_PROPS_PATH, sites=[EXEC_SITE],
            output_dir=str(OUTPUT_DIR), submit=True)
except PegasusClientError as e:
    print(e)
    sys.exit(1)
