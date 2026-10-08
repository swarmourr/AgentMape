#!/usr/bin/env bash
# =============================================================================
# install.sh — build a local venv for pegasus-healer
#
#   bash install.sh              # venv at ./agentic/
#   bash install.sh /my/venv    # custom path
#   PYTHON=python3.11 bash install.sh
#
# Requires: Pegasus 5.x installed on this machine (pegasus-config on PATH).
# The venv inherits all Pegasus packages from the real installation and adds
# Pegasus.healer on top.  No bundled copies, no partial installs.
#
# After this, run:   source activate.sh
# =============================================================================
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
VENV_DIR="${1:-$PROJECT_ROOT/agentic}"

echo "================================================================"
echo "  pegasus-healer venv builder"
echo "  Project : $PROJECT_ROOT"
echo "  Venv    : $VENV_DIR"
echo "================================================================"

# ── 1. Locate Pegasus installation via pegasus-config ─────────────────────────
echo ""
echo ">> Locating Pegasus installation ..."
if ! command -v pegasus-config &>/dev/null; then
    echo ""
    echo "ERROR: pegasus-config not found on PATH."
    echo "       Install Pegasus 5.x first, then re-run this script."
    echo "       https://pegasus.isi.edu/downloads"
    exit 1
fi

PEGASUS_PYTHON_DIR="$(pegasus-config --python 2>/dev/null || true)"
if [[ -z "$PEGASUS_PYTHON_DIR" ]]; then
    echo "ERROR: pegasus-config --python returned empty. Check your Pegasus installation."
    exit 1
fi
echo "   Pegasus Python dir : $PEGASUS_PYTHON_DIR"

# ── 2. Find Python 3.10+ ──────────────────────────────────────────────────────
# Prefer the Python that Pegasus itself uses, then fall back to common names.
PEGASUS_PYTHON="$(command -v pegasus-python-wrapper 2>/dev/null || true)"
[[ -x "$PEGASUS_PYTHON" ]] && PEGASUS_PYTHON="$("$PEGASUS_PYTHON" 2>/dev/null || true)"

PYTHON="${PYTHON:-}"
for _py in "$PYTHON" "$PEGASUS_PYTHON" python3.12 python3.11 python3.10 python3 python; do
    [[ -z "${_py:-}" ]] && continue
    if command -v "$_py" &>/dev/null || [[ -x "$_py" ]]; then
        if "$_py" -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" 2>/dev/null; then
            PYTHON="$_py"; break
        fi
    fi
done

if [[ -z "${PYTHON:-}" ]]; then
    echo "ERROR: Python 3.10+ not found. Set PYTHON=/path/to/python3.10"
    exit 1
fi
echo "   Python             : $PYTHON ($("$PYTHON" --version))"

# ── 3. Create venv ────────────────────────────────────────────────────────────
if [[ -d "$VENV_DIR" ]]; then
    echo ">> Venv exists — reusing $VENV_DIR"
else
    echo ">> Creating venv at $VENV_DIR ..."
    "$PYTHON" -m venv "$VENV_DIR"
fi
PIP="$VENV_DIR/bin/pip"
"$VENV_DIR/bin/python3" -m pip install --quiet --upgrade pip

# ── 4. Install healer dependencies ────────────────────────────────────────────
echo ">> Installing healer dependencies ..."
"$PIP" install --quiet -r "$PROJECT_ROOT/requirements.txt"

# ── 5. Wire Pegasus + healer into venv via .pth ───────────────────────────────
# The .pth file adds paths to sys.path at interpreter startup:
#   - The real Pegasus installation (braindump, api, python tools, etc.)
#   - src/ from this project (Pegasus.healer)
# src/Pegasus/__init__.py uses pkgutil.extend_path so both merge cleanly.
SITE_PACKAGES="$("$VENV_DIR/bin/python3" -c "import sysconfig; print(sysconfig.get_path('purelib'))")"
PTH_FILE="$SITE_PACKAGES/pegasus-source.pth"

echo ">> Writing $PTH_FILE ..."
{
    echo "# written by install.sh"
    echo "# real Pegasus installation"
    echo "$PEGASUS_PYTHON_DIR"
    echo "# Pegasus.healer source from this project"
    echo "$PROJECT_ROOT/src"
} > "$PTH_FILE"
echo "   done"

# ── 6. Verify ─────────────────────────────────────────────────────────────────
echo ">> Verifying imports ..."
"$VENV_DIR/bin/python3" -c "
from Pegasus.healer.rules.classifier import RULE_VERSION
from Pegasus.healer.models.diagnosis import FailureType
import Pegasus.braindump, Pegasus.api
print(f'   healer v{RULE_VERSION}          OK')
print(f'   Pegasus.braindump         OK')
print(f'   Pegasus.api               OK')
"

# ── 7. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo "  Done. Activate with:"
echo "    source $PROJECT_ROOT/activate.sh"
echo "================================================================"
