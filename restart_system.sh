#!/bin/bash
# AgentMape MAPE-K — Restart & Monitoring Console (shell wrapper)
# Delegates to restart_system.py for the full TUI experience.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="python3.11"

if ! command -v $PYTHON &>/dev/null; then
    echo "ERROR: python3.11 not found. Please install it first."
    exit 1
fi

# Activate venv if present
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

exec $PYTHON "$SCRIPT_DIR/restart_system.py" "$@"
