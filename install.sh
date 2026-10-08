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

# ── 3. Install healer dependencies ────────────────────────────────────────────
echo ">> Installing healer dependencies ..."
"$PIP" install --quiet -r "$PROJECT_ROOT/requirements.txt"

# ── 4. Install Pegasus packages + wire healer src/ ────────────────────────────
SITE_PACKAGES="$("$VENV_DIR/bin/python3" -c "import sysconfig; print(sysconfig.get_path('purelib'))")"
PTH_FILE="$SITE_PACKAGES/pegasus-source.pth"

if [[ -d "$PEGASUS_SRC/packages/pegasus-common" ]]; then
    # pegasus-src/ is checked out — install all Pegasus packages including
    # pegasus-healer (which provides Pegasus.healer).  No .pth needed.
    echo ">> Installing Pegasus packages from pegasus-src/ ..."
    for _pkg in pegasus-common pegasus-api pegasus-python pegasus-healer; do
        _path="$PEGASUS_SRC/packages/$_pkg"
        if [[ -d "$_path" ]]; then
            echo "   pip install $_pkg"
            "$PIP" install --quiet "$_path"
        fi
    done
    echo "   done (Pegasus.healer comes from pegasus-healer package)"
else
    # pegasus-src/ not present (shared VM with system Pegasus installed).
    # Locate where system Pegasus lives and add that site-packages dir to
    # the .pth so the venv sees braindump/api/etc without --system-site-packages.
    # Then add src/ which provides Pegasus.healer (not yet in system Pegasus).
    echo ">> pegasus-src/ not found — locating system Pegasus ..."
    PEGASUS_SITE="$("$PYTHON" -c "
import Pegasus, pathlib
print(str(pathlib.Path(Pegasus.__file__).parent.parent))
" 2>/dev/null || true)"
    if [[ -z "$PEGASUS_SITE" ]]; then
        echo "ERROR: Pegasus not importable from $PYTHON and pegasus-src/ is absent."
        echo "       Either check out pegasus-src/ or install Pegasus 5.x system-wide."
        exit 1
    fi
    echo "   system Pegasus at: $PEGASUS_SITE"
    {
        echo "# system Pegasus (braindump, api, etc.) — written by install.sh"
        echo "$PEGASUS_SITE"
        echo "# healer source (Pegasus.healer) — not yet in system Pegasus"
        echo "$PROJECT_ROOT/src"
    } > "$PTH_FILE"
    echo "   done"
fi

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
