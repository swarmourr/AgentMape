# WorkflowValidator Improvements Summary

## Overview
This document summarizes all improvements made to the WorkflowValidator to fix critical bugs and add support for complex workflow orchestration scenarios.

---

## 1. Critical Bug Fixes

### 1.1 Fixed Return Type Mismatch
**Problem:** The `validate()` method signature promised to return `Tuple[ValidationReport, Optional[str]]` but was only returning `ValidationReport`, causing the CLI to crash with unpacking errors.

**Location:** `validator.py:234`

**Fix:**
```python
# Before
return report

# After
return report, generated_yaml_path
```

**Impact:** CLI now works without crashes.

---

### 1.2 Fixed Import Error (openai_backend)
**Problem:** The `llm_backends/__init__.py` had a leftover import for `OpenAIBackend` which didn't exist.

**Location:** `validators/llm_enhanced/llm_backends/__init__.py`

**Status:** Already fixed in local repository. Remote deployment at `/home/hsafri/MAPEAgents/` needs to pull the updated code.

---

## 2. Path Resolution Improvements

### 2.1 Context-Aware Path Resolution
**Problem:** The validator was checking file paths relative to its own directory instead of the workflow's directory.

**Example of the issue:**
```bash
# Validator in: /opt/validator/
# Workflow in:  /home/user/my_workflow/workflow.py
# Script path:  scripts/train.py  (relative)

# Before: Looked for /opt/validator/scripts/train.py ❌
# After:  Looks for /home/user/my_workflow/scripts/train.py ✅
```

**Changes Made:**

1. **Added `base_directory` to WorkflowContext** (`models.py:177`)
   ```python
   base_directory: Optional[str] = None  # Directory where workflow file is located
   ```

2. **Created `_resolve_path()` helper** (`path_validator.py:26-48`)
   ```python
   def _resolve_path(self, file_path: str, base_dir: str = None) -> str:
       """Resolve file paths relative to workflow directory"""
       if os.path.isabs(file_path):
           return file_path
       if base_dir and not os.path.isabs(file_path):
           return os.path.join(base_dir, file_path)
       return file_path
   ```

3. **Updated path validators** to use resolved paths:
   - `_validate_transformations()` - transformation executables
   - `_validate_replicas()` - input data files

**Impact:** File paths now resolve correctly regardless of where the validator is invoked from.

---

## 3. Workflow Directory Override (`--workflow-dir`)

### 3.1 The Problem
When a workflow is orchestrated by another file (e.g., `orchestrator.py` imports `workflow_descriptor.py`), the validator needs to know the **actual** workflow working directory.

**Scenario:**
```
/home/user/workflows/ml_project/
├── orchestrator.py          # Imports workflow_descriptor.py
├── workflow_descriptor.py   # Defines workflow structure
├── scripts/
│   ├── preprocess.py       # Referenced as "scripts/preprocess.py"
│   └── train.py
└── data/
    └── input.csv
```

Without `--workflow-dir`, the validator would try to find `scripts/preprocess.py` relative to `orchestrator.py`'s location.

### 3.2 Solution: `--workflow-dir` Option

**CLI Option Added:** (`cli.py:43-45`)
```bash
--workflow-dir PATH    Working directory for the workflow
```

**Usage:**
```bash
# Validate orchestrator that imports workflow descriptor
python cli.py /anywhere/orchestrator.py \
  --workflow-dir /home/user/workflows/ml_project/

# Now paths resolve from /home/user/workflows/ml_project/
```

**Implementation:**
- Added parameter to `validate()` method
- Updated `_build_context()` to accept and use `workflow_dir`
- Paths resolve from custom directory if provided

---

## 4. Workflow Arguments Support (`--workflow-args`)

### 4.1 The Problem
Many workflows accept command-line arguments for configuration:
- Shell scripts: `./orchestrator.sh production --config=/etc/app.conf`
- Python: `python workflow.py --env=prod --workers=4`

The validator needs to know these arguments for proper context logging and documentation.

### 4.2 Solution: `--workflow-args` Option

**CLI Option Added:** (`cli.py:46-48`)
```bash
--workflow-args 'ARG1 ARG2...'    Arguments to pass to workflow script
```

**Usage Examples:**

**Shell Script:**
```bash
python cli.py orchestrator.sh \
  --workflow-dir /path/to/workflow \
  --workflow-args 'production --config=/etc/workflow.conf --workers=4'
```

**Python with Arguments:**
```bash
python cli.py workflow.py \
  --workflow-dir /home/user/workflows/ml_project \
  --workflow-args '--env=prod --data-dir=/mnt/data'
```

**What It Does:**
- Logs the arguments for validation context
- Documents the workflow's execution parameters
- Helps trace validation runs in logs

**Example Log Output:**
```
2025-11-08 15:30:00 - validator - INFO - ============================================================
2025-11-08 15:30:00 - validator - INFO - Workflow Validator Started
2025-11-08 15:30:00 - validator - INFO - ============================================================
2025-11-08 15:30:00 - validator - INFO - Input file: /path/to/orchestrator.sh
2025-11-08 15:30:00 - validator - INFO - File type: .sh
2025-11-08 15:30:00 - validator - INFO - Validation level: standard
2025-11-08 15:30:00 - validator - INFO - Workflow arguments: production --config=/etc/workflow.conf --workers=4
```

---

## 5. Complete Usage Guide

### Basic Validation
```bash
# YAML workflow
python cli.py workflow.yml

# Python descriptor (auto-generate YAML)
python cli.py workflow_descriptor.py
```

### Advanced Scenarios

#### Scenario 1: Orchestrator Script
```bash
# orchestrator.py imports workflow_descriptor.py
# Workflow files are in /home/user/workflows/project/

python cli.py orchestrator.py \
  --workflow-dir /home/user/workflows/project/ \
  --level full \
  --format json \
  -o validation_report.json
```

#### Scenario 2: Shell Script with Arguments
```bash
# orchestrator.sh accepts environment and config
python cli.py orchestrator.sh \
  --workflow-dir /opt/workflows/production \
  --workflow-args 'prod --config=/etc/app.conf' \
  --level standard
```

#### Scenario 3: Python Workflow with Custom Args
```bash
python cli.py workflow.py \
  --workflow-dir /data/ml_pipeline \
  --workflow-args '--env=staging --data-dir=/mnt/datasets' \
  --mode hybrid \
  --output-yaml generated_workflow.yml
```

#### Scenario 4: Offline Mode (No LLM)
```bash
# When Ollama is not available
python cli.py workflow.py \
  --workflow-dir /path/to/project \
  --mode offline \
  --level quick
```

---

## 6. Where Reports Are Saved

### Default Behavior
Reports print to **stdout** (terminal)

### Save to File
```bash
# JSON format
python cli.py workflow.py --format json -o report.json

# Terminal format to file
python cli.py workflow.py -o report.txt

# HTML format
python cli.py workflow.py --format html -o report.html
```

### Logs
Configured in `validator_config.json`:
```json
{
  "log_file": "validator.log",
  "log_to_console": true,
  "log_level": "INFO"
}
```

---

## 7. Files Modified

| File | Changes |
|------|---------|
| `validator.py` | Added `workflow_dir`, `workflow_args` parameters; fixed return statement |
| `models.py` | Added `base_directory` field to `WorkflowContext` |
| `path_validator.py` | Added `_resolve_path()` method; updated validation methods |
| `cli.py` | Added `--workflow-dir` and `--workflow-args` options |
| `README.md` | Added documentation for new features |
| `llm_backends/__init__.py` | Removed invalid `openai_backend` import (already done) |

---

## 8. Migration Guide

### For Existing Users
No breaking changes! All new features are **optional**.

**Before (still works):**
```bash
python cli.py workflow.yml
```

**Enhanced (new features):**
```bash
python cli.py workflow.yml --workflow-dir /custom/path
```

### For Remote Deployment
If you're using the validator on a remote server (`/home/hsafri/MAPEAgents/`):

1. Pull the latest code from the repository
2. Test imports:
   ```bash
   python3 -c "from validators.llm_enhanced.llm_backends import OllamaBackend"
   ```
3. Run validation as usual

---

## 9. Testing

### Test Path Resolution
```bash
# Create test structure
mkdir -p /tmp/test_workflow/scripts
echo "#!/bin/bash" > /tmp/test_workflow/scripts/test.sh
chmod +x /tmp/test_workflow/scripts/test.sh

# Create workflow with relative path
cat > /tmp/test_workflow/workflow.yml <<EOF
name: test
transformations:
  - name: Test
    pfn: scripts/test.sh
EOF

# Validate from different directory
cd /tmp
python /path/to/validator/cli.py test_workflow/workflow.yml \
  --level quick

# Should find scripts/test.sh correctly ✅
```

### Test Workflow Arguments
```bash
python cli.py workflow.py \
  --workflow-args '--env=test --verbose' \
  --verbose

# Check logs for: "Workflow arguments: --env=test --verbose"
```

---

## 10. Summary

✅ **Fixed critical bugs** (return type, imports)
✅ **Improved path resolution** (context-aware, base directory)
✅ **Added `--workflow-dir`** (custom working directory)
✅ **Added `--workflow-args`** (document execution parameters)
✅ **Updated documentation** (README, examples)
✅ **Backward compatible** (all changes are optional)

The validator is now production-ready and handles complex orchestration scenarios!
