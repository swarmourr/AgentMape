#!/bin/bash
# Example runner that saves workflows to a custom output directory
# The validator will auto-detect where this saves files

OUTPUT_DIR="generated_workflows"

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "Generating workflow to $OUTPUT_DIR/pipeline.yml"

# Generate a simple workflow
cat > "$OUTPUT_DIR/pipeline.yml" <<'EOF'
pegasus: "5.0"
name: auto_detected_workflow
jobs:
  - name: job1
    transformation: example_transform
    arguments: ["--input", "data.txt", "--output", "result.txt"]
    uses:
      - name: data.txt
        type: input
      - name: result.txt
        type: output
transformations:
  - name: example_transform
    pfn: /usr/bin/process
    type: stageable
EOF

echo "Workflow generated successfully!"
