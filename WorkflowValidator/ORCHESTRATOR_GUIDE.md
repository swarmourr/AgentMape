# Orchestrator Declaration Guide

## Overview

When you have an **orchestrator script** that calls a **generator** to create workflows, you need to **declare which generator it uses**. This tells the validator to validate the generator instead of the orchestrator.

---

## The Problem

You have two files:

```
orchestrator.py  →  calls  →  generate_workflow.py  →  outputs YAML
```

When you run:
```bash
python validator/cli.py orchestrator.py
```

The validator doesn't know that `orchestrator.py` uses `generate_workflow.py` to generate the workflow!

---

## The Solution: Declare Your Generator

Add a `VALIDATOR_CONFIG` block to your **orchestrator** declaring which generator it uses:

**orchestrator.py:**
```python
#!/usr/bin/env python3
"""
Workflow Orchestrator - Launches ML Pipeline

VALIDATOR_CONFIG:
  type: orchestrator
  generator: generate_workflow.py
  workflow_dir: /opt/workflows/ml_pipeline
  generator_args: production --workers=4
"""
import subprocess
import sys

def main():
    env = sys.argv[1] if len(sys.argv) > 1 else 'production'

    print(f"🚀 Launching workflow for: {env}")

    # Call generator to create YAML
    result = subprocess.run(
        ['python3', 'generate_workflow.py', env],
        capture_output=True,
        text=True,
        check=True
    )

    workflow_yaml = result.stdout

    # Save and execute
    with open(f'workflow_{env}.yml', 'w') as f:
        f.write(workflow_yaml)

    print(f"✅ Generated workflow_{env}.yml")

    # Execute with Pegasus
    # subprocess.run(['pegasus-plan', f'workflow_{env}.yml'])

if __name__ == '__main__':
    main()
```

---

## How It Works

When you validate the orchestrator:

```bash
python validator/cli.py orchestrator.py
```

**What happens:**
1. ✅ Validator reads `orchestrator.py`
2. ✅ Detects `VALIDATOR_CONFIG` with `type: orchestrator`
3. ✅ Finds declared generator: `generate_workflow.py`
4. ✅ **Validates the generator** instead
5. ✅ Uses `workflow_dir` and `generator_args` from orchestrator config

**Output:**
```
ℹ️  Auto-detected orchestrator configuration
   Orchestrator uses generator: /opt/workflows/ml_pipeline/generate_workflow.py
   Using workflow_dir from metadata: /opt/workflows/ml_pipeline
   Using generator_args from metadata: production --workers=4

⚙️  Generator script detected: generate_workflow.py
   Running: python3 generate_workflow.py production --workers=4
✅ Generator produced 567 bytes of YAML

🔍 Validating workflow (level: standard)...
✅ Validation PASSED
```

---

## Configuration Fields

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `type` | ✅ | Must be `orchestrator` | `orchestrator` |
| `generator` | ✅ | Path to generator script (relative or absolute) | `generate_workflow.py` |
| `workflow_dir` | ❌ | Base directory for path resolution | `/opt/workflows/project` |
| `generator_args` | ❌ | Arguments to pass to generator | `production --workers=4` |

---

## Complete Example

### Project Structure

```
/opt/workflows/ml_pipeline/
├── orchestrator.py          # Launches workflow (declares generator)
├── generate_workflow.py     # Generates YAML (actual generator)
├── scripts/
│   ├── download.py
│   ├── preprocess.py
│   └── train.py
├── config/
│   └── production.yaml
└── data/
    └── datasets/
```

### orchestrator.py (Declares Generator)

```python
#!/usr/bin/env python3
"""
ML Pipeline Orchestrator

VALIDATOR_CONFIG:
  type: orchestrator
  generator: generate_workflow.py
  workflow_dir: /opt/workflows/ml_pipeline
  generator_args: production --workers=8
"""
import subprocess
import sys
import yaml

def main():
    env = sys.argv[1] if len(sys.argv) > 1 else 'production'
    workers = sys.argv[2] if len(sys.argv) > 2 else '8'

    print(f"🚀 Launching ML Pipeline")
    print(f"   Environment: {env}")
    print(f"   Workers: {workers}")

    # Generate workflow using declared generator
    print("\n📝 Generating workflow...")
    result = subprocess.run(
        ['python3', 'generate_workflow.py', env, workers],
        capture_output=True,
        text=True,
        check=True,
        cwd='/opt/workflows/ml_pipeline'
    )

    if result.returncode != 0:
        print(f"❌ Generator failed: {result.stderr}")
        sys.exit(1)

    workflow_yaml = result.stdout

    # Validate generated YAML structure
    try:
        workflow = yaml.safe_load(workflow_yaml)
        print(f"✅ Generated workflow: {workflow['name']}")
        print(f"   Jobs: {len(workflow.get('jobs', []))}")
    except Exception as e:
        print(f"❌ Invalid YAML: {e}")
        sys.exit(1)

    # Save to file
    output_file = f'workflows/generated_{env}.yml'
    with open(output_file, 'w') as f:
        f.write(workflow_yaml)
    print(f"💾 Saved to: {output_file}")

    # Execute workflow
    print("\n🏃 Executing workflow...")
    # subprocess.run(['pegasus-plan', output_file])
    # subprocess.run(['pegasus-run', ...])

    print("\n✅ Workflow execution complete!")

if __name__ == '__main__':
    main()
```

### generate_workflow.py (The Generator)

```python
#!/usr/bin/env python3
"""
ML Workflow Generator

Generates dynamic ML pipeline based on environment and worker count.
"""
import sys
import yaml

def generate_ml_workflow(env, num_workers):
    """Generate ML pipeline workflow"""

    workflow = {
        'name': f'ml_pipeline_{env}',
        'version': '1.0',
        'jobs': [
            {
                'name': 'download_data',
                'transformation': 'Download',
                'arguments': [
                    '--source', f's3://data-{env}/datasets/',
                    '--output', 'raw_data.csv'
                ],
                'uses': [
                    {'name': 'raw_data.csv', 'type': 'output'}
                ]
            },
            {
                'name': 'preprocess',
                'transformation': 'Preprocess',
                'arguments': ['--input', 'raw_data.csv', '--output', 'clean_data.csv'],
                'parents': ['download_data'],
                'uses': [
                    {'name': 'raw_data.csv', 'type': 'input'},
                    {'name': 'clean_data.csv', 'type': 'output'}
                ]
            }
        ],
        'transformations': [
            {'name': 'Download', 'pfn': 'scripts/download.py', 'type': 'stageable'},
            {'name': 'Preprocess', 'pfn': 'scripts/preprocess.py', 'type': 'stageable'},
            {'name': 'Train', 'pfn': 'scripts/train.py', 'type': 'stageable'}
        ]
    }

    # Add training jobs based on worker count
    for i in range(int(num_workers)):
        workflow['jobs'].append({
            'name': f'train_worker_{i}',
            'transformation': 'Train',
            'arguments': [
                '--input', 'clean_data.csv',
                '--worker-id', str(i),
                '--model-output', f'model_{i}.pkl'
            ],
            'parents': ['preprocess'],
            'uses': [
                {'name': 'clean_data.csv', 'type': 'input'},
                {'name': f'model_{i}.pkl', 'type': 'output'}
            ]
        })

    return workflow

def main():
    env = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    workers = sys.argv[2] if len(sys.argv) > 2 else '1'

    workflow = generate_ml_workflow(env, workers)
    print(yaml.dump(workflow, default_flow_style=False))

if __name__ == '__main__':
    main()
```

### Validation

```bash
# Validate the orchestrator (auto-detects generator)
python /path/to/validator/cli.py orchestrator.py
```

**Output:**
```
ℹ️  Auto-detected orchestrator configuration
   Orchestrator uses generator: /opt/workflows/ml_pipeline/generate_workflow.py
   Using workflow_dir from metadata: /opt/workflows/ml_pipeline
   Using generator_args from metadata: production --workers=8

⚙️  Generator script detected: generate_workflow.py
   Running: python3 generate_workflow.py production --workers=8
✅ Generator produced 1,234 bytes of YAML

🔍 Validating workflow (level: standard)...

Running structure validator...
✓ Workflow structure valid
✓ All jobs have valid transformations
✓ No circular dependencies

Running path validator...
✓ Transformation 'Download' validated: scripts/download.py ✅
✓ Transformation 'Preprocess' validated: scripts/preprocess.py ✅
✓ Transformation 'Train' validated: scripts/train.py ✅
✓ All transformations validated (3 checks)

✅ Validation PASSED - Workflow is ready to submit!
```

---

## Shell Script Orchestrator

You can also declare generators in shell scripts:

**orchestrator.sh:**
```bash
#!/bin/bash
#
# Batch Processing Orchestrator
#
# VALIDATOR_CONFIG:
#   type: orchestrator
#   generator: generate.sh
#   workflow_dir: /data/workflows/batch
#   generator_args: production

set -e

ENV=${1:-production}

echo "🚀 Launching batch workflow for: $ENV"

# Generate workflow using declared generator
echo "📝 Generating workflow..."
WORKFLOW_YAML=$(bash generate.sh $ENV)

# Save to file
OUTPUT_FILE="workflow_${ENV}.yml"
echo "$WORKFLOW_YAML" > $OUTPUT_FILE
echo "✅ Generated: $OUTPUT_FILE"

# Execute
echo "🏃 Executing workflow..."
# pegasus-plan $OUTPUT_FILE
# pegasus-run ...

echo "✅ Complete!"
```

**Validation:**
```bash
python cli.py orchestrator.sh
```

---

## Relative vs Absolute Paths

### Relative Paths (Recommended for Portability)

```python
"""
VALIDATOR_CONFIG:
  type: orchestrator
  generator: generate_workflow.py  # ← Relative to orchestrator
  workflow_dir: .                  # ← Current directory
  generator_args: dev
"""
```

**Resolves to:**
- Generator: `/path/to/orchestrator/generate_workflow.py`
- Workflow dir: `/path/to/orchestrator/`

### Absolute Paths (Recommended for Production)

```python
"""
VALIDATOR_CONFIG:
  type: orchestrator
  generator: /opt/workflows/ml_pipeline/generate_workflow.py
  workflow_dir: /opt/workflows/ml_pipeline
  generator_args: production
"""
```

### Parent Directory References

```python
"""
VALIDATOR_CONFIG:
  type: orchestrator
  generator: ../generators/generate_workflow.py
  workflow_dir: ..
  generator_args: staging
"""
```

---

## Multiple Orchestrators, One Generator

You can have multiple orchestrators declaring the same generator:

```
/opt/workflows/project/
├── generate_workflow.py         # The generator
├── orchestrator_dev.py          # Declares generator with dev args
├── orchestrator_prod.py         # Declares generator with prod args
└── orchestrator_staging.py      # Declares generator with staging args
```

**orchestrator_dev.py:**
```python
"""
VALIDATOR_CONFIG:
  type: orchestrator
  generator: generate_workflow.py
  workflow_dir: .
  generator_args: dev --workers=1
"""
```

**orchestrator_prod.py:**
```python
"""
VALIDATOR_CONFIG:
  type: orchestrator
  generator: generate_workflow.py
  workflow_dir: .
  generator_args: production --workers=16
"""
```

**Validation:**
```bash
# Validate dev orchestrator
python cli.py orchestrator_dev.py

# Validate prod orchestrator
python cli.py orchestrator_prod.py
```

Each validates the same generator with different arguments!

---

## Override Declared Settings

You can override the orchestrator's declared settings:

```bash
# Use different generator
python cli.py orchestrator.py --from-generator custom_generator.py

# Use different arguments
python cli.py orchestrator.py --workflow-args 'staging --workers=2'

# Use different workflow directory
python cli.py orchestrator.py --workflow-dir /custom/path
```

---

## Comparison: Generator vs Orchestrator

| Aspect | Generator | Orchestrator |
|--------|-----------|--------------|
| **Purpose** | Generates YAML | Launches/manages workflow |
| **Declaration** | `type: generator` | `type: orchestrator` |
| **Must specify** | workflow_dir | generator + workflow_dir |
| **Validation** | Validates itself | Validates declared generator |

---

## Best Practices

### 1. Always Declare Your Generator
```python
"""
VALIDATOR_CONFIG:
  type: orchestrator
  generator: generate_workflow.py  # ✅ Always specify
  workflow_dir: .
  generator_args: production
"""
```

### 2. Use Consistent Directory Structure
```
project/
├── orchestrator.py
├── generate_workflow.py  # ← Same directory as orchestrator
└── scripts/
```

### 3. Document the Relationship
```python
"""
ML Pipeline Orchestrator

This orchestrator uses generate_workflow.py to create dynamic
ML workflows based on environment and configuration.

VALIDATOR_CONFIG:
  type: orchestrator
  generator: generate_workflow.py
  workflow_dir: /opt/workflows/ml_pipeline
  generator_args: production --workers=8
"""
```

### 4. Test Each Environment
```bash
# Validate with dev settings
python cli.py orchestrator.py --workflow-args 'dev --workers=1'

# Validate with production settings
python cli.py orchestrator.py --workflow-args 'production --workers=16'
```

---

## Troubleshooting

### Issue 1: Generator Not Found
```
❌ Orchestrator declares generator 'generate_workflow.py' but file not found
```

**Solution:** Check generator path is correct
```python
"""
VALIDATOR_CONFIG:
  type: orchestrator
  generator: ./generate_workflow.py  # ← Add ./ for same directory
  workflow_dir: .
"""
```

### Issue 2: Wrong Workflow Directory
```
❌ Transformation executable not found: scripts/train.py
```

**Solution:** Verify workflow_dir points to correct location
```python
"""
VALIDATOR_CONFIG:
  type: orchestrator
  generator: generate_workflow.py
  workflow_dir: /opt/workflows/ml_pipeline  # ← Use absolute path
  generator_args: production
"""
```

### Issue 3: Not Detecting Orchestrator Config
```
📄 YAML workflow detected: orchestrator.py
```

**Solution:** Check indentation in VALIDATOR_CONFIG
```python
# Wrong ❌
"""
VALIDATOR_CONFIG:
type: orchestrator  # ← No indentation
"""

# Correct ✅
"""
VALIDATOR_CONFIG:
  type: orchestrator  # ← Two spaces
  generator: generate_workflow.py
"""
```

---

## Complete Workflow

### Development
```bash
# 1. Write orchestrator with generator declaration
vim orchestrator.py

# 2. Write generator
vim generate_workflow.py

# 3. Validate
python validator/cli.py orchestrator.py

# 4. Run orchestrator
python orchestrator.py dev
```

### CI/CD Pipeline
```yaml
# .github/workflows/validate.yml
name: Validate Workflow

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Validate Orchestrator
        run: |
          python validator/cli.py orchestrator.py \
            --format json \
            -o validation_report.json

      - name: Check Results
        run: |
          if [ $? -ne 0 ]; then
            echo "❌ Validation failed"
            exit 1
          fi
```

---

This orchestrator declaration system ensures the validator always knows which generator to validate, even when called by other scripts! 🎯
