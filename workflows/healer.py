"""
Pegasus healer integration helpers.

Registers pegasus-healer as the DAGMan POST script via pegasus.properties
so Pegasus writes it into every node of the generated .dag at plan time.
No manual .dag patching required.

Usage
─────
    from workflows.healer import configure_healer_properties, add_healer_to_job

    props = Properties()
    configure_healer_properties(props, max_retries=3)
    props.write()                   # writes pegasus.properties to CWD

    wf.plan(..., submit=True)       # healer is already wired into the .dag
"""
from __future__ import annotations

import shutil
from pathlib import Path

from Pegasus.api import Job, Namespace, Properties


def _find_pegasus_healer() -> str:
    """Return the absolute path to the pegasus-healer command."""
    # 1. Already on PATH (activate.sh sourced, or system install)
    found = shutil.which("pegasus-healer")
    if found:
        return found
    # 2. Project bin/ relative to this file
    project_bin = Path(__file__).resolve().parents[1] / "bin" / "pegasus-healer"
    if project_bin.exists():
        project_bin.chmod(0o755)
        return str(project_bin)
    # 3. pegasus-src/bin/ in the project
    src_bin = Path(__file__).resolve().parents[1] / "pegasus-src" / "bin" / "pegasus-healer"
    if src_bin.exists():
        src_bin.chmod(0o755)
        return str(src_bin)
    raise FileNotFoundError(
        "pegasus-healer not found on PATH. Run 'source activate.sh' first, "
        "or add the project bin/ directory to PATH."
    )


def configure_healer_properties(
    props: Properties,
    max_retries: int = 3,
) -> None:
    """
    Register pegasus-healer as the DAGMan POST script in Pegasus properties.

    Pegasus writes dagman.post into every user-job node of the generated
    .dag file at plan time — no post-plan .dag patching required.

    DAGMan substitutes $RETURN, $JOB, $RETRY, $MAX_RETRIES at runtime.
    """
    healer = _find_pegasus_healer()
    props["dagman.post"]           = healer
    props["dagman.post.arguments"] = "$RETURN $JOB $RETRY $MAX_RETRIES"
    props["dagman.maxretries"]     = str(max_retries)


def add_healer_to_job(job: Job, max_retries: int = 3) -> Job:
    """
    Add a DAGMan RETRY profile to a single job.

    The POST script is registered globally via configure_healer_properties;
    this sets the per-job retry budget so DAGMan knows how many times to
    call the healer before giving up.
    """
    job.add_profiles(Namespace.DAGMAN, key="RETRY", value=str(max_retries))
    return job
