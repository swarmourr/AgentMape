# Multiple Workflows Output

## Your Use Case

Your runner can output **multiple workflows** in one go, separated by `---`.

---

## Simple Example

**multi_workflow_runner.sh:**
```bash
#!/bin/bash

# Output Workflow 1
cat <<EOF
name: workflow_1
version: 1.0
jobs:
  - name: job1
    transformation: Process
transformations:
  - name: Process
    pfn: scripts/process1.sh
---
EOF

# Output Workflow 2
cat <<EOF
name: workflow_2
version: 1.0
jobs:
  - name: job2
    transformation: Process
transformations:
  - name: Process
    pfn: scripts/process2.sh
---
EOF

# Output Workflow 3
cat <<EOF
name: workflow_3
version: 1.0
jobs:
  - name: job3
    transformation: Process
transformations:
  - name: Process
    pfn: scripts/process3.sh
EOF
```

---

## Validate

```bash
python cli.py workflow.py \
  --runner multi_workflow_runner.sh \
  --workflow-dir /path/to/workflow/
```

**Output:**
```
🏃 Runner script detected: multi_workflow_runner.sh
   Generator: workflow.py
   Running: bash multi_workflow_runner.sh

✅ Runner produced 3 YAML documents (1,234 bytes)
   Validating all 3 workflows...

📄 Validating workflow 1/3...
✓ workflow_1 validated

📄 Validating workflow 2/3...
✓ workflow_2 validated

📄 Validating workflow 3/3...
✓ workflow_3 validated

✅ All 3 workflows validated successfully!
```

---

## YAML Document Separator

Use `---` to separate workflows:

```yaml
name: workflow_1
jobs: [...]
---
name: workflow_2
jobs: [...]
---
name: workflow_3
jobs: [...]
```

---

## Python Runner Example

**multi_workflow_generator.py:**
```python
#!/usr/bin/env python3
import yaml

workflows = [
    {
        'name': 'training_workflow',
        'jobs': [{'name': 'train', 'transformation': 'Train'}],
        'transformations': [{'name': 'Train', 'pfn': 'scripts/train.py'}]
    },
    {
        'name': 'evaluation_workflow',
        'jobs': [{'name': 'evaluate', 'transformation': 'Evaluate'}],
        'transformations': [{'name': 'Evaluate', 'pfn': 'scripts/evaluate.py'}]
    },
    {
        'name': 'deployment_workflow',
        'jobs': [{'name': 'deploy', 'transformation': 'Deploy'}],
        'transformations': [{'name': 'Deploy', 'pfn': 'scripts/deploy.py'}]
    }
]

# Output all workflows separated by ---
for i, workflow in enumerate(workflows):
    print(yaml.dump(workflow, default_flow_style=False))
    if i < len(workflows) - 1:
        print('---')
```

**Validate:**
```bash
python cli.py workflow.py \
  --runner multi_workflow_generator.py \
  --workflow-dir /opt/workflows/
```

---

## Real Use Case: ML Pipeline

**ml_pipeline_runner.sh:**
```bash
#!/bin/bash

# Generate 3 workflows for different stages

# Stage 1: Data preparation
cat <<EOF
name: data_preparation
version: 1.0
jobs:
  - name: download_data
    transformation: Download
  - name: preprocess
    transformation: Preprocess
transformations:
  - name: Download
    pfn: scripts/download.py
  - name: Preprocess
    pfn: scripts/preprocess.py
---
EOF

# Stage 2: Training (multiple models)
cat <<EOF
name: model_training
version: 1.0
jobs:
  - name: train_llama
    transformation: Train
  - name: train_falcon
    transformation: Train
transformations:
  - name: Train
    pfn: scripts/train.py
---
EOF

# Stage 3: Deployment
cat <<EOF
name: model_deployment
version: 1.0
jobs:
  - name: deploy_best
    transformation: Deploy
transformations:
  - name: Deploy
    pfn: scripts/deploy.py
EOF
```

---

## Validation Result

```
✅ Runner produced 3 YAML documents (2,345 bytes)
   Validating all 3 workflows...

📄 Validating workflow 1/3...
   Workflow: data_preparation
   ✓ scripts/download.py found
   ✓ scripts/preprocess.py found

📄 Validating workflow 2/3...
   Workflow: model_training
   ✓ scripts/train.py found

📄 Validating workflow 3/3...
   Workflow: model_deployment
   ✓ scripts/deploy.py found

✅ All 3 workflows PASSED validation!
```

---

## Summary

**Your runner outputs:**
```yaml
workflow 1
---
workflow 2
---
workflow 3
```

**Validator:**
1. Detects multiple documents
2. Validates each one
3. Reports all results

**Simple as that!** 🚀
