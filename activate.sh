#!/usr/bin/env bash
# =============================================================================
# activate.sh — point Pegasus at this project folder
#
#   source /path/to/project/activate.sh
#
# Sets up in one shot:
#   PATH        → project bin/ first (pegasus-healer, pegasus-inspect, ...)
#   PYTHONPATH  → project src/ (healer runs from source, no pip install)
#   HEALER_*    → policy file, checkpoint DB, memory DB
#   ~/.pegasus/properties → dagman.post registered to use this project
# =============================================================================

# ── Resolve project root (works in bash and zsh) ──────────────────────────────
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    _SRC="${BASH_SOURCE[0]}"
else
    _SRC="${(%):-%x}"   # zsh
fi
HEALER_PROJECT="$(cd "$(dirname "$_SRC")" && pwd)"
export HEALER_PROJECT

# ── Python interpreter ────────────────────────────────────────────────────────
# Use project venv if present; otherwise fall back to any python3 on PATH.
if [[ -x "$HEALER_PROJECT/agentic/bin/python3" ]]; then
    export HEALER_PYTHON="$HEALER_PROJECT/agentic/bin/python3"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python3" ]]; then
    export HEALER_PYTHON="$VIRTUAL_ENV/bin/python3"
else
    export HEALER_PYTHON="$(command -v python3 || command -v python)"
fi

# ── PATH — source bins before the installed Pegasus ──────────────────────────
# Order: project bin/ → pegasus-src/bin/ → rest of PATH
# This makes every pegasus-* command resolve from source first.
# pegasus-src/bin/pegasus-config bridges to installed JARs so pegasus-plan works.
_SRC_BIN="$HEALER_PROJECT/pegasus-src/bin"
case ":$PATH:" in
    *":$HEALER_PROJECT/bin:"*) ;;
    *) export PATH="$HEALER_PROJECT/bin:$_SRC_BIN:$PATH" ;;
esac
unset _SRC_BIN

# ── PYTHONPATH — healer imports from project src/ ────────────────────────────
case ":${PYTHONPATH:-}:" in
    *":$HEALER_PROJECT/src:"*) ;;
    *) export PYTHONPATH="$HEALER_PROJECT/src${PYTHONPATH:+:$PYTHONPATH}" ;;
esac

# ── Load .env first (API keys, LLM config, etc.) — before we pin paths ───────
if [[ -f "$HEALER_PROJECT/.env" ]]; then
    set -o allexport
    # shellcheck disable=SC1090
    source "$HEALER_PROJECT/.env"
    set +o allexport
fi

# ── Healer paths — always absolute, override anything from .env ───────────────
_PEGASUS_STATE="${HOME:-/tmp}/.pegasus"
mkdir -p "$_PEGASUS_STATE"
export POLICY_FILE="$HEALER_PROJECT/policies/remediation.yaml"
export HEALER_CHECKPOINT="${HEALER_CHECKPOINT:-$_PEGASUS_STATE/healer_checkpoint.db}"
export HEALER_MEMORY_DB="${HEALER_MEMORY_DB:-$_PEGASUS_STATE/healer_memory.db}"

# ── Mark bin/ scripts executable ─────────────────────────────────────────────
chmod +x "$HEALER_PROJECT"/bin/* 2>/dev/null || true

# ── Register dagman.post in ~/.pegasus/properties (idempotent) ───────────────
_PROPS="$HOME/.pegasus/properties"
_HEALER_BIN="$HEALER_PROJECT/bin/pegasus-healer"
if ! grep -q "^dagman\.post" "$_PROPS" 2>/dev/null; then
    cat >> "$_PROPS" <<PROPS

# pegasus-healer (registered by activate.sh — $HEALER_PROJECT)
dagman.post           = $_HEALER_BIN
dagman.post.arguments = \$RETURN \$JOB \$RETRY \$MAX_RETRIES
dagman.maxretries     = 3
PROPS
    echo "[pegasus-healer] registered dagman.post → $_PROPS"
elif ! grep -q "$HEALER_PROJECT" "$_PROPS" 2>/dev/null; then
    # Properties exist but point to a different project — update in place
    sed -i.bak "s|^dagman\.post\s*=.*|dagman.post           = $_HEALER_BIN|" "$_PROPS"
    echo "[pegasus-healer] updated dagman.post → $_PROPS"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo "[pegasus-healer] project   : $HEALER_PROJECT"
echo "[pegasus-healer] python    : $HEALER_PYTHON"
echo "[pegasus-healer] policy    : $POLICY_FILE"
echo ""
echo "Commands available:"
echo "  pegasus-healer        — healer POST script / manual invoke"
echo "  pegasus-inspect       — workflow inspector (v1)"
echo "  pegasus-inspect-v3    — workflow inspector with agent"
echo "  pegasus-plan          — standard Pegasus planner (system)"
echo "  pegasus-run           — standard Pegasus runner  (system)"

unset _SRC _PEGASUS_STATE _PROPS _HEALER_BIN
