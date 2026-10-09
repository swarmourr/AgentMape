#!/usr/bin/env bash
# =============================================================================
# install.sh — build a self-contained venv with Pegasus + healer
#
#   bash install.sh              # venv at ./agentic/
#   bash install.sh /my/venv    # custom path
#   PYTHON=python3.11 bash install.sh
#
# Installs Pegasus 5.x into the venv via pip (no system install required),
# then wires Pegasus.healer from this project's src/ on top.
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

# ── 1. Find Python 3.10+ ──────────────────────────────────────────────────────
PYTHON="${PYTHON:-}"
for _py in "$PYTHON" python3.12 python3.11 python3.10 python3 python; do
    [[ -z "${_py:-}" ]] && continue
    if command -v "$_py" &>/dev/null; then
        if "$_py" -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" 2>/dev/null; then
            PYTHON="$_py"; break
        fi
    fi
done

if [[ -z "${PYTHON:-}" ]]; then
    echo "ERROR: Python 3.10+ not found. Set PYTHON=/path/to/python3.10"
    exit 1
fi
echo ""
echo ">> Python: $PYTHON ($("$PYTHON" --version))"

# ── 2. Create venv ────────────────────────────────────────────────────────────
if [[ -d "$VENV_DIR" ]]; then
    echo ">> Venv exists — reusing $VENV_DIR"
else
    echo ">> Creating venv at $VENV_DIR ..."
    "$PYTHON" -m venv "$VENV_DIR"
fi
PIP="$VENV_DIR/bin/pip"
"$VENV_DIR/bin/python3" -m pip install --quiet --upgrade pip

# ── 3. Install Pegasus Python packages from pegasus-src/ ─────────────────────
# Install the individual pure-Python packages (no CMake/Go/Java required).
# The root pegasus-wms package requires a full C/Go build — skip it.
PEGASUS_SRC="$PROJECT_ROOT/pegasus-src"
if [[ -d "$PEGASUS_SRC/packages" ]]; then
    echo ">> Installing Pegasus packages from pegasus-src/ ..."
    for _pkg in pegasus-common pegasus-api pegasus-python pegasus-healer; do
        _pkgdir="$PEGASUS_SRC/packages/$_pkg"
        if [[ -d "$_pkgdir" ]]; then
            echo "   pip install $_pkg ..."
            "$PIP" install --quiet "$_pkgdir"
        fi
    done
    echo "   done"
else
    echo "WARNING: pegasus-src/ not found — skipping Pegasus package install."
    echo "         Run: git pull origin integration"
fi

# ── 4. Install healer dependencies ────────────────────────────────────────────
echo ">> Installing healer dependencies ..."
"$PIP" install --quiet -r "$PROJECT_ROOT/requirements.txt"

# ── 5. Wire Pegasus.healer from src/ via .pth ─────────────────────────────────
# Keep src/ on sys.path so live edits to the healer are picked up immediately
# without reinstalling pegasus-healer.
SITE_PACKAGES="$("$VENV_DIR/bin/python3" -c "import sysconfig; print(sysconfig.get_path('purelib'))")"
PTH_FILE="$SITE_PACKAGES/pegasus-healer.pth"

echo ">> Wiring src/ (live edits) → $PTH_FILE"
echo "$PROJECT_ROOT/src" > "$PTH_FILE"
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
