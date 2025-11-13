# Quick Start Guide

## Installation

No installation needed! The validator is ready to use.

---

## Basic Usage

### 1. Validate a Workflow

```bash
cd WorkflowValidator
python3.11 cli.py /path/to/workflow.yml
```

### 2. Verbose Output (See Details)

```bash
python3.11 cli.py /path/to/workflow.yml -v
```

Shows:
- Which files were validated
- File sizes and paths
- What checks were performed

### 3. Full Validation (All Checks)

```bash
python3.11 cli.py /path/to/workflow.yml -l full -v
```

Runs all validators:
- Syntax
- Structure
- Paths
- Integrity
- Job inputs
- Resources
- DAG (dependencies)

### 4. Generate HTML Report

```bash
python3.11 cli.py /path/to/workflow.yml -l full -f html-interactive -o report.html
```

Then open `report.html` in your browser for an interactive report.

---

## Validation Levels

### Quick
Fast validation (syntax only):
```bash
python3.11 cli.py workflow.yml -l quick
```

### Standard (Default)
Basic checks:
```bash
python3.11 cli.py workflow.yml -l standard
```

### Full
All checks:
```bash
python3.11 cli.py workflow.yml -l full
```

---

## Output Formats

### Terminal (Default)
```bash
python3.11 cli.py workflow.yml
```

### JSON
```bash
python3.11 cli.py workflow.yml -f json -o report.json
```

### HTML (Basic)
```bash
python3.11 cli.py workflow.yml -f html -o report.html
```

### HTML (Interactive)
```bash
python3.11 cli.py workflow.yml -f html-interactive -o report.html
```

---

## Common Scenarios

### Validate Before Submission
```bash
python3.11 cli.py my_workflow.yml -l full -v
```

If you see:
```
✅ VALIDATION PASSED
Workflow is ready for submission!
```

Then submit with:
```bash
pegasus-plan my_workflow.yml
```

### Check Specific File Exists
```bash
python3.11 cli.py workflow.yml -v | grep "Validating replica"
```

### Find All Errors
```bash
python3.11 cli.py workflow.yml -l full 2>&1 | grep "ERROR"
```

### Generate Report for Team
```bash
python3.11 cli.py workflow.yml -l full -f html-interactive -o validation_report.html
```

Share `validation_report.html` with your team.

---

## Understanding Output

### Terminal Report Structure

```
═══════════════════════════════════════════════════════════════
🔍  PEGASUS WORKFLOW VALIDATION REPORT
═══════════════════════════════════════════════════════════════

Workflow: /path/to/workflow.yml
Validated: 2025-01-15 10:30:45
Duration: 2.34s

Overall Status: ✅ PASSED

───────────────────────────────────────────────────────────────
📊 SUMMARY
───────────────────────────────────────────────────────────────
  Total Issues: 0
  ├─ Errors:    0
  └─ Warnings:  0

───────────────────────────────────────────────────────────────
🔧 VALIDATOR RESULTS
───────────────────────────────────────────────────────────────

✅ PATHS (0.15s)
   Checks performed: 3
   Errors: 0, Warnings: 0
   Files validated: 3
      ✓ finetune.py (2.5KB) - exists, readable, executable, valid_shebang
      ✓ pegasus_data (12.3MB) - exists, readable, non-empty

✅ INTEGRITY (0.08s)
   Checks performed: 1
   Errors: 0, Warnings: 0
   Files validated: 1
      ✓ pegasus_data (12.3MB) - readable

✅ JOB_INPUTS (0.05s)
   Checks performed: 1
   Errors: 0, Warnings: 0
   Jobs validated: 1
      ✓ FineTuneLLM (1 inputs, 0 outputs)

✅ RESOURCES (0.03s)
   Checks performed: 1
   Errors: 0, Warnings: 0
   Jobs validated: 1
      ✓ FineTuneLLM (16GB RAM, 4 CPUs)

✅ DAG (0.02s)
   Checks performed: 2
   Errors: 0, Warnings: 0

   📊 DAG Statistics:
      Total Jobs: 1
      Jobs with Dependencies: 0
      Max Depth: 0
      Cycles Detected: 0

═══════════════════════════════════════════════════════════════
✅ VALIDATION PASSED

Workflow is ready for submission!
═══════════════════════════════════════════════════════════════
```

---

## Fixing Common Issues

### Error: Input file not found in replica catalog

```
❌ Job 'ProcessData' requires input file 'data.csv' not found in replica catalog
💡 Fix: Add 'data.csv' to replicaCatalog
```

**Solution:**
```yaml
replicaCatalog:
  replicas:
  - lfn: data.csv
    pfns:
    - site: local
      pfn: /path/to/data.csv
```

### Error: Transformation executable not found

```
❌ Transformation executable not found: /tmp/script.py
💡 Fix: Create file at /tmp/script.py or update PFN in catalog
```

**Solution:**
```bash
# Make sure file exists
ls -la /tmp/script.py

# Or update path in workflow
vim workflow.yml
```

### Error: Circular dependency

```
🔴 CRITICAL: Circular dependency detected: JobA -> JobB -> JobA
💡 Fix: Remove one of the dependencies to break the cycle
```

**Solution:**
```yaml
# Before (circular):
jobs:
- name: JobA
  parents: [JobB]
- name: JobB
  parents: [JobA]

# After (fixed):
jobs:
- name: JobA
  parents: []
- name: JobB
  parents: [JobA]
```

### Warning: High memory request

```
⚠️ Job 'TrainModel' requests high memory: 256GB
💡 Consider if 256GB is necessary
```

**Solution:**
```yaml
# If you really need 256GB, ignore warning
# Otherwise, reduce:
profiles:
  condor:
    request_memory: 128GB  # Reduced from 256GB
```

---

## Configuration

Edit `validator_config.json` to customize:

```json
{
  "validation_levels": {
    "full": {
      "validators": [
        "syntax",
        "paths",
        "integrity",
        "job_inputs",
        "resources",
        "dag"
      ]
    }
  },
  "rule_based_config": {
    "resources": {
      "max_memory_gb": 512,
      "max_cpus": 128
    }
  }
}
```

---

## Tips

1. **Always use `-v` for first-time validation**
   ```bash
   python3.11 cli.py workflow.yml -l full -v
   ```

2. **Save reports for debugging**
   ```bash
   python3.11 cli.py workflow.yml -l full -f json -o debug.json
   ```

3. **Test incrementally**
   ```bash
   # First, test syntax
   python3.11 cli.py workflow.yml -l quick

   # Then, test paths
   python3.11 cli.py workflow.yml -l standard

   # Finally, full validation
   python3.11 cli.py workflow.yml -l full
   ```

4. **Use interactive HTML for presentations**
   ```bash
   python3.11 cli.py workflow.yml -l full -f html-interactive -o presentation.html
   ```

---

## Examples

### Example 1: Simple Workflow

**workflow.yml:**
```yaml
pegasus: "5.0.4"
name: simple-workflow

transformationCatalog:
  transformations:
  - name: Echo
    sites:
    - name: local
      pfn: /bin/echo

jobs:
- type: job
  name: Echo
  arguments: ["Hello World"]
```

**Validate:**
```bash
python3.11 cli.py workflow.yml -v
```

**Expected Output:**
```
✅ VALIDATION PASSED
```

### Example 2: Workflow with Data Files

**workflow.yml:**
```yaml
pegasus: "5.0.4"
name: data-workflow

transformationCatalog:
  transformations:
  - name: Process
    sites:
    - name: local
      pfn: /usr/bin/python3

replicaCatalog:
  replicas:
  - lfn: input.csv
    pfns:
    - site: local
      pfn: /data/input.csv

jobs:
- type: job
  name: Process
  arguments: ["process.py", "input.csv"]
  uses:
  - lfn: input.csv
    type: input
```

**Validate:**
```bash
python3.11 cli.py workflow.yml -l full -v
```

**Expected Output:**
```
✅ PATHS - Checked input.csv exists
✅ INTEGRITY - Validated input.csv is readable
✅ JOB_INPUTS - Verified Process job has input.csv in catalog
✅ VALIDATION PASSED
```

---

## Next Steps

- Read [NEW_FEATURES.md](NEW_FEATURES.md) for detailed feature descriptions
- Read [VALIDATORS.md](VALIDATORS.md) to understand each validator
- Read [ARCHITECTURE.md](ARCHITECTURE.md) for system design

---

## Support

If you encounter issues:
1. Run with `-v` to see detailed output
2. Check `validator.log` for error details
3. Generate JSON report for debugging: `-f json -o debug.json`
