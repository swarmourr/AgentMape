#!/bin/bash
# Runner that sets output directory via environment variable
# Generator defines the filename
# LLM must analyze BOTH to determine: workflows/pipeline.yml

# Set output directory
export WORKFLOW_OUTPUT_DIR="workflows"

echo "Running workflow generator with OUTPUT_DIR=$WORKFLOW_OUTPUT_DIR"
python3 examples/test_combined_analysis.py
echo "Workflow generation complete"
