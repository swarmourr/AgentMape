#!/usr/bin/env bash
# =============================================================================
# install.sh — build a local venv from pegasus-src/ (no system install needed)
#
#   bash install.sh              # venv at ./agentic/
#   bash install.sh /my/venv    # custom path
#   PYTHON=python3.11 bash install.sh
#
# After this, run:   source activate.sh
# =============================================================================
set -euo pipefail

SCRIPT="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT")" && pwd)"
PEGASUS_SRC="$PROJECT_ROOT/pegasus-src"
VENV_DIR="${1:-$PROJECT_ROOT/agentic}"

echo "================================================================"
echo "  pegasus-healer venv builder"
echo "  Project  : $PROJECT_ROOT"
echo "  Pegasus  : $PEGASUS_SRC"
echo "  Venv     : $VENV_DIR"
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

# ── 3. Install Pegasus Python packages from source (editable) ─────────────────
echo ">> Installing Pegasus packages from pegasus-src/ ..."
for pkg in pegasus-common pegasus-api pegasus-python; do
    PKG_DIR="$PEGASUS_SRC/packages/$pkg"
    if [[ -f "$PKG_DIR/pyproject.toml" || -f "$PKG_DIR/setup.py" ]]; then
        echo "   pip install -e $pkg"
        "$PIP" install --quiet -e "$PKG_DIR"
    fi
done

# ── 4. Install healer deps + healer package ───────────────────────────────────
echo ">> Installing healer dependencies ..."
"$PIP" install --quiet -r "$PROJECT_ROOT/requirements.txt"

echo ">> Installing pegasus-healer from pegasus-src/ (editable) ..."
"$PIP" install --quiet -e "$PEGASUS_SRC/packages/pegasus-healer"
# NOTE: project src/ is NOT installed as a package — activate.sh prepends it
# to PYTHONPATH so live edits to src/Pegasus/healer/ are picked up directly
# without risking namespace conflicts with pegasus-common.

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
