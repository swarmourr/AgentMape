# Generator Auto-Detection Guide

## Overview

The validator can **automatically detect** that a file is a generator and use the correct settings without requiring manual flags. This is perfect for workflows where other files invoke your generator!

## Why Auto-Detection?

**Problem:** Your generator is called by other scripts:
```
orchestrator.py → calls → generate_workflow.py → outputs YAML
```

Without auto-detection, validators need to know:
```bash
# Manual way (tedious)
python cli.py generate_workflow.py \
  --from-generator \
  --workflow-dir /opt/workflows/project/ \
  --workflow-args 'production'
```

With auto-detection:
```bash
# Automatic way (simple!)
python cli.py generate_workflow.py
```

The validator reads metadata **from the generator itself** and knows what to do!

---

## Method 1: Inline Metadata (Recommended)

Add a `VALIDATOR_CONFIG` block to your generator's docstring or comments.

### Python Generator

**generate_workflow.py:**
```python
#!/usr/bin/env python3
"""
ML Pipeline Workflow Generator

VALIDATOR_CONFIG:
  type: generator
  workflow_dir: /opt/workflows/ml_pipeline
  default_args: production --workers=4
"""
import sys
import yaml

def generate_workflow(env, workers):
    workflow = {
        'name': f'ml_pipeline_{env}',
        'version': '1.0',
        'jobs': [
            {'name': f'worker_{i}', 'transformation': 'Train'}
            for i in range(int(workers))
        ],
        'transformations': [
            {'name': 'Train', 'pfn': 'scripts/train.py', 'type': 'stageable'}
        ]
    }
    return workflow

def main():
    env = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    workers = sys.argv[2] if len(sys.argv) > 2 else '1'

    workflow = generate_workflow(env, workers)
    print(yaml.dump(workflow, default_flow_style=False))

if __name__ == '__main__':
    main()
```

**Usage:**
```bash
# Auto-detects generator, workflow_dir, and default_args!
python cli.py generate_workflow.py

# Override default args if needed
python cli.py generate_workflow.py --workflow-args 'staging --workers=2'
```

**Output:**
```
ℹ️  Auto-detected generator configuration
   Using workflow_dir from metadata: /opt/workflows/ml_pipeline
   Using default_args from metadata: production --workers=4
⚙️  Generator script detected: generate_workflow.py
   Running: python3 generate_workflow.py production --workers=4
✅ Generator produced 345 bytes of YAML

🔍 Validating workflow (level: standard)...
✅ Validation PASSED
```

---

### Shell Script Generator

**generate.sh:**
```bash
#!/bin/bash
#
# Workflow Generator for Batch Processing
#
# VALIDATOR_CONFIG:
#   type: generator
#   workflow_dir: /data/workflows/batch
#   default_args: production

ENV=${1:-dev}

cat <<EOF
name: batch_workflow_$ENV
version: 1.0

jobs:
  - name: extract
    transformation: Extract
    arguments: ['--env', '$ENV']

transformations:
  - name: Extract
    pfn: bin/extract.sh
    type: stageable
EOF
```

**Usage:**
```bash
# Auto-detects from shell comments
python cli.py generate.sh

# Override with custom args
python cli.py generate.sh --workflow-args 'staging'
```

---

## Method 2: `.validator.yaml` Config File (Project-Level)

Place a `.validator.yaml` file in your workflow directory to configure validation for the entire project.

### Project Structure

```
/opt/workflows/ml_pipeline/
├── .validator.yaml          # ← Configuration file
├── generate_workflow.py     # Generator script
├── orchestrator.py          # Calls generator
├── scripts/
│   ├── download.py
│   ├── preprocess.py
│   └── train.py
└── config/
    └── prod.yaml
```

### .validator.yaml

**.validator.yaml:**
```yaml
# Workflow validation configuration

workflow:
  # Path to generator script (relative to this file)
  generator: generate_workflow.py

  # Working directory for path resolution
  # Use "." for current directory, or specify absolute/relative path
  directory: .

  # Default arguments to pass to generator
  default_args: production --workers=4

  # Validation level: quick, standard, or full
  validation_level: standard

  # Output format: terminal, json, or html
  output_format: terminal

# Optional: catalog paths
catalogs:
  transformation_catalog: null
  replica_catalog: null

# Optional: Override config file location
validator_config: /path/to/custom/validator_config.json
```

### Usage

From anywhere:
```bash
# Validator finds .validator.yaml and uses its settings
python /path/to/validator/cli.py /opt/workflows/ml_pipeline/generate_workflow.py
```

From project directory:
```bash
cd /opt/workflows/ml_pipeline/
python /path/to/validator/cli.py generate_workflow.py
```

---

## Method 3: Relative Workflow Directory

If your generator uses **relative paths**, specify `workflow_dir` relative to the generator's location:

**generate_workflow.py:**
```python
"""
VALIDATOR_CONFIG:
  type: generator
  workflow_dir: .  # ← Current directory (where generator is located)
  default_args: dev
"""
```

This resolves to the directory containing `generate_workflow.py`.

**Or use parent directory:**
```python
"""
VALIDATOR_CONFIG:
  type: generator
  workflow_dir: ../  # ← Parent directory
  default_args: dev
"""
```

---

## Configuration Options

| Option | Description | Example |
|--------|-------------|---------|
| `type` | Must be `generator` | `generator` |
| `workflow_dir` | Base directory for path resolution | `/opt/workflows/project` or `.` |
| `default_args` | Default arguments to pass to generator | `production --workers=4` |

---

## Complete Examples

### Example 1: Database-Driven Generator

**generate_from_db.py:**
```python
#!/usr/bin/env python3
"""
Generate workflow from database configuration

VALIDATOR_CONFIG:
  type: generator
  workflow_dir: /opt/workflows/dynamic
  default_args: workflows.db 42
"""
import sys
import yaml
import sqlite3

def fetch_workflow(db_path, workflow_id):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name, version FROM workflows WHERE id = ?", (workflow_id,))
    name, version = cursor.fetchone()

    cursor.execute("SELECT name, transformation FROM jobs WHERE workflow_id = ?", (workflow_id,))
    jobs = [{'name': row[0], 'transformation': row[1]} for row in cursor.fetchall()]

    cursor.execute("SELECT name, pfn FROM transformations WHERE workflow_id = ?", (workflow_id,))
    transformations = [
        {'name': row[0], 'pfn': row[1], 'type': 'stageable'}
        for row in cursor.fetchall()
    ]

    conn.close()

    return {
        'name': name,
        'version': version,
        'jobs': jobs,
        'transformations': transformations
    }

def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'workflows.db'
    workflow_id = sys.argv[2] if len(sys.argv) > 2 else '1'

    workflow = fetch_workflow(db_path, workflow_id)
    print(yaml.dump(workflow, default_flow_style=False))

if __name__ == '__main__':
    main()
```

**Usage:**
```bash
# Uses defaults from VALIDATOR_CONFIG
python cli.py generate_from_db.py

# Override to use different database/workflow
python cli.py generate_from_db.py --workflow-args 'other.db 100'
```

---

### Example 2: Template-Based Generator

**generate_from_template.py:**
```python
#!/usr/bin/env python3
"""
Generate workflow from Jinja2 template

VALIDATOR_CONFIG:
  type: generator
  workflow_dir: /home/user/workflows/templates
  default_args: config/production.yaml
"""
import sys
import yaml
from jinja2 import Template

TEMPLATE_FILE = 'templates/workflow.j2'

def main():
    config_file = sys.argv[1] if len(sys.argv) > 1 else 'config/default.yaml'

    # Load configuration
    with open(config_file) as f:
        config = yaml.safe_load(f)

    # Load template
    with open(TEMPLATE_FILE) as f:
        template = Template(f.read())

    # Render workflow
    output = template.render(**config)
    print(output)

if __name__ == '__main__':
    main()
```

**Project:**
```
/home/user/workflows/templates/
├── .validator.yaml  # OR inline config in generate_from_template.py
├── generate_from_template.py
├── templates/
│   └── workflow.j2
├── config/
│   ├── default.yaml
│   └── production.yaml
└── scripts/
    └── process.py
```

**Validation:**
```bash
# Auto-detects and validates
python cli.py generate_from_template.py
```

---

### Example 3: Multi-Environment Generator

**generate.py:**
```python
#!/usr/bin/env python3
"""
Multi-environment workflow generator

VALIDATOR_CONFIG:
  type: generator
  workflow_dir: .
  default_args: production
"""
import sys
import yaml

ENVIRONMENTS = {
    'dev': {'workers': 1, 'data_source': 'dev_data.csv'},
    'staging': {'workers': 2, 'data_source': 'staging_data.csv'},
    'production': {'workers': 8, 'data_source': 's3://prod-bucket/data.csv'}
}

def generate_workflow(env):
    config = ENVIRONMENTS.get(env, ENVIRONMENTS['dev'])

    workflow = {
        'name': f'pipeline_{env}',
        'version': '1.0',
        'jobs': [
            {
                'name': 'download',
                'transformation': 'Download',
                'arguments': ['--source', config['data_source']]
            }
        ] + [
            {
                'name': f'process_{i}',
                'transformation': 'Process',
                'arguments': ['--worker-id', str(i)],
                'parents': ['download']
            }
            for i in range(config['workers'])
        ],
        'transformations': [
            {'name': 'Download', 'pfn': 'scripts/download.py', 'type': 'stageable'},
            {'name': 'Process', 'pfn': 'scripts/process.py', 'type': 'stageable'}
        ]
    }

    return workflow

def main():
    env = sys.argv[1] if len(sys.argv) > 1 else 'dev'

    if env not in ENVIRONMENTS:
        print(f"Error: Unknown environment '{env}'", file=sys.stderr)
        print(f"Available: {', '.join(ENVIRONMENTS.keys())}", file=sys.stderr)
        sys.exit(1)

    workflow = generate_workflow(env)
    print(yaml.dump(workflow, default_flow_style=False))

if __name__ == '__main__':
    main()
```

**Usage:**
```bash
# Uses production (from default_args)
python cli.py generate.py

# Test with dev
python cli.py generate.py --workflow-args 'dev'

# Validate staging
python cli.py generate.py --workflow-args 'staging'
```

---

## Priority Order

When the validator looks for configuration, it checks in this order:

1. **Command-line flags** (highest priority)
   ```bash
   python cli.py generate.py --from-generator --workflow-dir /custom/path
   ```

2. **Inline `VALIDATOR_CONFIG`** in the file
   ```python
   """
   VALIDATOR_CONFIG:
     type: generator
     workflow_dir: /opt/workflows
   """
   ```

3. **`.validator.yaml`** in the same directory

4. **Default behavior** (workflow file's parent directory)

---

## When Other Files Use Your Generator

This is the key use case! Your generator is called by other scripts:

**orchestrator.py:**
```python
#!/usr/bin/env python3
import subprocess
import sys

def main():
    env = sys.argv[1] if len(sys.argv) > 1 else 'dev'

    # Generate workflow YAML
    result = subprocess.run(
        ['python3', 'generate_workflow.py', env],
        capture_output=True,
        text=True
    )

    workflow_yaml = result.stdout

    # Save and execute
    with open(f'workflow_{env}.yml', 'w') as f:
        f.write(workflow_yaml)

    print(f"✅ Generated workflow_{env}.yml")

    # Execute workflow
    # ...

if __name__ == '__main__':
    main()
```

**With auto-detection in generate_workflow.py:**
```python
"""
VALIDATOR_CONFIG:
  type: generator
  workflow_dir: /opt/workflows/project
  default_args: production
"""
```

**Now validation works seamlessly:**
```bash
# Validate the generator (auto-detects settings)
python validator/cli.py generate_workflow.py

# Validate the orchestrator (uses generator's settings)
python validator/cli.py orchestrator.py \
  --workflow-dir /opt/workflows/project
```

---

## Best Practices

### 1. Always Include `VALIDATOR_CONFIG`
```python
"""
Your docstring

VALIDATOR_CONFIG:
  type: generator
  workflow_dir: .  # Or absolute path
  default_args: production
"""
```

### 2. Use Absolute Paths in Production
```python
"""
VALIDATOR_CONFIG:
  type: generator
  workflow_dir: /opt/workflows/ml_pipeline  # ✅ Absolute
  default_args: production
"""
```

### 3. Relative Paths for Development
```python
"""
VALIDATOR_CONFIG:
  type: generator
  workflow_dir: .  # ✅ Current directory
  default_args: dev
"""
```

### 4. Document Your Configuration
```python
"""
ML Pipeline Workflow Generator

Generates a dynamic machine learning workflow based on environment.

VALIDATOR_CONFIG:
  type: generator
  workflow_dir: /opt/workflows/ml_pipeline
  default_args: production --workers=8

Usage:
  python generate_workflow.py [environment] [--workers=N]

Environments: dev, staging, production
"""
```

---

## Troubleshooting

### Issue 1: Metadata Not Detected
```
📄 YAML workflow detected: generate.py
```

**Solution:** Check indentation in `VALIDATOR_CONFIG` block
```python
# Wrong ❌
"""
VALIDATOR_CONFIG:
type: generator  # ← No indentation
"""

# Correct ✅
"""
VALIDATOR_CONFIG:
  type: generator  # ← Two spaces
  workflow_dir: /path
"""
```

### Issue 2: Paths Still Wrong
```
❌ Transformation executable not found: scripts/train.py
```

**Solution:** Verify `workflow_dir` is correct
```python
"""
VALIDATOR_CONFIG:
  type: generator
  workflow_dir: /opt/workflows/project  # ← Make sure this is absolute
```

### Issue 3: Args Not Applied
```bash
# Shows: Running: python3 generate.py
# Expected: Running: python3 generate.py production
```

**Solution:** Check `default_args` syntax
```python
"""
VALIDATOR_CONFIG:
  type: generator
  workflow_dir: .
  default_args: production --workers=4  # ← Space-separated, no quotes
"""
```

---

This auto-detection makes validation seamless when generators are called by other scripts! 🎉
