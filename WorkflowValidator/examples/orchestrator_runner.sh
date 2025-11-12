#!/bin/bash
# Orchestrator that runs generator and outputs YAML

set -e

GENERATOR="generate_workflow.py"
ENV=${1:-production}
WORKERS=${2:-4}

echo "🚀 Running workflow generator..." >&2
echo "   Environment: $ENV" >&2
echo "   Workers: $WORKERS" >&2

# Execute generator and output YAML to stdout
python3 "$GENERATOR" "$ENV" "$WORKERS"

echo "✅ Workflow generated successfully" >&2
