# Pegasus Workflow Validator - Design Document

## Overview

A comprehensive validation system that checks Pegasus workflows **before submission** to catch errors early, reducing failures and improving workflow reliability. This acts as a **preventive layer** before the MAPE-K reactive system.

---

## 1. Conceptual Architecture

### **Position in the System**

```
┌─────────────────────────────────────────────────────────────┐
│                   Workflow Development                       │
│  User writes workflow YAML + transformation scripts          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              🔍 WORKFLOW VALIDATOR (NEW!)                    │
│  Pre-submission validation catches 80% of common errors      │
│  • Syntax validation                                         │
│  • Semantic validation                                       │
│  • Dependency checking                                       │
│  • Resource validation                                       │
│  • Security scanning                                         │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ├─── ✅ VALID ────┐
                   │                 │
                   └─── ❌ INVALID   │
                        (Fix before   │
                         submit)      │
                                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Pegasus Workflow Submission                     │
│  pegasus-plan + pegasus-run                                  │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
         (If still fails...)
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              MAPE-K Reactive System                          │
│  Monitor → Analyze → Plan → Execute                          │
└─────────────────────────────────────────────────────────────┘
```

**Key Insight**: Validator is **proactive** (prevent errors), MAPE-K is **reactive** (fix errors). Together they provide comprehensive reliability.

---

## 2. Validation Levels

### **Level 1: Syntax Validation** (Fast, Local)
**Purpose**: Catch basic structural errors
**Speed**: <1 second
**Complexity**: Low

**Checks**:
- YAML syntax correctness (parseable?)
- Required fields present (name, version, jobs, transformations)
- Data types correct (strings, numbers, booleans)
- Valid Pegasus schema version
- No duplicate job/transformation names
- Proper indentation and formatting

**Example Issues Caught**:
- Missing colon after job name
- Invalid YAML structure
- Duplicate transformation IDs
- Missing mandatory fields

---

### **Level 2: Semantic Validation** (Medium, Local)
**Purpose**: Check logical correctness
**Speed**: 1-5 seconds
**Complexity**: Medium

**Checks**:
- **Job Dependencies**: All parent jobs exist
- **Transformation References**: All jobs reference valid transformations
- **File References**:
  - Input files exist in catalog or are outputs of parent jobs
  - Output files don't conflict
- **Argument Consistency**: Required arguments provided
- **Namespace Resolution**: All namespaces defined
- **Graph Structure**:
  - No circular dependencies
  - No orphan jobs (unreachable from root)
  - Single entry point or valid DAG

**Example Issues Caught**:
- Job depends on non-existent parent
- Transformation not defined in catalog
- Input file missing from catalog
- Circular dependency: A → B → C → A

---

### **Level 3: Resource Validation** (Slow, May Need Remote)
**Purpose**: Verify resource availability
**Speed**: 5-30 seconds
**Complexity**: High

**Checks**:
- **File Existence**:
  - Input files physically exist at specified PFNs
  - Paths are accessible
  - File sizes match expectations
- **Transformation Executables**:
  - Executable files exist
  - Have execute permissions
  - Shebang lines valid (for scripts)
  - Required interpreters available (python3, bash, etc.)
- **Environment Requirements**:
  - Conda environments exist
  - Python packages available
  - System libraries present
- **Compute Resources**:
  - Requested memory reasonable (<available RAM)
  - CPU cores available
  - Disk space sufficient

**Example Issues Caught**:
- Input file doesn't exist: `/data/missing.csv`
- Python script missing shebang
- Conda environment "myenv" not found
- Requesting 256GB RAM on 64GB machine

---

### **Level 4: Dependency Validation** (Slow, May Need Network)
**Purpose**: Check external dependencies
**Speed**: 10-60 seconds
**Complexity**: High

**Checks**:
- **Python Dependencies**:
  - Import statements in scripts
  - Package versions compatible
  - No conflicting versions
- **System Dependencies**:
  - External tools available (curl, wget, ffmpeg, etc.)
  - Database connections work
  - API endpoints reachable
- **Container Dependencies** (if using containers):
  - Docker/Singularity images exist
  - Container registries accessible
  - Image tags valid

**Example Issues Caught**:
- Script imports `pandas` but it's not installed
- Requires `ffmpeg` but not in PATH
- Docker image `myrepo/myimage:v1.0` doesn't exist
- API endpoint `https://api.example.com` unreachable

---

### **Level 5: Security Validation** (Fast, Pattern-Based)
**Purpose**: Detect security risks
**Speed**: 2-5 seconds
**Complexity**: Medium

**Checks**:
- **Dangerous Commands**:
  - `rm -rf /`
  - `dd` without bounds
  - `sudo` usage
  - Wildcard deletion patterns
- **Sensitive Data Exposure**:
  - Hardcoded passwords
  - API keys in plain text
  - AWS credentials
  - SSH private keys
- **Path Traversal**:
  - `../` sequences escaping workflow directory
  - Absolute paths to system directories
- **Code Injection Risks**:
  - `eval()` usage
  - `exec()` with user input
  - Shell injection vulnerabilities

**Example Issues Caught**:
- Script contains: `rm -rf $TEMP/*` (dangerous wildcard)
- Hardcoded password: `DB_PASSWORD="mypass123"`
- SSH key in catalog: `id_rsa`
- Path traversal: `../../../etc/passwd`

---

### **Level 6: Best Practices Validation** (Fast, Rule-Based)
**Purpose**: Suggest improvements
**Speed**: 1-3 seconds
**Complexity**: Low

**Checks**:
- **Performance**:
  - Jobs too granular (too many tiny jobs)
  - Jobs too coarse (huge monolithic jobs)
  - Parallelization opportunities missed
- **Reliability**:
  - No retry strategy defined
  - Missing error handling
  - No checkpointing for long jobs
- **Maintainability**:
  - Poor naming conventions
  - Missing documentation/comments
  - Magic numbers instead of named constants
- **Resource Efficiency**:
  - Over-requesting resources (asking for 64GB when 4GB enough)
  - Under-requesting (likely to fail due to OOM)

**Example Issues Caught**:
- 1000 jobs that could be parallelized into 10
- Job named "job1" (not descriptive)
- No retry strategy for flaky API call
- Requesting 64GB for simple text processing

---

## 3. Validation Architecture

### **Component Structure**

```
┌──────────────────────────────────────────────────────────────┐
│                   Workflow Validator                          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Validation Engine (Core)                   │   │
│  │  • Orchestrates all validation levels                │   │
│  │  • Manages validation pipeline                       │   │
│  │  • Aggregates results                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────┬──────────────┬──────────────┬──────────┐ │
│  │  Syntax      │  Semantic    │  Resource    │ Security  │ │
│  │  Validator   │  Validator   │  Validator   │ Validator │ │
│  │              │              │              │           │ │
│  │  • YAML      │  • DAG       │  • Files     │ • Patterns│ │
│  │  • Schema    │  • Deps      │  • Execs     │ • Secrets │ │
│  │  • Types     │  • Catalog   │  • Env       │ • Paths   │ │
│  └──────────────┴──────────────┴──────────────┴──────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Validation Rules Database                  │   │
│  │  • Pegasus schema definitions                        │   │
│  │  • Security patterns                                 │   │
│  │  • Best practice rules                               │   │
│  │  • Custom user rules                                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           LLM-Powered Validator (Optional)           │   │
│  │  • Deep semantic analysis                            │   │
│  │  • Suggest workflow improvements                     │   │
│  │  • Detect subtle logical errors                      │   │
│  │  • Explain validation failures                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Results Formatter                          │   │
│  │  • Human-readable reports                            │   │
│  │  • JSON output for automation                        │   │
│  │  • Web dashboard integration                         │   │
│  │  • Fix suggestions                                   │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Validation Report Structure

### **Report Format**

```yaml
validation_report:
  workflow_id: "example_workflow"
  validated_at: "2025-01-30T15:30:00Z"
  validator_version: "1.0.0"

  overall_status: "FAILED"  # PASSED, FAILED, WARNING

  summary:
    total_checks: 156
    passed: 142
    failed: 8
    warnings: 6

  levels:
    syntax:
      status: "PASSED"
      duration_seconds: 0.3
      checks_run: 25
      errors: []

    semantic:
      status: "FAILED"
      duration_seconds: 2.1
      checks_run: 45
      errors:
        - code: "E201"
          severity: "ERROR"
          category: "dependency"
          message: "Job 'process_data' depends on non-existent job 'load_data'"
          location:
            file: "workflow.yml"
            line: 45
            column: 12
          suggestion: "Check job name spelling or add missing job definition"

        - code: "E305"
          severity: "ERROR"
          category: "catalog"
          message: "Input file 'input.csv' not found in replica catalog"
          location:
            file: "workflow.yml"
            line: 67
          suggestion: "Add file to catalog or check PFN path"

    resource:
      status: "WARNING"
      duration_seconds: 15.4
      checks_run: 32
      warnings:
        - code: "W401"
          severity: "WARNING"
          category: "executable"
          message: "Script 'process.py' missing shebang line"
          location:
            file: "transformations/process.py"
            line: 1
          suggestion: "Add '#!/usr/bin/env python3' at top of file"

    security:
      status: "FAILED"
      duration_seconds: 1.8
      checks_run: 28
      errors:
        - code: "S501"
          severity: "CRITICAL"
          category: "secrets"
          message: "Hardcoded password detected"
          location:
            file: "scripts/connect.sh"
            line: 12
            snippet: "PASSWORD='admin123'"
          suggestion: "Use environment variables or secrets manager"

    best_practices:
      status: "WARNING"
      duration_seconds: 0.9
      checks_run: 26
      warnings:
        - code: "BP201"
          severity: "INFO"
          category: "naming"
          message: "Job name 'job1' not descriptive"
          location:
            file: "workflow.yml"
            line: 23
          suggestion: "Rename to describe what job does (e.g., 'preprocess_images')"

  recommendations:
    - priority: "HIGH"
      message: "Fix 8 critical errors before submission"

    - priority: "MEDIUM"
      message: "Address 6 warnings to improve reliability"

    - priority: "LOW"
      message: "Consider applying 4 best practice suggestions"

  next_steps:
    - "Fix dependency error in job 'process_data'"
    - "Add 'input.csv' to replica catalog"
    - "Remove hardcoded password from connect.sh"
    - "Add shebang to process.py"
```

---

## 5. Integration Points

### **A. Command-Line Interface (CLI)**

**Standalone Tool**:
```bash
# Validate before submission
pegasus-validate workflow.yml

# Quick syntax check only
pegasus-validate workflow.yml --level syntax

# Full validation including slow checks
pegasus-validate workflow.yml --level full

# Output JSON for automation
pegasus-validate workflow.yml --format json > report.json

# Fix mode - auto-fix simple issues
pegasus-validate workflow.yml --fix

# Watch mode - validate on file changes
pegasus-validate workflow.yml --watch
```

**Integrated with Pegasus**:
```bash
# Auto-validate during planning
pegasus-plan --validate workflow.yml

# Strict mode - abort if validation fails
pegasus-plan --validate-strict workflow.yml
```

---

### **B. Dashboard Integration**

**Pre-Submission Validation Tab**:
- Upload workflow YAML
- Select validation levels
- See real-time validation progress
- View detailed error reports
- Download fixed version (if auto-fixable)
- Compare multiple workflow versions

**Workflow Editor**:
- Inline validation as you type
- Red underlines for errors
- Yellow underlines for warnings
- Hover for suggestions
- Quick-fix actions

**Validation History**:
- Track validation runs over time
- Compare validation reports
- See improvement trends
- Export validation statistics

---

### **C. CI/CD Integration**

**GitHub Actions**:
```yaml
- name: Validate Pegasus Workflow
  uses: pegasus-validate-action@v1
  with:
    workflow: workflow.yml
    level: full
    fail-on: error  # or warning
```

**Pre-commit Hooks**:
```yaml
- repo: local
  hooks:
    - id: pegasus-validate
      name: Validate Pegasus Workflows
      entry: pegasus-validate
      language: system
      files: \.yml$
```

---

### **D. IDE Integration**

**VS Code Extension**:
- Real-time validation as you type
- Error highlighting
- Quick-fix suggestions
- Autocomplete for Pegasus keywords
- Workflow visualization

**IntelliJ/PyCharm Plugin**:
- Schema validation
- Reference checking
- Refactoring support

---

## 6. Advanced Features

### **6.1 LLM-Powered Deep Validation**

**Use Case**: Catch subtle semantic errors that rule-based validators miss

**Example**:
```yaml
# Workflow defines:
jobs:
  - name: "process"
    arguments: "--input ${INPUT_FILE}"

# But INPUT_FILE is never defined anywhere
# LLM detects: "Variable INPUT_FILE used but never declared"
```

**Benefits**:
- Understands context and intent
- Detects logical inconsistencies
- Suggests workflow improvements
- Explains errors in plain language

**Approach**:
- Send workflow YAML + transformations to LLM
- Ask: "What errors or potential issues do you see?"
- Parse structured response
- Add to validation report

---

### **6.2 Historical Learning**

**Concept**: Learn from past failures to improve validation

**How It Works**:
1. When workflow fails in production
2. MAPE-K identifies root cause
3. Validator learns: "This pattern causes this failure"
4. Next time, validator catches it pre-submission

**Example**:
- Workflow failed 3 times due to missing Python package
- Validator learns: "Check if 'pandas' imported but not in requirements"
- Future workflows are validated for this pattern

---

### **6.3 Similarity Detection**

**Concept**: "You've seen similar workflows fail before"

**How It Works**:
- Calculate workflow similarity (graph structure, transformations)
- If similar workflow failed before, warn user
- Show what went wrong last time
- Suggest preventive fixes

---

### **6.4 Performance Prediction**

**Concept**: Estimate workflow performance before running

**Predictions**:
- **Estimated Runtime**: Based on similar past workflows
- **Resource Usage**: Expected CPU, RAM, disk
- **Cost Estimate**: Compute costs if running on cloud
- **Failure Probability**: Risk score based on complexity

---

### **6.5 Auto-Fix Capability**

**Simple Fixes** (High Confidence):
- Add missing shebang lines
- Fix indentation
- Add missing required fields with defaults
- Remove trailing whitespace

**Suggested Fixes** (User Confirms):
- Add missing dependencies to requirements.txt
- Rename poorly named jobs
- Add retry strategies
- Optimize resource requests

---

## 7. Validation Rules Database

### **Rule Structure**

```yaml
rule_id: "E201"
name: "Missing Job Dependency"
category: "semantic"
severity: "error"
description: "Job references a parent that doesn't exist"

check:
  type: "graph_traversal"
  logic: "For each job, verify all dependencies exist in job list"

message_template: "Job '{job_name}' depends on non-existent job '{parent_name}'"

suggestion_template: "Add job '{parent_name}' or remove dependency"

auto_fixable: false

examples:
  - bad: |
      jobs:
        - name: "process"
          parents: ["load"]  # 'load' doesn't exist

  - good: |
      jobs:
        - name: "load"
        - name: "process"
          parents: ["load"]
```

---

## 8. User Experience Flow

### **Scenario: Developer Submitting New Workflow**

**Step 1: Write Workflow**
- User creates `workflow.yml`
- Writes transformation scripts

**Step 2: Validate Locally**
```bash
$ pegasus-validate workflow.yml

🔍 Validating workflow.yml...

✅ Syntax validation (0.3s) - PASSED
✅ Semantic validation (1.8s) - PASSED
⚠️  Resource validation (12.4s) - 2 warnings
✅ Security validation (1.1s) - PASSED
⚠️  Best practices (0.7s) - 3 suggestions

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  WARNINGS (2)

W401: Script 'process.py' missing shebang
  Location: transformations/process.py:1
  Fix: Add '#!/usr/bin/env python3'

W402: Large memory request (64GB) seems excessive
  Location: workflow.yml:45
  Suggestion: Profile script - might work with 8GB

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 SUGGESTIONS (3)

BP201: Job 'job1' has non-descriptive name
BP305: Consider adding retry strategy to API calls
BP401: Workflow could be 3x faster with better parallelization

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Overall: ✅ PASSED (with warnings)

🎯 Workflow is valid and can be submitted!
   Consider addressing 2 warnings for better reliability.
```

**Step 3: Fix Issues** (Optional)
```bash
$ pegasus-validate workflow.yml --fix

🔧 Auto-fixing issues...
✓ Added shebang to process.py
✓ Reduced memory request from 64GB to 8GB

2 issues fixed automatically.
0 issues require manual review.
```

**Step 4: Submit with Confidence**
```bash
$ pegasus-plan workflow.yml
$ pegasus-run submit-dir
```

---

## 9. Benefits & Impact

### **For Users**
- ✅ **Faster Development**: Catch errors before submission
- ✅ **Less Frustration**: No waiting for workflow to fail
- ✅ **Learning Tool**: Understand Pegasus best practices
- ✅ **Confidence**: Submit knowing it will likely work

### **For System**
- ✅ **Reduced Load**: Fewer failed workflows to analyze
- ✅ **Better Metrics**: Higher success rates overall
- ✅ **Cost Savings**: Less wasted compute on broken workflows
- ✅ **Faster MAPE-K**: Only handles truly unexpected failures

### **Expected Impact**
- 📉 **60-80% reduction** in common workflow errors
- 📉 **50% reduction** in MAPE-K system load
- 📈 **30% improvement** in workflow success rate
- 📈 **70% faster** error detection (pre vs. post submission)

---

## 10. Implementation Priority

### **Phase 1: MVP (Essential)**
- Syntax validation
- Basic semantic validation (dependencies, catalog)
- CLI tool
- JSON output

### **Phase 2: Production (Important)**
- Resource validation
- Security validation
- Dashboard integration
- Detailed error reports
- Auto-fix for simple issues

### **Phase 3: Advanced (Nice to Have)**
- LLM-powered validation
- Historical learning
- Performance prediction
- IDE integration
- CI/CD integration

---

## 11. Integration with Existing MAPE-K

### **Validator ↔ Monitor**
- Validator runs before submission (proactive)
- Monitor watches after submission (reactive)
- Share validation rules database
- Monitor learns new patterns → adds to Validator

### **Validator ↔ Analyzer**
- If workflow fails despite validation
- Analyzer checks: "Why did validator miss this?"
- Improves validation rules based on real failures

### **Validator ↔ Knowledge Base**
- Validator uses known error patterns
- Successful validations add to knowledge base
- Failed workflows that passed validation → improve rules

---

This creates a comprehensive **defense-in-depth** strategy:
1. **Validator** (Layer 1): Prevent 80% of errors before submission
2. **MAPE-K** (Layer 2): Fix remaining 20% that still fail
3. **Result**: Near-perfect workflow reliability

---

**Ready to implement whenever you are!**
