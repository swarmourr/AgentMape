# Validators API Documentation

## Overview

This document describes the API for each validator in the system.

---

## Validator Interface

All validators must implement:

```python
class MyValidator:
    def __init__(self, config: Dict[str, Any]):
        """Initialize with configuration"""
        self.config = config.get('rule_based_config', {}).get('my_validator', {})

    def validate(self, context: WorkflowContext) -> ValidatorResult:
        """
        Perform validation

        Args:
            context: WorkflowContext with workflow data

        Returns:
            ValidatorResult with issues and metadata
        """
        pass
```

---

## Data Models

### WorkflowContext

Contains all workflow information:

```python
@dataclass
class WorkflowContext:
    workflow_yaml_path: str
    workflow_yaml_content: Optional[Dict[str, Any]] = None
    transformation_catalog_path: Optional[str] = None
    transformation_catalog: Optional[Dict[str, Any]] = None
    replica_catalog_path: Optional[str] = None
    replica_catalog: Optional[Dict[str, Any]] = None
    transformation_scripts: Dict[str, str] = field(default_factory=dict)
    data_samples: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    base_directory: Optional[str] = None
```

### ValidatorResult

Return value from validators:

```python
@dataclass
class ValidatorResult:
    name: str                              # Validator name
    status: ValidationStatus               # PASSED, FAILED, WARNING
    duration_seconds: float                # Time taken
    issues: List[ValidationIssue] = []     # Issues found
    checks_performed: int = 0              # Number of checks
    metadata: Dict[str, Any] = {}          # Additional data
```

### ValidationIssue

Individual issue:

```python
@dataclass
class ValidationIssue:
    severity: Severity                     # CRITICAL, ERROR, WARNING, INFO
    category: Category                     # SYNTAX, STRUCTURE, PATHS, etc.
    message: str                           # Short description
    location: Optional[str] = None         # Where (e.g., "job:TrainModel")
    explanation: Optional[str] = None      # Why this is a problem
    impact: Optional[str] = None           # What happens if not fixed
    suggestion: Optional[str] = None       # How to fix
    code_snippet: Optional[str] = None     # Example fix
    detected_by: str = "rule"              # "rule" or "llm"
```

---

## JobInputValidator

### Purpose
Validates job input files exist in replica catalog.

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

### Input Context

Requires:
- `context.workflow_yaml_content` - Workflow jobs
- `context.replica_catalog` - Available replicas

### Output Metadata

```python
{
  "validated_jobs": [
    {
      "job_name": "ProcessData",
      "input_files": ["input.csv"],
      "output_files": ["output.csv"],
      "missing_inputs": [],
      "conflicting_outputs": [],
      "status": "OK"
    }
  ]
}
```

### Example Usage

```python
from validators.rule_based.job_input_validator import JobInputValidator

validator = JobInputValidator(config)
result = validator.validate(context)

for job_info in result.metadata['validated_jobs']:
    print(f"Job: {job_info['job_name']}")
    print(f"Inputs: {job_info['input_files']}")
    print(f"Outputs: {job_info['output_files']}")
```

---

## ResourceValidator

### Purpose
Validates resource requirements are reasonable.

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

### Input Context

Requires:
- `context.workflow_yaml_content` - Workflow jobs with profiles

### Output Metadata

```python
{
  "validated_resources": [
    {
      "job_name": "TrainModel",
      "memory_gb": 256.0,
      "cpus": 64,
      "disk_gb": 1000.0,
      "issues": ["high_memory"]
    }
  ]
}
```

### Memory Parsing

Supports formats:
- `"256GB"` → 256.0
- `"256G"` → 256.0
- `"256000MB"` → 250.0
- `"256000000KB"` → 244.14
- `256000000000` (bytes) → 238.42

### Example Usage

```python
from validators.rule_based.resource_validator import ResourceValidator

validator = ResourceValidator(config)
result = validator.validate(context)

for res in result.metadata['validated_resources']:
    print(f"Job: {res['job_name']}")
    print(f"Memory: {res['memory_gb']}GB")
    print(f"CPUs: {res['cpus']}")
```

---

## DAGValidator

### Purpose
Validates workflow dependency graph.

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

### Input Context

Requires:
- `context.workflow_yaml_content` - Workflow jobs with parents

### Output Metadata

```python
{
  "total_jobs": 5,
  "jobs_with_parents": 3,
  "max_depth": 3,
  "cycles_detected": [
    ["JobA", "JobB", "JobA"]  # List of cycles found
  ]
}
```

### Algorithm

Uses depth-first search (DFS) for cycle detection:

```python
def _detect_cycles(dependencies: Dict[str, List[str]]) -> List[List[str]]:
    """
    Detect cycles in dependency graph using DFS

    Time Complexity: O(V + E) where V = jobs, E = dependencies
    Space Complexity: O(V)
    """
    cycles = []
    visited = set()
    rec_stack = set()
    path = []

    def dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for parent in dependencies.get(node, []):
            if parent not in visited:
                if dfs(parent):
                    return True
            elif parent in rec_stack:
                # Found cycle
                cycle_start = path.index(parent)
                cycle = path[cycle_start:] + [parent]
                cycles.append(cycle)
                return True

        path.pop()
        rec_stack.remove(node)
        return False

    for job_name in dependencies:
        if job_name not in visited:
            dfs(job_name)

    return cycles
```

### Example Usage

```python
from validators.rule_based.dag_validator import DAGValidator

validator = DAGValidator(config)
result = validator.validate(context)

print(f"Total jobs: {result.metadata['total_jobs']}")
print(f"Max depth: {result.metadata['max_depth']}")
print(f"Cycles: {result.metadata['cycles_detected']}")
```

---

## IntegrityValidator (Enhanced)

### Purpose
Validates data file integrity.

### Configuration

```json
{
  "rule_based_config": {
    "integrity": {
      "check_file_readability": true,
      "check_file_corruption": true,
      "validate_csv_format": true,
      "check_data_schema": true,
      "max_file_size_mb": 1000
    }
  }
}
```

### Input Context

Requires:
- `context.replica_catalog` - Files to check

### Output Metadata

```python
{
  "validated_files": [
    {
      "lfn": "training_data",
      "pfn": "/data/train.csv",
      "size_bytes": 12884901,
      "checks": ["readable", "valid_csv"],
      "status": "OK"
    }
  ]
}
```

### Checks Performed

1. **Readability**: Try to read first 1KB
2. **CSV Format**: Parse with pandas, check columns
3. **File Size**: Check not empty and within limits

### Example Usage

```python
from validators.rule_based.integrity_validator import IntegrityValidator

validator = IntegrityValidator(config)
result = validator.validate(context)

for file_info in result.metadata['validated_files']:
    size_mb = file_info['size_bytes'] / (1024 * 1024)
    print(f"File: {file_info['lfn']} ({size_mb:.1f}MB)")
    print(f"Checks: {', '.join(file_info['checks'])}")
```

---

## PathValidator (Enhanced)

### Purpose
Validates file paths exist and are accessible.

### Configuration

```json
{
  "rule_based_config": {
    "paths": {
      "check_file_exists": true,
      "check_readable": true,
      "check_executable": true,
      "check_shebang": true
    }
  }
}
```

### Input Context

Requires:
- `context.transformation_catalog` - Executables
- `context.replica_catalog` - Data files
- `context.base_directory` - For resolving relative paths

### Output Metadata

```python
{
  "validated_files": [
    {
      "lfn": "finetune.py",
      "pfn": "/home/user/bin/finetune.py",
      "size_bytes": 2560,
      "checks": ["exists", "readable", "executable", "valid_shebang"],
      "status": "OK",
      "type": "transformation"
    },
    {
      "lfn": "input_data",
      "pfn": "/data/input.csv",
      "size_bytes": 12884901,
      "checks": ["exists", "readable", "non-empty"],
      "status": "OK",
      "type": "replica"
    }
  ]
}
```

### Path Resolution

Handles:
- Absolute paths: `/home/user/file.py`
- Relative paths: `data/file.csv` (resolved from base_directory)
- File:// URLs: `file:///path/to/file`

### Example Usage

```python
from validators.rule_based.path_validator import PathValidator

validator = PathValidator(config)
result = validator.validate(context)

for file_info in result.metadata['validated_files']:
    print(f"{file_info['type']}: {file_info['lfn']}")
    print(f"  Path: {file_info['pfn']}")
    print(f"  Checks: {', '.join(file_info['checks'])}")
```

---

## Creating Custom Validators

### Step 1: Create Validator Class

```python
# validators/rule_based/my_validator.py
import logging
from typing import Dict, List, Any
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from models import ValidationIssue, ValidatorResult, ValidationStatus, Severity, Category, WorkflowContext

logger = logging.getLogger(__name__)


class MyValidator:
    """Validates custom requirements"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('rule_based_config', {}).get('my_validator', {})
        self.my_setting = self.config.get('my_setting', True)

    def validate(self, context: WorkflowContext) -> ValidatorResult:
        """Perform validation"""
        import time
        start_time = time.time()

        issues = []
        checks_performed = 0

        # Your validation logic here
        if context.workflow_yaml_content:
            checks_performed += 1
            # ... check something ...

            if problem_found:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    category=Category.STRUCTURE,
                    message="Problem description",
                    location="job:JobName",
                    explanation="Why this is a problem",
                    impact="What will happen",
                    suggestion="How to fix it",
                    detected_by="rule"
                ))

        # Determine status
        error_count = len([i for i in issues if i.severity in [Severity.CRITICAL, Severity.ERROR]])
        if error_count > 0:
            status = ValidationStatus.FAILED
        elif len(issues) > 0:
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.PASSED

        duration = time.time() - start_time

        return ValidatorResult(
            name="my_validator",
            status=status,
            duration_seconds=duration,
            issues=issues,
            checks_performed=checks_performed,
            metadata={"custom_data": []}
        )
```

### Step 2: Add Configuration

```json
{
  "validation_levels": {
    "full": {
      "validators": [..., "my_validator"]
    }
  },
  "rule_based_config": {
    "my_validator": {
      "my_setting": true
    }
  }
}
```

### Step 3: Register Validator

Edit `validator.py`:

```python
from validators.rule_based.my_validator import MyValidator

# In _run_rule_based_validators method:
if 'my_validator' in enabled_validators:
    validator = MyValidator(self.config)
    result = validator.validate(context)
    results.append(result)
```

---

## Best Practices

1. **Always handle missing data gracefully**
   ```python
   if not context.workflow_yaml_content:
       return ValidatorResult(name="my_validator", status=ValidationStatus.PASSED, ...)
   ```

2. **Use appropriate severity levels**
   - `CRITICAL`: Workflow will definitely fail
   - `ERROR`: Likely to fail
   - `WARNING`: May cause issues
   - `INFO`: Suggestions

3. **Provide actionable suggestions**
   ```python
   suggestion="Add 'input.csv' to replicaCatalog with: lfn: input.csv, pfn: /path/to/input.csv"
   ```

4. **Track validated items in metadata**
   ```python
   metadata={"validated_items": [...]}
   ```

5. **Use logger for verbose output**
   ```python
   logger.info(f"Validating: {item_name}")
   ```

---

## Testing

### Unit Test Example

```python
import unittest
from validators.rule_based.my_validator import MyValidator
from models import WorkflowContext

class TestMyValidator(unittest.TestCase):
    def test_validation_passes(self):
        config = {"rule_based_config": {"my_validator": {}}}
        validator = MyValidator(config)

        context = WorkflowContext(
            workflow_yaml_path="/tmp/test.yml",
            workflow_yaml_content={"name": "test", "jobs": []}
        )

        result = validator.validate(context)

        self.assertEqual(result.status, ValidationStatus.PASSED)
        self.assertEqual(len(result.issues), 0)

    def test_validation_fails(self):
        # Test failure case
        pass
```

---

## Performance Tips

1. **Cache expensive operations**
   ```python
   @lru_cache(maxsize=128)
   def expensive_check(self, file_path: str) -> bool:
       # ...
   ```

2. **Skip unnecessary checks**
   ```python
   if not self.config.get('check_enabled', True):
       return result
   ```

3. **Use early returns**
   ```python
   if not context.replica_catalog:
       return result  # Nothing to validate
   ```

4. **Batch operations**
   ```python
   # Good: Check all files at once
   for file in files:
       check_file(file)

   # Bad: Multiple passes
   for file in files:
       check_exists(file)
   for file in files:
       check_readable(file)
   ```

---

## Documentation

Always document:
- Purpose of validator
- What it checks
- Configuration options
- Example issues
- Performance characteristics

See `docs/NEW_FEATURES.md` for documentation template.
