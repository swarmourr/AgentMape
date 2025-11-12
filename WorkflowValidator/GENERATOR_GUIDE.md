# Simple Generator Scripts Guide

## What is a Generator Script?

A **generator script** is a simple program that outputs Pegasus workflow YAML to stdout. Unlike workflow descriptors (which define workflow structure in Python variables), generators dynamically create YAML based on arguments or configuration.

## Generator vs Descriptor

| Type | Description | Example |
|------|-------------|---------|
| **Descriptor** | Python file with `workflow`, `jobs`, `transformations` variables | `workflow_descriptor.py` |
| **Generator** | Script that prints YAML to stdout | `generate_workflow.py`, `generate.sh` |

## Simple Generator Examples

### Example 1: Basic Python Generator

**generate_workflow.py:**
```python
#!/usr/bin/env python3
import sys
import yaml

def main():
    num_jobs = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    workflow = {
        'name': 'generated_workflow',
        'version': '1.0',
        'jobs': []
    }

    # Generate N jobs
    for i in range(num_jobs):
        workflow['jobs'].append({
            'name': f'job_{i}',
            'transformation': 'Process',
            'arguments': ['-i', f'input_{i}.dat']
        })

    workflow['transformations'] = [
        {'name': 'Process', 'pfn': 'scripts/process.sh', 'type': 'stageable'}
    ]

    # Output YAML to stdout
    print(yaml.dump(workflow, default_flow_style=False))

if __name__ == '__main__':
    main()
```

**Validate:**
```bash
# Generator creates workflow with 10 jobs
python cli.py generate_workflow.py \
  --from-generator \
  --workflow-args '10' \
  --workflow-dir /path/to/workflow/
```

**What happens:**
1. Runs: `python3 generate_workflow.py 10`
2. Captures YAML output from stdout
3. Validates the generated YAML
4. Checks that `scripts/process.sh` exists in `/path/to/workflow/`

---

### Example 2: Shell Script Generator

**generate.sh:**
```bash
#!/bin/bash

ENV=${1:-dev}
WORKERS=${2:-1}

cat <<EOF
name: batch_workflow
version: 1.0

jobs:
  - name: extract
    transformation: Extract
    arguments: ['--env', '$ENV']

  - name: process
    transformation: Process
    arguments: ['--workers', '$WORKERS']
    parents: [extract]

  - name: load
    transformation: Load
    parents: [process]

transformations:
  - name: Extract
    pfn: bin/extract.sh
    type: stageable

  - name: Process
    pfn: bin/process.sh
    type: stageable

  - name: Load
    pfn: bin/load.sh
    type: stageable
EOF
```

**Validate:**
```bash
python cli.py generate.sh \
  --from-generator \
  --workflow-args 'production 4' \
  --workflow-dir /opt/workflows/batch/
```

**Output:**
```
⚙️  Generator script detected: generate.sh
   Running: bash generate.sh production 4
✅ Generator produced 423 bytes of YAML

🔍 Validating workflow (level: standard)...

Running structure validator...
Running path validator...
✓ All transformations validated (3 checks)

✅ Validation PASSED - Workflow is ready to submit!
```

---

### Example 3: Template-Based Generator

**generate_from_template.py:**
```python
#!/usr/bin/env python3
import sys
import yaml
from jinja2 import Template

# Template for workflow
TEMPLATE = """
name: {{ workflow_name }}
version: 1.0

jobs:
{% for job in jobs %}
  - name: {{ job.name }}
    transformation: {{ job.transformation }}
    arguments: {{ job.args }}
    {% if job.parents %}parents: {{ job.parents }}{% endif %}
{% endfor %}

transformations:
{% for trans in transformations %}
  - name: {{ trans.name }}
    pfn: {{ trans.pfn }}
    type: stageable
{% endfor %}
"""

def main():
    config_file = sys.argv[1] if len(sys.argv) > 1 else 'config.yaml'

    # Load configuration
    with open(config_file) as f:
        config = yaml.safe_load(f)

    # Render template
    template = Template(TEMPLATE)
    output = template.render(**config)

    print(output)

if __name__ == '__main__':
    main()
```

**config.yaml:**
```yaml
workflow_name: ml_pipeline
jobs:
  - name: download
    transformation: Download
    args: ['--url', 'https://data.com/dataset.csv']
  - name: train
    transformation: Train
    args: ['--epochs', '100']
    parents: [download]

transformations:
  - name: Download
    pfn: scripts/download.py
  - name: Train
    pfn: scripts/train.py
```

**Validate:**
```bash
python cli.py generate_from_template.py \
  --from-generator \
  --workflow-args 'config.yaml' \
  --workflow-dir /home/user/ml_project/
```

---

### Example 4: Dynamic Workflow from Database

**generate_from_db.py:**
```python
#!/usr/bin/env python3
import sys
import yaml
import sqlite3

def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'workflows.db'
    workflow_id = sys.argv[2] if len(sys.argv) > 2 else '1'

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Fetch workflow definition
    cursor.execute("""
        SELECT name, version FROM workflows WHERE id = ?
    """, (workflow_id,))
    name, version = cursor.fetchone()

    # Fetch jobs
    cursor.execute("""
        SELECT name, transformation, arguments FROM jobs
        WHERE workflow_id = ?
    """, (workflow_id,))
    jobs = [
        {'name': row[0], 'transformation': row[1], 'arguments': row[2].split()}
        for row in cursor.fetchall()
    ]

    # Fetch transformations
    cursor.execute("""
        SELECT name, pfn FROM transformations
        WHERE workflow_id = ?
    """, (workflow_id,))
    transformations = [
        {'name': row[0], 'pfn': row[1], 'type': 'stageable'}
        for row in cursor.fetchall()
    ]

    # Build workflow
    workflow = {
        'name': name,
        'version': version,
        'jobs': jobs,
        'transformations': transformations
    }

    print(yaml.dump(workflow, default_flow_style=False))

    conn.close()

if __name__ == '__main__':
    main()
```

**Validate:**
```bash
python cli.py generate_from_db.py \
  --from-generator \
  --workflow-args 'workflows.db 42' \
  --workflow-dir /opt/dynamic_workflows/
```

---

## Usage Patterns

### Pattern 1: Simple Generator
```bash
# Generator takes no arguments
python cli.py generate.py --from-generator
```

### Pattern 2: Generator with Arguments
```bash
# Pass configuration to generator
python cli.py generate.py \
  --from-generator \
  --workflow-args 'config.json production'
```

### Pattern 3: Generator with Custom Working Directory
```bash
# Generator uses relative paths, need to set base directory
python cli.py generate.py \
  --from-generator \
  --workflow-dir /path/to/workflow/ \
  --workflow-args 'prod'
```

### Pattern 4: Save Generated YAML
```bash
# Validate and save the generated YAML
python cli.py generate.py \
  --from-generator \
  --output-yaml /tmp/generated_workflow.yml \
  --format json \
  -o validation_report.json
```

---

## How It Works

When you use `--from-generator`:

1. **Execute the generator script**
   - Runs: `python3 script.py [args]` or `bash script.sh [args]`
   - Working directory: `--workflow-dir` or script's parent directory
   - Timeout: 120 seconds

2. **Capture stdout**
   - Generator must output valid YAML to stdout
   - stderr is ignored (unless generator fails)

3. **Save to temporary file**
   - YAML is saved to `/tmp/workflow_XXXX.yml`

4. **Validate the YAML**
   - Runs normal validation on generated YAML
   - Paths resolve from `--workflow-dir` if provided

5. **Report results**
   - Shows validation results
   - Optionally saves generated YAML

---

## Best Practices

### 1. Always Output Valid YAML
```python
# Good ✅
print(yaml.dump(workflow))

# Bad ❌
print(f"Workflow: {workflow}")  # Not valid YAML
```

### 2. Use stderr for Logging
```python
# Good ✅
import sys
print("Generating workflow...", file=sys.stderr)
print(yaml.dump(workflow))  # YAML goes to stdout

# Bad ❌
print("Generating workflow...")  # Pollutes YAML output
print(yaml.dump(workflow))
```

### 3. Handle Arguments Properly
```python
import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: generate.py <config_file>", file=sys.stderr)
        sys.exit(1)

    config_file = sys.argv[1]
    # ... generate workflow ...
```

### 4. Set Executable Permission
```bash
chmod +x generate.py
chmod +x generate.sh
```

### 5. Use Absolute Paths in Production
```yaml
# Good ✅
transformations:
  - name: Process
    pfn: /opt/workflows/scripts/process.sh

# Acceptable with --workflow-dir ✅
transformations:
  - name: Process
    pfn: scripts/process.sh  # Resolves from --workflow-dir
```

---

## Troubleshooting

### Issue 1: Generator Fails to Run
```
❌ Generator failed with exit code 1
Error output: ModuleNotFoundError: No module named 'yaml'
```

**Solution:** Install dependencies
```bash
pip install pyyaml
```

### Issue 2: Invalid YAML Output
```
❌ Failed to load workflow YAML: ...
```

**Solution:** Debug generator output
```bash
# Test generator directly
python generate.py args > test.yml
cat test.yml

# Validate YAML manually
python -c "import yaml; yaml.safe_load(open('test.yml'))"
```

### Issue 3: Paths Not Found
```
❌ Transformation executable not found: scripts/process.sh
```

**Solution:** Use `--workflow-dir`
```bash
python cli.py generate.py \
  --from-generator \
  --workflow-dir /correct/base/directory/
```

### Issue 4: Generator Timeout
```
❌ Generator timed out after 120 seconds
```

**Solution:** Optimize generator or increase timeout (modify `cli.py:120`)

---

## Comparison: When to Use What?

| Scenario | Use |
|----------|-----|
| Static workflow structure | **Descriptor** (`workflow_descriptor.py`) |
| Dynamic workflow (config-based) | **Generator** with `--from-generator` |
| Workflow from database/API | **Generator** with `--from-generator` |
| Template-based workflows | **Generator** with `--from-generator` |
| Simple validation of existing YAML | Direct validation (no flags) |

---

## Complete Example: Production Workflow

**Structure:**
```
/opt/workflows/production/
├── generate_pipeline.py    # Generator
├── config/
│   └── prod.yaml          # Configuration
├── scripts/
│   ├── extract.py
│   ├── transform.py
│   └── load.py
└── Makefile
```

**generate_pipeline.py:**
```python
#!/usr/bin/env python3
import sys
import yaml

def generate_etl_workflow(config_file):
    with open(config_file) as f:
        config = yaml.safe_load(f)

    workflow = {
        'name': f"etl_pipeline_{config['environment']}",
        'version': '1.0',
        'jobs': [
            {
                'name': 'extract',
                'transformation': 'Extract',
                'arguments': ['--source', config['data_source']]
            },
            {
                'name': 'transform',
                'transformation': 'Transform',
                'arguments': ['--workers', str(config['workers'])],
                'parents': ['extract']
            },
            {
                'name': 'load',
                'transformation': 'Load',
                'arguments': ['--target', config['data_target']],
                'parents': ['transform']
            }
        ],
        'transformations': [
            {'name': 'Extract', 'pfn': 'scripts/extract.py', 'type': 'stageable'},
            {'name': 'Transform', 'pfn': 'scripts/transform.py', 'type': 'stageable'},
            {'name': 'Load', 'pfn': 'scripts/load.py', 'type': 'stageable'}
        ]
    }

    return yaml.dump(workflow, default_flow_style=False)

if __name__ == '__main__':
    config_file = sys.argv[1]
    print(generate_etl_workflow(config_file))
```

**Makefile:**
```makefile
VALIDATOR := python /opt/validator/cli.py
WORKFLOW_DIR := $(shell pwd)

validate-prod:
	$(VALIDATOR) generate_pipeline.py \
		--from-generator \
		--workflow-args 'config/prod.yaml' \
		--workflow-dir $(WORKFLOW_DIR) \
		--level full \
		--format json \
		-o reports/validation_$(shell date +%Y%m%d_%H%M%S).json

deploy: validate-prod
	@echo "✅ Validation passed - deploying to production"
	# Deploy workflow...
```

**Run:**
```bash
cd /opt/workflows/production/
make validate-prod
```

---

This generator support makes the validator much more flexible for dynamic workflow scenarios!
