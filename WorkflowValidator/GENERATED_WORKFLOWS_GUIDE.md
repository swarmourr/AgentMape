# Generated Workflows Guide

## When Your Runner Saves YAML Files

If your runner saves YAML files to disk instead of outputting to stdout, use `--generated-workflows` to tell the validator where to find them.

---

## Usage

```bash
python cli.py workflow.py \
  --runner run_workflows.sh \
  --generated-workflows OUTPUT_PATH \
  --workflow-dir /path/to/workflow/
```

---

## Examples

### 1. **Single File**
```bash
python cli.py workflow.py \
  --runner run_workflows.sh \
  --generated-workflows output/workflow.yml \
  --workflow-dir /opt/workflows/
```

### 2. **Directory** (all *.yml files)
```bash
python cli.py workflow.py \
  --runner run_workflows.sh \
  --generated-workflows output/ \
  --workflow-dir /opt/workflows/
```

### 3. **Glob Pattern**
```bash
python cli.py workflow.py \
  --runner run_workflows.sh \
  --generated-workflows "output/*.yml" \
  --workflow-dir /opt/workflows/
```

### 4. **Specific Pattern**
```bash
python cli.py workflow.py \
  --runner run_workflows.sh \
  --generated-workflows "output/workflow_*.yml" \
  --workflow-dir /opt/workflows/
```

---

## Complete Example

### Your Runner Script

**run_workflows.sh:**
```bash
#!/bin/bash
# Generates workflows and saves to files

OUTPUT_DIR="output"
mkdir -p $OUTPUT_DIR

echo "Generating workflows..." >&2

# Generate workflow 1
python workflow.py --model llama3 > $OUTPUT_DIR/workflow_llama3.yml
echo "✅ Generated: $OUTPUT_DIR/workflow_llama3.yml" >&2

# Generate workflow 2
python workflow.py --model falcon > $OUTPUT_DIR/workflow_falcon.yml
echo "✅ Generated: $OUTPUT_DIR/workflow_falcon.yml" >&2

# Generate workflow 3
python workflow.py --model mistral > $OUTPUT_DIR/workflow_mistral.yml
echo "✅ Generated: $OUTPUT_DIR/workflow_mistral.yml" >&2

echo "All workflows generated in $OUTPUT_DIR/" >&2
```

### Validation

```bash
python cli.py workflow.py \
  --runner run_workflows.sh \
  --generated-workflows "output/*.yml" \
  --workflow-dir /opt/ml_workflows/
```

### Output

```
🏃 Runner script detected: run_workflows.sh
   Generator: workflow.py
   Generated workflows: output/*.yml
   Running: bash run_workflows.sh

Generating workflows...
✅ Generated: output/workflow_llama3.yml
✅ Generated: output/workflow_falcon.yml
✅ Generated: output/workflow_mistral.yml
All workflows generated in output/

✅ Runner completed successfully

🔍 Looking for generated workflows...
   Found 3 workflow(s) to validate

📄 Validating workflow_llama3.yml (1/3)...
✓ Structure valid
✓ Paths validated

📄 Validating workflow_falcon.yml (2/3)...
✓ Structure valid
✓ Paths validated

📄 Validating workflow_mistral.yml (3/3)...
✓ Structure valid
✓ Paths validated

✅ All 3 workflows PASSED validation!
```

---

## Your LLM-Fine-Tune Use Case

Based on your setup:

```bash
python cli.py /home/hsafri/LLM-Fine-Tune/workflow.py \
  --runner /home/hsafri/LLM-Fine-Tune/run_workdlows.sh \
  --generated-workflows "/home/hsafri/LLM-Fine-Tune/output/*.yml" \
  --workflow-dir /home/hsafri/LLM-Fine-Tune/ \
  -l full -m hybrid -v
```

**Or if saved in specific directory:**
```bash
python cli.py /home/hsafri/LLM-Fine-Tune/workflow.py \
  --runner /home/hsafri/LLM-Fine-Tune/run_workdlows.sh \
  --generated-workflows /home/hsafri/LLM-Fine-Tune/output/ \
  --workflow-dir /home/hsafri/LLM-Fine-Tune/ \
  -l full -m hybrid -v
```

---

## Path Types Supported

| Type | Example | Description |
|------|---------|-------------|
| **Single file** | `output/workflow.yml` | Validate one specific file |
| **Directory** | `output/` | All *.yml and *.yaml in directory |
| **Glob pattern** | `output/*.yml` | Pattern matching |
| **Specific pattern** | `output/workflow_*.yml` | More specific pattern |
| **Absolute path** | `/home/user/output/*.yml` | Full path |
| **Relative path** | `../output/*.yml` | Relative to current dir |

---

## Runner Output Options

### Option 1: Stdout (Original)
```bash
# Runner outputs YAML to stdout
python cli.py workflow.py --runner runner.sh
```

### Option 2: Save to Files (New!)
```bash
# Runner saves YAML to files
python cli.py workflow.py \
  --runner runner.sh \
  --generated-workflows output/
```

---

## Fix Your Error

Your error was:
```
/home/hsafri/LLM-Fine-Tune/run_workdlows.sh: line 17: python: command not found
```

**Two solutions:**

### 1. Fix the runner script
```bash
# Change 'python' to 'python3'
sed -i 's/python /python3 /g' /home/hsafri/LLM-Fine-Tune/run_workdlows.sh
```

### 2. Use generated workflows path
```bash
# Run the runner manually first
cd /home/hsafri/LLM-Fine-Tune/
bash run_workdlows.sh

# Then validate generated files
python cli.py workflow.py \
  --generated-workflows output/*.yml \
  --workflow-dir /home/hsafri/LLM-Fine-Tune/
```

---

## Complete Workflow

### 1. Create Runner

**run_workflows.sh:**
```bash
#!/bin/bash
OUTPUT_DIR="output"
mkdir -p $OUTPUT_DIR

# Generate workflows
python3 workflow.py > $OUTPUT_DIR/workflow.yml

echo "Generated: $OUTPUT_DIR/workflow.yml" >&2
```

### 2. Run Validator

```bash
python cli.py workflow.py \
  --runner run_workflows.sh \
  --generated-workflows output/ \
  --workflow-dir $(pwd)
```

### 3. Done!

```
✅ Runner completed successfully
🔍 Looking for generated workflows...
   Found 1 workflow(s) to validate
📄 Validating workflow.yml...
✅ Validation PASSED!
```

---

## Summary

**When runner saves files:**
```bash
python cli.py workflow.py \
  --runner runner.sh \
  --generated-workflows WHERE_FILES_ARE_SAVED \
  --workflow-dir /path/
```

**Three ways to specify generated workflows:**
1. Single file: `--generated-workflows output/workflow.yml`
2. Directory: `--generated-workflows output/`
3. Pattern: `--generated-workflows "output/*.yml"`

🚀
