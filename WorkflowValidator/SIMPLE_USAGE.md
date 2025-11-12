# Simple Usage Guide

## Just Run and Validate

The validator can **execute your script** and **validate the YAML it outputs**. Simple as that!

---

## Basic Usage

### 1. Your Generator Script

**generate_workflow.py:**
```python
#!/usr/bin/env python3
import yaml
import sys

# Get arguments
env = sys.argv[1] if len(sys.argv) > 1 else 'dev'

# Generate workflow
workflow = {
    'name': f'pipeline_{env}',
    'version': '1.0',
    'jobs': [
        {'name': 'job1', 'transformation': 'Process'}
    ],
    'transformations': [
        {'name': 'Process', 'pfn': 'scripts/process.sh', 'type': 'stageable'}
    ]
}

# Output to stdout
print(yaml.dump(workflow))
```

### 2. Validate

```bash
python cli.py generate_workflow.py \
  --from-generator \
  --workflow-dir /path/to/your/workflow/
```

**That's it!**

---

## What Happens

1. **Runs your script:** `python3 generate_workflow.py`
2. **Captures YAML** from stdout
3. **Validates the YAML:**
   - Structure
   - Paths (scripts/process.sh exists?)
   - Dependencies
   - More...
4. **Shows results**

---

## With Arguments

```bash
python cli.py generate_workflow.py \
  --from-generator \
  --workflow-args 'production --workers=4' \
  --workflow-dir /opt/workflows/project/
```

Runs: `python3 generate_workflow.py production --workers=4`

---

## Shell Scripts

**generate.sh:**
```bash
#!/bin/bash
ENV=${1:-dev}

cat <<EOF
name: workflow_$ENV
version: 1.0
jobs:
  - name: extract
    transformation: Extract
transformations:
  - name: Extract
    pfn: bin/extract.sh
    type: stageable
EOF
```

**Validate:**
```bash
python cli.py generate.sh \
  --from-generator \
  --workflow-args 'production' \
  --workflow-dir /data/workflows/
```

---

## Complete Example

### Project Structure
```
/opt/workflows/ml_pipeline/
├── generate_workflow.py
├── scripts/
│   ├── download.py
│   ├── process.py
│   └── train.py
└── data/
```

### Generator Script

**generate_workflow.py:**
```python
#!/usr/bin/env python3
import yaml
import sys

def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    workflow = {
        'name': 'ml_pipeline',
        'version': '1.0',
        'jobs': [
            {
                'name': 'download',
                'transformation': 'Download',
                'uses': [{'name': 'data.csv', 'type': 'output'}]
            }
        ],
        'transformations': [
            {'name': 'Download', 'pfn': 'scripts/download.py', 'type': 'stageable'},
            {'name': 'Process', 'pfn': 'scripts/process.py', 'type': 'stageable'},
            {'name': 'Train', 'pfn': 'scripts/train.py', 'type': 'stageable'}
        ]
    }

    # Add worker jobs
    for i in range(workers):
        workflow['jobs'].append({
            'name': f'train_{i}',
            'transformation': 'Train',
            'parents': ['download']
        })

    print(yaml.dump(workflow, default_flow_style=False))

if __name__ == '__main__':
    main()
```

### Run Validation

```bash
python /path/to/validator/cli.py /opt/workflows/ml_pipeline/generate_workflow.py \
  --from-generator \
  --workflow-args '4' \
  --workflow-dir /opt/workflows/ml_pipeline/
```

### Output

```
⚙️  Generator script detected: generate_workflow.py
   Running: python3 generate_workflow.py 4
✅ Generator produced 456 bytes of YAML

🔍 Validating workflow (level: standard)...

Running structure validator...
✓ Workflow structure valid
✓ 5 jobs defined
✓ 3 transformations defined
✓ No circular dependencies

Running path validator...
✓ scripts/download.py ✅ (exists, readable, executable)
✓ scripts/process.py ✅ (exists, readable, executable)
✓ scripts/train.py ✅ (exists, readable, executable)

✅ Validation PASSED - Workflow is ready to submit!
```

---

## Flags Explained

| Flag | Description | Example |
|------|-------------|---------|
| `--from-generator` | Tells validator to run the script | Required |
| `--workflow-args` | Arguments to pass to your script | `'production 4'` |
| `--workflow-dir` | Where workflow files are located | `/opt/workflows/project` |
| `--level` | Validation depth | `quick`, `standard`, `full` |
| `--format` | Output format | `terminal`, `json`, `html` |
| `-o` | Save report to file | `report.json` |

---

## Common Patterns

### Pattern 1: Development Testing
```bash
# Quick validation during development
python cli.py generate.py \
  --from-generator \
  --workflow-args 'dev' \
  --workflow-dir . \
  --level quick
```

### Pattern 2: Production Validation
```bash
# Full validation before deployment
python cli.py generate.py \
  --from-generator \
  --workflow-args 'production --workers=16' \
  --workflow-dir /opt/workflows/prod/ \
  --level full \
  --format json \
  -o validation_report.json
```

### Pattern 3: CI/CD Pipeline
```bash
# In your CI/CD script
python validator/cli.py generate_workflow.py \
  --from-generator \
  --workflow-args "$ENV $WORKERS" \
  --workflow-dir $WORKFLOW_DIR \
  --level standard

if [ $? -ne 0 ]; then
    echo "❌ Validation failed"
    exit 1
fi
```

---

## Requirements for Your Script

Your generator script must:

1. ✅ **Output valid YAML to stdout**
   ```python
   print(yaml.dump(workflow))  # ✅ Good
   ```

2. ✅ **Use stderr for logs** (not stdout)
   ```python
   print("Generating...", file=sys.stderr)  # ✅ Good
   print(yaml.dump(workflow))  # YAML to stdout
   ```

3. ✅ **Exit with 0 on success**
   ```python
   sys.exit(0)  # or just end normally
   ```

4. ✅ **Be executable** (optional but recommended)
   ```bash
   chmod +x generate_workflow.py
   ```

---

## Troubleshooting

### Issue: "Generator failed with exit code 1"
```
❌ Generator failed with exit code 1
Error output: ModuleNotFoundError: No module named 'yaml'
```

**Fix:** Install dependencies
```bash
pip install pyyaml
```

### Issue: "Invalid YAML"
```
❌ Failed to load workflow YAML
```

**Fix:** Test your generator directly
```bash
python generate_workflow.py production > test.yml
cat test.yml  # Check if it's valid YAML
```

### Issue: "Paths not found"
```
❌ Transformation executable not found: scripts/process.sh
```

**Fix:** Use correct `--workflow-dir`
```bash
python cli.py generate.py \
  --from-generator \
  --workflow-dir /correct/path/to/workflow/  # ← Set this correctly
```

---

## Complete Workflow

### 1. Create Generator
```bash
cat > generate_workflow.py <<'EOF'
#!/usr/bin/env python3
import yaml
import sys

workflow = {
    'name': 'simple_workflow',
    'jobs': [{'name': 'job1', 'transformation': 'Process'}],
    'transformations': [{'name': 'Process', 'pfn': 'scripts/process.sh'}]
}

print(yaml.dump(workflow))
EOF

chmod +x generate_workflow.py
```

### 2. Create Scripts
```bash
mkdir scripts
cat > scripts/process.sh <<'EOF'
#!/bin/bash
echo "Processing..."
EOF

chmod +x scripts/process.sh
```

### 3. Validate
```bash
python /path/to/validator/cli.py generate_workflow.py \
  --from-generator \
  --workflow-dir $(pwd)
```

### 4. Done!
```
✅ Validation PASSED - Workflow is ready to submit!
```

---

## Summary

**One command does it all:**

```bash
python cli.py YOUR_SCRIPT \
  --from-generator \
  --workflow-args 'YOUR ARGS' \
  --workflow-dir /path/to/workflow/
```

1. Runs your script
2. Captures YAML
3. Validates everything
4. Reports results

**Simple and powerful!** 🚀
