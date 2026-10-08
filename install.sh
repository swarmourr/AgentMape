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

# ── 2. Create venv (with system site-packages so installed Pegasus is visible) ─
if [[ -d "$VENV_DIR" ]]; then
    echo ">> Venv exists — reusing $VENV_DIR"
    # Ensure system site-packages is enabled even for pre-existing venvs
    PYVENV_CFG="$VENV_DIR/pyvenv.cfg"
    if [[ -f "$PYVENV_CFG" ]] && grep -q "include-system-site-packages = false" "$PYVENV_CFG"; then
        sed -i.bak "s/include-system-site-packages = false/include-system-site-packages = true/" "$PYVENV_CFG"
        echo ">> Enabled system-site-packages in existing venv"
    fi
else
    echo ">> Creating venv at $VENV_DIR ..."
    "$PYTHON" -m venv --system-site-packages "$VENV_DIR"
fi
PIP="$VENV_DIR/bin/pip"
"$VENV_DIR/bin/python3" -m pip install --quiet --upgrade pip

# ── 3. Install healer dependencies ────────────────────────────────────────────
echo ">> Installing healer dependencies ..."
"$PIP" install --quiet -r "$PROJECT_ROOT/requirements.txt"

# ── 4. Wire source packages via a .pth file ───────────────────────────────────
# A .pth file in site-packages adds paths to sys.path at interpreter startup.
# pegasus-src/ packages are optional — if absent the system-installed Pegasus
# (made visible via --system-site-packages above) provides braindump/api/etc.
# src/Pegasus/__init__.py uses pkgutil.extend_path so both the healer source
# and the system Pegasus namespace merge transparently.
SITE_PACKAGES="$("$VENV_DIR/bin/python3" -c "import sysconfig; print(sysconfig.get_path('purelib'))")"
PTH_FILE="$SITE_PACKAGES/pegasus-source.pth"

echo ">> Writing source paths to $PTH_FILE ..."
{
    echo "# Pegasus source packages — written by install.sh"
    # Optional: pegasus-src sub-packages (only if the tree is checked out)
    for _pkg in pegasus-common pegasus-api pegasus-python pegasus-healer; do
        _path="$PEGASUS_SRC/packages/$_pkg/src"
        if [[ -d "$_path" ]]; then
            echo "$_path"
        fi
    done
    # Always add the healer src/ from this project
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
