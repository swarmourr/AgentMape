# New Validation Features - Quick Reference

## 🎉 What's New

4 new validators + enhanced reporting!

### 1. Job Input Validation
✅ Verifies job inputs exist in replica catalog
```bash
python3.11 cli.py workflow.yml -l full -v
```

### 2. Resource Validation
✅ Checks memory/CPU/disk requirements are reasonable
```bash
# Validates against configurable limits
```

### 3. DAG Validation
✅ Detects circular dependencies and missing parents
```bash
# Ensures workflow is a valid DAG
```

### 4. Interactive HTML Reports
✅ Beautiful, searchable reports
```bash
python3.11 cli.py workflow.yml -f html-interactive -o report.html
```

---

## Quick Start

### Run Full Validation
```bash
cd WorkflowValidator
python3.11 cli.py /path/to/workflow.yml -l full -v
```

### Generate HTML Report
```bash
python3.11 cli.py /path/to/workflow.yml -l full -f html-interactive -o report.html
open report.html
```

---

## What Gets Checked

### Job Inputs ✅
- Input files declared in replica catalog
- Output files don't conflict with existing replicas

### Resources ✅
- Memory requests < 512GB (configurable)
- CPU requests < 128 cores (configurable)
- Disk requests < 10TB (configurable)

### DAG ✅
- No circular dependencies
- All parent jobs exist
- Valid graph structure

### Integrity ✅ (Enhanced)
- Files are readable
- CSV files have valid format
- Shows which files were checked

### Paths ✅ (Enhanced)
- Files exist and are accessible
- Executables have proper permissions
- Shows which files were validated

---

## Example Output

```
═══════════════════════════════════════════════════════════
🔍  PEGASUS WORKFLOW VALIDATION REPORT
═══════════════════════════════════════════════════════════

Workflow: falcon-7b.yml
Validated: 2025-01-15 10:30:45
Duration: 2.34s

Overall Status: ✅ PASSED

───────────────────────────────────────────────────────────
📊 SUMMARY
───────────────────────────────────────────────────────────
  Total Issues: 0
  ├─ Errors:    0
  └─ Warnings:  0

───────────────────────────────────────────────────────────
🔧 VALIDATOR RESULTS
───────────────────────────────────────────────────────────

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

✅ INTEGRITY (0.08s)
   Checks performed: 1
   Errors: 0, Warnings: 0
   Files validated: 1
      ✓ pegasus_data (12.3MB) - readable

✅ PATHS (0.15s)
   Checks performed: 2
   Errors: 0, Warnings: 0
   Files validated: 2
      ✓ FineTuneLLM (2.5KB) - exists, readable, executable
      ✓ pegasus_data (12.3MB) - exists, readable, non-empty

═══════════════════════════════════════════════════════════
✅ VALIDATION PASSED

Workflow is ready for submission!
═══════════════════════════════════════════════════════════
```

---

## Configuration

Edit `validator_config.json`:

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
    "job_inputs": {
      "check_input_files": true,
      "check_output_conflicts": true
    },
    "resources": {
      "max_memory_gb": 512,
      "max_cpus": 128,
      "warn_memory_gb": 256,
      "warn_cpus": 64
    },
    "dag": {
      "check_cycles": true,
      "check_missing_parents": true
    }
  }
}
```

---

## Common Errors

### ❌ Input file not found
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

### ❌ Excessive memory
```
❌ Job 'TrainModel' requests excessive memory: 1000GB (max: 512GB)
💡 Fix: Reduce memory request to 512GB or less
```

**Solution:**
```yaml
jobs:
- name: TrainModel
  profiles:
    condor:
      request_memory: 256GB  # Reduced
```

### 🔴 Circular dependency
```
🔴 CRITICAL: Circular dependency detected: JobA -> JobB -> JobA
💡 Fix: Remove one dependency to break cycle
```

**Solution:**
```yaml
# Before:
jobs:
- name: JobA
  parents: [JobB]
- name: JobB
  parents: [JobA]

# After:
jobs:
- name: JobA
  parents: []
- name: JobB
  parents: [JobA]
```

---

## Documentation

- **QUICKSTART.md** - Installation and basic usage
- **NEW_FEATURES.md** - Detailed feature descriptions
- **VALIDATORS_API.md** - API reference and custom validators
- **IMPLEMENTATION_SUMMARY.md** - Architecture and implementation details

---

## Features at a Glance

| Validator | Purpose | Time |
|-----------|---------|------|
| Job Inputs | Validate job I/O files | < 0.01s |
| Resources | Check resource limits | < 0.01s |
| DAG | Detect cycles | < 0.01s |
| Integrity | Verify file health | ~0.08s |
| Paths | Check file access | ~0.15s |

**Total overhead:** < 0.25s for typical workflows

---

## Try It Now!

```bash
# Navigate to validator directory
cd /home/hsafri/WorkflowValidator

# Validate your workflow
python3.11 cli.py /home/hsafri/LLM-Fine-Tune/generated_workflows/falcon-7b.yml -l full -v

# Generate interactive report
python3.11 cli.py /home/hsafri/LLM-Fine-Tune/generated_workflows/falcon-7b.yml -l full -f html-interactive -o ~/validation_report.html

# Open in browser
firefox ~/validation_report.html
```

---

## Architecture

**Multi-Prompt Design:**
- Each validator is independent
- No tight coupling
- Easy to extend
- Configuration-driven

```
validators/
  rule_based/
    job_input_validator.py    # 165 lines
    resource_validator.py      # 205 lines
    dag_validator.py           # 190 lines
```

---

## Benefits

1. ✅ **Catch issues before submission** - Save time and compute resources
2. ✅ **Comprehensive checks** - 8 validators covering all aspects
3. ✅ **Beautiful reports** - Interactive HTML with search
4. ✅ **Actionable feedback** - Clear suggestions for fixing issues
5. ✅ **Fast** - < 0.25s overhead
6. ✅ **Extensible** - Easy to add custom validators

---

## Next Steps

1. Run validation on your workflows
2. Generate HTML reports for your team
3. Customize limits in `validator_config.json`
4. Read full documentation in `docs/`

---

## Questions?

See documentation:
- `docs/QUICKSTART.md`
- `docs/NEW_FEATURES.md`
- `docs/VALIDATORS_API.md`
