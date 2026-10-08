#!/usr/bin/env bash
# =============================================================================
# install.sh — build a local venv for pegasus-healer
#
#   bash install.sh              # venv at ./agentic/
#   bash install.sh /my/venv    # custom path
#   PYTHON=python3.11 bash install.sh
#
# Requirements on the target machine:
#   - Pegasus 5.x installed (pegasus-config on PATH)
#   - Python 3.10+
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

# ── 3. Install healer dependencies ────────────────────────────────────────────
echo ">> Installing healer dependencies ..."
"$PIP" install --quiet -r "$PROJECT_ROOT/requirements.txt"

# ── 4. Wire Pegasus packages into the venv via .pth ───────────────────────────
# Strategy:
#   a) Use pegasus-config --python to find where Pegasus is installed.
#      This works on any machine that has Pegasus 5.x on PATH, regardless
#      of which Python version it was installed under.
#   b) Add that path to a .pth file so the venv can import Pegasus.*.
#   c) Add src/ so the venv can import Pegasus.healer from this project.
#      src/Pegasus/__init__.py uses pkgutil.extend_path, merging both.
SITE_PACKAGES="$("$VENV_DIR/bin/python3" -c "import sysconfig; print(sysconfig.get_path('purelib'))")"
PTH_FILE="$SITE_PACKAGES/pegasus-source.pth"

echo ">> Locating installed Pegasus via pegasus-config ..."
PEGASUS_PYTHON_DIR="$(pegasus-config --python 2>/dev/null || true)"
if [[ -z "$PEGASUS_PYTHON_DIR" ]]; then
    echo "ERROR: 'pegasus-config --python' failed. Is Pegasus 5.x installed and on PATH?"
    exit 1
fi
echo "   Pegasus Python dir: $PEGASUS_PYTHON_DIR"

echo ">> Writing $PTH_FILE ..."
{
    echo "# written by install.sh"
    echo "# system Pegasus packages (braindump, api, etc.)"
    echo "$PEGASUS_PYTHON_DIR"
    echo "# healer source — provides Pegasus.healer"
    echo "$PROJECT_ROOT/src"
} > "$PTH_FILE"
echo "   done"

# ── 5. Verify ─────────────────────────────────────────────────────────────────
echo ">> Verifying imports ..."
"$VENV_DIR/bin/python3" -c "
from Pegasus.healer.rules.classifier import RULE_VERSION
from Pegasus.healer.models.diagnosis import FailureType
import Pegasus.braindump, Pegasus.api
print(f'   healer v{RULE_VERSION}          OK')
print(f'   Pegasus.braindump         OK')
print(f'   Pegasus.api               OK')
"

# ── 6. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo "  Done. Activate with:"
echo "    source $PROJECT_ROOT/activate.sh"
echo "================================================================"
