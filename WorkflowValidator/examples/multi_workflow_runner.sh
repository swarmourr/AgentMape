#!/bin/bash
# Runner that outputs multiple workflow YAMLs

echo "Generating multiple workflows..." >&2

# Workflow 1: Training
cat <<EOF
name: training_workflow
version: 1.0
jobs:
  - name: train_model
    transformation: Train
transformations:
  - name: Train
    pfn: scripts/train.py
    type: stageable
---
EOF

# Workflow 2: Evaluation
cat <<EOF
name: evaluation_workflow
version: 1.0
jobs:
  - name: evaluate_model
    transformation: Evaluate
transformations:
  - name: Evaluate
    pfn: scripts/evaluate.py
    type: stageable
---
EOF

# Workflow 3: Deployment
cat <<EOF
name: deployment_workflow
version: 1.0
jobs:
  - name: deploy_model
    transformation: Deploy
transformations:
  - name: Deploy
    pfn: scripts/deploy.py
    type: stageable
EOF

echo "Generated 3 workflows!" >&2
