# Runner Flag Guide

## Perfect for Your Use Case!

Use `--runner` when you have an **orchestrator/wrapper script** that executes your generator.

---

## Simple Syntax

```bash
python cli.py GENERATOR.py --runner ORCHESTRATOR.sh --workflow-dir /path/
```

**Translation:** "Run `ORCHESTRATOR.sh`, capture its YAML output, and validate it using `/path/` as the workflow directory"

---

## How It Works

```
You specify:
  - generator.py (the actual generator)
  - --runner orchestrator.sh (the script that calls generator.py)

Validator:
  1. Runs: orchestrator.sh
  2. Captures YAML from stdout
  3. Validates YAML with paths from workflow_dir
```

---

## Complete Example

### Your Files

**generate_workflow.py** (The generator):
```python
#!/usr/bin/env python3
import yaml
import sys

env = sys.argv[1] if len(sys.argv) > 1 else 'dev'
workers = sys.argv[2] if len(sys.argv) > 2 else '1'

workflow = {
    'name': f'pipeline_{env}',
    'jobs': [
        {'name': f'job_{i}', 'transformation': 'Process'}
        for i in range(int(workers))
    ],
    'transformations': [
        {'name': 'Process', 'pfn': 'scripts/process.sh', 'type': 'stageable'}
    ]
}

print(yaml.dump(workflow))
```

**orchestrator.sh** (Your runner):
```bash
#!/bin/bash
# Orchestrator that runs generator

ENV=${1:-production}
WORKERS=${2:-4}

echo "🚀 Generating workflow..." >&2
echo "   Environment: $ENV" >&2
echo "   Workers: $WORKERS" >&2

# Run generator and output YAML to stdout
python3 generate_workflow.py "$ENV" "$WORKERS"

echo "✅ Generated!" >&2
```

### Project Structure
```
/opt/workflows/ml_pipeline/
├── generate_workflow.py
├── orchestrator.sh
└── scripts/
    └── process.sh
```

### Validate
```bash
python cli.py generate_workflow.py \
  --runner orchestrator.sh \
  --workflow-args 'production 8' \
  --workflow-dir /opt/workflows/ml_pipeline/
```

### What Happens
```
🏃 Runner script detected: orchestrator.sh
   Generator: generate_workflow.py
   Running: bash orchestrator.sh production 8

Output (stderr):
🚀 Generating workflow...
   Environment: production
   Workers: 8
✅ Generated!

✅ Runner produced 456 bytes of YAML

🔍 Validating workflow (level: standard)...
Running path validator...
✓ scripts/process.sh ✅ (exists, executable)

✅ Validation PASSED - Workflow is ready!
```

---

## Use Cases

### Use Case 1: Shell Wrapper

You have a shell script that sets up environment and runs generator:

**run_generator.sh:**
```bash
#!/bin/bash
set -e

# Setup
export PATH=/opt/tools:$PATH
source /etc/workflow.conf

# Run generator
python3 generate_workflow.py "$@"
```

**Validate:**
```bash
python cli.py generate_workflow.py \
  --runner run_generator.sh \
  --workflow-args 'production' \
  --workflow-dir /opt/workflows/
```

---

### Use Case 2: Python Orchestrator

**orchestrator.py:**
```python
#!/usr/bin/env python3
import subprocess
import sys

def main():
    env = sys.argv[1] if len(sys.argv) > 1 else 'dev'

    # Load config
    config = load_config(env)

    # Run generator with config
    result = subprocess.run(
        ['python3', 'generate_workflow.py', env, str(config['workers'])],
        capture_output=True,
        text=True
    )

    # Output YAML to stdout
    print(result.stdout)

if __name__ == '__main__':
    main()
```

**Validate:**
```bash
python cli.py generate_workflow.py \
  --runner orchestrator.py \
  --workflow-args 'production' \
  --workflow-dir $(pwd)
```

---

### Use Case 3: Complex Setup

**orchestrator.sh:**
```bash
#!/bin/bash
set -e

# Complex setup
docker pull myimage:latest
mkdir -p /tmp/workflow
cd /tmp/workflow

# Generate
python3 /opt/generators/generate_workflow.py "$@"

# Cleanup
cd -
rm -rf /tmp/workflow
```

**Validate:**
```bash
python cli.py generate_workflow.py \
  --runner orchestrator.sh \
  --workflow-dir /opt/workflows/project/
```

---

## Arguments Flow

```bash
python cli.py generator.py \
  --runner orchestrator.sh \
  --workflow-args 'arg1 arg2 arg3'
```

**Result:** Runs `orchestrator.sh arg1 arg2 arg3`

The orchestrator receives the arguments and can pass them to the generator however it wants.

---

## Comparison: --from-generator vs --runner

| Flag | When to Use | Example |
|------|-------------|---------|
| `--from-generator` | Generator is **directly executable** | `python cli.py gen.py --from-generator` |
| `--runner` | Orchestrator **wraps** generator | `python cli.py gen.py --runner orch.sh` |

### Direct Generator
```bash
# Direct execution
python cli.py generate.py --from-generator
```
Runs: `python3 generate.py`

### With Runner
```bash
# Orchestrator executes generator
python cli.py generate.py --runner orchestrator.sh
```
Runs: `bash orchestrator.sh`

---

## Complete Workflow

### 1. Create Generator
```bash
cat > generate_workflow.py <<'EOF'
#!/usr/bin/env python3
import yaml, sys

workflow = {
    'name': f'workflow_{sys.argv[1] if len(sys.argv) > 1 else "dev"}',
    'jobs': [{'name': 'job1', 'transformation': 'Process'}],
    'transformations': [{'name': 'Process', 'pfn': 'scripts/process.sh'}]
}

print(yaml.dump(workflow))
EOF

chmod +x generate_workflow.py
```

### 2. Create Orchestrator
```bash
cat > orchestrator.sh <<'EOF'
#!/bin/bash
echo "Running generator for: $1" >&2
python3 generate_workflow.py "$1"
EOF

chmod +x orchestrator.sh
```

### 3. Create Scripts
```bash
mkdir scripts
echo '#!/bin/bash' > scripts/process.sh
echo 'echo "Processing..."' >> scripts/process.sh
chmod +x scripts/process.sh
```

### 4. Validate
```bash
python /path/to/validator/cli.py generate_workflow.py \
  --runner orchestrator.sh \
  --workflow-args 'production' \
  --workflow-dir $(pwd)
```

### 5. Output
```
🏃 Runner script detected: orchestrator.sh
   Generator: generate_workflow.py
   Running: bash orchestrator.sh production

✅ Runner produced 234 bytes of YAML

🔍 Validating workflow...
✓ scripts/process.sh ✅

✅ Validation PASSED!
```

---

## Advanced: Multiple Generators

One orchestrator, multiple generators:

**orchestrator.sh:**
```bash
#!/bin/bash
TYPE=$1
shift  # Remove first arg

case $TYPE in
    ml)
        python3 generate_ml_workflow.py "$@"
        ;;
    batch)
        python3 generate_batch_workflow.py "$@"
        ;;
    *)
        echo "Unknown type: $TYPE" >&2
        exit 1
        ;;
esac
```

**Validate ML workflow:**
```bash
python cli.py generate_ml_workflow.py \
  --runner orchestrator.sh \
  --workflow-args 'ml production' \
  --workflow-dir /opt/workflows/ml/
```

**Validate Batch workflow:**
```bash
python cli.py generate_batch_workflow.py \
  --runner orchestrator.sh \
  --workflow-args 'batch staging' \
  --workflow-dir /opt/workflows/batch/
```

---

## Requirements for Runner

Your runner script must:

1. ✅ **Output YAML to stdout**
   ```bash
   python3 generator.py "$@"  # YAML goes to stdout
   ```

2. ✅ **Use stderr for logs**
   ```bash
   echo "Starting..." >&2  # Logs to stderr
   python3 generator.py "$@"  # YAML to stdout
   ```

3. ✅ **Exit with 0 on success**
   ```bash
   python3 generator.py "$@" || exit 1
   ```

4. ✅ **Be executable** (optional)
   ```bash
   chmod +x orchestrator.sh
   ```

---

## Real-World Example

**Scenario:** CI/CD pipeline that generates workflows

**ci-runner.sh:**
```bash
#!/bin/bash
set -e

# CI/CD environment setup
export BUILD_ID=$1
export ENVIRONMENT=$2
shift 2

# Load secrets
aws secretsmanager get-secret-value --secret-id workflow-config > /tmp/config.json

# Generate workflow
python3 generate_workflow.py \
  --config /tmp/config.json \
  --build-id "$BUILD_ID" \
  --env "$ENVIRONMENT" \
  "$@"

# Cleanup
rm /tmp/config.json
```

**Validation in CI:**
```bash
# .github/workflows/validate.yml
python validator/cli.py generate_workflow.py \
  --runner ci-runner.sh \
  --workflow-args "$BUILD_ID $ENVIRONMENT --workers=8" \
  --workflow-dir /opt/workflows/ \
  --format json \
  -o validation_report.json
```

---

## Troubleshooting

### Issue: "Runner failed with exit code 1"
```
❌ Runner failed with exit code 1
```

**Fix:** Check runner script directly
```bash
bash orchestrator.sh production
```

### Issue: "No YAML output"
```
✅ Runner produced 0 bytes of YAML
❌ Failed to load workflow YAML
```

**Fix:** Ensure runner outputs YAML to **stdout**, not stderr
```bash
# Wrong ❌
echo "$YAML" >&2

# Correct ✅
echo "$YAML"  # or just: python3 generator.py
```

### Issue: "Paths not found"
```
❌ Transformation executable not found: scripts/process.sh
```

**Fix:** Specify correct `--workflow-dir`
```bash
python cli.py gen.py \
  --runner orch.sh \
  --workflow-dir /correct/absolute/path/
```

---

## Summary

**Your perfect command:**
```bash
python cli.py GENERATOR.py \
  --runner ORCHESTRATOR.sh \
  --workflow-args 'YOUR ARGS' \
  --workflow-dir /path/to/workflow/
```

**What it does:**
1. Runs `ORCHESTRATOR.sh YOUR ARGS`
2. Orchestrator calls generator however it wants
3. Captures YAML from stdout
4. Validates with correct paths

**Clean, simple, powerful!** 🚀
