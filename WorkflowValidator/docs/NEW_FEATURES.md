# New Validation Features

## Overview

This document describes the new validation features added to the Pegasus Workflow Validator.

---

## 1. Job Input File Validation

### Purpose
Validates that all input files referenced in job `uses` sections are declared in the replica catalog.

### What It Checks
- ✅ All input files exist in replica catalog
- ✅ Output files don't conflict with existing replicas
- ✅ Job dependencies are properly declared

### Configuration

```json
{
  "rule_based_config": {
    "job_inputs": {
      "check_input_files": true,
      "check_output_conflicts": true
    }
  }
}
```

### Example Error

```yaml
jobs:
- name: ProcessData
  uses:
  - lfn: input_data  # ERROR: Not found in replicaCatalog!
    type: input
```

**Error Message:**
```
❌ Job 'ProcessData' requires input file 'input_data' not found in replica catalog
💡 Suggestion: Add 'input_data' to replicaCatalog with a valid PFN
```

### Report Output

```
✅ JOB_INPUTS (0.05s)
   Checks performed: 3
   Errors: 1, Warnings: 0
   Jobs validated: 3
      ✓ DownloadData (0 inputs, 1 outputs)
      ✗ ProcessData (1 inputs, 1 outputs) - missing: input_data
      ✓ Train (1 inputs, 1 outputs)
```

---

## 2. Resource Requirements Validation

### Purpose
Validates that job resource requirements (memory, CPU, disk) are reasonable and within system limits.

### What It Checks
- ✅ Memory requests < max_memory_gb
- ✅ CPU requests < max_cpus
- ✅ Disk requests < max_disk_gb
- ⚠️ Warns on high but valid resource requests

### Configuration

```json
{
  "rule_based_config": {
    "resources": {
      "max_memory_gb": 512,
      "max_cpus": 128,
      "max_disk_gb": 10000,
      "warn_memory_gb": 256,
      "warn_cpus": 64
    }
  }
}
```

### Example Error

```yaml
jobs:
- name: TrainModel
  profiles:
    condor:
      request_memory: 1000GB  # ERROR: Exceeds 512GB limit!
      request_cpus: 256       # ERROR: Exceeds 128 CPU limit!
```

**Error Messages:**
```
❌ Job 'TrainModel' requests excessive memory: 1000GB (max: 512GB)
💡 Suggestion: Reduce memory request to 512GB or less

❌ Job 'TrainModel' requests excessive CPUs: 256 (max: 128)
💡 Suggestion: Reduce CPU request to 128 or less
```

### Report Output

```
✅ RESOURCES (0.03s)
   Checks performed: 2
   Errors: 0, Warnings: 1
   Jobs validated: 2
      ✓ Download (4GB RAM, 1 CPUs)
      ⚠️ TrainModel (256GB RAM, 64 CPUs) - high memory warning
```

---

## 3. DAG (Dependency Graph) Validation

### Purpose
Validates that the workflow forms a valid Directed Acyclic Graph with no circular dependencies.

### What It Checks
- ✅ All parent jobs exist
- ✅ No circular dependencies (cycles)
- ✅ DAG depth and structure

### Configuration

```json
{
  "rule_based_config": {
    "dag": {
      "check_cycles": true,
      "check_missing_parents": true
    }
  }
}
```

### Example Errors

**Missing Parent:**
```yaml
jobs:
- name: TrainModel
  parents: [Preprocess]  # ERROR: Preprocess job doesn't exist!
```

**Circular Dependency:**
```yaml
jobs:
- name: JobA
  parents: [JobB]
- name: JobB
  parents: [JobA]  # ERROR: Circular dependency!
```

**Error Messages:**
```
❌ Job 'TrainModel' has undefined parent: 'Preprocess'
💡 Suggestion: Add job 'Preprocess' to workflow or remove from parents list

🔴 CRITICAL: Circular dependency detected: JobA -> JobB -> JobA
💡 Suggestion: Remove one of the dependencies to break the cycle
```

### Report Output

```
✅ DAG (0.02s)
   Checks performed: 2
   Errors: 0, Warnings: 0

   📊 DAG Statistics:
      Total Jobs: 5
      Jobs with Dependencies: 3
      Max Depth: 3
      Cycles Detected: 0
```

---

## 4. Enhanced Integrity Validation

### What's New
- Shows which files were validated
- Displays file sizes
- Lists checks performed (readable, valid_csv, etc.)

### Report Output (with -v flag)

```
✅ INTEGRITY (0.08s)
   Checks performed: 2
   Errors: 0, Warnings: 0
   Files validated: 2
      ✓ training_data (12.3MB) - readable, valid_csv
      ✓ model_config (1.2KB) - readable
```

---

## 5. Interactive HTML Reports

### Purpose
Generate beautiful, interactive HTML reports with search and collapsible sections.

### Usage

```bash
python3.11 cli.py workflow.yml -f html-interactive -o report.html
```

### Features

1. **Interactive UI**
   - Collapsible validator sections
   - Search functionality
   - Clickable file paths

2. **Visual Statistics**
   - Total issues, errors, warnings
   - Files validated count
   - Jobs checked count
   - Duration metrics

3. **Detailed Breakdowns**
   - Per-validator file lists
   - Job validation details
   - DAG statistics
   - Resource usage

4. **Color-Coded Issues**
   - 🔴 Critical (red)
   - ❌ Errors (orange)
   - ⚠️ Warnings (yellow)

5. **Suggestions**
   - Each issue shows actionable fix suggestions
   - Copy-paste friendly commands

### Screenshot Description

The interactive HTML report includes:
- Header with workflow path and overall status badge
- Grid of statistics cards (issues, errors, warnings, duration, files, jobs)
- Expandable validator cards with detailed file lists
- Searchable issues with severity color coding
- Suggestions panel for each issue

---

## Usage Examples

### Run All New Validators

```bash
python3.11 cli.py workflow.yml -l full -v
```

This runs:
- ✅ Job input validation
- ✅ Resource validation
- ✅ DAG validation
- ✅ Enhanced integrity validation
- ✅ All existing validators

### Generate Interactive Report

```bash
python3.11 cli.py workflow.yml -l full -f html-interactive -o report.html
```

Then open `report.html` in a browser.

### Check Only DAG and Resources

Modify `validator_config.json`:
```json
{
  "validation_levels": {
    "custom": {
      "enabled": true,
      "validators": ["dag", "resources"]
    }
  }
}
```

Then run:
```bash
python3.11 cli.py workflow.yml -l custom
```

---

## Integration with Existing Validators

All new validators integrate seamlessly:

1. **Uses same configuration system** (`validator_config.json`)
2. **Same error reporting format** (`ValidationIssue`)
3. **Supports all output formats** (terminal, JSON, HTML)
4. **Works with verbose mode** (`-v` flag)
5. **Respects validation levels** (quick, standard, full)

---

## Multi-Prompt Architecture

Each new validator is self-contained:

```
validators/
  rule_based/
    job_input_validator.py    # Validates job inputs
    resource_validator.py      # Validates resources
    dag_validator.py           # Validates DAG structure
```

Benefits:
- ✅ Easy to maintain
- ✅ Easy to test
- ✅ Easy to extend
- ✅ No tight coupling

---

## Configuration Reference

### Complete Config Example

```json
{
  "validation_levels": {
    "full": {
      "validators": [
        "syntax",
        "required_fields",
        "dependencies",
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
      "max_disk_gb": 10000,
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

## Performance Impact

All new validators are optimized:

- **Job Input Validator**: O(n) where n = number of jobs
- **Resource Validator**: O(n) where n = number of jobs
- **DAG Validator**: O(n + e) where n = jobs, e = edges (DFS algorithm)

Typical overhead: **< 0.1s for workflows with < 100 jobs**

---

## Error Handling

All validators handle edge cases:

1. **Missing fields** → Skip validation for that job
2. **Invalid data** → Warn but continue
3. **Empty catalogs** → Pass with 0 checks
4. **Malformed YAML** → Caught by syntax validator

---

## Future Enhancements

Planned improvements:

1. **Container validation** - Verify Docker images exist
2. **Site validation** - Check execution sites are valid
3. **Performance predictions** - Estimate runtime and cost
4. **Auto-fix generation** - Generate bash scripts to fix issues
5. **Visual DAG graphs** - Show workflow graph in HTML report

---

## Questions?

For issues or feature requests, see:
- `docs/ARCHITECTURE.md` - System architecture
- `docs/VALIDATORS.md` - Validator development guide
- `README.md` - Getting started guide
