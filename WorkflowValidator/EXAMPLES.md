# Practical Examples for WorkflowValidator

## Example 1: Simple Python Workflow

**Project Structure:**
```
/home/user/simple_workflow/
├── workflow.py
└── scripts/
    └── process.py
```

**workflow.py:**
```python
workflow = {'name': 'simple_workflow', 'version': '1.0'}

jobs = [
    {
        'name': 'process',
        'transformation': 'Process',
        'arguments': ['--input', 'data.csv'],
        'uses': [{'name': 'data.csv', 'type': 'input'}]
    }
]

transformations = [
    {'name': 'Process', 'pfn': 'scripts/process.py', 'type': 'stageable'}
]
```

**Validation:**
```bash
cd /home/user/simple_workflow/
python /path/to/validator/cli.py workflow.py --level standard
```

**Result:** ✅ Validates `scripts/process.py` relative to `/home/user/simple_workflow/`

---

## Example 2: Orchestrator Importing Workflow

**Project Structure:**
```
/opt/workflows/ml_pipeline/
├── run.py                  # Orchestrator
├── workflow_descriptor.py  # Imported by run.py
├── scripts/
│   ├── download.py
│   ├── preprocess.py
│   └── train.py
└── data/
    └── config.json
```

**run.py:**
```python
#!/usr/bin/env python3
import sys
from workflow_descriptor import workflow, jobs, transformations

def main():
    env = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    print(f"Running workflow in {env} environment")
    # ... execute workflow ...

if __name__ == '__main__':
    main()
```

**workflow_descriptor.py:**
```python
workflow = {'name': 'ml_pipeline', 'version': '1.0'}

jobs = [
    {
        'name': 'download',
        'transformation': 'Download',
        'uses': [{'name': 'raw_data.csv', 'type': 'output'}]
    },
    # ... more jobs ...
]

transformations = [
    {'name': 'Download', 'pfn': 'scripts/download.py', 'type': 'stageable'},
    {'name': 'Preprocess', 'pfn': 'scripts/preprocess.py', 'type': 'stageable'},
    {'name': 'Train', 'pfn': 'scripts/train.py', 'type': 'stageable'}
]
```

**Problem:** If you validate `run.py` directly, paths resolve from `run.py`'s directory.

**Solution:**
```bash
python /path/to/validator/cli.py run.py \
  --workflow-dir /opt/workflows/ml_pipeline/ \
  --workflow-args 'production' \
  --level full \
  -o /opt/workflows/ml_pipeline/validation_report.json
```

**What Happens:**
- Validator reads `run.py`
- Resolves paths from `/opt/workflows/ml_pipeline/`
- Finds `scripts/download.py`, `scripts/preprocess.py`, etc. ✅
- Logs argument: `production`
- Saves JSON report

---

## Example 3: Shell Script Orchestrator

**Project Structure:**
```
/data/workflows/batch_processing/
├── orchestrator.sh
├── workflow.yml
├── bin/
│   ├── extract.sh
│   ├── transform.sh
│   └── load.sh
└── config/
    └── production.conf
```

**orchestrator.sh:**
```bash
#!/bin/bash
set -e

ENV=${1:-dev}
CONFIG=${2:-config/${ENV}.conf}
WORKERS=${3:-1}

echo "Running workflow: ENV=$ENV, CONFIG=$CONFIG, WORKERS=$WORKERS"

# Load configuration
source $CONFIG

# Execute workflow
pegasus-plan workflow.yml
pegasus-run workflow.yml
```

**workflow.yml:**
```yaml
name: batch_processing
version: 1.0

transformations:
  - name: Extract
    pfn: bin/extract.sh
    type: stageable
  - name: Transform
    pfn: bin/transform.sh
    type: stageable
  - name: Load
    pfn: bin/load.sh
    type: stageable

jobs:
  - name: extract_job
    transformation: Extract
  # ... more jobs ...
```

**Validation:**
```bash
python /path/to/validator/cli.py /data/workflows/batch_processing/orchestrator.sh \
  --workflow-dir /data/workflows/batch_processing/ \
  --workflow-args 'production config/production.conf 4' \
  --level standard
```

**Log Output:**
```
INFO - Workflow Validator Started
INFO - Input file: /data/workflows/batch_processing/orchestrator.sh
INFO - File type: .sh
INFO - Validation level: standard
INFO - Workflow arguments: production config/production.conf 4
INFO - Using provided workflow directory: /data/workflows/batch_processing/
```

---

## Example 4: Complex Multi-Directory Setup

**Project Structure:**
```
/projects/research/
├── orchestrators/
│   └── run_experiment.py
├── workflows/
│   └── experiment_workflow.py
├── scripts/
│   ├── data_prep.py
│   ├── model_train.py
│   └── evaluate.py
└── data/
    └── dataset.csv
```

**orchestrators/run_experiment.py:**
```python
import sys
sys.path.insert(0, '../workflows')
from experiment_workflow import workflow, jobs, transformations

# Run experiment...
```

**workflows/experiment_workflow.py:**
```python
workflow = {'name': 'experiment', 'version': '1.0'}

transformations = [
    {'name': 'DataPrep', 'pfn': '../scripts/data_prep.py', 'type': 'stageable'},
    {'name': 'Train', 'pfn': '../scripts/model_train.py', 'type': 'stageable'},
    {'name': 'Evaluate', 'pfn': '../scripts/evaluate.py', 'type': 'stageable'}
]

# Note: paths are relative to workflows/ directory
```

**Problem:** Paths in `experiment_workflow.py` are relative to `workflows/`, not `orchestrators/`

**Solution 1: Validate from workflows/ directory**
```bash
cd /projects/research/workflows/
python /path/to/validator/cli.py experiment_workflow.py --level standard
```

**Solution 2: Use --workflow-dir**
```bash
python /path/to/validator/cli.py \
  /projects/research/orchestrators/run_experiment.py \
  --workflow-dir /projects/research/workflows/ \
  --level standard
```

**Best Practice:** Use absolute paths in production:
```python
transformations = [
    {'name': 'DataPrep', 'pfn': '/projects/research/scripts/data_prep.py', 'type': 'stageable'},
    # ...
]
```

---

## Example 5: CI/CD Integration

**GitHub Actions Workflow:**
```yaml
name: Validate Workflow

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install pyyaml click

      - name: Validate Workflow
        run: |
          python validator/cli.py workflow.py \
            --workflow-dir ${{ github.workspace }} \
            --level full \
            --format json \
            -o validation_report.json

      - name: Upload Report
        uses: actions/upload-artifact@v2
        with:
          name: validation-report
          path: validation_report.json

      - name: Check Validation
        run: |
          if [ $? -ne 0 ]; then
            echo "Workflow validation failed!"
            exit 1
          fi
```

---

## Example 6: Docker Container

**Dockerfile:**
```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install validator
COPY WorkflowValidator/ /app/validator/
RUN pip install pyyaml click requests

# Copy workflow
COPY workflow.py /app/workflow.py
COPY scripts/ /app/scripts/

# Validate on build
RUN python /app/validator/cli.py /app/workflow.py \
    --workflow-dir /app \
    --level quick

ENTRYPOINT ["python", "workflow.py"]
```

**Build:**
```bash
docker build -t my-workflow .
```

---

## Example 7: Remote Validation

**Scenario:** Validate workflow on a remote server

**deploy.sh:**
```bash
#!/bin/bash
SERVER="user@production-server"
WORKFLOW_DIR="/opt/workflows/current"

# Upload workflow
scp -r workflow.py scripts/ $SERVER:$WORKFLOW_DIR/

# Run validation remotely
ssh $SERVER << EOF
  cd $WORKFLOW_DIR
  python /opt/validator/cli.py workflow.py \
    --workflow-dir $WORKFLOW_DIR \
    --workflow-args 'production --workers=8' \
    --level full \
    --format json \
    -o validation_report.json

  # Check result
  if [ \$? -eq 0 ]; then
    echo "✅ Validation passed - deploying workflow"
    # Deploy workflow...
  else
    echo "❌ Validation failed - aborting deployment"
    exit 1
  fi
EOF
```

---

## Example 8: Makefile Integration

**Makefile:**
```makefile
VALIDATOR := python /path/to/validator/cli.py
WORKFLOW_DIR := $(shell pwd)

.PHONY: validate validate-quick validate-full clean

validate:
	$(VALIDATOR) workflow.py \
		--workflow-dir $(WORKFLOW_DIR) \
		--level standard

validate-quick:
	$(VALIDATOR) workflow.py \
		--workflow-dir $(WORKFLOW_DIR) \
		--level quick

validate-full:
	$(VALIDATOR) workflow.py \
		--workflow-dir $(WORKFLOW_DIR) \
		--level full \
		--format json \
		-o reports/validation_$(shell date +%Y%m%d_%H%M%S).json

clean:
	rm -rf reports/*.json
```

**Usage:**
```bash
make validate        # Standard validation
make validate-quick  # Quick syntax check
make validate-full   # Full validation with report
```

---

## Example 9: Pre-commit Hook

**.git/hooks/pre-commit:**
```bash
#!/bin/bash

VALIDATOR="/path/to/validator/cli.py"
WORKFLOW_FILES=$(git diff --cached --name-only | grep -E '\.py$|\.yml$')

if [ -z "$WORKFLOW_FILES" ]; then
    exit 0
fi

echo "Validating workflows..."

for file in $WORKFLOW_FILES; do
    if [[ $file == *workflow* ]]; then
        python $VALIDATOR $file --level quick
        if [ $? -ne 0 ]; then
            echo "❌ Validation failed for $file"
            echo "Fix errors or use 'git commit --no-verify' to skip validation"
            exit 1
        fi
    fi
done

echo "✅ All workflows validated successfully"
exit 0
```

---

## Troubleshooting Guide

### Issue 1: Paths Not Found
```
❌ Transformation executable not found: scripts/process.py
   (resolved to: /wrong/path/scripts/process.py)
```

**Solution:**
```bash
# Check where validator is looking
python cli.py workflow.py --verbose

# Fix with --workflow-dir
python cli.py workflow.py --workflow-dir /correct/path/
```

### Issue 2: Import Errors
```
❌ ModuleNotFoundError: No module named 'workflow_descriptor'
```

**Solution:** Your orchestrator imports files - use `--workflow-dir` to set Python path context

### Issue 3: Ollama Not Available
```
⚠️ LLM validation skipped (Ollama not available)
```

**Solution:** Use offline mode or quick level
```bash
python cli.py workflow.py --mode offline --level quick
```

---

These examples cover the most common use cases. Mix and match options based on your needs!
